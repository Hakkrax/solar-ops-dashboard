"""Daily performance metrics, expected energy and anomaly rules.

Everything here is plain pandas so it can be unit-tested without Streamlit.

Definitions
-----------
- Daylight hour: weather-model GHI of at least 20 W/m2.
- Coverage: share of daylight hours with a trusted energy value from the ETL.
- Performance ratio (PR): energy / (DC capacity x plane-of-array insolation),
  using only hours where both energy and irradiance are present.
- Expected energy: the system's own reference PR x DC capacity x insolation on
  the day. When the site irradiance sensor is missing, the weather-model GHI is
  used with a separate reference ratio for that basis.
- Performance index: actual / expected energy. 1.0 means "as usual for this
  system in this weather".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DAYLIGHT_GHI_WM2 = 20.0
MIN_SCORING_INSOLATION = 2.0  # kWh/m2: skip very dark days, where ratios are noisy
PRODUCING_FRACTION = 0.01     # an hour "produces" above 1% of DC capacity


@dataclass(frozen=True)
class Thresholds:
    min_coverage: float = 0.80      # below this a day is not scored
    under_index: float = 0.85       # performance index below this -> underperformance
    critical_index: float = 0.60    # ... below this -> critical
    over_index: float = 1.15        # above this -> likely sensor problem
    robust_z: float = 3.5           # statistical outlier vs the previous 30 scored days
    sensor_ratio_low: float = 0.60  # site POA / model GHI outside this band on bright days
    sensor_ratio_high: float = 1.40
    window_days: int = 30


DEFAULT_THRESHOLDS = Thresholds()


def daily_metrics(hourly: pd.DataFrame, systems: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hourly rows to one row per system and local date."""
    h = hourly.merge(systems[["system_id", "dc_capacity_kw"]], on="system_id", how="left")
    daylight = h["ghi_wm2"] >= DAYLIGHT_GHI_WM2
    has_energy = h["energy_kwh"].notna()
    paired_poa = has_energy & h["poa_wm2"].notna()
    paired_ghi = has_energy & h["ghi_wm2"].notna()
    producing = has_energy & (h["energy_kwh"] > PRODUCING_FRACTION * h["dc_capacity_kw"])
    bright = daylight & (h["poa_wm2"].fillna(h["ghi_wm2"]) >= 50)

    g = h.assign(
        daylight=daylight,
        daylight_with_energy=daylight & has_energy,
        e_poa=h["energy_kwh"].where(paired_poa),
        poa_paired=h["poa_wm2"].where(paired_poa),
        e_ghi=h["energy_kwh"].where(paired_ghi),
        ghi_paired=h["ghi_wm2"].where(paired_ghi),
        bright_trusted=bright & has_energy,
        bright_producing=bright & producing,
    ).groupby(["system_id", "local_date"], as_index=False)

    d = g.agg(
        energy_kwh=("energy_kwh", lambda s: s.sum(min_count=1)),
        poa_kwh_m2=("poa_wm2", lambda s: s.sum(min_count=1) / 1000.0),
        ghi_kwh_m2=("ghi_wm2", lambda s: s.sum(min_count=1) / 1000.0),
        e_poa=("e_poa", "sum"),
        poa_paired_kwh_m2=("poa_paired", lambda s: s.sum() / 1000.0),
        e_ghi=("e_ghi", "sum"),
        ghi_paired_kwh_m2=("ghi_paired", lambda s: s.sum() / 1000.0),
        daylight_hours=("daylight", "sum"),
        daylight_hours_with_energy=("daylight_with_energy", "sum"),
        bright_hours_trusted=("bright_trusted", "sum"),
        bright_hours_producing=("bright_producing", "sum"),
        max_air_temp_c=("air_temp_c", "max"),
        mean_cloud_cover_pct=("cloud_cover_pct", "mean"),
    )
    d = d.merge(systems[["system_id", "dc_capacity_kw"]], on="system_id", how="left")
    d["local_date"] = pd.to_datetime(d["local_date"])
    # Night-time zeros alone don't make a day "0 kWh": with no daylight readings it is a gap.
    d.loc[d["daylight_hours_with_energy"] == 0, "energy_kwh"] = np.nan
    d["coverage"] = _safe_div(d["daylight_hours_with_energy"], d["daylight_hours"])
    d["performance_ratio"] = _safe_div(d["e_poa"], d["dc_capacity_kw"] * d["poa_paired_kwh_m2"])
    d["ghi_ratio"] = _safe_div(d["e_ghi"], d["dc_capacity_kw"] * d["ghi_paired_kwh_m2"])
    d["specific_yield"] = d["energy_kwh"] / d["dc_capacity_kw"]
    d["sensor_ratio"] = _safe_div(d["poa_kwh_m2"], d["ghi_kwh_m2"])
    return d.sort_values(["system_id", "local_date"]).reset_index(drop=True)


def add_expected(daily: pd.DataFrame, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> pd.DataFrame:
    """Add reference ratios, expected energy and the performance index.

    The reference is each system's median ratio over all scorable days, so a
    system is compared with its own normal behaviour, not with a datasheet.
    """
    d = daily.copy()
    scorable = d["coverage"] >= thresholds.min_coverage
    poa_ok = scorable & (d["poa_paired_kwh_m2"] >= MIN_SCORING_INSOLATION)
    ghi_ok = scorable & (d["ghi_paired_kwh_m2"] >= MIN_SCORING_INSOLATION)
    ref_poa = d[poa_ok].groupby("system_id")["performance_ratio"].median()
    ref_ghi = d[ghi_ok].groupby("system_id")["ghi_ratio"].median()
    d["reference_pr"] = d["system_id"].map(ref_poa)
    d["reference_ghi_ratio"] = d["system_id"].map(ref_ghi)

    use_poa = poa_ok & d["reference_pr"].notna()
    use_ghi = ~use_poa & ghi_ok & d["reference_ghi_ratio"].notna()
    d["expected_basis"] = np.select([use_poa, use_ghi], ["site sensor", "weather model"], default="not scored")
    d["expected_kwh"] = np.select(
        [use_poa, use_ghi],
        [
            d["reference_pr"] * d["dc_capacity_kw"] * d["poa_paired_kwh_m2"],
            d["reference_ghi_ratio"] * d["dc_capacity_kw"] * d["ghi_paired_kwh_m2"],
        ],
        default=np.nan,
    )
    actual = np.where(use_poa, d["e_poa"], np.where(use_ghi, d["e_ghi"], np.nan))
    d["scored_energy_kwh"] = actual
    d["performance_index"] = _safe_div(pd.Series(actual, index=d.index), d["expected_kwh"])
    return d


def flag_anomalies(daily: pd.DataFrame, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> pd.DataFrame:
    """One row per (system, day, rule) with severity and a plain-English reason."""
    t = thresholds
    d = daily.sort_values(["system_id", "local_date"]).copy()
    d["robust_z"] = _rolling_robust_z(d, t.window_days)
    out: list[dict] = []

    def add(row, rule: str, severity: str, reason: str) -> None:
        out.append({
            "system_id": int(row.system_id), "local_date": row.local_date,
            "rule": rule, "severity": severity, "reason": reason,
            "energy_kwh": row.energy_kwh, "expected_kwh": row.expected_kwh,
            "performance_index": row.performance_index,
        })

    for row in d.itertuples(index=False):
        if row.daylight_hours == 0:
            continue
        if row.daylight_hours_with_energy == 0:
            add(row, "no_data", "data",
                "No trusted readings for this day: the source file was missing or rejected by the ETL.")
            continue
        if row.coverage < t.min_coverage:
            add(row, "low_coverage", "data",
                f"Only {int(row.daylight_hours_with_energy)} of {int(row.daylight_hours)} daylight hours "
                "have trusted readings, so the day is not scored.")
            continue
        pi = row.performance_index
        if not np.isnan(pi):
            pct = f"{pi:.0%}"
            vs = f"({row.scored_energy_kwh:,.0f} kWh vs {row.expected_kwh:,.0f} kWh expected)"
            if pi < t.critical_index:
                add(row, "underperformance", "critical",
                    f"Produced {pct} of expected energy {vs}. A drop this large in normal weather "
                    "usually points to an inverter or string outage.")
            elif pi < t.under_index:
                add(row, "underperformance", "warning",
                    f"Produced {pct} of expected energy {vs}. Check for soiling, shading or a partial outage.")
            elif pi > t.over_index:
                add(row, "over_performance", "warning",
                    f"Produced {pct} of expected energy {vs}. Output cannot really beat the weather, "
                    "so the irradiance reading is probably low (sensor fault or soiling).")
            elif not np.isnan(row.robust_z) and row.robust_z < -t.robust_z:
                add(row, "statistical_drop", "info",
                    f"Performance index {pi:.2f} is unusually low compared with the previous "
                    f"{t.window_days} scored days (robust z = {row.robust_z:.1f}).")
        bright = row.ghi_kwh_m2 >= 4 if not np.isnan(row.ghi_kwh_m2) else False
        if bright and not np.isnan(row.sensor_ratio) and not (
            t.sensor_ratio_low <= row.sensor_ratio <= t.sensor_ratio_high
        ):
            add(row, "sensor_mismatch", "warning",
                f"Site irradiance sensor recorded {row.sensor_ratio:.0%} of the weather-model value "
                "on a sunny day. Check the sensor before trusting PR for this day.")

    cols = ["system_id", "local_date", "rule", "severity", "reason",
            "energy_kwh", "expected_kwh", "performance_index"]
    return pd.DataFrame(out, columns=cols)


def kpis(daily: pd.DataFrame) -> dict[str, float]:
    """Headline KPIs for the filtered days (energy-weighted, not averages of ratios)."""
    if daily.empty:
        return {k: float("nan") for k in (
            "energy_mwh", "specific_yield", "performance_ratio", "coverage", "availability",
            "performance_index")}
    dc_total = daily.groupby("system_id")["dc_capacity_kw"].first().sum()
    scored = daily["expected_kwh"].notna()
    return {
        "energy_mwh": daily["energy_kwh"].sum() / 1000.0,
        # kWh per installed kWp over the whole selected period (fleet total).
        "specific_yield": _ratio(daily["energy_kwh"].sum(), dc_total),
        "performance_ratio": _ratio(daily["e_poa"].sum(),
                                    (daily["dc_capacity_kw"] * daily["poa_paired_kwh_m2"]).sum()),
        "coverage": _ratio(daily["daylight_hours_with_energy"].sum(), daily["daylight_hours"].sum()),
        "availability": _ratio(daily["bright_hours_producing"].sum(), daily["bright_hours_trusted"].sum()),
        "performance_index": _ratio(daily.loc[scored, "scored_energy_kwh"].sum(),
                                    daily.loc[scored, "expected_kwh"].sum()),
    }


def _rolling_robust_z(d: pd.DataFrame, window: int) -> pd.Series:
    """Robust z-score of the performance index vs the previous `window` scored days."""
    def per_system(s: pd.Series) -> pd.Series:
        prev = s.shift(1).rolling(window, min_periods=max(10, window // 3))
        med = prev.median()
        mad = prev.apply(lambda x: np.nanmedian(np.abs(x - np.nanmedian(x))), raw=True)
        return 0.6745 * (s - med) / mad.replace(0, np.nan)

    pi = d["performance_index"]
    return pi.groupby(d["system_id"], group_keys=False).apply(
        lambda s: per_system(s.dropna()).reindex(s.index))


def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    den = den.astype(float)
    return (num.astype(float) / den.where(den != 0)).astype(float)


def _ratio(num: float, den: float) -> float:
    return float(num / den) if den else float("nan")
