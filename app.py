"""Canadian EV Adoption Dashboard - Streamlit app.

Run locally:  streamlit run app.py
Reads data/ev.db, which is small and committed, so the deployed app needs no raw download.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

# The forecasts are precomputed into data/processed/ by `python src/forecast.py --export`,
# so the deployed app needs neither statsmodels nor any model fitting at request time.
DEFAULT_START = "2021Q1"

DB = ROOT / "data" / "ev.db"
INK, GREY = "#3d3c39", "#8a8984"
# Colour follows the province, never its rank, so filtering never repaints a line.
PROV_COLOURS = {"BC": "#2a78d6", "QC": "#eb6834", "ON": "#1baf7a", "MB": "#eda100",
                "NS": "#e87ba4", "SK": "#008300", "NB": "#4a3aa7", "PE": "#e34948"}
FUEL_COLOURS = {"Battery electric": "#2a78d6", "Plug-in hybrid": "#eb6834",
                "Hybrid (not plug-in)": "#1baf7a", "Gasoline, diesel and other": "#c9c8c2"}
POLICY = [("2025-01-01", "Federal iZEV paused,<br>Quebec rebate cut")]

st.set_page_config(page_title="Canadian EV Adoption", page_icon="🔌", layout="wide")


def quarter_to_date(labels) -> pd.Series:
    """'2026Q2' -> 2026-04-01. Done arithmetically rather than with pd.PeriodIndex,
    whose frequency aliases have changed across pandas versions."""
    lab = pd.Series(list(labels), dtype="string")
    year = lab.str.slice(0, 4).astype(int)
    qtr = lab.str.slice(-1).astype(int)
    return pd.to_datetime(dict(year=year, month=(qtr - 1) * 3 + 1, day=1))


@st.cache_data
def load_quarterly() -> pd.DataFrame:
    with sqlite3.connect(DB) as con:
        df = pd.read_sql_query("SELECT * FROM quarterly ORDER BY quarter", con)
    df["date"] = quarter_to_date(df["quarter"])
    return df


@st.cache_data
def load_honesty() -> dict:
    return json.loads((ROOT / "docs" / "forecast_honesty.json").read_text())


@st.cache_data
def load_forecasts() -> tuple[pd.DataFrame, pd.DataFrame]:
    fc = pd.read_csv(ROOT / "data" / "processed" / "forecasts.csv")
    bt = pd.read_csv(ROOT / "data" / "processed" / "forecast_backtest.csv").set_index("prov_code")
    return fc, bt


def style(fig, height=380, y_title=None, pct=True, policy=True):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=8), hovermode="x unified",
                      legend=dict(orientation="h", y=-0.18), yaxis_title=y_title,
                      xaxis_title=None)
    fig.update_xaxes(showgrid=False, hoverformat="%Y Q%q")
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False,
                     ticksuffix="%" if pct else None, rangemode="tozero")
    if policy:
        for date, label in POLICY:
            fig.add_vline(x=date, line_dash="dot", line_color=GREY,
                          annotation_text=label, annotation_position="top left",
                          annotation_font_size=10, annotation_font_color=GREY)
    return fig


st.title("Where is Canada going electric?")

try:
    q = load_quarterly()
    honesty = load_honesty()
    forecasts, backtests = load_forecasts()
except Exception as exc:                      # noqa: BLE001
    st.error(
        "The dashboard could not load its data files. This is a deployment problem, "
        "not a data problem: every file it needs is committed to the repository.\n\n"
        f"**{type(exc).__name__}:** {exc}")
    st.caption(f"Working directory: `{Path.cwd()}` · app directory: `{ROOT}`")
    st.stop()

prov = q[(q["prov_code"] != "CA") & q["total"].notna()]
ca = q[q["prov_code"] == "CA"].set_index("quarter")
quarters = sorted(q["quarter"].unique())
latest = quarters[-1]
names = dict(zip(q["prov_code"], q["province"]))

st.caption(
    f"New motor vehicle registrations by province and fuel type, Q1 2017 to {latest}. "
    "ZEV = battery electric + plug-in hybrid, StatCan's own definition. "
    "Source: Statistics Canada table 20-10-0025-01. Alberta and Newfoundland and Labrador "
    "are inside the national total but not published separately (StatCan footnote 2)."
)

f1, f2, f3 = st.columns([1, 2, 1])
sel_q = f1.selectbox("Quarter", quarters[::-1], index=0)
options = sorted(prov["prov_code"].unique(), key=lambda c: names[c])
sel = f2.multiselect("Compare provinces (up to 4)", options,
                     default=[c for c in ["BC", "QC", "ON"] if c in options],
                     max_selections=4, format_func=lambda c: names[c])
mix_geo = f3.selectbox("Fuel mix for", ["CA"] + options, format_func=lambda c: names[c])

now = ca.loc[sel_q]
yr, qn = int(sel_q[:4]), int(sel_q[-1])
prev = ca.loc[f"{yr-1}Q{qn}"] if f"{yr-1}Q{qn}" in ca.index else None
top = prov[prov["quarter"] == sel_q].sort_values("zev_share", ascending=False).iloc[0]
peak = ca["zev_share"].max()
peak_q = ca["zev_share"].idxmax()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Canada ZEV share", f"{now['zev_share']:.1f}%",
          None if prev is None else f"{now['zev_share'] - prev['zev_share']:+.1f} pts year over year")
k2.metric("ZEVs registered", f"{now['zev']:,.0f}",
          None if prev is None else f"{100*(now['zev']/prev['zev']-1):+.0f}% year over year")
k3.metric("Hybrid share (not plug-in)", f"{now['hybrid_share']:.1f}%")
k4.metric("Leading province", top["province"], f"{top['zev_share']:.1f}% ZEV", delta_color="off")
if sel_q != peak_q:
    st.caption(f"Peak was {peak:.1f}% in {peak_q}; the current quarter is "
               f"{now['zev_share'] - peak:+.1f} points from it.")

tab_trend, tab_prov, tab_fc, tab_biz = st.tabs(
    ["Trend", "Provinces", "Forecast", "What it means"])

with tab_trend:
    st.subheader("ZEV share of new vehicles")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ca["date"], y=ca["zev_share"], name="Canada", mode="lines",
                             line=dict(color=INK, width=3, dash="dot")))
    for code in sel:
        d = prov[prov["prov_code"] == code]
        fig.add_trace(go.Scatter(x=d["date"], y=d["zev_share"], name=names[code], mode="lines",
                                 line=dict(color=PROV_COLOURS.get(code, GREY), width=2)))
    st.plotly_chart(style(fig, y_title="ZEV share"), width="stretch")

    st.subheader(f"Fuel mix, {names[mix_geo]}")
    m = q[(q["prov_code"] == mix_geo) & q["total"].notna()].copy()
    parts = {"Battery electric": m["bev"], "Plug-in hybrid": m["phev"],
             "Hybrid (not plug-in)": m["hybrid"],
             "Gasoline, diesel and other":
                 m["total"] - m[["bev", "phev", "hybrid"]].fillna(0).sum(axis=1)}
    fig = go.Figure()
    for label, values in parts.items():
        fig.add_trace(go.Scatter(x=m["date"], y=100 * values.fillna(0) / m["total"], name=label,
                                 stackgroup="one", mode="lines",
                                 line=dict(width=0.5, color="white"),
                                 fillcolor=FUEL_COLOURS[label],
                                 hovertemplate=label + ": %{y:.1f}%<extra></extra>"))
    fig = style(fig, height=360)
    fig.update_yaxes(range=[0, 100])
    st.plotly_chart(fig, width="stretch")
    st.caption("Plain hybrids kept growing straight through the 2025 rebate cuts, which is "
               "the clearest sign that buyers substituted rather than left the market.")

with tab_prov:
    st.subheader(f"Province ranking, {sel_q}")
    r = prov[prov["quarter"] == sel_q].sort_values("zev_share")
    fig = go.Figure(go.Bar(
        x=r["zev_share"], y=r["province"], orientation="h", marker_color="#2a78d6",
        text=r["zev_share"].map(lambda v: f"{v:.1f}%"), textposition="outside",
        customdata=r[["zev", "total"]], cliponaxis=False,
        hovertemplate="%{y}: %{x:.1f}% (%{customdata[0]:,.0f} of %{customdata[1]:,.0f})<extra></extra>"))
    fig.add_vline(x=now["zev_share"], line_dash="dot", line_color=INK,
                  annotation_text=f"Canada {now['zev_share']:.1f}%",
                  annotation_position="bottom right")
    fig = style(fig, height=420, policy=False)
    fig.update_layout(hovermode="closest", bargap=0.35)
    fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor="rgba(128,128,128,0.15)")
    fig.update_yaxes(ticksuffix=None, showgrid=False)
    st.plotly_chart(fig, width="stretch")

    st.subheader("What the 2025 rebate cuts cost each province")
    shock = (q[q["year"].isin([2024, 2025]) & q["total"].notna()]
             .groupby(["province", "year"])[["zev", "total"]].sum().reset_index())
    shock["share"] = 100 * shock["zev"] / shock["total"]
    wide = shock.pivot(index="province", columns="year", values="share").dropna()
    wide["change"] = (wide[2025] - wide[2024]).round(2)
    wide = wide.sort_values("change")
    fig = go.Figure(go.Bar(x=wide["change"], y=wide.index, orientation="h",
                           marker_color="#eb6834", cliponaxis=False,
                           text=wide["change"].map(lambda v: f"{v:+.1f}"),
                           textposition="outside",
                           hovertemplate="%{y}: %{x:+.2f} pts<extra></extra>"))
    fig = style(fig, height=380, policy=False)
    fig.update_layout(hovermode="closest", bargap=0.35)
    fig.update_xaxes(ticksuffix=" pts", showgrid=True, gridcolor="rgba(128,128,128,0.15)")
    fig.update_yaxes(ticksuffix=None, showgrid=False)
    st.plotly_chart(fig, width="stretch")
    st.caption("Change in annual ZEV share, 2024 to 2025. The provinces that had subsidised "
               "most had the furthest to fall.")

with tab_fc:
    st.subheader("Forecast: ZEV share, next four quarters")
    have = [c for c in ["CA"] + options if c in set(forecasts["prov_code"])]
    geo = st.selectbox("Forecast for", have, format_func=lambda c: names[c])
    hist_df = q[(q["prov_code"] == geo) & q["zev_share"].notna()
                & (q["quarter"] >= DEFAULT_START)].sort_values("quarter")
    hist = hist_df["zev_share"].to_numpy()
    fc = forecasts[forecasts["prov_code"] == geo].drop(columns=["prov_code"])
    hx = quarter_to_date(hist_df["quarter"])
    fx = quarter_to_date(fc["quarter"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(fx) + list(fx)[::-1],
                             y=list(fc["high"]) + list(fc["low"][::-1]),
                             fill="toself", mode="lines", fillcolor="rgba(42,120,214,0.15)",
                             line=dict(width=0), name="80% interval", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=hx, y=hist, name="Actual", mode="lines",
                             line=dict(color=INK, width=2)))
    fig.add_trace(go.Scatter(x=[hx.iloc[-1]] + list(fx), y=[float(hist[-1])] + list(fc["forecast"]),
                             name="Forecast", mode="lines+markers",
                             line=dict(color="#2a78d6", width=2, dash="dash"),
                             marker=dict(size=8)))
    st.plotly_chart(style(fig, y_title="ZEV share", policy=False), width="stretch")

    b = backtests.loc[geo] if geo in backtests.index else None
    verdict = ("**this model does not beat the naive baseline.**" if b is None or not b["beats_naive"]
               else "it edges out the naive baseline here, which it does not do nationally.")
    st.warning(
        f"**Read the band, not the line.** Damped-trend exponential smoothing fitted from "
        f"{DEFAULT_START}. In a rolling back-test over "
        f"{int(b['folds']) if b is not None else honesty['folds']} origins it was off by "
        f"{b['model_mae_pts'] if b is not None else honesty['model_mae_pts']} percentage points "
        f"on average, against "
        f"{b['naive_mae_pts'] if b is not None else honesty['naive_mae_pts']} points for a naive "
        f"\"same as last quarter\" guess — so {verdict} The reason is visible in the "
        f"history: ZEV share halved in one quarter when the federal and Quebec rebates were "
        f"cut in January 2025, and no model fitted on past share can anticipate a policy "
        f"decision. Treat the interval as a plausible range under unchanged policy.")
    st.dataframe(fc.round(2), width="stretch", hide_index=True)

with tab_biz:
    st.subheader("What this means for an automaker's dealer network")
    last4 = sorted(q["quarter"].unique())[-4:]
    recent = (q[q["quarter"].isin(last4) & (q["prov_code"] != "CA") & q["total"].notna()]
              .groupby("province")[["zev", "total"]].sum())
    recent["share"] = 100 * recent["zev"] / recent["total"]
    recent["pct_of_zevs"] = 100 * recent["zev"] / recent["zev"].sum()
    recent = recent.sort_values("zev", ascending=False)
    top3 = recent.head(3)
    on = recent.loc["Ontario"]
    national = q[(q["prov_code"] == "CA") & q["quarter"].isin(last4)][["zev", "total"]].sum()
    nat_share = 100 * national["zev"] / national["total"]

    st.markdown(f"""
**1. Three provinces are the EV market.** Over the last four quarters,
{top3.index[0]}, {top3.index[1]} and {top3.index[2]} took
**{top3['pct_of_zevs'].sum():.0f}%** of every ZEV registered in Canada. Allocate EV
inventory and charging-ready dealer upgrades there first; the rest of the country is a
hybrid and gasoline market for now.

**2. Ontario is the volume opportunity, not the share leader.** Its ZEV share is
**{on['share']:.1f}%** against {nat_share:.1f}% nationally, but it registers
{on['total']:,.0f} new vehicles a quarter-year — so one point of share there is about
**{on['total']*0.01:,.0f} extra EVs**, more than most provinces sell in total.

**3. Plan for policy, not trend.** When the federal iZEV programme paused and Quebec cut
its rebate in January 2025, national ZEV share fell from
{ca.loc['2024Q4','zev_share']:.1f}% to {ca.loc['2025Q1','zev_share']:.1f}% in a single
quarter, and Quebec's annual share fell 14.0 points. Inventory plans that assume a smooth
adoption curve will be wrong in both directions; the planning input is the policy calendar.

**4. Hybrids are the hedge.** Non-plug-in hybrids went from
{ca.loc['2024Q4','hybrid_share']:.1f}% of new registrations in Q4 2024 to
{ca.loc[latest,'hybrid_share']:.1f}% in {latest}, straight through the rebate cuts. Buyers
moved down the electrification ladder rather than leaving it.

**5. The recovery is real but partial.** ZEV share is back to
{ca.loc[latest,'zev_share']:.1f}% from a low of {ca['zev_share'].loc['2025Q2']:.1f}%, still
{peak - ca.loc[latest,'zev_share']:.1f} points below the {peak:.1f}% peak. A dealer network
sized for the 2024 peak is oversized for today's market.
""")
    with st.expander("See the data"):
        cols = ["quarter", "province", "total", "bev", "phev", "hybrid", "zev", "zev_share"]
        st.dataframe(q[cols], width="stretch", hide_index=True)
        st.download_button("Download CSV", q[cols].to_csv(index=False),
                           "canada_zev_quarterly.csv")

st.caption("Built by David Okeya · "
           "[GitHub](https://github.com/OkeyaDavid/canada-ev-adoption) · "
           "Data: [Statistics Canada 20-10-0025-01]"
           "(https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=2010002501)")
