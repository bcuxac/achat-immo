"""Simulation annuelle d'un investissement immobilier locatif."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from achat_immo.cashflow import appliquer_scenario_location, rendement_brut, rendement_net
from achat_immo.loan import credit_par_annee, tableau_amortissement
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
from achat_immo.scenario_metrics import (
    tri_annuel_approx,
    valeur_bien,
    van,
)
from achat_immo.scenario_projection import simuler_projection_annuelle


def scenario_central(horizon_annees: int = 20) -> Scenario:
    """Scenario volontairement prudent pour un premier tri."""

    return Scenario(
        nom="central",
        horizon_annees=horizon_annees,
        appreciation_annuelle_pct=0.5,
        loyer_multiplicateur=1.0,
        charges_multiplicateur=1.0,
        vacance_mois_par_an=1.0,
        frais_revente_pct=7.0,
    )


def scenario_pessimiste(horizon_annees: int = 20) -> Scenario:
    return Scenario(
        nom="pessimiste",
        horizon_annees=horizon_annees,
        appreciation_annuelle_pct=-0.5,
        loyer_multiplicateur=0.95,
        charges_multiplicateur=1.15,
        vacance_mois_par_an=2.0,
        frais_revente_pct=8.0,
    )


def scenario_optimiste(horizon_annees: int = 20) -> Scenario:
    return Scenario(
        nom="optimiste",
        horizon_annees=horizon_annees,
        appreciation_annuelle_pct=1.5,
        loyer_multiplicateur=1.05,
        charges_multiplicateur=0.95,
        vacance_mois_par_an=0.5,
        frais_revente_pct=6.0,
    )


def _valeur_bien(bien: BienImmobilier, scenario: Scenario, annee: int) -> float:
    return valeur_bien(bien, scenario, annee)


def _tri_annuel_approx(flux: Sequence[float]) -> float | None:
    return tri_annuel_approx(flux)


def _van(flux: Sequence[float], taux_actualisation_pct: float) -> float:
    return van(flux, taux_actualisation_pct)


def simuler_bien_sur_horizon(
    bien: BienImmobilier,
    location: HypothesesLocation,
    financement: Financement,
    fiscalite: Fiscalite | None = None,
    scenario: Scenario | None = None,
) -> ResultatSimulation:
    """Simule un bien locatif sur l'horizon du scenario."""

    fiscalite = fiscalite or Fiscalite()
    scenario = scenario or scenario_central()
    bien_simule, location_scenario = _preparer_hypotheses(bien, location, fiscalite, scenario)
    (
        montant_emprunte,
        mensualite_credit,
        mensualite_assurance,
        mensualite_totale,
        credit_annuel_rows,
    ) = _preparer_credit(financement, bien_simule.cout_total_projet)
    projection = simuler_projection_annuelle(
        bien=bien_simule,
        location=location_scenario,
        fiscalite=fiscalite,
        scenario=scenario,
        montant_emprunte=montant_emprunte,
        apport=financement.apport,
        credit_annuel=credit_annuel_rows,
    )
    tri = _tri_annuel_approx(projection.flux_tri)
    van_value = _van(projection.flux_tri, scenario.taux_actualisation_pct)

    premiere_annee = projection.projection_annuelle[1]
    rb = rendement_brut(bien_simule, location_scenario)
    rn = rendement_net(
        bien=bien_simule,
        revenus_hc=premiere_annee["revenus_hc"],
        charges={
            "total": premiere_annee["charges"],
        },
    )
    cashflow_mensuel_avant = round(premiere_annee["cashflow_annuel_avant_impot"] / 12, 2)
    cashflow_mensuel_apres = round(premiere_annee["cashflow_annuel_apres_impot"] / 12, 2)
    cash_on_cash_return_pct = (
        round(premiere_annee["cashflow_annuel_apres_impot"] / financement.apport * 100, 2)
        if financement.apport > 0
        else None
    )
    rendement_net_net = _rendement_net_net(bien_simule, premiere_annee)

    return ResultatSimulation(
        bien=bien_simule,
        scenario=scenario,
        cout_total_projet=bien_simule.cout_total_projet,
        montant_emprunte=montant_emprunte,
        mensualite_credit=mensualite_credit,
        mensualite_assurance=mensualite_assurance,
        mensualite_totale=mensualite_totale,
        rendement_brut_pct=rb,
        rendement_net_avant_impot_pct=rn,
        rendement_net_net_pct=rendement_net_net,
        cashflow_mensuel_avant_impot=cashflow_mensuel_avant,
        cashflow_mensuel_apres_impot=cashflow_mensuel_apres,
        effort_epargne_mensuel=max(0.0, -cashflow_mensuel_apres),
        tri_annuel_approx_pct=round(tri * 100, 2) if tri is not None else None,
        patrimoine_net_horizon=projection.projection_annuelle[-1]["patrimoine_net"],
        projection_annuelle=projection.projection_annuelle,
        mode_location=location_scenario.mode_location,
        regime_fiscal=fiscalite.regime,
        tri_annuel_pct=round(tri * 100, 2) if tri is not None else None,
        van=van_value,
        cash_on_cash_return_pct=cash_on_cash_return_pct,
        cashflow_cumule_horizon=projection.cashflow_cumule,
        patrimoine_net_sortie=projection.patrimoine_net_sortie,
        flux_sortie_net=projection.flux_sortie_net,
        impot_plus_value=projection.plus_value.impot_total,
        impots_total_horizon=round(projection.impots_total_horizon + projection.plus_value.impot_total, 2),
        break_even_year=projection.break_even_year,
        nb_annees_cashflow_negatif=projection.nb_annees_cashflow_negatif,
        fiscalite_annuelle=projection.fiscalite_annuelle,
        amortissements_fiscaux=projection.amortissements_fiscaux,
        credit_annuel=credit_annuel_rows,
        plus_value=projection.plus_value.to_dict(),
    )


def _preparer_hypotheses(
    bien: BienImmobilier,
    location: HypothesesLocation,
    fiscalite: Fiscalite,
    scenario: Scenario,
) -> tuple[BienImmobilier, HypothesesLocation]:
    location_scenario = appliquer_scenario_location(location, scenario)
    if fiscalite.regime != RegimeFiscal.LMNP_REEL and location_scenario.comptable_lmnp:
        location_scenario = replace(location_scenario, comptable_lmnp=0.0)
    if location_scenario.mode_location == ModeLocation.NUE and location_scenario.cfe_annuelle:
        location_scenario = replace(location_scenario, cfe_annuelle=0.0)
    if location_scenario.mode_location == ModeLocation.NUE and bien.meubles_estimes:
        bien = replace(bien, meubles_estimes=0.0)
    return bien, location_scenario


def _preparer_credit(
    financement: Financement,
    cout_total_projet: float,
) -> tuple[float, float, float, float, list[dict[str, float]]]:
    montant_emprunte = financement.montant_emprunte(cout_total_projet)
    echeances = tableau_amortissement(
        montant=montant_emprunte,
        taux_annuel_pct=financement.taux_credit_annuel_pct,
        duree_annees=financement.duree_credit_annees,
        assurance_annuelle_pct=financement.assurance_emprunteur_annuelle_pct,
    )
    mensualite_credit = echeances[0].mensualite_credit if echeances else 0.0
    mensualite_assurance = echeances[0].assurance if echeances else 0.0
    mensualite_totale = echeances[0].mensualite_totale if echeances else 0.0
    return (
        montant_emprunte,
        mensualite_credit,
        mensualite_assurance,
        mensualite_totale,
        credit_par_annee(echeances),
    )


def _rendement_net_net(bien: BienImmobilier, premiere_annee: dict[str, Any]) -> float:
    return round(
        (
            premiere_annee["revenus_hc"]
            - premiere_annee["charges"]
            - premiere_annee["impot"]
        )
        / bien.cout_total_projet
        * 100,
        2,
    )
