"""Simulation de grilles de scenarios pour une annonce."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, fields, replace
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
    ModeLocation,
    RegimeFiscal,
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

    prix_achats: tuple[float, ...] = ()
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
    modes_location: tuple[ModeLocation, ...] = ()
    regimes_fiscaux: tuple[RegimeFiscal, ...] = ()
    comparer_regimes: bool = True


@dataclass(frozen=True, slots=True)
class GrilleResultat:
    """Resultat d'une combinaison de grille."""

    prix_achat: float
    loyer_hc_mensuel: float
    taux_credit: float
    duree_annees: int
    apport: float
    vacance_mois: float
    gestion_agence: bool
    frais_gestion_pct: float
    assurance_emprunteur_annuelle_pct: float
    mode_location: ModeLocation
    regime_fiscal: RegimeFiscal
    resultat: ResultatSimulation
    score: int
    decision: str
    alertes: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Representation plate pour tableau, SQLite ou Streamlit."""

        return {
            "scenario": self.resultat.scenario.nom,
            "mode_location": self.mode_location.value,
            "regime_fiscal": self.regime_fiscal.value,
            "prix_achat": self.prix_achat,
            "cout_total_projet": self.resultat.cout_total_projet,
            "loyer_hc_mensuel": self.loyer_hc_mensuel,
            "taux_credit": self.taux_credit,
            "duree_annees": self.duree_annees,
            "apport": self.apport,
            "vacance_mois": self.vacance_mois,
            "gestion_agence": self.gestion_agence,
            "frais_gestion_pct": self.frais_gestion_pct,
            "assurance_emprunteur_annuelle_pct": self.assurance_emprunteur_annuelle_pct,
            "montant_emprunte": self.resultat.montant_emprunte,
            "mensualite_totale": self.resultat.mensualite_totale,
            "cashflow_mensuel_avant_impot": self.resultat.cashflow_mensuel_avant_impot,
            "cashflow_mensuel_apres_impot": self.resultat.cashflow_mensuel_apres_impot,
            "effort_epargne_mensuel": self.resultat.effort_epargne_mensuel,
            "rendement_brut_pct": self.resultat.rendement_brut_pct,
            "rendement_net_avant_impot_pct": self.resultat.rendement_net_avant_impot_pct,
            "rendement_net_net_pct": self.resultat.rendement_net_net_pct,
            "tri_annuel_approx_pct": self.resultat.tri_annuel_approx_pct,
            "tri_annuel_pct": self.resultat.tri_annuel_pct,
            "tri": self.resultat.tri_annuel_pct,
            "van": self.resultat.van,
            "cash_on_cash_return_pct": self.resultat.cash_on_cash_return_pct,
            "cash_on_cash": self.resultat.cash_on_cash_return_pct,
            "cashflow_cumule_horizon": self.resultat.cashflow_cumule_horizon,
            "impots_total_horizon": self.resultat.impots_total_horizon,
            "impot_plus_value": self.resultat.impot_plus_value,
            "patrimoine_net_horizon": self.resultat.patrimoine_net_horizon,
            "patrimoine_net_sortie": self.resultat.patrimoine_net_sortie,
            "break_even_year": self.resultat.break_even_year,
            "nb_annees_cashflow_negatif": self.resultat.nb_annees_cashflow_negatif,
            "score": self.score,
            "decision": self.decision,
            "alertes": ", ".join(self.alertes),
            "diagnostics": ", ".join(self.diagnostics),
        }


def regimes_compatibles_mode(mode_location: ModeLocation) -> tuple[RegimeFiscal, ...]:
    """Regimes modelises compatibles avec un mode de location."""

    if mode_location == ModeLocation.NUE:
        return (RegimeFiscal.LOCATION_NUE_REEL, RegimeFiscal.MICRO_FONCIER)
    return (RegimeFiscal.LMNP_REEL, RegimeFiscal.MICRO_BIC)


def _prelevements_sociaux_regime(regime: RegimeFiscal) -> float:
    if regime in {RegimeFiscal.LMNP_REEL, RegimeFiscal.MICRO_BIC}:
        return 18.6
    return 17.2


def _modes_a_tester(location: HypothesesLocation, parametres: GrilleParametres) -> tuple[ModeLocation, ...]:
    modes_location = getattr(parametres, "modes_location", ())
    if modes_location:
        return modes_location
    return (location.mode_location,)


def _regimes_a_tester(
    mode_location: ModeLocation,
    fiscalite: Fiscalite,
    parametres: GrilleParametres,
) -> tuple[RegimeFiscal, ...]:
    compatibles = regimes_compatibles_mode(mode_location)
    if not getattr(parametres, "comparer_regimes", True):
        return (fiscalite.regime,) if fiscalite.regime in compatibles else (compatibles[0],)
    regimes_fiscaux = getattr(parametres, "regimes_fiscaux", ())
    if regimes_fiscaux:
        return tuple(regime for regime in regimes_fiscaux if regime in compatibles)
    return compatibles


def _regime_eligible(regime: RegimeFiscal, loyer_hc_mensuel: float, fiscalite: Fiscalite) -> bool:
    revenus_bruts = loyer_hc_mensuel * 12
    if regime == RegimeFiscal.MICRO_BIC:
        return revenus_bruts <= fiscalite.seuil_micro_bic
    if regime == RegimeFiscal.MICRO_FONCIER:
        return revenus_bruts <= fiscalite.seuil_micro_foncier
    return True


def _bien_pour_mode(bien: BienImmobilier, mode_location: ModeLocation, prix_achat: float) -> BienImmobilier:
    if mode_location == ModeLocation.NUE:
        return replace(bien, prix_negocie=prix_achat, meubles_estimes=0.0)
    return replace(bien, prix_negocie=prix_achat)


def _location_pour_mode(location: HypothesesLocation, mode_location: ModeLocation) -> HypothesesLocation:
    if mode_location == ModeLocation.NUE:
        return replace(location, mode_location=ModeLocation.NUE, cfe_annuelle=0.0, comptable_lmnp=0.0)
    return replace(location, mode_location=ModeLocation.MEUBLEE)


def _build_scenario(**kwargs: Any) -> Scenario:
    accepted_fields = {field.name for field in fields(Scenario)}
    return Scenario(**{key: value for key, value in kwargs.items() if key in accepted_fields})


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
    prix_achats = parametres.prix_achats or (bien.prix_achat,)
    loyers = parametres.loyers_hc_mensuels or (location.loyer_hc_mensuel,)
    if getattr(parametres, "appliquer_plafond_loyer", True):
        loyers = borner_loyers_hc(loyers, bien, location)
    modes = _modes_a_tester(location, parametres)
    resultats: list[GrilleResultat] = []

    for prix_achat, loyer, taux, duree, apport, vacance, gestion, mode_location in product(
        prix_achats,
        loyers,
        parametres.taux_credit,
        parametres.durees_annees,
        parametres.apports,
        parametres.vacances_mois,
        gestions,
        modes,
    ):
        frais_options = parametres.frais_gestion_pct if gestion else (0.0,)
        for frais_gestion_pct in frais_options:
            bien_scenario = _bien_pour_mode(bien, mode_location, prix_achat)
            if apport > bien_scenario.cout_total_projet:
                continue

            location_scenario = replace(
                _location_pour_mode(location, mode_location),
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
            for regime in _regimes_a_tester(mode_location, fiscalite, parametres):
                if not _regime_eligible(regime, loyer, fiscalite):
                    continue
                fiscalite_scenario = replace(
                    fiscalite,
                    regime=regime,
                    prelevements_sociaux_pct=_prelevements_sociaux_regime(regime),
                )
                scenario = _build_scenario(
                    nom=(
                        f"h{parametres.horizon_annees}_t{taux:g}_d{duree}"
                        f"_p{int(prix_achat)}_l{int(loyer)}_a{int(apport)}_v{vacance:g}_g{int(gestion)}"
                        f"_fg{frais_gestion_pct:g}_{mode_location.value}_{regime.value}"
                    ),
                    horizon_annees=parametres.horizon_annees,
                    appreciation_annuelle_pct=scenario_base.appreciation_annuelle_pct,
                    loyer_multiplicateur=scenario_base.loyer_multiplicateur,
                    charges_multiplicateur=scenario_base.charges_multiplicateur,
                    vacance_mois_par_an=vacance,
                    frais_revente_pct=scenario_base.frais_revente_pct,
                    taux_actualisation_pct=getattr(scenario_base, "taux_actualisation_pct", 4.0),
                )
                resultat = simuler_bien_sur_horizon(
                    bien=bien_scenario,
                    location=location_scenario,
                    financement=financement,
                    fiscalite=fiscalite_scenario,
                    scenario=scenario,
                )
                diagnostics = diagnostiquer_annonce(bien_scenario, location_scenario)
                score = scorer_bien(resultat, diagnostics=diagnostics)
                resultats.append(
                    GrilleResultat(
                        prix_achat=prix_achat,
                        loyer_hc_mensuel=loyer,
                        taux_credit=taux,
                        duree_annees=duree,
                        apport=apport,
                        vacance_mois=vacance,
                        gestion_agence=gestion,
                        frais_gestion_pct=frais_gestion_pct,
                        assurance_emprunteur_annuelle_pct=parametres.assurance_emprunteur_annuelle_pct,
                        mode_location=mode_location,
                        regime_fiscal=regime,
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
            item.resultat.patrimoine_net_sortie,
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
    fiscalite: Fiscalite | None = None,
    gestion_agence_possible: bool = True,
) -> int:
    """Compte les simulations qui seraient lancees avec la grille donnee."""

    fiscalite = fiscalite or Fiscalite()
    loyers = parametres.loyers_hc_mensuels or (location.loyer_hc_mensuel,)
    if parametres.appliquer_plafond_loyer:
        loyers = borner_loyers_hc(loyers, bien, location)
    gestions = parametres.gestions_agence if gestion_agence_possible else (False,)
    prix_achats = parametres.prix_achats or (bien.prix_achat,)
    modes = _modes_a_tester(location, parametres)
    count = 0
    for prix_achat, loyer, gestion, mode_location in product(
        prix_achats,
        loyers,
        gestions,
        modes,
    ):
        bien_scenario = _bien_pour_mode(bien, mode_location, prix_achat)
        apports_valides = [apport for apport in parametres.apports if apport <= bien_scenario.cout_total_projet]
        frais_options = parametres.frais_gestion_pct if gestion else (0.0,)
        regimes = tuple(
            regime
            for regime in _regimes_a_tester(mode_location, fiscalite, parametres)
            if _regime_eligible(regime, loyer, fiscalite)
        )
        count += (
            len(parametres.taux_credit)
            * len(parametres.durees_annees)
            * len(parametres.vacances_mois)
            * len(apports_valides)
            * len(frais_options)
            * len(regimes)
        )
    return count
