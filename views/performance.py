import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from solar_ops import ui

ctx = st.session_state["ctx"]
systems, sel = ctx["systems"], ctx["sel"]
labels = ui.system_label(systems)

st.title("Actual vs expected energy")
st.markdown(
    "Expected energy = the system's **own usual performance ratio** × installed DC capacity × the "
    "sunlight it received that day. So a system is compared with its normal self in that day's "
    "weather, not with a datasheet. When the site's sunlight sensor is missing, the weather "
    "model's sunlight is used instead (with its own reference ratio)."
)
if ui.empty_state(sel):
    st.stop()

d = ui.apply(ctx["daily"], sel)
scored = d[d["expected_kwh"].notna()]
if scored.empty:
    st.warning("No scored days in this selection. Days with under 80% data coverage or very "
               "little sunlight are not scored.")
    st.stop()

options = list(sel.system_ids)
# Open on 1419 when it's selected: its outages make the comparison easiest to read.
system_id = st.selectbox("System", options=options, format_func=labels.get,
                         index=options.index(1419) if 1419 in options else 0)
s = scored[scored["system_id"] == system_id].sort_values("local_date")
if s.empty:
    st.info("This system has no scored days in the selected range.")
    st.stop()

ref = s["reference_pr"].iloc[0]
c = st.columns(3)
c[0].metric("Reference PR", ui.fmt(ref, ".1%"), help="Median daily PR over all scored days, 2017–2019.")
c[1].metric("Scored days", f"{len(s):,}")
c[2].metric("Actual ÷ expected", ui.fmt(s["scored_energy_kwh"].sum() / s["expected_kwh"].sum(), ".2f"))

color = ui.SYSTEM_COLORS[system_id]
fig = go.Figure()
fig.add_scatter(x=s["local_date"], y=s["expected_kwh"], name="Expected", mode="lines",
                line=dict(color="#8a8a86", width=1.5, dash="dot"))
fig.add_scatter(x=s["local_date"], y=s["scored_energy_kwh"], name="Actual", mode="lines",
                line=dict(color=color, width=2))
fig.update_layout(hovermode="x unified", yaxis_title="Energy (kWh/day)", xaxis_title=None,
                  legend=dict(orientation="h", y=-0.15), margin=dict(t=10))
fig.update_traces(hovertemplate="%{y:,.0f} kWh")
st.plotly_chart(fig, width="stretch")

st.subheader("Performance index by day")
st.caption("1.00 means the system did exactly as usual for the sunlight it got. "
           "The shaded band (0.85–1.15) is treated as normal.")
fig = px.scatter(s, x="local_date", y="performance_index",
                 labels={"local_date": "Date", "performance_index": "Actual ÷ expected"},
                 hover_data={"expected_basis": True, "performance_index": ":.2f"})
fig.update_traces(marker=dict(color=color, size=8, line=dict(width=1, color="white")))
fig.add_hrect(y0=0.85, y1=1.15, fillcolor="#8a8a86", opacity=0.12, line_width=0)
fig.add_hline(y=1.0, line_color="#8a8a86", line_width=1)
fig.update_layout(margin=dict(t=10))
st.plotly_chart(fig, width="stretch")

st.subheader("Energy vs sunlight")
st.caption("Each dot is a day. Healthy days sit on a straight line; outages fall well below it.")
basis = s[s["expected_basis"] == "site sensor"]
if basis.empty:
    st.info("No days scored against the site sensor in this range.")
else:
    fig = px.scatter(basis, x="poa_paired_kwh_m2", y="e_poa",
                     labels={"poa_paired_kwh_m2": "Sunlight on the panels (kWh/m²)",
                             "e_poa": "Energy (kWh)"},
                     hover_data={"local_date": "|%d %b %Y"})
    fig.update_traces(marker=dict(color=color, size=8, opacity=0.8, line=dict(width=1, color="white")))
    x_max = basis["poa_paired_kwh_m2"].max()
    dc = basis["dc_capacity_kw"].iloc[0]
    fig.add_scatter(x=[0, x_max], y=[0, ref * dc * x_max], mode="lines", name="Usual performance",
                    line=dict(color="#8a8a86", dash="dot"))
    fig.update_layout(legend=dict(orientation="h", y=-0.2), margin=dict(t=10))
    st.plotly_chart(fig, width="stretch")
