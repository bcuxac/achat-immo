"""Simulation de grilles de scenarios pour une annonce."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from itertools import product
from typing import Any

import pandas as pd

from achat_immo.comparison import scorer_bien
from achat_immo.city_profiles import borner_loyers_hc
from achat_immo.diagnostics import diagnostiquer_annonce
from achat_immo.models import (
    BienImmobilier,
    Financement,
    Fiscalite,
    HypothesesLocation,
    ResultatSimulation,
    Scenario,
)
from achat_immo.scenarios import scenario_central, simuler_bien_sur_horizon


def generer_plage_float(
    borne_min: float,
    borne_max: float,
    pas: float = 0.01,
    *,
    decimales: int = 2,
) -> tuple[float, ...]:
    """Genere une plage inclusive pour les taux ou pourcentages."""

    if pas <= 0:
        raise ValueError("Le pas doit etre strictement positif.")
    if borne_max < borne_min:
        raise ValueError("La borne maximum doit etre superieure ou egale a la borne minimum.")

    valeurs: list[float] = []
    courant = borne_min
    epsilon = pas / 10
    while courant <= borne_max + epsilon:
        valeur = round(courant, decimales)
        if not valeurs or valeur != valeurs[-1]:
            valeurs.append(valeur)
        courant += pas
    return tuple(valeurs)


def generer_plage_int(borne_min: int, borne_max: int, pas: int = 1) -> tuple[int, ...]:
    """Genere une plage entiere inclusive pour les durees de credit."""

    if pas <= 0:
        raise ValueError("Le pas doit etre strictement positif.")
    if borne_max < borne_min:
        raise ValueError("La borne maximum doit etre superieure ou egale a la borne minimum.")
    return tuple(range(int(borne_min), int(borne_max) + 1, int(pas)))


@dataclass(frozen=True, slots=True)
class GrilleParametres:
    """Hypotheses iterees automatiquement par l'application."""

    loyers_hc_mensuels: tuple[float, ...] = ()
    taux_credit: tuple[float, ...] = (3.3, 3.6, 4.0)
    durees_annees: tuple[int, ...] = (15, 20, 25)
    apports: tuple[float, ...] = (10_000.0, 15_000.0, 20_000.0)
    vacances_mois: tuple[float, ...] = (0.0, 1.0, 2.0)
    gestions_agence: tuple[bool, ...] = (False, True)
    frais_gestion_pct: tuple[float, ...] = (5.0, 7.0, 8.0)
    horizon_annees: int = 10
    assurance_emprunteur_annuelle_pct: float = 0.30
    appliquer_plafond_loyer: bool = True


@dataclass(frozen=True, slots=True)
class GrilleResultat:
    """Resultat d'une combinaison de grille."""

    loyer_hc_mensuel: float
    taux_credit: float
    duree_annees: int
    apport: float
    vacance_mois: float
    gestion_agence: bool
    frais_gestion_pct: float
    resultat: ResultatSimulation
    score: int
    decision: str
    alertes: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Representation plate pour tableau, SQLite ou Streamlit."""

        return {
            "scenario": self.resultat.scenario.nom,
            "loyer_hc_mensuel": self.loyer_hc_mensuel,
            "taux_credit": self.taux_credit,
            "duree_annees": self.duree_annees,
            "apport": self.apport,
            "vacance_mois": self.vacance_mois,
            "gestion_agence": self.gestion_agence,
            "frais_gestion_pct": self.frais_gestion_pct,
            "montant_emprunte": self.resultat.montant_emprunte,
            "mensualite_totale": self.resultat.mensualite_totale,
            "cashflow_mensuel_avant_impot": self.resultat.cashflow_mensuel_avant_impot,
            "cashflow_mensuel_apres_impot": self.resultat.cashflow_mensuel_apres_impot,
            "effort_epargne_mensuel": self.resultat.effort_epargne_mensuel,
            "rendement_brut_pct": self.resultat.rendement_brut_pct,
            "rendement_net_avant_impot_pct": self.resultat.rendement_net_avant_impot_pct,
            "rendement_net_net_pct": self.resultat.rendement_net_net_pct,
            "tri_annuel_approx_pct": self.resultat.tri_annuel_approx_pct,
            "patrimoine_net_horizon": self.resultat.patrimoine_net_horizon,
            "score": self.score,
            "decision": self.decision,
            "alertes": ", ".join(self.alertes),
            "diagnostics": ", ".join(self.diagnostics),
        }


def simuler_grille_annonce(
    bien: BienImmobilier,
    location: HypothesesLocation,
    fiscalite: Fiscalite | None = None,
    parametres: GrilleParametres | None = None,
    scenario_base: Scenario | None = None,
    gestion_agence_possible: bool = True,
) -> list[GrilleResultat]:
    """Simule toutes les combinaisons de taux, durees, apports et scenarios."""

    fiscalite = fiscalite or Fiscalite()
    parametres = parametres or GrilleParametres()
    scenario_base = scenario_base or scenario_central(parametres.horizon_annees)
    gestions = parametres.gestions_agence if gestion_agence_possible else (False,)
    loyers = parametres.loyers_hc_mensuels or (location.loyer_hc_mensuel,)
    if parametres.appliquer_plafond_loyer:
        loyers = borner_loyers_hc(loyers, bien, location)
    resultats: list[GrilleResultat] = []

    for loyer, taux, duree, apport, vacance, gestion in product(
        loyers,
        parametres.taux_credit,
        parametres.durees_annees,
        parametres.apports,
        parametres.vacances_mois,
        gestions,
    ):
        frais_options = parametres.frais_gestion_pct if gestion else (0.0,)
        for frais_gestion_pct in frais_options:
            if apport > bien.cout_total_projet:
                continue

            location_scenario = replace(
                location,
                loyer_hc_mensuel=loyer,
                vacance_mois_par_an=vacance,
                gestion_agence_active=gestion,
                frais_gestion_pct=frais_gestion_pct,
            )
            financement = Financement(
                apport=apport,
                taux_credit_annuel_pct=taux,
                duree_credit_annees=duree,
                assurance_emprunteur_annuelle_pct=parametres.assurance_emprunteur_annuelle_pct,
            )
            scenario = Scenario(
                nom=(
                    f"h{parametres.horizon_annees}_t{taux:g}_d{duree}"
                    f"_l{int(loyer)}_a{int(apport)}_v{vacance:g}_g{int(gestion)}"
                    f"_fg{frais_gestion_pct:g}"
                ),
                horizon_annees=parametres.horizon_annees,
                appreciation_annuelle_pct=scenario_base.appreciation_annuelle_pct,
                loyer_multiplicateur=scenario_base.loyer_multiplicateur,
                charges_multiplicateur=scenario_base.charges_multiplicateur,
                vacance_mois_par_an=vacance,
                frais_revente_pct=scenario_base.frais_revente_pct,
            )
            resultat = simuler_bien_sur_horizon(
                bien=bien,
                location=location_scenario,
                financement=financement,
                fiscalite=fiscalite,
                scenario=scenario,
            )
            diagnostics = diagnostiquer_annonce(bien, location_scenario)
            score = scorer_bien(resultat, diagnostics=diagnostics)
            resultats.append(
                GrilleResultat(
                    loyer_hc_mensuel=loyer,
                    taux_credit=taux,
                    duree_annees=duree,
                    apport=apport,
                    vacance_mois=vacance,
                    gestion_agence=gestion,
                    frais_gestion_pct=frais_gestion_pct,
                    resultat=resultat,
                    score=int(score["score"]),
                    decision=str(score["decision"]),
                    alertes=tuple(str(alerte) for alerte in score["alertes"]),
                    diagnostics=tuple(diagnostic.code for diagnostic in diagnostics),
                )
            )

    return sorted(
        resultats,
        key=lambda item: (
            item.score,
            item.resultat.cashflow_mensuel_apres_impot,
            item.resultat.patrimoine_net_horizon,
        ),
        reverse=True,
    )


def grille_to_dataframe(resultats: Iterable[GrilleResultat]) -> pd.DataFrame:
    return pd.DataFrame([resultat.to_dict() for resultat in resultats])


def compter_scenarios_grille(
    bien: BienImmobilier,
    location: HypothesesLocation,
    parametres: GrilleParametres,
    *,
    gestion_agence_possible: bool = True,
) -> int:
    """Compte les simulations qui seraient lancees avec la grille donnee."""

    loyers = parametres.loyers_hc_mensuels or (location.loyer_hc_mensuel,)
    if parametres.appliquer_plafond_loyer:
        loyers = borner_loyers_hc(loyers, bien, location)
    gestions = parametres.gestions_agence if gestion_agence_possible else (False,)
    apports_valides = tuple(apport for apport in parametres.apports if apport <= bien.cout_total_projet)
    scenarios_gestion = sum(
        len(parametres.frais_gestion_pct) if gestion else 1
        for gestion in gestions
    )
    return (
        len(loyers)
        * len(parametres.taux_credit)
        * len(parametres.durees_annees)
        * len(apports_valides)
        * len(parametres.vacances_mois)
        * scenarios_gestion
    )
