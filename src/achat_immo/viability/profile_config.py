"""Conversion du profil utilisateur en configuration de cartographie."""

from __future__ import annotations

from achat_immo.investment_profile import InvestmentProfile
from achat_immo.viability.models import (
    InvestorProfile,
    LocalMarketScope,
    ParameterRange,
    ViabilityMapConfig,
)


def viability_config_from_profile(
    profile: InvestmentProfile,
    market: LocalMarketScope,
    *,
    seed: int = 42,
    property_count: int | None = None,
    scenarios_per_property: int | None = None,
    worker_count: int | None = None,
) -> ViabilityMapConfig:
    """Construit une configuration sans recopier les choix utilisateur."""

    if market.city != profile.target_city:
        raise ValueError(
            f"Le perimetre {market.city} ne correspond pas a la ville active {profile.target_city}."
        )
    return ViabilityMapConfig(
        market=market,
        investor=InvestorProfile(
            tax_regime=profile.reference_tax_regime,
            credit_rate_pct=profile.credit_rate_pct,
            credit_duration_years=profile.credit_duration_years,
            borrower_insurance_pct=profile.borrower_insurance_pct,
            horizon_years=profile.holding_horizon_years,
            marginal_tax_rate_pct=profile.marginal_tax_rate_pct,
            management_enabled=profile.management_enabled,
            management_fee_pct=profile.management_fee_pct,
            notary_cost_pct=profile.notary_cost_pct,
        ),
        targets=profile.profitability_targets,
        risk_assumptions=profile.stochastic_assumptions,
        property_count=profile.map_property_count if property_count is None else property_count,
        scenarios_per_property=(
            profile.map_scenarios_per_property if scenarios_per_property is None else scenarios_per_property
        ),
        worker_count=profile.map_worker_count if worker_count is None else worker_count,
        seed=seed,
        profile_fingerprint=profile.fingerprint,
        total_project_budget=ParameterRange(profile.total_budget_min, profile.total_budget_max),
        equity=ParameterRange(profile.equity_min, profile.equity_max),
    )
