"""Solar Fleet Performance Monitor: Streamlit entry point."""

import streamlit as st

from solar_ops import ui
from solar_ops.data import DataError

st.set_page_config(page_title="Solar Fleet Performance Monitor", page_icon="☀️", layout="wide")

try:
    systems, daily, dq_daily, source_run = ui.load_fleet()
except DataError as exc:
    st.error(f"The dashboard could not load its data. {exc}")
    st.stop()

sel = ui.sidebar_filters(systems, daily)
st.session_state["ctx"] = {
    "systems": systems, "daily": daily, "dq_daily": dq_daily, "source_run": source_run, "sel": sel,
}

with st.sidebar:
    st.divider()
    st.caption(ui.HISTORICAL_NOTE)

pages = [
    st.Page("views/overview.py", title="Overview", icon=":material/dashboard:", default=True),
    st.Page("views/performance.py", title="Actual vs expected", icon=":material/show_chart:"),
    st.Page("views/anomalies.py", title="Anomalies", icon=":material/warning:"),
    st.Page("views/data_quality.py", title="Data quality", icon=":material/fact_check:"),
    st.Page("views/diesel.py", title="Diesel savings", icon=":material/local_gas_station:"),
    st.Page("views/about.py", title="About the data", icon=":material/info:"),
]
st.navigation(pages).run()
