"""Step 6 - Forecast ZEV share for the next 4 quarters.

Run:  python src/forecast.py              (Canada)
      python src/forecast.py BC           (one province, by code)

Model: exponential smoothing with a damped trend (statsmodels ETS).
  - "Exponential smoothing" = recent quarters count more than old ones.
  - "Damped trend" = the trend is assumed to flatten out rather than grow forever,
    which is sensible for a market share that can't pass 100%.
We also back-test: hide the last 4 real quarters, forecast them, and compare the error
with a naive "next quarter = this quarter" guess. That's what you quote in interviews.
"""
import sqlite3
import sys
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

warnings.filterwarnings("ignore")  # statsmodels prints convergence chatter

DB_PATH = "data/ev.db"
START = "2019Q1"   # earlier quarters have almost no EVs and add noise


def load_share(prov_code="CA", db_path=DB_PATH) -> pd.Series:
    with sqlite3.connect(db_path) as con:
        df = pd.read_sql_query(
            "SELECT quarter, zev_share FROM quarterly WHERE prov_code = ? ORDER BY quarter",
            con, params=(prov_code,))
    s = pd.Series(df["zev_share"].values,
                  index=pd.PeriodIndex(df["quarter"], freq="Q"), name="zev_share").dropna()
    return s[s.index >= pd.Period(START, freq="Q")]


def fit_forecast(series: pd.Series, horizon=4, level=0.80) -> pd.DataFrame:
    """Return a table with the forecast and a low/high band (80% by default)."""
    model = ETSModel(series.astype(float), error="add", trend="add", damped_trend=True)
    fit = model.fit(disp=False)
    pred = fit.get_prediction(start=len(series), end=len(series) + horizon - 1)
    frame = pred.summary_frame(alpha=1 - level)
    idx = pd.period_range(series.index[-1] + 1, periods=horizon, freq="Q")
    return pd.DataFrame({
        "quarter": idx.astype(str),
        "forecast": frame["mean"].clip(lower=0).values,
        "low": frame["pi_lower"].clip(lower=0).values,
        "high": frame["pi_upper"].clip(upper=100).values,
    })


def backtest(series: pd.Series, horizon=4) -> dict:
    """Hide the last `horizon` quarters, forecast them, and measure the error."""
    train, test = series[:-horizon], series[-horizon:]
    fc = fit_forecast(train, horizon)["forecast"].values
    naive = np.repeat(train.iloc[-1], horizon)
    return {
        "model_mae": float(np.mean(np.abs(fc - test.values))),
        "naive_mae": float(np.mean(np.abs(naive - test.values))),
        "test_quarters": f"{test.index[0]}-{test.index[-1]}",
    }


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "CA"
    s = load_share(code)
    print(f"{code}: {len(s)} quarters, latest {s.index[-1]} = {s.iloc[-1]:.1f}%")
    print("\nForecast (80% range):")
    print(fit_forecast(s).round(1).to_string(index=False))
    bt = backtest(s)
    print(f"\nBack-test on {bt['test_quarters']}: model error {bt['model_mae']:.2f} pts, "
          f"naive error {bt['naive_mae']:.2f} pts (lower is better)")
