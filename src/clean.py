"""Step 3 - Clean the StatCan table and load it into SQLite.

Run:  python src/clean.py

Input : data/raw/20100025-eng.zip  (or the unzipped 20100025.csv)
Output: data/ev.db   - SQLite database with one tidy table: registrations
        data/processed/registrations.csv - the same table as CSV

What it does:
  1. Keeps only Canada + the provinces/territories (drops cities, which make the file huge)
  2. Keeps only "all vehicle types" (the total), so fuel types add up correctly
  3. Renames fuel types to short codes: bev, phev, hybrid, gasoline, diesel, other, total
     (plus zev_reported = StatCan's own ZEV subtotal, used only to double-check bev + phev)
  4. Turns "2026-04" into a proper quarter: 2026Q2
  5. Checks the national numbers against StatCan's published figures
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from explore import open_raw_csv  # noqa: E402

DB_PATH = Path("data/ev.db")
CSV_OUT = Path("data/processed/registrations.csv")

PROVINCES = {
    "Canada": "CA",
    "Newfoundland and Labrador": "NL",
    "Prince Edward Island": "PE",
    "Nova Scotia": "NS",
    "New Brunswick": "NB",
    "Quebec": "QC",
    "Ontario": "ON",
    "Manitoba": "MB",
    "Saskatchewan": "SK",
    "Alberta": "AB",
    "British Columbia": "BC",
    "Yukon": "YT",
    "Northwest Territories": "NT",
    "Nunavut": "NU",
    "Territories": "TR",
}


def fuel_code(label: str) -> str:
    """Map StatCan's fuel-type wording to a short code. Order matters: subtotals first, and 'plug-in' before 'hybrid'."""
    s = label.lower()
    if "all fuel" in s or s.startswith("total"):
        return "total"
    if "zero-emission" in s:
        return "zev_reported"   # StatCan's own BEV + PHEV subtotal - kept only as a cross-check
    if "battery" in s:
        return "bev"
    if "plug-in" in s or "plug in" in s:
        return "phev"
    if "hybrid" in s:
        return "hybrid"
    if "gasoline" in s:
        return "gasoline"
    if "diesel" in s:
        return "diesel"
    return "other"


def find_col(columns, word):
    """Find the column whose name contains `word` (e.g. 'fuel' -> 'Fuel type')."""
    matches = [c for c in columns if word in c.lower()]
    if not matches:
        raise KeyError(f"No column containing '{word}'. Columns are: {list(columns)}")
    return matches[0]


def load_raw() -> pd.DataFrame:
    """Read the big CSV in chunks, keeping only provincial/national rows."""
    header = pd.read_csv(open_raw_csv(), nrows=0, encoding="utf-8-sig").columns
    fuel_col = find_col(header, "fuel")
    veh_col = find_col(header, "vehicle type")
    stat_cols = [c for c in header if c.lower() in ("statistics", "statistic")]
    usecols = ["REF_DATE", "GEO", fuel_col, veh_col, "VALUE"] + stat_cols

    parts = []
    for chunk in pd.read_csv(open_raw_csv(), usecols=usecols, chunksize=500_000,
                             low_memory=False, encoding="utf-8-sig"):
        parts.append(chunk[chunk["GEO"].isin(PROVINCES)])
    df = pd.concat(parts, ignore_index=True)

    # Keep the "total of all vehicle types" rows only
    veh_values = df[veh_col].dropna().unique()
    total_veh = [v for v in veh_values if "total" in v.lower() or "all" in v.lower()]
    if len(total_veh) != 1:
        raise ValueError(f"Can't tell which vehicle type is the total: {list(veh_values)}")
    df = df[df[veh_col] == total_veh[0]]

    # If there's a Statistics column, keep the vehicle counts (not dollars or percentages)
    for c in stat_cols:
        counts = [v for v in df[c].unique() if "number" in str(v).lower()]
        if counts:
            df = df[df[c] == counts[0]]

    return df.rename(columns={fuel_col: "fuel_label"})[["REF_DATE", "GEO", "fuel_label", "VALUE"]]


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "quarter": pd.PeriodIndex(pd.to_datetime(df["REF_DATE"]), freq="Q").astype(str),
        "province": df["GEO"].values,
        "prov_code": df["GEO"].map(PROVINCES).values,
        "fuel_type": df["fuel_label"].map(fuel_code).values,
        "vehicles": pd.to_numeric(df["VALUE"], errors="coerce").values,
    })
    out["year"] = out["quarter"].str[:4].astype(int)
    out["q"] = out["quarter"].str[-1].astype(int)
    # Some fuel labels can map to the same code (e.g. several 'other' types) -> add them up
    out = (out.groupby(["quarter", "year", "q", "province", "prov_code", "fuel_type"],
                       as_index=False)["vehicles"].sum(min_count=1))
    return out.sort_values(["province", "quarter", "fuel_type"]).reset_index(drop=True)


def check(out: pd.DataFrame) -> None:
    """Compare with numbers StatCan published. Big differences = a filtering mistake."""
    expected = {("2026Q2", "total"): 547_673, ("2026Q2", "zev"): 58_811,
                ("2026Q1", "total"): 397_601, ("2026Q1", "zev"): 43_113}
    ca = out[out["prov_code"] == "CA"].pivot_table(index="quarter", columns="fuel_type",
                                                   values="vehicles", aggfunc="sum")
    ca["zev"] = ca.get("bev", 0) + ca.get("phev", 0)
    print("\nCheck against StatCan's published figures:")
    for (qtr, col), exp in expected.items():
        if qtr in ca.index:
            got = ca.loc[qtr, col]
            flag = "OK " if abs(got - exp) / exp < 0.01 else "CHECK"
            print(f"  [{flag}] {qtr} {col:5}: got {got:>9,.0f}  expected {exp:>9,}")
        else:
            print(f"  [skip] {qtr} not in data")


if __name__ == "__main__":
    raw = load_raw()
    print(f"Kept {len(raw):,} provincial/national rows")
    print("Fuel types found:", sorted(raw["fuel_label"].unique()))

    out = tidy(raw)
    print(f"Tidy table: {len(out):,} rows, {out['quarter'].min()} to {out['quarter'].max()}, "
          f"{out['province'].nunique()} places")

    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(CSV_OUT, index=False)
    with sqlite3.connect(DB_PATH) as con:
        out.to_sql("registrations", con, if_exists="replace", index=False)
        con.executescript(Path("sql/01_views.sql").read_text())
    print(f"Saved {DB_PATH} and {CSV_OUT}")

    check(out)
