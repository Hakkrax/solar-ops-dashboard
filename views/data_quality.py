import pandas as pd
import plotly.express as px
import streamlit as st

from solar_ops import ui

ctx = st.session_state["ctx"]
systems, sel = ctx["systems"], ctx["sel"]
labels = ui.system_label(systems)

st.title("Data quality")
st.markdown(
    "Before any KPI is trusted, the ETL pipeline checks every reading against 23 named rules "
    "and records what it fixed or rejected. This page shows how complete the data is and "
    "what the rules found, so gaps are visible instead of hidden."
)
if ui.empty_state(sel):
    st.stop()

d = ui.apply(ctx["daily"], sel)
if d.empty:
    st.warning("No data in the selected date range.")
    st.stop()

st.subheader("Daylight coverage by month")
st.caption("Share of daylight hours with a trusted energy reading. Darker is more complete.")
m = (d.assign(month=d["local_date"].dt.to_period("M").dt.to_timestamp())
     .groupby(["system_id", "month"], as_index=False)[["daylight_hours_with_energy", "daylight_hours"]].sum())
m["coverage"] = m["daylight_hours_with_energy"] / m["daylight_hours"]
grid = m.pivot(index="system_id", columns="month", values="coverage")
grid.index = grid.index.map(labels)
fig = px.imshow(grid, color_continuous_scale=["#f2f1ed", "#86b6ef", "#2a78d6", "#104281"],
                zmin=0, zmax=1, aspect="auto",
                labels={"x": "Month", "y": "", "color": "Coverage"})
fig.update_traces(hovertemplate="%{y}<br>%{x|%b %Y}: %{z:.0%}<extra></extra>", xgap=2, ygap=2)
fig.update_layout(margin=dict(t=10), height=120 + 60 * len(grid), coloraxis_colorbar=dict(tickformat=".0%"))
st.plotly_chart(fig, width="stretch")

st.subheader("What the rules found")
dq = ctx["dq_daily"]
dq = dq[dq["system_id"].isin(sel.system_ids)
        & (dq["local_date"] >= pd.Timestamp(sel.start)) & (dq["local_date"] <= pd.Timestamp(sel.end))]
if dq.empty:
    st.info("No rule hits in this selection.")
else:
    units = {"missing_file": "days", "schema_missing_required": "days", "schema_missing_optional": "days",
             "low_coverage_hour": "hours"}
    totals = (dq.groupby(["rule", "severity"], as_index=False)["rows_affected"].sum()
              .sort_values("rows_affected", ascending=False))
    totals["unit"] = totals["rule"].map(units).fillna("readings")
    fig = px.bar(totals, x="rows_affected", y="rule", orientation="h", log_x=True,
                 labels={"rows_affected": "Count (log scale)", "rule": ""},
                 hover_data={"unit": True, "severity": True})
    fig.update_traces(marker_color="#2a78d6", marker_line_width=0)
    fig.update_layout(yaxis=dict(autorange="reversed"), margin=dict(t=10), height=80 + 28 * len(totals))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(totals.rename(columns={"rule": "Rule", "severity": "Severity",
                                        "rows_affected": "Count", "unit": "Unit"}),
                 hide_index=True, width="stretch")
    st.caption(
        "Log scale, because counts range from single readings to over 100,000. "
        "`unit_converted` is large because early-2017 files logged kW, °F and mph and were converted, "
        "not discarded. Full rule catalogue: "
        "[solar-etl-pipeline](https://github.com/Hakkrax/solar-etl-pipeline/blob/main/docs/DESIGN.md)."
    )

run = ctx["source_run"]
st.caption(f"Source: ETL run `{run['run_id']}`, window {run['window_start']} to {run['window_end']}.")
