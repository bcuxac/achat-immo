"""Générateur de critères de recherche depuis les cibles d'investissement."""

from dataclasses import dataclass, replace
from typing import Dict, Any, List
import copy

from achat_immo.stochastic.models import Strategy
from achat_immo.stochastic.scenario_generator import ScenarioGenerator
from achat_immo.stochastic.monte_carlo import MonteCarloRunner
from achat_immo.analysis.metrics import summarize_monte_carlo_outputs

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

class InverseSolver:
    """Trouve des critères de recherche satisfaisant des objectifs probabilistes."""
    
    def __init__(self, runner: MonteCarloRunner, generator: ScenarioGenerator):
        self.runner = runner
        self.generator = generator
        
    def find_criteria(
        self,
        base_strategy: Strategy,
        target_tri_median: float = 6.0,
        target_tri_p10: float = 3.0,
        min_prob_positive_cashflow: float = 0.5,
        min_coc_median: float = 0.0,
        min_monthly_cashflow_median: float = 0.0,
        n_scenarios_per_eval: int = 100
    ) -> SearchCriteria | None:
        """
        Recherche par quadrillage simple : on fait varier le prix max et le loyer min
        autour de la stratégie de base pour trouver une zone robuste.
        """
        
        # Grille de tests (variations en %)
        price_multipliers = [1.0, 0.95, 0.90, 0.85]
        rent_multipliers = [1.0, 1.05, 1.10]
        
        best_criteria = None
        
        for p_mult in price_multipliers:
            for r_mult in rent_multipliers:
                test_strategy = replace(
                    base_strategy,
                    prix_achat=base_strategy.prix_achat * p_mult,
                    loyer_hc_mensuel=base_strategy.loyer_hc_mensuel * r_mult
                )
                
                outputs = self.runner.run(test_strategy, self.generator, n_scenarios=n_scenarios_per_eval)
                summary = summarize_monte_carlo_outputs(outputs)
                
                if summary.get("tri_median") is None or summary.get("coc_median") is None:
                    continue
                    
                tri_median = summary["tri_median"]
                tri_p10 = summary["tri_p10"]
                prob_cf = summary["probabilite_cashflow_cumule_positif"]
                coc_median = summary["coc_median"]
                cf_mensuel = summary["cashflow_mensuel_minimal_median"]
                
                if (tri_median >= target_tri_median and 
                    tri_p10 >= target_tri_p10 and 
                    prob_cf >= min_prob_positive_cashflow and
                    coc_median >= min_coc_median and
                    cf_mensuel >= min_monthly_cashflow_median):
                    
                    # On a trouvé un ensemble de contraintes acceptables
                    best_criteria = SearchCriteria(
                        city=test_strategy.ville,
                        max_price=test_strategy.prix_achat,
                        max_price_per_m2=test_strategy.prix_achat / test_strategy.surface_m2,
                        min_monthly_rent=test_strategy.loyer_hc_mensuel,
                        max_monthly_charges=test_strategy.charges_copro_annuelles / 12,
                        max_property_tax=test_strategy.taxe_fonciere,
                        max_initial_works=test_strategy.travaux_initiaux,
                        preferred_tax_regime=test_strategy.regime_fiscal.value
                    )
                    return best_criteria
                    
        return None
