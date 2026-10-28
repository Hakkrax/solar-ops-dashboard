import pandas as pd
import plotly.express as px
import streamlit as st

from solar_ops import analytics, ui

ctx = st.session_state["ctx"]
systems, sel = ctx["systems"], ctx["sel"]
labels = ui.system_label(systems)

st.title("Anomalies")
st.markdown("Every system-day is checked against the rules below. Each flag says what was found "
            "in plain English, so an engineer knows where to look first.")
if ui.empty_state(sel):
    st.stop()

with st.expander("Rules and thresholds", icon=":material/tune:"):
    c = st.columns(2)
    under = c[0].slider("Underperformance below (actual ÷ expected)", 0.50, 0.95, 0.85, 0.01)
    critical = c[0].slider("Critical below", 0.30, 0.80, 0.60, 0.01)
    over = c[1].slider("Over-performance above", 1.05, 1.40, 1.15, 0.01)
    coverage = c[1].slider("Minimum data coverage to score a day", 0.50, 1.00, 0.80, 0.05)
    st.markdown(
        "- **Underperformance / critical:** energy well below what this system usually makes in that sunlight.\n"
        "- **Over-performance:** more energy than the sunlight allows, which usually means the sunlight sensor reads low.\n"
        "- **Statistical drop:** within the normal band but far below the previous 30 scored days "
        "(robust z-score below −3.5, using median and MAD so past outages don't hide new ones).\n"
        "- **Sensor mismatch:** on a sunny day the site's sunlight sensor disagrees with the weather model by more than 40%.\n"
        "- **Data gap:** no trusted readings, or under the coverage threshold, so the day can't be judged."
    )
if critical >= under:
    st.error("The critical threshold must be lower than the underperformance threshold.")
    st.stop()

thresholds = analytics.Thresholds(min_coverage=coverage, under_index=under,
                                  critical_index=critical, over_index=over)
full = ctx["daily"][ctx["daily"]["system_id"].isin(sel.system_ids)]
rescored = analytics.add_expected(full.drop(columns=[
    "reference_pr", "reference_ghi_ratio", "expected_basis", "expected_kwh",
    "scored_energy_kwh", "performance_index"]), thresholds)
flags = ui.anomalies_for(rescored, thresholds)
flags = flags[(flags["local_date"] >= pd.Timestamp(sel.start)) & (flags["local_date"] <= pd.Timestamp(sel.end))]

if flags.empty:
    st.success("No anomalies in this selection.")
    st.stop()

counts = flags.groupby("severity").size().reindex(ui.SEVERITY_ORDER, fill_value=0)
c = st.columns(4)
for col, sev in zip(c, ui.SEVERITY_ORDER, strict=True):
    col.metric(ui.SEVERITY_LABELS[sev], f"{counts[sev]:,}", border=True)

severities = st.pills("Show", options=ui.SEVERITY_ORDER, default=["critical", "warning", "info"],
                      format_func=ui.SEVERITY_LABELS.get, selection_mode="multi")
shown = flags[flags["severity"].isin(severities or [])]

st.subheader("When they happened")
if shown.empty:
    st.info("No flags of the selected severity.")
else:
    monthly = (shown.assign(month=shown["local_date"].dt.to_period("M").dt.to_timestamp(),
                            system=shown["system_id"].map(labels))
               .groupby(["month", "system"], as_index=False).size())
    fig = px.bar(monthly, x="month", y="size", color="system", barmode="group",
                 color_discrete_map={labels[i]: ui.SYSTEM_COLORS[i] for i in labels},
                 category_orders={"system": [labels[i] for i in sorted(labels)]},
                 labels={"month": "Month", "size": "Flagged days", "system": "System"})
    fig.update_traces(marker_line_width=0)
    fig.update_layout(legend=dict(orientation="h", y=-0.2), margin=dict(t=10), bargap=0.25)
    st.plotly_chart(fig, width="stretch")

st.subheader("Flag list")
table = shown.sort_values(["local_date", "system_id"], ascending=[False, True]).assign(
    System=lambda x: x["system_id"].map(labels),
    Severity=lambda x: x["severity"].map(ui.SEVERITY_LABELS),
)
st.dataframe(
    table[["local_date", "System", "Severity", "rule", "reason", "energy_kwh", "expected_kwh"]],
    hide_index=True, width="stretch",
    column_config={
        "local_date": st.column_config.DateColumn("Date", format="DD MMM YYYY"),
        "rule": "Rule",
        "reason": st.column_config.TextColumn("What was found", width="large"),
        "energy_kwh": st.column_config.NumberColumn("Energy (kWh)", format="%.0f"),
        "expected_kwh": st.column_config.NumberColumn("Expected (kWh)", format="%.0f"),
    },
)
ui.download(table.drop(columns=["System", "Severity"]), f"solar_anomalies_{sel.start}_{sel.end}.csv")
