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
            annual_pno_cost=profile.annual_pno_cost,
            annual_accounting_cost=profile.annual_accounting_cost,
            annual_maintenance_reserve=profile.annual_maintenance_reserve,
            annual_cfe_cost=profile.annual_cfe_cost,
        ),
        targets=profile.profitability_targets,
        risk_assumptions=profile.stochastic_assumptions,
        property_count=profile.map_property_count if property_count is None else property_count,
        scenarios_per_property=(
            profile.map_scenarios_per_property if scenarios_per_property is None else scenarios_per_property
        ),
        worker_count=profile.map_worker_count if worker_count is None else worker_count,
        frontier_share=profile.map_frontier_share,
        robust_neighbor_ratio=profile.prefilter_robust_neighbor_ratio,
        potential_neighbor_ratio=profile.prefilter_potential_neighbor_ratio,
        seed=seed,
        profile_fingerprint=profile.fingerprint,
        total_project_budget=ParameterRange(profile.total_budget_min, profile.total_budget_max),
        equity=ParameterRange(profile.equity_min, profile.equity_max),
        surface_m2=ParameterRange(profile.map_surface_min_m2, profile.map_surface_max_m2),
        price_per_m2=ParameterRange(profile.map_price_per_m2_min, profile.map_price_per_m2_max),
        rent_per_m2=ParameterRange(profile.map_rent_per_m2_min, profile.map_rent_per_m2_max),
        annual_nonrecoverable_charges_per_m2=ParameterRange(
            profile.map_nonrecoverable_charges_per_m2_min,
            profile.map_nonrecoverable_charges_per_m2_max,
        ),
        property_tax_per_m2=ParameterRange(
            profile.map_property_tax_per_m2_min,
            profile.map_property_tax_per_m2_max,
        ),
        initial_works_per_m2=ParameterRange(
            profile.map_initial_works_per_m2_min,
            profile.map_initial_works_per_m2_max,
        ),
    )
