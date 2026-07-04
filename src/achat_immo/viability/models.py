"""Contrats de donnees d'une cartographie de viabilite."""

from __future__ import annotations

from dataclasses import dataclass, field

from achat_immo.models import ModeLocation, RegimeFiscal
from achat_immo.qualification import ProfitabilityTargets
from achat_immo.stochastic.assumptions import StochasticAssumptions


@dataclass(frozen=True, slots=True)
class ParameterRange:
    """Intervalle ferme utilise par le plan d'experiences."""

    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if self.minimum < 0:
            raise ValueError("La borne minimale doit etre positive ou nulle.")
        if self.maximum <= self.minimum:
            raise ValueError("La borne maximale doit etre superieure a la borne minimale.")


@dataclass(frozen=True, slots=True)
class LocalMarketScope:
    """Perimetre local et ensemble de plafonds legaux a explorer."""

    city: str
    legal_rent_caps_per_m2: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.city.strip():
            raise ValueError("La ville du perimetre est obligatoire.")
        if any(cap <= 0 for cap in self.legal_rent_caps_per_m2):
            raise ValueError("Les plafonds de loyer doivent etre strictement positifs.")
        if tuple(sorted(set(self.legal_rent_caps_per_m2))) != self.legal_rent_caps_per_m2:
            raise ValueError("Les plafonds de loyer doivent etre uniques et tries.")


@dataclass(frozen=True, slots=True)
class InvestorProfile:
    """Parametres stables du financement et de la strategie etudiee."""

    tax_regime: RegimeFiscal = RegimeFiscal.LMNP_REEL
    credit_rate_pct: float = 3.6
    credit_duration_years: int = 20
    borrower_insurance_pct: float = 0.30
    horizon_years: int = 20
    marginal_tax_rate_pct: float = 30.0
    management_enabled: bool = False
    management_fee_pct: float = 7.0
    notary_cost_pct: float = 8.0

    def __post_init__(self) -> None:
        if self.credit_rate_pct < 0 or self.borrower_insurance_pct < 0:
            raise ValueError("Les taux de financement doivent etre positifs ou nuls.")
        if self.credit_duration_years <= 0 or self.horizon_years <= 0:
            raise ValueError("Les durees doivent etre strictement positives.")
        if self.management_fee_pct < 0 or self.notary_cost_pct < 0:
            raise ValueError("Les taux de frais doivent etre positifs ou nuls.")
        if not 0 <= self.marginal_tax_rate_pct <= 100:
            raise ValueError("marginal_tax_rate_pct doit etre compris entre 0 et 100.")

    @property
    def rental_mode(self) -> ModeLocation:
        if self.tax_regime in {RegimeFiscal.LMNP_REEL, RegimeFiscal.MICRO_BIC}:
            return ModeLocation.MEUBLEE
        return ModeLocation.NUE


@dataclass(frozen=True, slots=True)
class ViabilityMapConfig:
    """Configuration versionnable d'un plan d'experiences local."""

    market: LocalMarketScope
    investor: InvestorProfile = field(default_factory=InvestorProfile)
    targets: ProfitabilityTargets = field(default_factory=ProfitabilityTargets)
    risk_assumptions: StochasticAssumptions = field(default_factory=StochasticAssumptions)
    property_count: int = 64
    scenarios_per_property: int = 20
    worker_count: int = 1
    seed: int = 42
    profile_fingerprint: str = ""
    total_project_budget: ParameterRange = field(default_factory=lambda: ParameterRange(80_000.0, 120_000.0))
    equity: ParameterRange = field(default_factory=lambda: ParameterRange(15_000.0, 20_000.0))
    surface_m2: ParameterRange = field(default_factory=lambda: ParameterRange(18.0, 70.0))
    price_per_m2: ParameterRange = field(default_factory=lambda: ParameterRange(1_500.0, 5_500.0))
    rent_per_m2: ParameterRange = field(default_factory=lambda: ParameterRange(10.0, 25.0))
    annual_charges_per_m2: ParameterRange = field(default_factory=lambda: ParameterRange(15.0, 55.0))
    property_tax_per_m2: ParameterRange = field(default_factory=lambda: ParameterRange(10.0, 35.0))
    initial_works_per_m2: ParameterRange = field(default_factory=lambda: ParameterRange(0.0, 700.0))
    version: str = "viability_map_v1"

    def __post_init__(self) -> None:
        if self.property_count <= 0 or self.scenarios_per_property <= 0 or self.worker_count <= 0:
            raise ValueError("Les nombres de biens, de scenarios et de workers doivent etre strictement positifs.")


@dataclass(frozen=True, slots=True)
class HypotheticalProperty:
    """Bien structurel issu du plan d'experiences."""

    sample_id: int
    surface_m2: float
    price: float
    monthly_rent: float
    annual_charges: float
    property_tax: float
    initial_works: float
    equity: float
    total_project_cost: float
    legal_rent_cap_per_m2: float | None

    @property
    def price_per_m2(self) -> float:
        return self.price / self.surface_m2

    @property
    def rent_per_m2(self) -> float:
        return self.monthly_rent / self.surface_m2


@dataclass(frozen=True, slots=True)
class ViabilityPoint:
    """Resultat agrege d'un bien hypothetique sous les scenarios communs."""

    property: HypotheticalProperty
    qualification: str
    reasons: tuple[str, ...]
    tri_median: float | None
    tri_p10: float | None
    cash_on_cash_median: float | None
    prudent_monthly_cashflow: float | None
    positive_cashflow_probability: float | None
    valid_scenarios: int


@dataclass(frozen=True, slots=True)
class ViabilityMap:
    """Carte calculee et ses metadonnees de reproductibilite."""

    config: ViabilityMapConfig
    points: tuple[ViabilityPoint, ...]

    @property
    def viable_count(self) -> int:
        return sum(point.qualification == "robustement_viable" for point in self.points)
