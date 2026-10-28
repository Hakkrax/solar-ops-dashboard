"""Load the shipped SQLite snapshot and check it has what the app needs."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "solar_fleet.db"

REQUIRED_COLUMNS = {
    "systems": {"system_id", "name", "dc_capacity_kw", "ac_capacity_kw", "latitude", "longitude"},
    "hourly": {"system_id", "ts_utc", "local_date", "energy_kwh", "poa_wm2", "ghi_wm2",
               "air_temp_c", "cloud_cover_pct", "samples_valid", "dq_flags"},
    "dq_daily": {"system_id", "local_date", "rule", "severity", "rows_affected"},
    "source_run": {"run_id", "window_start", "window_end"},
}


class DataError(RuntimeError):
    """The data file is missing or does not have the expected shape."""


@dataclass(frozen=True)
class FleetData:
    systems: pd.DataFrame
    hourly: pd.DataFrame
    dq_daily: pd.DataFrame
    source_run: pd.Series


def load(path: Path = DB_PATH) -> FleetData:
    path = Path(path)
    if not path.exists():
        raise DataError(f"Data file not found: {path.name}. Run scripts/build_data.py first.")
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = set(REQUIRED_COLUMNS) - tables
        if missing:
            raise DataError(f"Data file is missing tables: {', '.join(sorted(missing))}")
        frames = {name: pd.read_sql(f"SELECT * FROM {name}", conn) for name in REQUIRED_COLUMNS}
    for name, cols in REQUIRED_COLUMNS.items():
        lacking = cols - set(frames[name].columns)
        if lacking:
            raise DataError(f"Table {name} is missing columns: {', '.join(sorted(lacking))}")
    if frames["hourly"].empty or frames["systems"].empty:
        raise DataError("Data file has no rows.")
    if frames["source_run"].empty:
        raise DataError("Data file has no source run record.")

    systems = frames["systems"].copy()
    systems["label"] = systems["system_id"].astype(str) + " · " + systems["name"].str.replace(
        "Clark County NV - ", "", regex=False)
    hourly = frames["hourly"]
    hourly["ts_utc"] = pd.to_datetime(hourly["ts_utc"])
    dq = frames["dq_daily"]
    dq["local_date"] = pd.to_datetime(dq["local_date"])
    return FleetData(systems=systems, hourly=hourly, dq_daily=dq, source_run=frames["source_run"].iloc[0])
