"""Profil investisseur configurable et versionnable."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from achat_immo.models import RegimeFiscal
from achat_immo.qualification import AnalysisTargets, ProfitabilityTargets
from achat_immo.stochastic.assumptions import StochasticAssumptions


PROFILE_SCHEMA_VERSION = 1
DEFAULT_PROFILE_KEY = "principal"


@dataclass(frozen=True, slots=True)
class InvestmentProfile:
    """Choix utilisateur communs a la cartographie et aux analyses detaillees."""

    name: str = "Profil principal"
    target_city: str = "Grenoble"
    total_budget_min: float = 80_000.0
    total_budget_max: float = 120_000.0
    equity_min: float = 15_000.0
    equity_max: float = 20_000.0
    credit_duration_years: int = 15
    credit_rate_pct: float = 3.6
    credit_rate_updated_on: str = ""
    credit_rate_source: str = ""
    borrower_insurance_pct: float = 0.30
    holding_horizon_years: int = 20
    marginal_tax_rate_pct: float = 30.0
    reference_tax_regime: RegimeFiscal = RegimeFiscal.LMNP_REEL
    management_enabled: bool = False
    management_fee_pct: float = 7.0
    notary_cost_pct: float = 8.0
    annual_pno_cost: float = 180.0
    annual_accounting_cost: float = 500.0
    annual_maintenance_reserve: float = 500.0
    annual_cfe_cost: float = 0.0

    map_surface_min_m2: float = 18.0
    map_surface_max_m2: float = 70.0
    map_price_per_m2_min: float = 1_500.0
    map_price_per_m2_max: float = 5_500.0
    map_rent_per_m2_min: float = 10.0
    map_rent_per_m2_max: float = 25.0
    map_nonrecoverable_charges_per_m2_min: float = 15.0
    map_nonrecoverable_charges_per_m2_max: float = 55.0
    map_property_tax_per_m2_min: float = 10.0
    map_property_tax_per_m2_max: float = 35.0
    map_initial_works_per_m2_min: float = 0.0
    map_initial_works_per_m2_max: float = 700.0

    target_tri_median: float = 6.0
    target_tri_p10: float = 3.0
    target_cash_on_cash: float = 0.0
    target_monthly_cashflow: float = 0.0
    min_positive_cashflow_probability: float = 0.5

    detailed_scenario_count: int = 1_000
    solver_scenario_count: int = 300
    map_property_count: int = 512
    map_scenarios_per_property: int = 500
    map_worker_count: int = 1
    map_frontier_share: float = 0.25

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
        if not self.name.strip() or not self.target_city.strip():
            raise ValueError("Le nom du profil et la ville cible sont obligatoires.")
        _validate_range("budget total", self.total_budget_min, self.total_budget_max, strictly_positive=True)
        _validate_range("apport", self.equity_min, self.equity_max)
        if self.equity_max > self.total_budget_max:
            raise ValueError("L'apport maximal ne peut pas depasser le budget total maximal.")
        if self.credit_duration_years <= 0 or self.holding_horizon_years <= 0:
            raise ValueError("Les durees doivent etre strictement positives.")
        for name in (
            "credit_rate_pct",
            "borrower_insurance_pct",
            "marginal_tax_rate_pct",
            "management_fee_pct",
            "notary_cost_pct",
        ):
            value = float(getattr(self, name))
            if not 0 <= value <= 100:
                raise ValueError(f"{name} doit etre compris entre 0 et 100.")
        for name in (
            "annual_pno_cost",
            "annual_accounting_cost",
            "annual_maintenance_reserve",
            "annual_cfe_cost",
        ):
            if float(getattr(self, name)) < 0:
                raise ValueError(f"{name} doit etre positif ou nul.")
        for label, minimum_name, maximum_name in (
            ("surface de carte", "map_surface_min_m2", "map_surface_max_m2"),
            ("prix au m2", "map_price_per_m2_min", "map_price_per_m2_max"),
            ("loyer au m2", "map_rent_per_m2_min", "map_rent_per_m2_max"),
            (
                "charges non recuperables au m2",
                "map_nonrecoverable_charges_per_m2_min",
                "map_nonrecoverable_charges_per_m2_max",
            ),
            ("taxe fonciere au m2", "map_property_tax_per_m2_min", "map_property_tax_per_m2_max"),
            ("travaux initiaux au m2", "map_initial_works_per_m2_min", "map_initial_works_per_m2_max"),
        ):
            minimum = float(getattr(self, minimum_name))
            maximum = float(getattr(self, maximum_name))
            _validate_range(label, minimum, maximum)
            if maximum == minimum:
                raise ValueError(f"Le maximum de {label} doit etre strictement superieur au minimum.")
        if not 0 <= self.min_positive_cashflow_probability <= 1:
            raise ValueError("La probabilite minimale doit etre comprise entre 0 et 1.")
        if not 0 <= self.map_frontier_share <= 1:
            raise ValueError("La part de frontiere doit etre comprise entre 0 et 1.")
        for name in (
            "detailed_scenario_count",
            "solver_scenario_count",
            "map_property_count",
            "map_scenarios_per_property",
            "map_worker_count",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} doit etre strictement positif.")
        self.stochastic_assumptions

    @property
    def profitability_targets(self) -> ProfitabilityTargets:
        return ProfitabilityTargets(
            target_tri_median=self.target_tri_median,
            target_tri_p10=self.target_tri_p10,
            target_coc=self.target_cash_on_cash,
            target_cashflow=self.target_monthly_cashflow,
            min_prob_positive_cashflow=self.min_positive_cashflow_probability,
        )

    @property
    def analysis_targets(self) -> AnalysisTargets:
        return AnalysisTargets(
            target_tri_median=self.target_tri_median,
            target_tri_p10=self.target_tri_p10,
            target_coc=self.target_cash_on_cash,
            target_cashflow=self.target_monthly_cashflow,
            min_prob_positive_cashflow=self.min_positive_cashflow_probability,
            n_scenarios=self.detailed_scenario_count,
            n_solver_scenarios=self.solver_scenario_count,
        )

    @property
    def stochastic_assumptions(self) -> StochasticAssumptions:
        return StochasticAssumptions(
            rent_multiplier_low=self.rent_multiplier_low,
            rent_multiplier_mode=self.rent_multiplier_mode,
            rent_multiplier_high=self.rent_multiplier_high,
            vacancy_mean_months=self.vacancy_mean_months,
            vacancy_std_months=self.vacancy_std_months,
            vacancy_max_months=self.vacancy_max_months,
            annual_rent_growth_mean_pct=self.annual_rent_growth_mean_pct,
            annual_rent_growth_std_pct=self.annual_rent_growth_std_pct,
            annual_rent_growth_min_pct=self.annual_rent_growth_min_pct,
            annual_rent_growth_max_pct=self.annual_rent_growth_max_pct,
            annual_charge_inflation_mean_pct=self.annual_charge_inflation_mean_pct,
            annual_charge_inflation_std_pct=self.annual_charge_inflation_std_pct,
            annual_charge_inflation_min_pct=self.annual_charge_inflation_min_pct,
            annual_charge_inflation_max_pct=self.annual_charge_inflation_max_pct,
            annual_appreciation_mean_pct=self.annual_appreciation_mean_pct,
            annual_appreciation_std_pct=self.annual_appreciation_std_pct,
            annual_appreciation_min_pct=self.annual_appreciation_min_pct,
            annual_appreciation_max_pct=self.annual_appreciation_max_pct,
            resale_cost_mean_pct=self.resale_cost_mean_pct,
            resale_cost_std_pct=self.resale_cost_std_pct,
            resale_cost_min_pct=self.resale_cost_min_pct,
            resale_cost_max_pct=self.resale_cost_max_pct,
            unexpected_works_mode_per_m2=self.unexpected_works_mode_per_m2,
            unexpected_works_max_per_m2=self.unexpected_works_max_per_m2,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> InvestmentProfile:
        defaults = asdict(cls())
        values: dict[str, Any] = json.loads(payload)
        defaults.update({key: value for key, value in values.items() if key in defaults})
        defaults["reference_tax_regime"] = RegimeFiscal(defaults["reference_tax_regime"])
        return cls(**defaults)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @property
    def simulation_fingerprint(self) -> str:
        """Identifie uniquement les entrees qui modifient les resultats de la carte."""

        values = asdict(self)
        for name in (
            "name",
            "credit_rate_updated_on",
            "credit_rate_source",
            "target_tri_median",
            "target_tri_p10",
            "target_cash_on_cash",
            "target_monthly_cashflow",
            "min_positive_cashflow_probability",
            "detailed_scenario_count",
            "solver_scenario_count",
        ):
            values.pop(name, None)
        payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_range(
    name: str,
    minimum: float,
    maximum: float,
    *,
    strictly_positive: bool = False,
    allow_negative: bool = False,
) -> None:
    lower_bound = 0.0
    if not allow_negative and (minimum < lower_bound or (strictly_positive and minimum == lower_bound)):
        qualifier = "strictement positif" if strictly_positive else "positif ou nul"
        raise ValueError(f"Le minimum de {name} doit etre {qualifier}.")
    if maximum < minimum:
        raise ValueError(f"Le maximum de {name} doit etre superieur ou egal au minimum.")
