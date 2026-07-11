"""Agrégation et calculs de métriques de risque."""

import numpy as np
from typing import Dict, Any, List
from achat_immo.stochastic.models import ScenarioOutput

def summarize_monte_carlo_outputs(outputs: List[ScenarioOutput]) -> Dict[str, Any]:
    """Agrége les sorties d'une simulation de Monte Carlo."""
    
    valid_outputs = [o for o in outputs if o.is_valid]
    if not valid_outputs:
        return {"error": "Aucun scénario valide."}
        
    # Extract arrays
    tri_array = np.array([o.tri_annuel_pct for o in valid_outputs if o.tri_annuel_pct is not None])
    cashflow_cumule_array = np.array([o.cashflow_cumule_horizon for o in valid_outputs])
    nb_annees_negatif_array = np.array([o.nb_annees_cashflow_negatif for o in valid_outputs])
    coc_array = np.array([o.cash_on_cash_return_pct for o in valid_outputs if o.cash_on_cash_return_pct is not None])
    cf_annuel_minimal_array = np.array([o.cashflow_annuel_minimal for o in valid_outputs])
    cf_premiere_annee_array = np.array([o.cashflow_premiere_annee for o in valid_outputs])
    
    summary = {}
    
    if len(tri_array) > 0:
        summary["tri_moyen"] = float(np.mean(tri_array))
        summary["tri_median"] = float(np.median(tri_array))
        summary["tri_p05"] = float(np.percentile(tri_array, 5))
        summary["tri_p10"] = float(np.percentile(tri_array, 10))
        summary["tri_p90"] = float(np.percentile(tri_array, 90))
        summary["probabilite_tri_negatif"] = float(np.mean(tri_array < 0))
    else:
        summary["tri_moyen"] = None
        summary["tri_median"] = None
        summary["tri_p10"] = None

    if len(coc_array) > 0:
        summary["coc_median"] = float(np.median(coc_array))
        summary["coc_p10"] = float(np.percentile(coc_array, 10))
    else:
        summary["coc_median"] = None
        summary["coc_p10"] = None
        
    summary["cashflow_mensuel_minimal_median"] = float(np.median(cf_annuel_minimal_array)) / 12.0
    summary["cashflow_premiere_annee_mensuel_median"] = (
        float(np.median(cf_premiere_annee_array)) / 12.0
    )
    summary["cashflow_premiere_annee_mensuel_p10"] = (
        float(np.percentile(cf_premiere_annee_array, 10)) / 12.0
    )
    summary["cashflow_cumule_median"] = float(np.median(cashflow_cumule_array))
    summary["cashflow_cumule_p10"] = float(np.percentile(cashflow_cumule_array, 10))
    summary["probabilite_cashflow_premiere_annee_positif"] = float(
        np.mean(cf_premiere_annee_array >= 0)
    )
    summary["probabilite_toutes_annees_cashflow_positif"] = float(
        np.mean(cf_annuel_minimal_array >= 0)
    )
    summary["probabilite_cashflow_cumule_positif"] = float(np.mean(cashflow_cumule_array > 0))
    summary["probabilite_annee_cashflow_negatif"] = float(np.mean(nb_annees_negatif_array > 0))
    
    summary["nb_scenarios_valides"] = len(valid_outputs)
    summary["nb_scenarios_total"] = len(outputs)
    
    return summary
