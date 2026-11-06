"""Clean StatCan table 20-10-0025-01 and load it into SQLite.

Run:  python src/clean.py

In:  data/raw/20100025-eng.zip  (1.4 GB extracted, 8.1M rows, read in chunks)
Out: data/ev.db                 (one tidy table + the `quarterly` view)
     data/processed/registrations.csv

Steps
  1. Keep Canada and the provinces/territories; drop the ~5,100 city rows
  2. Keep "Total, vehicle type" so fuel types are not double counted
  3. Map StatCan's fuel labels to short codes; keep its own ZEV subtotal separately
  4. Turn REF_DATE (2026-04) into a quarter label (2026Q2)
  5. Verify national totals against StatCan's published Daily release

Footnote 2 of the table: Newfoundland and Labrador and Alberta are not published because of
data-sharing agreements. They are inside the Canada total but cannot be shown separately.
"""
from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_ZIP = ROOT / "data" / "raw" / "20100025-eng.zip"
DB = ROOT / "data" / "ev.db"
OUT_CSV = ROOT / "data" / "processed" / "registrations.csv"
CHUNK = 500_000

PROVINCES = {
    "Canada": "CA", "Newfoundland and Labrador": "NL", "Prince Edward Island": "PE",
    "Nova Scotia": "NS", "New Brunswick": "NB", "Quebec": "QC", "Ontario": "ON",
    "Manitoba": "MB", "Saskatchewan": "SK", "Alberta": "AB", "British Columbia": "BC",
    "Yukon": "YT", "Northwest Territories": "NT", "Nunavut": "NU", "Territories": "TR",
}

# StatCan's published figures, used as a correctness check (The Daily, 2026-06-11 for Q1 2026;
# Q2 2026 from the table itself as reported in industry coverage).
EXPECTED = {("2026Q2", "total"): 547_673, ("2026Q2", "zev"): 58_811,
            ("2026Q1", "total"): 397_601, ("2026Q1", "zev"): 43_113}


def fuel_code(label: str) -> str:
    """Short code per fuel label. Order matters: subtotals first, plug-in before hybrid."""
    s = str(label).lower()
    if "all fuel" in s:
        return "total"
    if "zero-emission" in s:
        return "zev_reported"      # StatCan's own BEV+PHEV subtotal: kept, never re-added
    if "battery" in s:
        return "bev"
    if "plug-in" in s:
        return "phev"
    if "hybrid" in s:
        return "hybrid"
    if "gasoline" in s:
        return "gasoline"
    if "diesel" in s:
        return "diesel"
    return "other"


def open_csv():
    return zipfile.ZipFile(RAW_ZIP).open("20100025.csv")


def load() -> pd.DataFrame:
    if not RAW_ZIP.exists():
        raise SystemExit(f"Missing {RAW_ZIP}. Download it from "
                         "https://www150.statcan.gc.ca/n1/tbl/csv/20100025-eng.zip")
    cols = ["REF_DATE", "GEO", "Fuel type", "Vehicle type", "Statistics", "VALUE"]
    parts, rows = [], 0
    for chunk in pd.read_csv(open_csv(), usecols=cols, chunksize=CHUNK,
                             encoding="utf-8-sig", low_memory=False):
        rows += len(chunk)
        keep = chunk[(chunk["GEO"].isin(PROVINCES))
                     & (chunk["Vehicle type"] == "Total, vehicle type")
                     & (chunk["Statistics"] == "Number of vehicles")]
        parts.append(keep)
    df = pd.concat(parts, ignore_index=True)
    print(f"Read {rows:,} rows; kept {len(df):,} national/provincial totals")
    return df


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "quarter": pd.PeriodIndex(pd.to_datetime(df["REF_DATE"]), freq="Q").astype(str),
        "province": df["GEO"].values,
        "prov_code": df["GEO"].map(PROVINCES).values,
        "fuel_type": df["Fuel type"].map(fuel_code).values,
        "vehicles": pd.to_numeric(df["VALUE"], errors="coerce").values,
    })
    out["year"] = out["quarter"].str[:4].astype(int)
    out["q"] = out["quarter"].str[-1].astype(int)
    out = (out.groupby(["quarter", "year", "q", "province", "prov_code", "fuel_type"],
                       as_index=False)["vehicles"].sum(min_count=1))
    return out.sort_values(["province", "quarter", "fuel_type"]).reset_index(drop=True)


def verify(out: pd.DataFrame) -> bool:
    ca = (out[out["prov_code"] == "CA"]
          .pivot_table(index="quarter", columns="fuel_type", values="vehicles", aggfunc="sum"))
    ca["zev"] = ca["zev_reported"]
    ok = True
    print("\nCheck against StatCan's published figures:")
    for (qtr, col), exp in EXPECTED.items():
        got = ca.loc[qtr, col] if qtr in ca.index else float("nan")
        good = abs(got - exp) / exp < 0.005
        ok &= bool(good)
        print(f"  [{'OK ' if good else 'FAIL'}] {qtr} {col:5}: got {got:>9,.0f}  expected {exp:>9,}")
    # internal consistency: BEV + PHEV must equal StatCan's own ZEV subtotal
    mismatch = ca[(ca[["bev", "phev"]].sum(axis=1) - ca["zev_reported"]).abs() > 0.5]
    print(f"  [{'OK ' if mismatch.empty else 'FAIL'}] BEV + PHEV equals the published ZEV "
          f"subtotal in every quarter ({len(mismatch)} mismatches)")
    return ok and mismatch.empty


if __name__ == "__main__":
    out = tidy(load())
    print(f"Tidy table: {len(out):,} rows, {out['quarter'].min()} to {out['quarter'].max()}, "
          f"{out['province'].nunique()} places")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    with sqlite3.connect(DB) as con:
        out.to_sql("registrations", con, if_exists="replace", index=False)
        con.executescript((ROOT / "sql" / "01_views.sql").read_text())
    print(f"Saved {DB} and {OUT_CSV}")

    if not verify(out):
        raise SystemExit("Verification failed: the cleaned data does not match StatCan.")
