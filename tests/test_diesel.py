import pandas as pd
import pytest

from solar_ops.diesel import DieselAssumptions, displacement, monthly_displacement


def test_displacement_maths():
    out = displacement(1000.0, DieselAssumptions(litres_per_kwh=0.3, price_per_litre=3.0,
                                                 co2_kg_per_litre=2.68))
    assert out["litres"] == pytest.approx(300.0)
    assert out["cost"] == pytest.approx(900.0)
    assert out["co2_tonnes"] == pytest.approx(0.804)


def test_negative_energy_never_creates_savings():
    assert displacement(-50.0, DieselAssumptions())["litres"] == 0


@pytest.mark.parametrize("bad", [
    DieselAssumptions(litres_per_kwh=0.0),
    DieselAssumptions(litres_per_kwh=2.0),
    DieselAssumptions(price_per_litre=-1.0),
    DieselAssumptions(co2_kg_per_litre=0.0),
])
def test_unrealistic_assumptions_are_rejected(bad):
    with pytest.raises(ValueError):
        displacement(100.0, bad)


def test_monthly_totals_match_the_overall_figure():
    daily = pd.DataFrame({
        "system_id": [1, 1, 1, 2],
        "local_date": pd.to_datetime(["2019-01-30", "2019-01-31", "2019-02-01", "2019-02-01"]),
        "energy_kwh": [100.0, None, 50.0, 25.0],
    })
    a = DieselAssumptions(litres_per_kwh=0.25)
    m = monthly_displacement(daily, a)
    assert len(m) == 3
    assert m["litres"].sum() == pytest.approx(displacement(175.0, a)["litres"])
    jan = m[(m.system_id == 1) & (m.month == "2019-01-01")].iloc[0]
    assert jan.energy_kwh == pytest.approx(100.0)  # missing day adds nothing


def test_monthly_on_empty_input():
    m = monthly_displacement(pd.DataFrame(columns=["system_id", "local_date", "energy_kwh"]),
                             DieselAssumptions())
    assert m.empty
