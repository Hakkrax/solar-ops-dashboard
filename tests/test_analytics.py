import math

import numpy as np
import pandas as pd
import pytest
from conftest import DC, SYSTEMS, day_rows, frame

from solar_ops import analytics as a


def scored(*days):
    return a.add_expected(a.daily_metrics(frame(*days), SYSTEMS))


def test_daily_metrics_on_a_normal_day():
    d = a.daily_metrics(frame(day_rows("2019-06-01")), SYSTEMS).iloc[0]
    assert d.energy_kwh == pytest.approx(40.0)
    assert d.daylight_hours == 10
    assert d.coverage == pytest.approx(1.0)
    assert d.performance_ratio == pytest.approx(0.80)
    assert d.specific_yield == pytest.approx(4.0)
    assert d.sensor_ratio == pytest.approx(1.0)


def test_missing_hours_are_not_counted_as_zero():
    d = a.daily_metrics(frame(day_rows("2019-06-01", hours_with_energy=6)), SYSTEMS).iloc[0]
    assert d.energy_kwh == pytest.approx(24.0)
    assert d.coverage == pytest.approx(0.6)
    # PR uses only hours where energy and sunlight are both present, so it stays 0.80.
    assert d.performance_ratio == pytest.approx(0.80)


def test_day_without_any_energy_has_no_energy_value():
    d = a.daily_metrics(frame(day_rows("2019-06-01", energy=None)), SYSTEMS).iloc[0]
    assert math.isnan(d.energy_kwh)
    assert d.coverage == 0


def test_expected_uses_the_systems_own_median_pr(normal_days):
    d = scored(*normal_days, day_rows("2019-07-01", energy=2.0))
    assert d["reference_pr"].iloc[0] == pytest.approx(0.80)
    half = d[d.local_date == "2019-07-01"].iloc[0]
    assert half.expected_kwh == pytest.approx(0.80 * DC * 5.0)
    assert half.performance_index == pytest.approx(0.5)
    assert half.expected_basis == "site sensor"


def test_falls_back_to_weather_model_when_site_sensor_missing(normal_days):
    d = scored(*normal_days, day_rows("2019-07-01", poa=None))
    row = d[d.local_date == "2019-07-01"].iloc[0]
    assert row.expected_basis == "weather model"
    assert row.performance_index == pytest.approx(1.0)


def test_low_coverage_day_is_not_scored(normal_days):
    d = scored(*normal_days, day_rows("2019-07-01", hours_with_energy=5))
    row = d[d.local_date == "2019-07-01"].iloc[0]
    assert row.expected_basis == "not scored"
    assert math.isnan(row.performance_index)


def rules_for(flags, day):
    return set(flags[flags.local_date == pd.Timestamp(day)]["rule"])


def test_anomaly_rules_each_fire_on_their_own_defect(normal_days):
    d = scored(
        *normal_days,
        day_rows("2019-07-01", energy=2.0),               # 50% -> critical underperformance
        day_rows("2019-07-02", energy=3.0),               # 75% -> warning underperformance
        day_rows("2019-07-03", energy=5.4),               # 135% -> over-performance
        day_rows("2019-07-04", energy=None),              # no data
        day_rows("2019-07-05", hours_with_energy=5),      # low coverage
        day_rows("2019-07-06", poa=250.0, energy=2.0),    # sensor reads 50% of model, PR still normal
    )
    f = a.flag_anomalies(d)
    assert rules_for(f, "2019-07-01") == {"underperformance"}
    assert f[f.local_date == "2019-07-01"].severity.item() == "critical"
    assert f[f.local_date == "2019-07-02"].severity.item() == "warning"
    assert rules_for(f, "2019-07-03") == {"over_performance"}
    assert rules_for(f, "2019-07-04") == {"no_data"}
    assert rules_for(f, "2019-07-05") == {"low_coverage"}
    assert rules_for(f, "2019-07-06") == {"sensor_mismatch"}
    # Normal days raise nothing.
    assert f[f.local_date < pd.Timestamp("2019-07-01")].empty


def test_reasons_are_plain_english_with_numbers(normal_days):
    f = a.flag_anomalies(scored(*normal_days, day_rows("2019-07-01", energy=2.0)))
    reason = f.reason.item()
    assert "50% of expected" in reason
    assert "20 kWh vs 40 kWh expected" in reason


def test_statistical_drop_catches_a_dip_inside_the_normal_band():
    # 30 days with a little natural variation around index 1.0, then a 0.90 day.
    rng = np.random.default_rng(1)
    days = [day_rows(str(dt.date()), energy=4.0 * (1 + rng.normal(0, 0.005)))
            for dt in pd.date_range("2019-06-01", periods=30)]
    f = a.flag_anomalies(scored(*days, day_rows("2019-07-01", energy=3.6)))
    assert rules_for(f, "2019-07-01") == {"statistical_drop"}


def test_thresholds_change_what_is_flagged(normal_days):
    d = scored(*normal_days, day_rows("2019-07-01", energy=3.0))  # index 0.75
    assert rules_for(a.flag_anomalies(d), "2019-07-01") == {"underperformance"}
    lenient = a.Thresholds(under_index=0.70)
    assert rules_for(a.flag_anomalies(d, lenient), "2019-07-01") == set()


def test_kpis_are_energy_weighted(normal_days):
    d = scored(*normal_days[:2], day_rows("2019-07-01", energy=2.0))
    k = a.kpis(d)
    assert k["energy_mwh"] == pytest.approx(0.1)
    assert k["specific_yield"] == pytest.approx(10.0)
    assert k["performance_ratio"] == pytest.approx(100 / (DC * 15))
    assert k["coverage"] == pytest.approx(1.0)
    assert k["performance_index"] == pytest.approx(100 / 120)


def test_kpis_on_empty_selection_are_nan():
    k = a.kpis(pd.DataFrame())
    assert all(math.isnan(v) for v in k.values())
