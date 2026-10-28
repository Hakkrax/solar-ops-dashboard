"""Shared Streamlit pieces: cached data, sidebar filters, formatting."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd
import streamlit as st

from solar_ops import analytics, data

# Fixed colour per system (validated for colour-blind separation); never reassigned by filters.
SYSTEM_COLORS = {1418: "#2a78d6", 1419: "#eb6834", 1420: "#1baf7a"}
SEVERITY_ORDER = ["critical", "warning", "info", "data"]
SEVERITY_LABELS = {"critical": "🔴 Critical", "warning": "🟠 Warning", "info": "🔵 Info", "data": "⚪ Data gap"}
HISTORICAL_NOTE = (
    "Historical open data (NREL PVDAQ, 2017–2019) cleaned by my "
    "[solar ETL pipeline](https://github.com/Hakkrax/solar-etl-pipeline). Not a live equipment feed."
)


@st.cache_data(show_spinner="Loading fleet data…")
def load_fleet() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    fd = data.load()
    daily = analytics.add_expected(analytics.daily_metrics(fd.hourly, fd.systems))
    return fd.systems, daily, fd.dq_daily, fd.source_run.to_dict()


@st.cache_data(show_spinner="Checking every day for anomalies…")
def anomalies_for(daily: pd.DataFrame, thresholds: analytics.Thresholds) -> pd.DataFrame:
    return analytics.flag_anomalies(daily, thresholds)


@dataclass(frozen=True)
class Selection:
    system_ids: tuple[int, ...]
    start: date
    end: date


def sidebar_filters(systems: pd.DataFrame, daily: pd.DataFrame) -> Selection:
    lo, hi = daily["local_date"].min().date(), daily["local_date"].max().date()
    labels = dict(zip(systems["system_id"], systems["label"], strict=True))
    with st.sidebar:
        st.markdown("### Filters")
        ids = st.multiselect("Systems", options=list(labels), default=list(labels),
                             format_func=labels.get, key="systems")
        period = st.date_input("Date range", value=(date(2019, 1, 1), hi), min_value=lo,
                               max_value=hi, key="period", format="DD/MM/YYYY")
        st.caption(f"Data covers {lo:%d %b %Y} to {hi:%d %b %Y}.")
    if isinstance(period, tuple) and len(period) == 2:
        start, end = period
    else:  # the user has picked only the first date so far
        start = end = period[0] if isinstance(period, tuple) else period
    return Selection(tuple(ids), start, end)


def apply(daily: pd.DataFrame, sel: Selection) -> pd.DataFrame:
    mask = (daily["system_id"].isin(sel.system_ids)
            & (daily["local_date"] >= pd.Timestamp(sel.start))
            & (daily["local_date"] <= pd.Timestamp(sel.end)))
    return daily[mask]


def empty_state(sel: Selection) -> bool:
    """Show a friendly message and return True when there is nothing to plot."""
    if not sel.system_ids:
        st.info("Pick at least one system in the sidebar to see results.")
        return True
    return False


def system_label(systems: pd.DataFrame) -> dict[int, str]:
    return dict(zip(systems["system_id"], systems["label"], strict=True))


def fmt(value: float, spec: str, suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    return f"{value:{spec}}{suffix}"


def download(df: pd.DataFrame, name: str, label: str = "Download CSV") -> None:
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), file_name=name,
                       mime="text/csv", icon=":material/download:")
