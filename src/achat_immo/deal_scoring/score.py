"""Fonction de scoring d'attractivité des annonces immobilières."""

from typing import Dict, Any
from achat_immo.deal_scoring.candidate_property import CandidateProperty

def compute_deal_score(candidate: CandidateProperty, mc_summary: Dict[str, Any]) -> float:
    """Calcule un score global combinant métriques probabilistes et qualité de la donnée."""
    
    if "error" in mc_summary or mc_summary.get("tri_median") is None:
        return 0.0
        
    tri_median = mc_summary["tri_median"]
    tri_p10 = mc_summary["tri_p10"]
    prob_cf_positif = mc_summary["probabilite_cashflow_cumule_positif"]
    
    # Poids de base des métriques financières
    score = (
        100.0 * tri_median 
        + 80.0 * tri_p10 
        + 20.0 * prob_cf_positif
    )
    
    # Pénalités de qualité de donnée
    missing_data_penalty = len(candidate.donnees_manquantes) * 5.0
    score -= missing_data_penalty
    
    # Pénalité DPE
    dpe_penalties = {
        'A': 0, 'B': 0, 'C': 0, 'D': 0,
        'E': 10, 'F': 25, 'G': 50
    }
    score -= dpe_penalties.get(candidate.dpe.upper(), 30) # Inconnu = pénalité moyenne
    
    # Pénalité Red flags
    score -= len(candidate.red_flags) * 15.0
    
    return max(0.0, score)
