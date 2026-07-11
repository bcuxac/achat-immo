"""Scenarios economiques communs a tous les biens d'une carte."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from achat_immo.stochastic.assumptions import StochasticAssumptions
from achat_immo.stochastic.models import ScenarioInput
from achat_immo.viability.models import HypotheticalProperty


@dataclass(frozen=True, slots=True)
class MarketScenarioShock:
    scenario_id: int
    rent_multiplier: float
    vacancy_months: float
    annual_rent_growth_pct: float
    annual_charge_inflation_pct: float
    unexpected_works_per_m2: float
    annual_appreciation_pct: float
    resale_cost_pct: float


def generate_common_scenario_shocks(
    count: int,
    seed: int,
    assumptions: StochasticAssumptions | None = None,
) -> tuple[MarketScenarioShock, ...]:
    """Produit des chocs reproductibles reutilisables pour chaque bien."""

    if count <= 0:
        raise ValueError("Le nombre de scenarios doit etre strictement positif.")
    assumptions = assumptions or StochasticAssumptions()
    rng = np.random.default_rng(seed)
    shocks: list[MarketScenarioShock] = []
    for scenario_id in range(count):
        shocks.append(
            MarketScenarioShock(
                scenario_id=scenario_id,
                rent_multiplier=float(
                    rng.triangular(
                        assumptions.rent_multiplier_low,
                        assumptions.rent_multiplier_mode,
                        assumptions.rent_multiplier_high,
                    )
                ),
                vacancy_months=float(
                    np.clip(
                        rng.normal(assumptions.vacancy_mean_months, assumptions.vacancy_std_months),
                        0.0,
                        assumptions.vacancy_max_months,
                    )
                ),
                annual_rent_growth_pct=float(
                    np.clip(
                        rng.normal(
                            assumptions.annual_rent_growth_mean_pct,
                            assumptions.annual_rent_growth_std_pct,
                        ),
                        assumptions.annual_rent_growth_min_pct,
                        assumptions.annual_rent_growth_max_pct,
                    )
                ),
                annual_charge_inflation_pct=float(
                    np.clip(
                        rng.normal(
                            assumptions.annual_charge_inflation_mean_pct,
                            assumptions.annual_charge_inflation_std_pct,
                        ),
                        assumptions.annual_charge_inflation_min_pct,
                        assumptions.annual_charge_inflation_max_pct,
                    )
                ),
                unexpected_works_per_m2=float(
                    rng.triangular(
                        0.0,
                        assumptions.unexpected_works_mode_per_m2,
                        assumptions.unexpected_works_max_per_m2,
                    )
                ),
                annual_appreciation_pct=float(
                    np.clip(
                        rng.normal(
                            assumptions.annual_appreciation_mean_pct,
                            assumptions.annual_appreciation_std_pct,
                        ),
                        assumptions.annual_appreciation_min_pct,
                        assumptions.annual_appreciation_max_pct,
                    )
                ),
                resale_cost_pct=float(
                    np.clip(
                        rng.normal(assumptions.resale_cost_mean_pct, assumptions.resale_cost_std_pct),
                        assumptions.resale_cost_min_pct,
                        assumptions.resale_cost_max_pct,
                    )
                ),
            )
        )
    return tuple(shocks)


def scenario_inputs_for_property(
    property_: HypotheticalProperty,
    shocks: tuple[MarketScenarioShock, ...],
) -> list[ScenarioInput]:
    def scenario_rent(shock: MarketScenarioShock) -> float:
        rent = property_.monthly_rent * shock.rent_multiplier
        if property_.legal_rent_cap_per_m2 is not None:
            legal_cap = property_.surface_m2 * property_.legal_rent_cap_per_m2
            return min(rent, legal_cap)
        return rent

    return [
        ScenarioInput(
            scenario_id=shock.scenario_id,
            loyer_hc_mensuel=scenario_rent(shock),
            vacance_mois_par_an=shock.vacancy_months,
            croissance_loyer_annuelle_pct=shock.annual_rent_growth_pct,
            inflation_charges_annuelle_pct=shock.annual_charge_inflation_pct,
            travaux_imprevus_annuels=property_.surface_m2 * shock.unexpected_works_per_m2,
            appreciation_bien_annuelle_pct=shock.annual_appreciation_pct,
            decote_revente_pct=shock.resale_cost_pct,
        )
        for shock in shocks
    ]
