"""Hypotheses economiques partagees par les simulations probabilistes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StochasticAssumptions:
    rent_multiplier_low: float = 0.90
    rent_multiplier_mode: float = 1.00
    rent_multiplier_high: float = 1.05
    vacancy_mean_months: float = 1.2
    vacancy_std_months: float = 0.8
    vacancy_max_months: float = 6.0
    annual_rent_growth_mean_pct: float = 1.0
    annual_rent_growth_std_pct: float = 0.6
    annual_rent_growth_min_pct: float = 0.0
    annual_rent_growth_max_pct: float = 3.0
    annual_charge_inflation_mean_pct: float = 2.5
    annual_charge_inflation_std_pct: float = 1.0
    annual_charge_inflation_min_pct: float = 0.0
    annual_charge_inflation_max_pct: float = 6.0
    annual_appreciation_mean_pct: float = 0.5
    annual_appreciation_std_pct: float = 1.4
    annual_appreciation_min_pct: float = -3.0
    annual_appreciation_max_pct: float = 4.0
    resale_cost_mean_pct: float = 7.0
    resale_cost_std_pct: float = 1.0
    resale_cost_min_pct: float = 5.0
    resale_cost_max_pct: float = 10.0
    unexpected_works_mode_per_m2: float = 8.0
    unexpected_works_max_per_m2: float = 45.0

    def __post_init__(self) -> None:
        if not self.rent_multiplier_low <= self.rent_multiplier_mode <= self.rent_multiplier_high:
            raise ValueError("Les multiplicateurs de loyer doivent etre ordonnes.")
        if not 0 <= self.vacancy_mean_months <= self.vacancy_max_months <= 12:
            raise ValueError("Les hypotheses de vacance doivent etre comprises entre 0 et 12 mois.")
        for name in (
            "vacancy_std_months",
            "annual_rent_growth_std_pct",
            "annual_charge_inflation_std_pct",
            "annual_appreciation_std_pct",
            "resale_cost_std_pct",
            "unexpected_works_mode_per_m2",
            "unexpected_works_max_per_m2",
        ):
            if float(getattr(self, name)) < 0:
                raise ValueError(f"{name} doit etre positif ou nul.")
        _ordered(
            "croissance des loyers",
            self.annual_rent_growth_min_pct,
            self.annual_rent_growth_mean_pct,
            self.annual_rent_growth_max_pct,
        )
        _ordered(
            "inflation des charges",
            self.annual_charge_inflation_min_pct,
            self.annual_charge_inflation_mean_pct,
            self.annual_charge_inflation_max_pct,
        )
        _ordered(
            "appreciation",
            self.annual_appreciation_min_pct,
            self.annual_appreciation_mean_pct,
            self.annual_appreciation_max_pct,
        )
        _ordered(
            "frais de revente",
            self.resale_cost_min_pct,
            self.resale_cost_mean_pct,
            self.resale_cost_max_pct,
        )
        if self.unexpected_works_mode_per_m2 > self.unexpected_works_max_per_m2:
            raise ValueError("Le mode des travaux imprevus ne peut pas depasser leur maximum.")


def _ordered(name: str, minimum: float, central: float, maximum: float) -> None:
    if not minimum <= central <= maximum:
        raise ValueError(f"Les hypotheses de {name} doivent etre ordonnees.")
