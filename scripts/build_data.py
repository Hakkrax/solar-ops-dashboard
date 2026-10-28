"""Build the app's compact SQLite file from a solar-etl-pipeline database.

Usage:
    python scripts/build_data.py path/to/solar.db

The source is the database written by https://github.com/Hakkrax/solar-etl-pipeline
(or its `solar-etl snapshot` export). Lineage columns are dropped and facts are
joined to weather so the file stays small enough to ship with the app.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "solar_fleet.db"

SCHEMA = """
CREATE TABLE systems (
    system_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    ac_capacity_kw REAL NOT NULL,
    dc_capacity_kw REAL NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timezone TEXT NOT NULL,
    tilt_deg REAL,
    azimuth_deg REAL,
    source TEXT NOT NULL
);
CREATE TABLE hourly (
    system_id INTEGER NOT NULL REFERENCES systems(system_id),
    ts_utc TEXT NOT NULL,
    local_date TEXT NOT NULL,
    energy_kwh REAL,
    poa_wm2 REAL,
    module_temp_c REAL,
    ghi_wm2 REAL,
    air_temp_c REAL,
    cloud_cover_pct REAL,
    samples_valid INTEGER NOT NULL,
    dq_flags TEXT,
    PRIMARY KEY (system_id, ts_utc)
);
CREATE INDEX ix_hourly_date ON hourly(local_date);
CREATE TABLE dq_daily (
    system_id INTEGER NOT NULL,
    local_date TEXT NOT NULL,
    rule TEXT NOT NULL,
    severity TEXT NOT NULL,
    rows_affected INTEGER NOT NULL,
    PRIMARY KEY (system_id, local_date, rule)
);
CREATE TABLE source_run (
    run_id TEXT PRIMARY KEY,
    finished_at TEXT,
    status TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    code_version TEXT
);
"""


def build(source: Path, out: Path = OUT) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    dst = sqlite3.connect(out)
    dst.executescript(SCHEMA)
    dst.execute("ATTACH DATABASE ? AS src", (str(source),))
    with dst:
        dst.execute("""
            INSERT INTO systems
            SELECT system_id, name, capacity_kw, dc_capacity_kw, latitude, longitude,
                   timezone, tilt_deg, azimuth_deg, source
            FROM src.dim_system""")
        dst.execute("""
            INSERT INTO hourly
            SELECT f.system_id, f.ts_utc, f.local_date, f.ac_energy_kwh, f.poa_irradiance_wm2,
                   f.module_temp_c, w.ghi_wm2, w.air_temp_c, w.cloud_cover_pct,
                   f.samples_valid, f.dq_flags
            FROM src.fact_pv_hourly f
            LEFT JOIN src.weather_hourly w ON w.system_id = f.system_id AND w.ts_utc = f.ts_utc""")
        # Keep quality counts from the latest successful run only.
        dst.execute("""
            INSERT INTO dq_daily
            SELECT system_id, local_date, rule, severity, rows_affected
            FROM src.dq_results
            WHERE run_id = (SELECT run_id FROM src.pipeline_runs
                            WHERE status = 'success' ORDER BY finished_at DESC LIMIT 1)""")
        dst.execute("""
            INSERT INTO source_run
            SELECT run_id, finished_at, status, window_start, window_end, code_version
            FROM src.pipeline_runs WHERE status = 'success'
            ORDER BY finished_at DESC LIMIT 1""")
    dst.execute("DETACH DATABASE src")
    dst.execute("VACUUM")
    dst.close()
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = build(Path(sys.argv[1]))
    print(f"wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
