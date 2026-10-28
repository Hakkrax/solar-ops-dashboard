"""Synthetic hourly data with known answers.

One 10 kWp system. A normal day has 10 daylight hours at 500 W/m2 (5 kWh/m2)
and 4 kWh per hour, so PR = 40 / (10 x 5) = 0.80 exactly.
"""

from __future__ import annotations

import pandas as pd
import pytest

DC = 10.0
SYSTEMS = pd.DataFrame({
    "system_id": [1], "name": ["Test roof"], "dc_capacity_kw": [DC], "ac_capacity_kw": [8.0],
    "latitude": [36.0], "longitude": [-115.0], "label": ["1 · Test roof"],
})


def day_rows(day: str, *, energy: float | None = 4.0, poa: float | None = 500.0,
             ghi: float = 500.0, hours_with_energy: int = 10) -> list[dict]:
    """24 hourly rows; daylight is 08:00-17:00."""
    rows = []
    for h in range(24):
        daylight = 8 <= h < 18
        e = energy if daylight and (h - 8) < hours_with_energy else (None if daylight else 0.0)
        rows.append({
            "system_id": 1, "ts_utc": pd.Timestamp(day) + pd.Timedelta(hours=h), "local_date": day,
            "energy_kwh": e, "poa_wm2": (poa if daylight else 0.0) if poa is not None else None,
            "ghi_wm2": ghi if daylight else 0.0, "air_temp_c": 30.0, "cloud_cover_pct": 10.0,
            "module_temp_c": 40.0, "samples_valid": 4, "dq_flags": None,
        })
    return rows


def frame(*days: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([r for d in days for r in d])


@pytest.fixture
def normal_days() -> list[list[dict]]:
    return [day_rows(str(d.date())) for d in pd.date_range("2019-06-01", periods=30)]
