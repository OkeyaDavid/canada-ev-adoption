"""Forecast ZEV share for the next four quarters, with an uncertainty band.

Run:  python src/forecast.py            # Canada
      python src/forecast.py BC         # any province code
      python src/forecast.py --bench    # compare models and training windows

Model: damped-trend exponential smoothing (statsmodels ETS). Recent quarters count for more
than old ones, and the trend is assumed to flatten rather than run forever, which suits a
market share bounded at 100%.

Honesty note: the series contains a policy shock (federal and Quebec EV rebates were cut in
January 2025, and ZEV share halved in one quarter). No univariate model can anticipate that
kind of break, so the band, not the line, is the forecast. `--bench` reports how each option
does against a naive "same as last quarter" baseline on the last four real quarters.
"""
from __future__ import annotations

import sqlite3
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "ev.db"
DEFAULT_START = "2021Q1"   # see --bench; chosen on back-test evidence, not taste
HORIZON = 4
LEVEL = 0.80


def load_share(prov_code: str = "CA", start: str = DEFAULT_START, db: Path = DB) -> pd.Series:
    with sqlite3.connect(db) as con:
        df = pd.read_sql_query(
            "SELECT quarter, zev_share FROM quarterly WHERE prov_code = ? ORDER BY quarter",
            con, params=(prov_code,))
    s = pd.Series(df["zev_share"].values,
                  index=pd.PeriodIndex(df["quarter"], freq="Q"), name="zev_share").dropna()
    return s[s.index >= pd.Period(start, freq="Q")].astype(float)


def fit_forecast(series: pd.Series, horizon: int = HORIZON, level: float = LEVEL,
                 damped: bool = True) -> pd.DataFrame:
    fit = ETSModel(series, error="add", trend="add", damped_trend=damped).fit(disp=False)
    frame = fit.get_prediction(start=len(series),
                               end=len(series) + horizon - 1).summary_frame(alpha=1 - level)
    idx = pd.period_range(series.index[-1] + 1, periods=horizon, freq="Q")
    return pd.DataFrame({
        "quarter": idx.astype(str),
        "forecast": frame["mean"].clip(lower=0).to_numpy(),
        "low": frame["pi_lower"].clip(lower=0).to_numpy(),
        "high": frame["pi_upper"].clip(upper=100).to_numpy(),
    })


def backtest(series: pd.Series, horizon: int = HORIZON, damped: bool = True) -> dict:
    """Hide the last `horizon` quarters, forecast them, compare with a naive baseline."""
    train, test = series[:-horizon], series[-horizon:]
    fc = fit_forecast(train, horizon, damped=damped)["forecast"].to_numpy()
    naive = np.repeat(train.iloc[-1], horizon)
    mae = float(np.mean(np.abs(fc - test.to_numpy())))
    naive_mae = float(np.mean(np.abs(naive - test.to_numpy())))
    return {"model_mae": round(mae, 3), "naive_mae": round(naive_mae, 3),
            "beats_naive": mae < naive_mae,
            "window": f"{series.index[0]}-{series.index[-1]}",
            "tested_on": f"{test.index[0]}-{test.index[-1]}"}


def bench() -> pd.DataFrame:
    rows = []
    for start in ["2017Q1", "2019Q1", "2021Q1", "2022Q1", "2023Q1"]:
        for damped in (True, False):
            s = load_share("CA", start)
            if len(s) < 12:
                continue
            bt = backtest(s, damped=damped)
            rows.append({"start": start, "damped": damped, "n_quarters": len(s),
                         "model_mae_pts": bt["model_mae"], "naive_mae_pts": bt["naive_mae"],
                         "beats_naive": bt["beats_naive"]})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    if "--export" in sys.argv:
        import sqlite3
        con = sqlite3.connect(DB)
        codes = [r[0] for r in con.execute("SELECT DISTINCT prov_code FROM quarterly")]
        out, bts = [], []
        for code in codes:
            s = load_share(code)
            if len(s) < 10 or s.isna().all():
                continue
            fc = fit_forecast(s); fc.insert(0, "prov_code", code); out.append(fc)
            full = load_share(code, "2017Q1"); errs, nerrs = [], []
            for origin in range(len(full) - 8, len(full) - 3):
                hist = full.iloc[:origin]
                hist = hist[hist.index >= pd.Period(DEFAULT_START, freq="Q")]
                if len(hist) < 10:
                    continue
                h = min(HORIZON, len(full) - origin)
                try:
                    f_ = fit_forecast(hist, h)["forecast"].to_numpy()
                except Exception:
                    continue
                act = full.iloc[origin:origin + h].to_numpy()
                errs.append(np.mean(np.abs(f_ - act)))
                nerrs.append(np.mean(np.abs(hist.iloc[-1] - act)))
            if errs:
                bts.append({"prov_code": code, "folds": len(errs),
                            "model_mae_pts": round(float(np.mean(errs)), 2),
                            "naive_mae_pts": round(float(np.mean(nerrs)), 2),
                            "beats_naive": bool(np.mean(errs) < np.mean(nerrs))})
        proc = ROOT / "data" / "processed"
        pd.concat(out).round(3).to_csv(proc / "forecasts.csv", index=False)
        pd.DataFrame(bts).to_csv(proc / "forecast_backtest.csv", index=False)
        print(f"Exported forecasts for {len(out)} geographies to {proc}")
        raise SystemExit

    if "--bench" in sys.argv:
        t = bench()
        print("Back-test on the last 4 quarters (Canada), mean absolute error in "
              "percentage points:\n")
        print(t.to_string(index=False))
        print("\nLower is better; the naive baseline repeats the last observed quarter.")
        t.to_csv(ROOT / "docs" / "forecast_benchmark.csv", index=False)
        raise SystemExit

    code = sys.argv[1] if len(sys.argv) > 1 else "CA"
    s = load_share(code)
    print(f"{code}: {len(s)} quarters from {s.index[0]}, latest {s.index[-1]} = {s.iloc[-1]:.2f}%")
    fc = fit_forecast(s)
    print(f"\nForecast, {int(LEVEL*100)}% interval:")
    print(fc.round(2).to_string(index=False))
    bt = backtest(s)
    print(f"\nBack-test on {bt['tested_on']}: model {bt['model_mae']} pts vs naive "
          f"{bt['naive_mae']} pts -> {'beats' if bt['beats_naive'] else 'does NOT beat'} "
          "the naive baseline")
