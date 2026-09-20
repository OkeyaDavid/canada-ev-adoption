"""Step 5 - The dashboard.

Run locally:  streamlit run app.py
It reads data/ev.db (made by src/clean.py). That small file is committed to GitHub
so the live version on Streamlit Community Cloud works without the raw download.
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from forecast import backtest, fit_forecast, load_share  # noqa: E402

DB_PATH = Path(__file__).parent / "data" / "ev.db"

# Colors are tied to the province (never to its rank), so a province keeps its color
# whatever you filter. Canada is always the dark ink line.
PROV_COLORS = {
    "BC": "#2a78d6", "QC": "#eb6834", "ON": "#1baf7a", "AB": "#eda100",
    "MB": "#e87ba4", "SK": "#008300", "NS": "#4a3aa7", "NB": "#e34948",
}
OTHER_PROV = "#8a8984"
CANADA_INK = "#3d3c39"
FUEL_COLORS = {"Battery electric": "#2a78d6", "Plug-in hybrid": "#eb6834",
               "Hybrid (not plug-in)": "#1baf7a", "Gasoline, diesel & other": "#b9b8b1"}

st.set_page_config(page_title="Canada EV Adoption", page_icon="🔌", layout="wide")


@st.cache_data
def load_quarterly() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as con:
        df = pd.read_sql_query("SELECT * FROM quarterly ORDER BY quarter", con)
    # A real date (first day of the quarter) so charts space the quarters correctly
    df["date"] = pd.PeriodIndex(df["quarter"], freq="Q").to_timestamp()
    return df


def qdates(quarters) -> pd.DatetimeIndex:
    return pd.PeriodIndex(list(quarters), freq="Q").to_timestamp()


def style(fig, height=380, y_title=None, pct=True):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8),
        hovermode="x unified", legend=dict(orientation="h", y=-0.15),
        yaxis_title=y_title, xaxis_title=None,
    )
    fig.update_xaxes(showgrid=False, hoverformat="%Y Q%q")
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False,
                     ticksuffix="%" if pct else None, rangemode="tozero")
    return fig


q = load_quarterly()
provinces = q[(q["prov_code"] != "CA") & (q["total"] > 0)]
quarters = sorted(q["quarter"].unique())
latest = quarters[-1]
names = dict(zip(q["prov_code"], q["province"]))

# ---------- Header + filters ----------
st.title("Where is Canada going electric?")
st.caption(f"New vehicle registrations by province and fuel type, Q1 2017 to {latest}. "
           "ZEV = battery electric + plug-in hybrid. Source: Statistics Canada, table 20-10-0025-01.")

f1, f2, f3 = st.columns([1, 2, 1])
sel_q = f1.selectbox("Quarter", quarters[::-1], index=0)
prov_options = sorted(provinces["prov_code"].unique(), key=lambda c: names[c])
sel_provs = f2.multiselect("Compare provinces (up to 4)", prov_options,
                           default=[p for p in ["BC", "QC", "ON"] if p in prov_options],
                           max_selections=4, format_func=lambda c: names[c])
mix_geo = f3.selectbox("Fuel mix for", ["CA"] + prov_options, format_func=lambda c: names[c])

# ---------- KPI row ----------
ca = q[q["prov_code"] == "CA"].set_index("quarter")
now = ca.loc[sel_q]
yr, qn = int(sel_q[:4]), int(sel_q[-1])
prev_key = f"{yr - 1}Q{qn}"
prev = ca.loc[prev_key] if prev_key in ca.index else None
top = provinces[provinces["quarter"] == sel_q].sort_values("zev_share", ascending=False).iloc[0]

k1, k2, k3, k4 = st.columns(4)
k1.metric("Canada ZEV share", f"{now['zev_share']:.1f}%",
          None if prev is None else f"{now['zev_share'] - prev['zev_share']:+.1f} pts vs {prev_key}")
k2.metric("ZEVs registered", f"{now['zev']:,.0f}",
          None if prev is None else f"{100 * (now['zev'] / prev['zev'] - 1):+.1f}% vs {prev_key}")
k3.metric("Battery electric share of ZEVs", f"{100 * now['bev'] / now['zev']:.0f}%")
k4.metric("Leading province", top["province"], f"{top['zev_share']:.1f}% ZEV", delta_color="off")

# ---------- Chart 1: ZEV share over time ----------
st.subheader("ZEV share of new vehicles over time")
fig = go.Figure()
fig.add_trace(go.Scatter(x=ca["date"], y=ca["zev_share"], name="Canada", mode="lines",
                         line=dict(color=CANADA_INK, width=3, dash="dot")))
for code in sel_provs:
    d = provinces[provinces["prov_code"] == code]
    fig.add_trace(go.Scatter(x=d["date"], y=d["zev_share"], name=names[code], mode="lines",
                             line=dict(color=PROV_COLORS.get(code, OTHER_PROV), width=2)))
st.plotly_chart(style(fig, y_title="ZEV share"), width="stretch")

# ---------- Chart 2: province ranking + Chart 3: fuel mix ----------
c1, c2 = st.columns(2)
with c1:
    st.subheader(f"Province ranking, {sel_q}")
    r = provinces[provinces["quarter"] == sel_q].sort_values("zev_share")
    fig = go.Figure(go.Bar(
        x=r["zev_share"], y=r["province"], orientation="h", marker_color="#2a78d6",
        text=r["zev_share"].map(lambda v: f"{v:.1f}%"), textposition="outside",
        customdata=r[["zev", "total"]], cliponaxis=False,
        hovertemplate="%{y}: %{x:.1f}% (%{customdata[0]:,.0f} of %{customdata[1]:,.0f})<extra></extra>"))
    fig.add_vline(x=now["zev_share"], line_dash="dot", line_color=CANADA_INK,
                  annotation_text=f"Canada {now['zev_share']:.1f}%",
                  annotation_position="bottom right")
    fig = style(fig, height=420)
    fig.update_layout(hovermode="closest", bargap=0.35)
    fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor="rgba(128,128,128,0.15)")
    fig.update_yaxes(ticksuffix=None, showgrid=False)
    st.plotly_chart(fig, width="stretch")

with c2:
    st.subheader(f"Fuel mix, {names[mix_geo]}")
    m = q[q["prov_code"] == mix_geo].copy()
    m = m[m["total"] > 0]
    parts = {
        "Battery electric": m["bev"],
        "Plug-in hybrid": m["phev"],
        "Hybrid (not plug-in)": m["hybrid"],
        "Gasoline, diesel & other": m["total"] - m[["bev", "phev", "hybrid"]].fillna(0).sum(axis=1),
    }
    fig = go.Figure()
    for label, values in parts.items():
        fig.add_trace(go.Scatter(x=m["date"], y=100 * values.fillna(0) / m["total"], name=label,
                                 stackgroup="one", mode="lines", line=dict(width=0.5, color="white"),
                                 fillcolor=FUEL_COLORS[label],
                                 hovertemplate=label + ": %{y:.1f}%<extra></extra>"))
    fig = style(fig, height=420)
    fig.update_yaxes(range=[0, 100])
    st.plotly_chart(fig, width="stretch")

# ---------- Chart 4: forecast ----------
st.subheader("Forecast: ZEV share, next 4 quarters")
fc_geo = st.selectbox("Forecast for", ["CA"] + prov_options, format_func=lambda c: names[c],
                      key="fc_geo")
hist = load_share(fc_geo, DB_PATH)
fc = fit_forecast(hist)
bt = backtest(hist)
hx = hist.index.to_timestamp()
fx = qdates(fc["quarter"])
fig = go.Figure()
fig.add_trace(go.Scatter(x=list(fx) + list(fx[::-1]),
                         y=list(fc["high"]) + list(fc["low"][::-1]), fill="toself", mode="lines",
                         fillcolor="rgba(42,120,214,0.15)", line=dict(width=0),
                         name="80% range", hoverinfo="skip"))
fig.add_trace(go.Scatter(x=hx, y=hist.values, name="Actual", mode="lines",
                         line=dict(color=CANADA_INK, width=2)))
fig.add_trace(go.Scatter(x=[hx[-1]] + list(fx), y=[hist.iloc[-1]] + list(fc["forecast"]),
                         name="Forecast", mode="lines+markers",
                         line=dict(color="#2a78d6", width=2, dash="dash"), marker=dict(size=8)))
st.plotly_chart(style(fig, y_title="ZEV share"), width="stretch")
st.caption(
    f"Damped-trend exponential smoothing on {hist.index[0]}–{hist.index[-1]}. Back-test on "
    f"{bt['test_quarters']}: average error {bt['model_mae']:.1f} pts vs {bt['naive_mae']:.1f} pts for a "
    "'same as last quarter' guess. Policy changes (like rebates ending) are not in the model, "
    "so treat the range, not the line, as the answer.")

# ---------- Business implications ----------
st.subheader("What this means for an automaker")
impl = Path(__file__).parent / "docs" / "business_implications.md"
st.markdown(impl.read_text() if impl.exists() else "_Coming soon._")

# ---------- Data ----------
with st.expander("See the data"):
    cols = ["quarter", "province", "total", "bev", "phev", "hybrid", "zev", "zev_share"]
    st.dataframe(q[cols], width="stretch", hide_index=True)
    st.download_button("Download CSV", q[cols].to_csv(index=False), "canada_zev_quarterly.csv")

st.caption("Built by David · [GitHub repo](https://github.com/YOUR-USERNAME/canada-ev-adoption) · "
           "Data: [Statistics Canada 20-10-0025-01]"
           "(https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=2010002501)")
