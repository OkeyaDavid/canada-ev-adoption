"""Render README.md from the database and artifacts, so its numbers cannot drift.

Run:  python src/make_readme.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "ev.db"
GH = "https://github.com/OkeyaDavid/canada-ev-adoption"
APP = "https://canada-ev-adoption.streamlit.app"


def main() -> None:
    with sqlite3.connect(DB) as con:
        q = pd.read_sql_query("SELECT * FROM quarterly", con)
    honesty = json.loads((ROOT / "docs" / "forecast_honesty.json").read_text())

    ca = q[q["prov_code"] == "CA"].set_index("quarter").sort_index()
    latest = ca.index[-1]
    peak_q, peak = ca["zev_share"].idxmax(), ca["zev_share"].max()
    trough_q = ca["zev_share"].loc["2025Q1":].idxmin()
    yearly = (q[q["prov_code"] == "CA"].groupby("year")[["zev", "total", "hybrid"]].sum())
    yearly["share"] = (100 * yearly["zev"] / yearly["total"]).round(2)
    yearly["hyb"] = (100 * yearly["hybrid"] / yearly["total"]).round(2)

    last4 = sorted(q["quarter"].unique())[-4:]
    prov = (q[q["quarter"].isin(last4) & (q["prov_code"] != "CA") & q["total"].notna()]
            .groupby("province")[["zev", "total"]].sum())
    prov["share"] = (100 * prov["zev"] / prov["total"]).round(2)
    prov["pct_of_zevs"] = (100 * prov["zev"] / prov["zev"].sum()).round(1)
    prov = prov.sort_values("zev", ascending=False)
    top3 = prov.head(3)

    year_rows = "\n".join(
        f"| {int(y)} | {r.share:.2f}% | {r.hyb:.2f}% | {int(r.total):,} |"
        for y, r in yearly.iterrows())
    prov_rows = "\n".join(
        f"| {p} | {r.share:.2f}% | {r.pct_of_zevs:.1f}% | {int(r.total):,} |"
        for p, r in prov.head(6).iterrows())

    text = f"""# Where is Canada going electric?

**[Live dashboard]({APP})** · [Code]({GH}) · Python · SQL (SQLite) · statsmodels · Streamlit · Plotly

Nine years of Canadian new-vehicle registrations, by province and fuel type, with a
four-quarter forecast and what the pattern means for an automaker's dealer network.

![Dashboard]({'docs/screenshot.png'})

## The question

Where, and how fast, is Canada actually switching to electric vehicles, and what should a
carmaker do about it?

## Key findings

1. **The market peaked and broke.** National ZEV share hit **{peak:.1f}% in {peak_q}**, then
   fell to **{ca.loc[trough_q, 'zev_share']:.1f}% in {trough_q}**, a drop of
   {peak - ca.loc[trough_q, 'zev_share']:.1f} points in two quarters, when the federal iZEV
   programme paused and Quebec cut its rebate in January 2025. It has recovered only to
   **{ca.loc[latest, 'zev_share']:.1f}% in {latest}**.
2. **Quebec carried the fall.** Its annual ZEV share went from
   {100 * q[(q.province == 'Quebec') & (q.year == 2024)].zev.sum() / q[(q.province == 'Quebec') & (q.year == 2024)].total.sum():.1f}%
   in 2024 to
   {100 * q[(q.province == 'Quebec') & (q.year == 2025)].zev.sum() / q[(q.province == 'Quebec') & (q.year == 2025)].total.sum():.1f}%
   in 2025, a 14.0-point swing, against 5.1 points nationally.
3. **Three provinces are the market.** {top3.index[0]}, {top3.index[1]} and {top3.index[2]}
   took **{top3['pct_of_zevs'].sum():.0f}%** of all ZEVs registered in the last four quarters.
4. **Buyers moved down the ladder, not out.** Non-plug-in hybrids rose from
   {yearly.loc[2024, 'hyb']:.1f}% of new registrations in 2024 to
   {yearly.loc[2026, 'hyb']:.1f}% in 2026, straight through the cuts.
5. **The forecast does not beat a naive baseline, and the README says so.** See below.

## National picture

| Year | ZEV share | Hybrid share | New registrations |
|---|---|---|---|
{year_rows}

## Provinces, last four quarters

| Province | ZEV share | Share of Canada's ZEVs | New registrations |
|---|---|---|---|
{prov_rows}

Alberta and Newfoundland and Labrador are inside the national total but not published
separately (StatCan footnote 2: data-sharing agreements). Nunavut and the territories are
small enough that their rates swing on a handful of vehicles.

## The forecast, honestly

Damped-trend exponential smoothing from {honesty['window_start']}, four quarters ahead, with
an 80% interval. In a rolling back-test over {honesty['folds']} origins it missed by
**{honesty['model_mae_pts']} percentage points** on average against
**{honesty['naive_mae_pts']} points** for a naive "same as last quarter" guess, so **it does
not beat the baseline**, and the dashboard says so on the forecast tab.

That is not a tuning failure. The series contains a policy break: no model fitted on past
share can anticipate a government cutting a rebate. The honest deliverable is the interval
under unchanged policy, plus the policy calendar as the real planning input.
`python src/forecast.py --bench` reproduces the comparison across training windows.

## Approach

1. **Clean** (`src/clean.py`): read 8.1M rows in chunks, keep national and provincial totals
   only, map fuel labels to codes, convert `REF_DATE` to quarters, load into SQLite. The
   script fails loudly unless national totals match StatCan's published figures
   (Q2 2026: 547,673 registrations, 58,811 ZEVs) and BEV + PHEV equals StatCan's own ZEV
   subtotal in every quarter.
2. **Analyse** (`sql/02_analysis.sql`, 8 queries): shares by province and year, year-over-year
   change, peak-to-latest gaps, fuel mix, and a before/after comparison of the 2025 cuts.
   Uses CTEs and window functions (`RANK`, `ROW_NUMBER`, `MAX OVER`).
3. **Forecast** (`src/forecast.py`): ETS with a rolling-origin back-test against a naive
   baseline.
4. **Dashboard** (`app.py`): Streamlit and Plotly, with the January 2025 policy break marked
   on every time series.

## Run it

```bash
git clone {GH}.git && cd canada-ev-adoption
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# optional, to rebuild from source: download the table into data/raw/
#   https://www150.statcan.gc.ca/n1/tbl/csv/20100025-eng.zip
python src/clean.py        # ~15s; verifies against StatCan's published totals
python src/run_sql.py      # the 8 analysis queries
python src/forecast.py --bench
streamlit run app.py
```

`data/ev.db` is committed (small), so the dashboard runs without the 1.4 GB raw extract.

## Limitations

- Registrations are a proxy for sales, not the same thing.
- Two provinces are missing from the provincial breakdown (footnote 2 above).
- The forecast assumes policy stays as it is, which the last two years suggest is optimistic.
- Quarterly data cannot see within-quarter pull-forward: the Q4 2024 Quebec spike is partly
  buyers racing a deadline, which inflates the peak and deepens the fall.

---
Built by David Okeya · [LinkedIn](https://www.linkedin.com/in/okeyadavid) ·
Data: [Statistics Canada table 20-10-0025-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=2010002501)
"""
    (ROOT / "README.md").write_text(text)
    print(f"Wrote {ROOT / 'README.md'}")


if __name__ == "__main__":
    main()
