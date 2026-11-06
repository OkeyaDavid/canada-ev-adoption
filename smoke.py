"""Minimal deployment test. If this renders and app.py does not, the fault is in app.py.
If this is blank too, the fault is the platform, the browser, or the app's configuration.
"""
import sys

import streamlit as st

st.title("Smoke test: this deployment works")
st.write("If you can read this, Streamlit is serving the repository correctly.")
st.write(f"Python {sys.version.split()[0]}")

for mod in ("pandas", "numpy", "plotly"):
    try:
        m = __import__(mod)
        st.write(f"{mod} {m.__version__} imported")
    except Exception as exc:  # noqa: BLE001
        st.error(f"{mod} failed to import: {type(exc).__name__}: {exc}")

from pathlib import Path  # noqa: E402

root = Path(__file__).parent
for rel in ("data/ev.db", "data/processed/forecasts.csv",
            "data/processed/forecast_backtest.csv", "docs/forecast_honesty.json"):
    p = root / rel
    st.write(f"{'found' if p.exists() else 'MISSING'} — {rel}"
             + (f" ({p.stat().st_size:,} bytes)" if p.exists() else ""))
