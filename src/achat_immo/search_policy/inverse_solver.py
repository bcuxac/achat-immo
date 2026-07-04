"""Solveur inverse pour déterminer un prix d'achat cible robuste."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from achat_immo.analysis.metrics import summarize_monte_carlo_outputs
from achat_immo.qualification import ProfitabilityTargets, evaluate_monte_carlo_summary
from achat_immo.search_policy.financing import FinancingPolicy, project_cost
from achat_immo.stochastic.models import Strategy, ScenarioInput
from achat_immo.stochastic.monte_carlo import MonteCarloRunner
from achat_immo.stochastic.scenario_generator import ScenarioGenerator


@dataclass(slots=True)
class SearchCriteria:
    city: str
    max_price: float
    max_price_per_m2: float
    min_monthly_rent: float
    max_monthly_charges: float
    max_property_tax: float
    max_initial_works: float
    preferred_tax_regime: str
    project_cost: float = 0.0
    apport: float = 0.0
    loan_amount: float = 0.0
    financing_policy: str = ""
    status: str = "solved"
    iterations: int = 0
    n_scenarios: int = 0
    price_floor: float = 0.0
    price_ceiling: float = 0.0
    summary: dict[str, Any] = field(default_factory=dict)
    diagnostics: list[str] = field(default_factory=list)


class InverseSolver:
    """Trouve le prix d'achat maximal compatible avec des objectifs probabilistes."""

    def __init__(self, runner: MonteCarloRunner, generator: ScenarioGenerator):
        self.runner = runner
        self.generator = generator
        self.last_diagnostics: list[str] = []

    def find_criteria(
        self,
        base_strategy: Strategy,
        target_tri_median: float = 6.0,
        target_tri_p10: float = 3.0,
        min_prob_positive_cashflow: float = 0.5,
        min_coc_median: float = 0.0,
        min_monthly_cashflow_median: float = 0.0,
        n_scenarios_per_eval: int = 100,
        price_floor_multiplier: float = 0.40,
        price_ceiling_multiplier: float = 1.00,
        price_tolerance: float = 500.0,
        max_iterations: int = 24,
        financing_policy: FinancingPolicy | None = None,
    ) -> SearchCriteria | None:
        """Recherche le prix maximum qui passe les seuils sur un même tirage d'aléas.

        Le solveur varie uniquement le prix d'achat. Le loyer, les charges et
        les travaux restent ceux de la stratégie de base afin que le résultat
        soit un vrai prix cible, pas une combinaison prix/loyer plus optimiste.
        Si une politique de financement est fournie, l'apport est recalculé pour
        chaque prix testé.
        """

        self.last_diagnostics = []
        if base_strategy.prix_achat <= 0 or base_strategy.surface_m2 <= 0:
            self.last_diagnostics.append("Strategie invalide : prix ou surface non positif.")
            return None
        if not 0 < price_floor_multiplier <= price_ceiling_multiplier:
            self.last_diagnostics.append("Intervalle de prix invalide pour le solveur.")
            return None
        if n_scenarios_per_eval <= 0:
            self.last_diagnostics.append("Le nombre de scenarios doit etre strictement positif.")
            return None

        scenarios_input = self.generator.sample_many(n_scenarios_per_eval, base_strategy)
        floor_price = base_strategy.prix_achat * price_floor_multiplier
        ceiling_price = base_strategy.prix_achat * price_ceiling_multiplier

        ceiling_summary = self._evaluate_price(base_strategy, ceiling_price, scenarios_input, financing_policy)
        if self._meets_targets(
            ceiling_summary,
            target_tri_median=target_tri_median,
            target_tri_p10=target_tri_p10,
            min_prob_positive_cashflow=min_prob_positive_cashflow,
            min_coc_median=min_coc_median,
            min_monthly_cashflow_median=min_monthly_cashflow_median,
        ):
            return self._criteria(
                strategy=self._strategy_for_price(base_strategy, ceiling_price, financing_policy),
                financing_policy=financing_policy,
                status="already_viable",
                iterations=0,
                n_scenarios=len(scenarios_input),
                price_floor=floor_price,
                price_ceiling=ceiling_price,
                summary=ceiling_summary,
                diagnostics=["Le prix affiche satisfait deja les seuils demandes."],
            )

        floor_summary = self._evaluate_price(base_strategy, floor_price, scenarios_input, financing_policy)
        if not self._meets_targets(
            floor_summary,
            target_tri_median=target_tri_median,
            target_tri_p10=target_tri_p10,
            min_prob_positive_cashflow=min_prob_positive_cashflow,
            min_coc_median=min_coc_median,
            min_monthly_cashflow_median=min_monthly_cashflow_median,
        ):
            self.last_diagnostics = [
                "Aucun prix viable trouve dans l'intervalle teste.",
                f"Prix plancher teste : {floor_price:.0f} EUR.",
            ]
            return None

        low_price = floor_price
        high_price = ceiling_price
        best_summary = floor_summary
        iterations = 0

        while high_price - low_price > price_tolerance and iterations < max_iterations:
            iterations += 1
            mid_price = (low_price + high_price) / 2.0
            mid_summary = self._evaluate_price(base_strategy, mid_price, scenarios_input, financing_policy)
            if self._meets_targets(
                mid_summary,
                target_tri_median=target_tri_median,
                target_tri_p10=target_tri_p10,
                min_prob_positive_cashflow=min_prob_positive_cashflow,
                min_coc_median=min_coc_median,
                min_monthly_cashflow_median=min_monthly_cashflow_median,
            ):
                low_price = mid_price
                best_summary = mid_summary
            else:
                high_price = mid_price

        return self._criteria(
            strategy=self._strategy_for_price(base_strategy, low_price, financing_policy),
            financing_policy=financing_policy,
            status="solved",
            iterations=iterations,
            n_scenarios=len(scenarios_input),
            price_floor=floor_price,
            price_ceiling=ceiling_price,
            summary=best_summary,
            diagnostics=[
                "Prix cible obtenu par dichotomie sur un jeu de scenarios fige.",
                f"Precision prix : +/- {price_tolerance:.0f} EUR.",
            ],
        )

    def _evaluate_price(
        self,
        base_strategy: Strategy,
        price: float,
        scenarios_input: list[ScenarioInput],
        financing_policy: FinancingPolicy | None,
    ) -> dict[str, Any]:
        test_strategy = self._strategy_for_price(base_strategy, price, financing_policy)
        outputs = self.runner.run_inputs(test_strategy, scenarios_input)
        return summarize_monte_carlo_outputs(outputs)

    def _strategy_for_price(
        self,
        base_strategy: Strategy,
        price: float,
        financing_policy: FinancingPolicy | None,
    ) -> Strategy:
        ratio = price / base_strategy.prix_achat if base_strategy.prix_achat > 0 else 1.0
        test_strategy = replace(
            base_strategy,
            prix_achat=price,
            frais_notaire_estimes=base_strategy.frais_notaire_estimes * ratio,
            frais_agence_achat=base_strategy.frais_agence_achat * ratio,
        )
        if financing_policy is None:
            return test_strategy
        return financing_policy.apply(test_strategy)

    def _meets_targets(
        self,
        summary: dict[str, Any],
        *,
        target_tri_median: float,
        target_tri_p10: float,
        min_prob_positive_cashflow: float,
        min_coc_median: float,
        min_monthly_cashflow_median: float,
    ) -> bool:
        targets = ProfitabilityTargets(
            target_tri_median=target_tri_median,
            target_tri_p10=target_tri_p10,
            target_coc=min_coc_median,
            target_cashflow=min_monthly_cashflow_median,
            min_prob_positive_cashflow=min_prob_positive_cashflow,
        )
        return evaluate_monte_carlo_summary(summary, targets).meets_targets

    def _criteria(
        self,
        *,
        strategy: Strategy,
        status: str,
        iterations: int,
        n_scenarios: int,
        price_floor: float,
        price_ceiling: float,
        summary: dict[str, Any],
        diagnostics: list[str],
        financing_policy: FinancingPolicy | None,
    ) -> SearchCriteria:
        cost = project_cost(strategy)
        return SearchCriteria(
            city=strategy.ville,
            max_price=strategy.prix_achat,
            max_price_per_m2=strategy.prix_achat / strategy.surface_m2,
            min_monthly_rent=strategy.loyer_hc_mensuel,
            max_monthly_charges=strategy.charges_copro_annuelles / 12,
            max_property_tax=strategy.taxe_fonciere,
            max_initial_works=strategy.travaux_initiaux,
            preferred_tax_regime=strategy.regime_fiscal.value,
            project_cost=cost,
            apport=strategy.apport,
            loan_amount=max(cost - strategy.apport, 0.0),
            financing_policy=financing_policy.describe() if financing_policy else "apport_fixe",
            status=status,
            iterations=iterations,
            n_scenarios=n_scenarios,
            price_floor=price_floor,
            price_ceiling=price_ceiling,
            summary=summary,
            diagnostics=diagnostics,
        )
