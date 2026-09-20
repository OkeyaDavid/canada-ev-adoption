# Where is Canada going electric?

**Live dashboard:** _link goes here after Step 8_

An interactive dashboard of new vehicle registrations in Canada, 2017 to 2026, by province and fuel type. It uses SQL analysis of zero-emission vehicle (ZEV) adoption and a 4-quarter forecast.

![Dashboard screenshot](docs/screenshot.png)

## The question
Where, and how fast, are Canadians switching to electric vehicles, and what should an automaker do about it?

## Key findings
<!-- Step 4: replace with your 3-5 findings, each with a number -->
1. ...
2. ...
3. ...

## Data
- **Source:** Statistics Canada, [table 20-10-0025-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=2010002501), New motor vehicle registrations, quarterly
- **Coverage:** Q1 2017 to Q2 2026, Canada + provinces, all vehicle types
- **ZEV** = battery electric + plug-in hybrid (StatCan's definition)
- **Check:** national totals match StatCan's published figures (e.g. Q2 2026: 547,673 vehicles, 58,811 ZEVs)

## Approach
1. **Clean** (`src/clean.py`): kept the national and provincial rows, mapped fuel types to short codes, converted months to quarters, and loaded the result into SQLite.
2. **Analyse** (`sql/02_analysis.sql`): ZEV share by province and year, year-over-year growth, peak vs latest share, fuel mix. Uses CTEs and window functions (`RANK`, `ROW_NUMBER`, `MAX OVER`).
3. **Forecast** (`src/forecast.py`): damped-trend exponential smoothing, back-tested against a naive "same as last quarter" baseline.
4. **Dashboard** (`app.py`): Streamlit + Plotly.

## Business implications
See [docs/business_implications.md](docs/business_implications.md).

## Limitations
- Registrations are not the same as sales, although they're a close proxy.
- The forecast doesn't know about policy changes, such as rebates starting or ending.
- Small provinces have small numbers, so their shares swing a lot from quarter to quarter.

## Run it yourself
```bash
git clone https://github.com/YOUR-USERNAME/canada-ev-adoption.git
cd canada-ev-adoption
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
To rebuild the database from scratch, download the table ZIP into `data/raw/`, then run `python src/clean.py`.

## Tech
Python · pandas · SQLite / SQL · statsmodels · Streamlit · Plotly

---
Built by David, [LinkedIn](https://www.linkedin.com/in/YOUR-PROFILE)
