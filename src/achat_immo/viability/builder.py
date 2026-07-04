"""Construction d'une carte de viabilite a partir du moteur existant."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import partial

from achat_immo.analysis.metrics import summarize_monte_carlo_outputs
from achat_immo.qualification import evaluate_monte_carlo_summary
from achat_immo.stochastic.models import Strategy
from achat_immo.stochastic.monte_carlo import MonteCarloRunner
from achat_immo.viability.models import (
    HypotheticalProperty,
    ViabilityMap,
    ViabilityMapConfig,
    ViabilityPoint,
)
from achat_immo.viability.sampling import sample_hypothetical_properties
from achat_immo.viability.scenarios import (
    MarketScenarioShock,
    generate_common_scenario_shocks,
    scenario_inputs_for_property,
)


def build_viability_map(config: ViabilityMapConfig) -> ViabilityMap:
    """Evalue les biens du plan d'experiences sous des chocs communs."""

    properties = sample_hypothetical_properties(config)
    shocks = generate_common_scenario_shocks(
        config.scenarios_per_property,
        config.seed + 1,
        config.risk_assumptions,
    )
    evaluate = partial(_evaluate_property, config=config, shocks=shocks)
    if config.worker_count == 1:
        points = tuple(evaluate(property_) for property_ in properties)
    else:
        chunksize = max(1, len(properties) // (config.worker_count * 4))
        with ThreadPoolExecutor(max_workers=config.worker_count) as executor:
            points = tuple(executor.map(evaluate, properties, chunksize=chunksize))
    return ViabilityMap(config=config, points=points)


def _evaluate_property(
    property_: HypotheticalProperty,
    *,
    config: ViabilityMapConfig,
    shocks: tuple[MarketScenarioShock, ...],
) -> ViabilityPoint:
    runner = MonteCarloRunner()
    strategy = _strategy_for_property(property_, config)
    outputs = runner.run_inputs(strategy, scenario_inputs_for_property(property_, shocks))
    summary = summarize_monte_carlo_outputs(outputs)
    evaluation = evaluate_monte_carlo_summary(summary, config.targets)
    return ViabilityPoint(
        property=property_,
        qualification="robustement_viable" if evaluation.meets_targets else "non_viable",
        reasons=evaluation.reasons,
        tri_median=_optional_float(summary.get("tri_median")),
        tri_p10=_optional_float(summary.get("tri_p10")),
        cash_on_cash_median=_optional_float(summary.get("coc_median")),
        prudent_monthly_cashflow=_optional_float(summary.get("cashflow_mensuel_minimal_median")),
        positive_cashflow_probability=_optional_float(summary.get("probabilite_cashflow_cumule_positif")),
        valid_scenarios=int(summary.get("nb_scenarios_valides", 0)),
    )


def _strategy_for_property(property_: HypotheticalProperty, config: ViabilityMapConfig) -> Strategy:
    investor = config.investor
    notary_cost = property_.price * investor.notary_cost_pct / 100
    return Strategy(
        ville=config.market.city,
        surface_m2=property_.surface_m2,
        prix_achat=property_.price,
        apport=property_.equity,
        duree_credit_annees=investor.credit_duration_years,
        taux_credit_pct=investor.credit_rate_pct,
        assurance_emprunteur_pct=investor.borrower_insurance_pct,
        regime_fiscal=investor.tax_regime,
        mode_location=investor.rental_mode,
        horizon_annees=investor.horizon_years,
        tmi_pct=investor.marginal_tax_rate_pct,
        loyer_hc_mensuel=property_.monthly_rent,
        charges_copro_annuelles=property_.annual_charges,
        taxe_fonciere=property_.property_tax,
        travaux_initiaux=property_.initial_works,
        frais_notaire_estimes=notary_cost,
        frais_gestion_pct=investor.management_fee_pct,
        gestion_agence_active=investor.management_enabled,
    )


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)
