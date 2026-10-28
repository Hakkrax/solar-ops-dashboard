"""Diesel-displacement scenario: what the solar energy would have saved in diesel.

This is a what-if calculation with user-set assumptions. The sites in the data
are grid-connected, so no diesel was actually burned or saved.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Combustion CO2 per litre of diesel. Defra/UK government conversion factors and the
# US EPA both put this at about 2.6-2.7 kg/L; 2.68 is the commonly used value.
DEFAULT_CO2_KG_PER_L = 2.68


@dataclass(frozen=True)
class DieselAssumptions:
    litres_per_kwh: float = 0.30   # generator specific fuel consumption at typical load
    price_per_litre: float = 3.00
    currency: str = "AED"
    co2_kg_per_litre: float = DEFAULT_CO2_KG_PER_L

    def validate(self) -> None:
        if not 0.1 <= self.litres_per_kwh <= 1.0:
            raise ValueError("litres per kWh should be between 0.1 and 1.0")
        if self.price_per_litre < 0:
            raise ValueError("fuel price cannot be negative")
        if self.co2_kg_per_litre <= 0:
            raise ValueError("CO2 factor must be positive")


def displacement(energy_kwh: float, a: DieselAssumptions) -> dict[str, float]:
    """Litres, cost and tonnes of CO2 avoided for a given solar energy."""
    a.validate()
    litres = max(energy_kwh, 0.0) * a.litres_per_kwh
    return {
        "energy_kwh": float(energy_kwh),
        "litres": litres,
        "cost": litres * a.price_per_litre,
        "co2_tonnes": litres * a.co2_kg_per_litre / 1000.0,
    }


def monthly_displacement(daily: pd.DataFrame, a: DieselAssumptions) -> pd.DataFrame:
    """Per system and month: energy and the diesel it would have displaced."""
    a.validate()
    cols = ["month", "system_id", "energy_kwh", "litres", "cost", "co2_tonnes"]
    if daily.empty:
        return pd.DataFrame(columns=cols)
    m = (daily.assign(month=daily["local_date"].dt.to_period("M").dt.to_timestamp())
         .groupby(["month", "system_id"], as_index=False)["energy_kwh"].sum(min_count=1))
    m["energy_kwh"] = m["energy_kwh"].fillna(0.0).clip(lower=0)
    m["litres"] = m["energy_kwh"] * a.litres_per_kwh
    m["cost"] = m["litres"] * a.price_per_litre
    m["co2_tonnes"] = m["litres"] * a.co2_kg_per_litre / 1000.0
    return m[cols]
