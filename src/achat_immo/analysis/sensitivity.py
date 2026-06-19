"""Analyse de sensibilité par corrélation de Spearman."""

import numpy as np
from scipy.stats import spearmanr
from typing import List, Tuple
from achat_immo.stochastic.models import ScenarioInput, ScenarioOutput

def analyze_sensitivity(inputs: List[ScenarioInput], outputs: List[ScenarioOutput], target_metric: str = "tri_annuel_pct") -> List[Tuple[str, float]]:
    """Calcule la corrélation de Spearman entre les variables d'entrée et une métrique cible."""
    
    # Filtrer sur les valides
    valid_pairs = [(i, o) for i, o in zip(inputs, outputs) if o.is_valid and getattr(o, target_metric) is not None]
    if not valid_pairs:
        return []
        
    valid_inputs, valid_outputs = zip(*valid_pairs)
    
    target_values = np.array([getattr(o, target_metric) for o in valid_outputs])
    
    input_features = [
        "loyer_hc_mensuel",
        "vacance_mois_par_an",
        "croissance_loyer_annuelle_pct",
        "inflation_charges_annuelle_pct",
        "travaux_imprevus_annuels",
        "appreciation_bien_annuelle_pct",
        "decote_revente_pct"
    ]
    
    results = []
    for feature in input_features:
        feature_values = np.array([getattr(i, feature) for i in valid_inputs])
        # Verifier s'il y a de la variance
        if np.std(feature_values) == 0:
            corr = 0.0
        else:
            corr, _ = spearmanr(feature_values, target_values)
            if np.isnan(corr):
                corr = 0.0
        results.append((feature, float(corr)))
        
    # Trier par valeur absolue d'impact
    results.sort(key=lambda x: abs(x[1]), reverse=True)
    return results
