"""Module de simulation de masse par methode de Monte-Carlo Profond."""

from __future__ import annotations

import random
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np
import pandas as pd

from achat_immo.fiscal_rules import prelevements_sociaux_par_regime
from achat_immo.models import (
    BienImmobilier,
    Financement,
    Fiscalite,
    HypothesesLocation,
    ModeLocation,
    RegimeFiscal,
    Scenario,
)
from achat_immo.scenarios import simuler_bien_sur_horizon


def generer_contexte_aleatoire(
    surface_min: float = 15.0,
    surface_max: float = 60.0,
    prix_m2_min: float = 1500.0,
    prix_m2_max: float = 6000.0,
    loyer_m2_min: float = 10.0,
    loyer_m2_max: float = 30.0,
    travaux_pct_min: float = 0.0,
    travaux_pct_max: float = 30.0,
) -> dict[str, Any]:
    """Genere une configuration complete (Bien, Financement, Location, Scenario)."""
    
    # 1. Le Bien
    surface = round(random.uniform(surface_min, surface_max), 1)
    prix_m2 = round(random.uniform(prix_m2_min, prix_m2_max), 2)
    prix_affiche = round(surface * prix_m2, 2)
    
    travaux_pct = round(random.uniform(travaux_pct_min, travaux_pct_max) / 100, 3)
    travaux_estimes = round(prix_affiche * travaux_pct, 2)
    
    is_neuf = random.random() < 0.1 # 10% de proba d'etre dans le neuf
    frais_notaire_pct = 0.025 if is_neuf else random.uniform(0.07, 0.085)
    frais_notaire = round(prix_affiche * frais_notaire_pct, 2)
    
    frais_agence_pct = random.uniform(0.0, 0.08)
    frais_agence = round(prix_affiche * frais_agence_pct, 2)
    
    bien = BienImmobilier(
        ville="Simulation",
        surface_m2=surface,
        prix_affiche=prix_affiche,
        frais_agence_achat=frais_agence,
        frais_notaire_estimes=frais_notaire,
        travaux_estimes=travaux_estimes,
        epoque_construction="apres_1990" if is_neuf else "inconnue",
    )
    
    # 2. La Location
    loyer_m2 = round(random.uniform(loyer_m2_min, loyer_m2_max), 2)
    loyer_mensuel = round(surface * loyer_m2, 2)
    
    tf_mois = round(random.uniform(0.5, 2.5), 1)
    taxe_fonciere = round(loyer_mensuel * tf_mois, 2)
    
    copro_m2_an = round(random.uniform(10.0, 40.0), 1)
    copro = round(surface * copro_m2_an, 2)
    
    # Loi normale pour la vacance (Moyenne 1 mois, ecart-type 0.5)
    vacance = max(0.0, round(np.random.normal(1.0, 0.5), 1))
    
    gestion_agence = random.random() < 0.5
    frais_gestion_pct = round(random.uniform(5.0, 10.0), 1) if gestion_agence else 0.0
    
    assurance_pno = round(random.uniform(100.0, 300.0), 2)
    
    # Loi normale pour l'inflation
    inflation_loyer = round(max(0.0, np.random.normal(1.5, 1.0)), 2)
    inflation_charges = round(max(0.0, np.random.normal(2.5, 1.5)), 2)
    
    location = HypothesesLocation(
        loyer_hc_mensuel=loyer_mensuel,
        taxe_fonciere=taxe_fonciere,
        charges_copro_annuelles=copro,
        vacance_mois_par_an=vacance,
        gestion_agence_active=gestion_agence,
        frais_gestion_pct=frais_gestion_pct,
        assurance_pno=assurance_pno,
        evolution_loyer_annuelle_pct=inflation_loyer,
        evolution_charges_annuelles_pct=inflation_charges,
    )
    
    # 3. Le Financement
    # Loi normale pour les taux (moyenne 3.5%, std 0.8)
    taux_credit = round(max(1.0, np.random.normal(3.5, 0.8)), 2)
    duree = random.choice([15, 20, 25])
    apport_pct = round(random.uniform(0.0, 0.20), 3)
    apport = round(bien.cout_total_projet * apport_pct, 2)
    assurance_emprunteur = round(random.uniform(0.1, 0.5), 2)
    
    financement = Financement(
        apport=apport,
        taux_credit_annuel_pct=taux_credit,
        duree_credit_annees=duree,
        assurance_emprunteur_annuelle_pct=assurance_emprunteur,
    )
    
    # 4. Le Scenario Macro
    appreciation = round(np.random.normal(1.0, 1.5), 2)
    scenario = Scenario(
        nom="monte_carlo",
        horizon_annees=10,
        appreciation_annuelle_pct=appreciation,
        vacance_mois_par_an=vacance,
    )
    
    return {
        "bien": bien,
        "location": location,
        "financement": financement,
        "scenario": scenario,
        "meta": {
            "is_neuf": is_neuf,
            "tf_mois": tf_mois,
            "copro_m2_an": copro_m2_an,
            "apport_pct": apport_pct,
            "frais_notaire_pct": frais_notaire_pct,
            "frais_agence_pct": frais_agence_pct,
            "travaux_pct": travaux_pct,
            "prix_m2": prix_m2,
            "loyer_m2": loyer_m2,
        }
    }


def _worker_simuler(contexte: dict[str, Any]) -> list[dict[str, Any]]:
    """Simule le contexte generé sur tous les regimes pertinents."""
    
    bien = contexte["bien"]
    location_base = contexte["location"]
    financement = contexte["financement"]
    scenario = contexte["scenario"]
    meta = contexte["meta"]
    
    fiscalite_base = Fiscalite()
    
    regimes_a_tester = [
        (ModeLocation.MEUBLEE, RegimeFiscal.LMNP_REEL),
        (ModeLocation.MEUBLEE, RegimeFiscal.MICRO_BIC),
        (ModeLocation.NUE, RegimeFiscal.LOCATION_NUE_REEL),
        (ModeLocation.NUE, RegimeFiscal.MICRO_FONCIER),
    ]
    
    rows = []
    
    import dataclasses
    
    for mode, regime in regimes_a_tester:
        meubles = 0.0 if mode == ModeLocation.NUE else 2000.0
        
        bien_sim = dataclasses.replace(
            bien,
            meubles_estimes=meubles,
        )
        
        revenus_bruts = location_base.loyer_hc_mensuel * 12
        if regime == RegimeFiscal.MICRO_BIC and revenus_bruts > fiscalite_base.seuil_micro_bic:
            continue
        if regime == RegimeFiscal.MICRO_FONCIER and revenus_bruts > fiscalite_base.seuil_micro_foncier:
            continue
            
        location_sim = dataclasses.replace(
            location_base,
            mode_location=mode,
            cfe_annuelle=0.0 if mode == ModeLocation.NUE else location_base.cfe_annuelle,
            comptable_lmnp=0.0 if mode == ModeLocation.NUE else location_base.comptable_lmnp,
        )
            
        fiscalite_sim = dataclasses.replace(
            fiscalite_base,
            regime=regime,
            prelevements_sociaux_pct=prelevements_sociaux_par_regime(regime)
        )
        
        try:
            resultat = simuler_bien_sur_horizon(
                bien=bien_sim,
                location=location_sim,
                financement=financement,
                fiscalite=fiscalite_sim,
                scenario=scenario,
            )
            
            row = {
                "regime_fiscal": regime.value,
                "mode_location": mode.value,
                "cout_total_projet": resultat.cout_total_projet,
                "mensualite_totale": resultat.mensualite_totale,
                "cashflow_mensuel_apres_impot": resultat.cashflow_mensuel_apres_impot,
                "effort_epargne_mensuel": resultat.effort_epargne_mensuel,
                "rendement_brut_pct": resultat.rendement_brut_pct,
                "tri_annuel_pct": resultat.tri_annuel_pct if resultat.tri_annuel_pct is not None else 0.0,
                "patrimoine_net_sortie": resultat.patrimoine_net_sortie,
            }
            row.update(meta)
            row["surface_m2"] = bien.surface_m2
            row["taux_credit_pct"] = financement.taux_credit_annuel_pct
            row["duree_credit_annees"] = financement.duree_credit_annees
            row["vacance_mois_par_an"] = location_base.vacance_mois_par_an
            row["gestion_agence_active"] = location_base.gestion_agence_active
            row["evolution_loyer_pct"] = location_base.evolution_loyer_annuelle_pct
            row["evolution_charges_pct"] = location_base.evolution_charges_annuelles_pct
            row["appreciation_bien_pct"] = scenario.appreciation_annuelle_pct
            
            rows.append(row)
        except Exception:
            pass
            
    return rows


def executer_simulation_masse(nb_simulations: int = 10000, workers: int = 4, **kwargs: Any) -> pd.DataFrame:
    """Execute un Monte-Carlo massif et retourne un DataFrame."""
    contextes = [generer_contexte_aleatoire(**kwargs) for _ in range(nb_simulations)]
    
    tous_resultats = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for resultats_bien in executor.map(_worker_simuler, contextes):
            tous_resultats.extend(resultats_bien)
            
    return pd.DataFrame(tous_resultats)
