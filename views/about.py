import streamlit as st

from solar_ops import ui

ctx = st.session_state["ctx"]
systems = ctx["systems"]

st.title("About the data")
st.markdown(
    """
**What this is.** A performance monitor for three rooftop solar systems on public buildings in
Las Vegas, Nevada, built on historical open data from 2017 to 2019. It is **not connected to
live equipment.**

**Where the data comes from.**
1. [NREL PV Data Acquisition (PVDAQ)](https://doi.org/10.25984/1846021): 5- and 15-minute
   monitoring files for each system (CC BY 4.0).
2. [Open-Meteo](https://open-meteo.com/) historical weather: hourly sunlight, temperature and
   cloud cover (CC BY 4.0).
3. Both were cleaned, checked and joined by my
   [solar-etl-pipeline](https://github.com/Hakkrax/solar-etl-pipeline) project. This app reads a
   compact copy of its output.

**Definitions.**
- *Daylight hour:* weather-model sunlight of at least 20 W/m².
- *Data coverage:* share of daylight hours with a trusted energy reading.
- *Performance ratio (PR):* energy ÷ (DC capacity × sunlight measured on the panels).
  Only hours with both values count.
- *Expected energy:* the system's own median PR × DC capacity × that day's sunlight.
- *Performance index:* actual ÷ expected. 1.00 means a normal day for that system.
- *Availability:* share of sunny hours (≥ 50 W/m²) with trusted readings where the system was producing.

**Known limits.**
- PR here is indicative, because capacity comes from PVDAQ's module list. System 1420's
  sunlight sensor reads lower relative to the weather model than the other two sites
  (median 92% vs about 100%), which may explain why its PR is higher.
- Days with missing files are shown as gaps, never filled in. Totals are therefore lower bounds.
- Anomaly rules flag days to investigate. They do not prove a fault.
"""
)

st.subheader("Systems")
st.dataframe(
    systems[["system_id", "name", "dc_capacity_kw", "ac_capacity_kw", "tilt_deg", "azimuth_deg"]],
    hide_index=True, width="stretch",
    column_config={
        "system_id": "ID", "name": "Name",
        "dc_capacity_kw": st.column_config.NumberColumn("DC capacity (kWp)", format="%.2f"),
        "ac_capacity_kw": st.column_config.NumberColumn("Rated AC (kW)", format="%.0f"),
        "tilt_deg": st.column_config.NumberColumn("Tilt (°)", format="%.0f"),
        "azimuth_deg": st.column_config.NumberColumn("Azimuth (°)", format="%.0f"),
    },
)
st.caption("Built by Faheem Niyas. Code: "
           "[github.com/Hakkrax/solar-ops-dashboard](https://github.com/Hakkrax/solar-ops-dashboard) · "
           + ui.HISTORICAL_NOTE)
