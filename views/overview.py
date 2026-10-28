import pandas as pd
import plotly.express as px
import streamlit as st

from solar_ops import analytics, ui

ctx = st.session_state["ctx"]
systems, sel = ctx["systems"], ctx["sel"]
labels = ui.system_label(systems)

st.title("Solar fleet overview")
st.caption(ui.HISTORICAL_NOTE)
if ui.empty_state(sel):
    st.stop()

d = ui.apply(ctx["daily"], sel)
if d.empty:
    st.warning("No data in the selected date range.")
    st.stop()

k = analytics.kpis(d)
anoms = ui.anomalies_for(ctx["daily"][ctx["daily"]["system_id"].isin(sel.system_ids)],
                         analytics.Thresholds())
anoms = anoms[(anoms["local_date"] >= pd.Timestamp(sel.start)) & (anoms["local_date"] <= pd.Timestamp(sel.end))]
critical_days = anoms[anoms["severity"] == "critical"][["system_id", "local_date"]].drop_duplicates()

c = st.columns(3)
c[0].metric("Energy", ui.fmt(k["energy_mwh"], ",.1f", " MWh"),
            help="AC energy from hours the ETL trusted. Missing hours are not filled in.", border=True)
c[1].metric("Specific yield", ui.fmt(k["specific_yield"], ",.0f", " kWh/kWp"),
            help="Energy per kW of installed DC capacity over the selected period.", border=True)
c[2].metric("Performance ratio", ui.fmt(k["performance_ratio"], ".1%"),
            help="Energy ÷ (DC capacity × measured plane-of-array sunlight). Hours with both values only.", border=True)
c = st.columns(3)
c[0].metric("Data coverage", ui.fmt(k["coverage"], ".1%"),
            help="Share of daylight hours with a trusted energy reading.", border=True)
c[1].metric("Performance index", ui.fmt(k["performance_index"], ".2f"),
            help="Actual ÷ expected energy on scored days. 1.00 = as usual for these systems in this weather.", border=True)
c[2].metric("Critical days", f"{len(critical_days):,}",
            help="System-days producing under 60% of expected energy. See the Anomalies page.", border=True)

# Lead with the one thing an engineer should look at first in this selection.
crit = anoms[anoms["severity"] == "critical"].drop_duplicates(["system_id", "local_date"])
if crit.empty:
    st.success("No critical days in this selection: every scored day produced at least 60% of expected energy.",
               icon=":material/check_circle:")
else:
    worst = crit["system_id"].value_counts()
    wid, n = int(worst.index[0]), int(worst.iloc[0])
    lost = (crit.loc[crit["system_id"] == wid, "expected_kwh"] - crit.loc[crit["system_id"] == wid, "energy_kwh"]).sum()
    median_pi = crit.loc[crit["system_id"] == wid, "performance_index"].median()
    with st.container(border=True):
        st.markdown(
            f"**Look first: {labels[wid]}.** {n:,} critical day{'s' if n != 1 else ''} in this period, producing a "
            f"median {median_pi:.0%} of expected energy, about {lost / 1000:,.1f} MWh below normal on those days."
        )
        st.page_link("views/anomalies.py", label="See the flagged days", icon=":material/warning:")

st.subheader("Daily energy")
smooth = st.segmented_control("View", ["7-day average", "Daily"], default="7-day average",
                              label_visibility="collapsed")
plot = d.assign(system=d["system_id"].map(labels)).sort_values("local_date")
if smooth != "Daily":
    plot["energy_kwh"] = (plot.set_index("local_date").groupby("system_id")["energy_kwh"]
                          .transform(lambda s: s.rolling("7D", min_periods=4).mean()).to_numpy())
fig = px.line(plot, x="local_date", y="energy_kwh", color="system",
              color_discrete_map={labels[i]: ui.SYSTEM_COLORS[i] for i in labels},
              category_orders={"system": [labels[i] for i in sorted(labels)]},
              labels={"local_date": "Date", "energy_kwh": "Energy (kWh/day)", "system": "System"})
fig.update_traces(line_width=1.5, connectgaps=False,
                  hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f} kWh<extra>%{fullData.name}</extra>")
fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=-0.2), margin=dict(t=10))
st.plotly_chart(fig, width="stretch")
st.caption("Gaps are days with no trusted readings. They are left empty, not filled with zeros.")

st.subheader("By system")
summary = pd.DataFrame([{"system_id": sid, **analytics.kpis(g)} for sid, g in d.groupby("system_id")])
summary.insert(1, "System", summary["system_id"].map(labels))
summary = summary.drop(columns="system_id").rename(columns={
    "energy_mwh": "Energy (MWh)", "specific_yield": "Specific yield (kWh/kWp)",
    "performance_ratio": "PR", "coverage": "Coverage", "availability": "Availability",
    "performance_index": "Performance index"})
st.dataframe(summary, hide_index=True, width="stretch", column_config={
    "Energy (MWh)": st.column_config.NumberColumn(format="%.1f"),
    "Specific yield (kWh/kWp)": st.column_config.NumberColumn(format="%.0f"),
    "PR": st.column_config.NumberColumn(format="percent"),
    "Coverage": st.column_config.NumberColumn(format="percent"),
    "Availability": st.column_config.NumberColumn(
        format="percent", help="Share of sunny hours (≥50 W/m²) with trusted readings where the system was producing."),
    "Performance index": st.column_config.NumberColumn(format="%.2f"),
})

export = d[["system_id", "local_date", "energy_kwh", "specific_yield", "performance_ratio",
            "coverage", "expected_kwh", "performance_index", "poa_kwh_m2", "ghi_kwh_m2"]]
ui.download(export, f"solar_daily_{sel.start}_{sel.end}.csv", "Download daily data (CSV)")
