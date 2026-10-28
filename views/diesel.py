import plotly.express as px
import streamlit as st

from solar_ops import diesel, ui

ctx = st.session_state["ctx"]
systems, sel = ctx["systems"], ctx["sel"]
labels = ui.system_label(systems)

st.title("Diesel savings scenario")
st.info(
    "**What-if calculation.** These sites are grid-connected, so no diesel was actually saved. "
    "This shows what the same solar energy would displace at a site that runs on diesel "
    "generators, using the assumptions you set below.",
    icon=":material/calculate:",
)
if ui.empty_state(sel):
    st.stop()

d = ui.apply(ctx["daily"], sel)
if d.empty:
    st.warning("No data in the selected date range.")
    st.stop()

with st.container(border=True):
    c = st.columns(3)
    lpk = c[0].number_input("Generator fuel use (litres per kWh)", 0.10, 1.00, 0.30, 0.01,
                            help="Typical diesel generators use roughly 0.25–0.35 L/kWh at a "
                                 "good load. Small or lightly loaded sets use more.")
    price = c[1].number_input("Fuel price per litre", 0.0, 20.0, 3.00, 0.05,
                              help="Set this to your current local price.")
    currency = c[2].text_input("Currency", "AED", max_chars=5)
    co2 = st.number_input("CO₂ per litre of diesel (kg)", 2.0, 3.5, diesel.DEFAULT_CO2_KG_PER_L, 0.01,
                          help="About 2.68 kg CO₂ per litre burned (common government conversion factor).")

a = diesel.DieselAssumptions(litres_per_kwh=lpk, price_per_litre=price, currency=currency or "",
                             co2_kg_per_litre=co2)
total = diesel.displacement(float(d["energy_kwh"].sum()), a)

c = st.columns(3)
c[0].metric("Diesel avoided", f"{total['litres']:,.0f} L", border=True)
c[1].metric("Fuel cost avoided", f"{a.currency} {total['cost']:,.0f}", border=True)
c[2].metric("CO₂ avoided", f"{total['co2_tonnes']:,.1f} t", border=True)
st.caption(f"From {total['energy_kwh'] / 1000:,.1f} MWh of trusted solar energy in the selection. "
           "Days with missing data count as zero, so these figures are a lower bound.")

monthly = diesel.monthly_displacement(d, a)
monthly["system"] = monthly["system_id"].map(labels)
fig = px.bar(monthly, x="month", y="litres", color="system",
             color_discrete_map={labels[i]: ui.SYSTEM_COLORS[i] for i in labels},
             category_orders={"system": [labels[i] for i in sorted(labels)]},
             labels={"month": "Month", "litres": "Diesel avoided (litres)", "system": "System"})
fig.update_traces(marker_line_width=0)
fig.update_layout(legend=dict(orientation="h", y=-0.2), margin=dict(t=10), bargap=0.2)
st.plotly_chart(fig, width="stretch")

st.dataframe(monthly[["month", "system", "energy_kwh", "litres", "cost", "co2_tonnes"]],
             hide_index=True, width="stretch",
             column_config={
                 "month": st.column_config.DateColumn("Month", format="MMM YYYY"),
                 "system": "System",
                 "energy_kwh": st.column_config.NumberColumn("Energy (kWh)", format="%.0f"),
                 "litres": st.column_config.NumberColumn("Diesel (L)", format="%.0f"),
                 "cost": st.column_config.NumberColumn(f"Cost ({a.currency})", format="%.0f"),
                 "co2_tonnes": st.column_config.NumberColumn("CO₂ (t)", format="%.2f"),
             })
ui.download(monthly.drop(columns="system"), f"diesel_scenario_{sel.start}_{sel.end}.csv")
