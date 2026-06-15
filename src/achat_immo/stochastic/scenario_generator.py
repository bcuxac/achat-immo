"""Générateur de scénarios aléatoires."""

import numpy as np
from typing import Dict
from achat_immo.stochastic.models import Strategy, ScenarioInput
from achat_immo.stochastic.distributions import Distribution

class ScenarioGenerator:
    """Génère des scénarios incertains à partir de distributions configurables."""
    
    def __init__(self, config: Dict[str, Distribution], seed: int = 42):
        self.config = config
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        
    def _sample_var(self, name: str, default: float) -> float:
        if name in self.config:
            return self.config[name].sample(self.rng)
        return default
        
    def sample(self, scenario_id: int, strategy: Strategy) -> ScenarioInput:
        """Tire un scénario aléatoire pour une stratégie donnée."""
        
        # Exemple de variables incertaines, on lit depuis la stratégie si pas de distrib specifique
        loyer = self._sample_var("loyer_hc_mensuel", strategy.loyer_hc_mensuel)
        vacance = self._sample_var("vacance_mois_par_an", 1.0)
        croissance_loyer = self._sample_var("croissance_loyer_annuelle_pct", 1.0)
        inflation_charges = self._sample_var("inflation_charges_annuelle_pct", 2.0)
        travaux_imprevus = self._sample_var("travaux_imprevus_annuels", 0.0)
        appreciation = self._sample_var("appreciation_bien_annuelle_pct", 0.5)
        decote = self._sample_var("decote_revente_pct", 7.0)
        
        return ScenarioInput(
            scenario_id=scenario_id,
            loyer_hc_mensuel=loyer,
            vacance_mois_par_an=vacance,
            croissance_loyer_annuelle_pct=croissance_loyer,
            inflation_charges_annuelle_pct=inflation_charges,
            travaux_imprevus_annuels=travaux_imprevus,
            appreciation_bien_annuelle_pct=appreciation,
            decote_revente_pct=decote,
        )
        
    def sample_many(self, n: int, strategy: Strategy) -> list[ScenarioInput]:
        return [self.sample(i, strategy) for i in range(n)]
