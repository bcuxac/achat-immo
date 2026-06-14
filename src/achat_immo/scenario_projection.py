"""Projection annuelle detaillee d'un scenario locatif."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from achat_immo.cashflow import charges_annuelles, revenus_annuels_hc, total_charges_annuelles
from achat_immo.models import BienImmobilier, Fiscalite, HypothesesLocation, Scenario
from achat_immo.scenario_metrics import valeur_bien
from achat_immo.taxes import EtatFiscal, calcul_plus_value, resultat_fiscal
from achat_immo.taxes_plus_value import PlusValueResult
from achat_immo.taxes_types import ResultatFiscal


@dataclass(frozen=True, slots=True)
class ProjectionHorizon:
    projection_annuelle: list[dict[str, Any]]
    fiscalite_annuelle: list[dict[str, Any]]
    amortissements_fiscaux: list[dict[str, Any]]
    flux_tri: list[float]
    cashflow_cumule: float
    impots_total_horizon: float
    amortissements_lmnp_deduits_plus_value: float
    break_even_year: int | None
    nb_annees_cashflow_negatif: int
    plus_value: PlusValueResult
    flux_sortie_net: float
    patrimoine_net_sortie: float


def simuler_projection_annuelle(
    *,
    bien: BienImmobilier,
    location: HypothesesLocation,
    fiscalite: Fiscalite,
    scenario: Scenario,
    montant_emprunte: float,
    apport: float,
    credit_annuel: Sequence[dict[str, float]],
) -> ProjectionHorizon:
    """Construit les lignes annuelles et applique la fiscalite de sortie."""

    credit_par_annee_map = {int(row["annee"]): row for row in credit_annuel}
    projection: list[dict[str, Any]] = [_projection_initiale(bien, scenario, montant_emprunte)]
    fiscalite_annuelle: list[dict[str, Any]] = []
    amortissements_fiscaux: list[dict[str, Any]] = []
    cashflow_cumule = 0.0
    impots_total_horizon = 0.0
    amortissements_lmnp_deduits_plus_value = 0.0
    break_even_year: int | None = None
    nb_annees_cashflow_negatif = 0
    flux_tri = [-apport]
    etat_fiscal = EtatFiscal()

    for annee in range(1, scenario.horizon_annees + 1):
        credit_annee = _credit_annee(credit_par_annee_map, annee)
        interets = float(credit_annee["interets"])
        assurance_credit = float(credit_annee["assurance"])
        mensualites_totales = float(credit_annee["mensualite_totale"])
        crd = float(credit_annee["crd_fin"]) if annee in credit_par_annee_map else 0.0
        revenus = revenus_annuels_hc(location, annee)
        charges = charges_annuelles(location, revenus, scenario, annee)
        total_charges = total_charges_annuelles(charges)
        fiscal = resultat_fiscal(
            bien=bien,
            revenus=revenus,
            charges_deductibles=total_charges,
            interets=interets,
            fiscalite=fiscalite,
            annee=annee,
            etat=etat_fiscal,
            mode_location=location.mode_location,
        )
        cashflow_avant_impot = round(revenus - total_charges - mensualites_totales, 2)
        cashflow_apres_impot = round(cashflow_avant_impot - fiscal.impot, 2)
        cashflow_cumule = round(cashflow_cumule + cashflow_apres_impot, 2)
        impots_total_horizon = round(impots_total_horizon + fiscal.impot, 2)
        amortissements_lmnp_deduits_plus_value = round(
            amortissements_lmnp_deduits_plus_value + fiscal.amortissement_deduit_plus_value,
            2,
        )
        if cashflow_apres_impot < 0:
            nb_annees_cashflow_negatif += 1
        if break_even_year is None and cashflow_cumule >= 0:
            break_even_year = annee

        valeur = valeur_bien(bien, scenario, annee)
        valeur_nette_revente = round(valeur * (1 - scenario.frais_revente_pct / 100), 2)
        patrimoine_hors_cashflow = round(valeur_nette_revente - crd, 2)
        patrimoine_net = round(patrimoine_hors_cashflow + cashflow_cumule, 2)

        fiscalite_annuelle.append(_ligne_fiscalite_annuelle(annee, fiscal))
        amortissements_fiscaux.append(_ligne_amortissements_fiscaux(annee, fiscal))
        projection.append(
            _ligne_projection_annuelle(
                annee=annee,
                valeur=valeur,
                valeur_nette_revente=valeur_nette_revente,
                crd=crd,
                revenus=revenus,
                total_charges=total_charges,
                interets=interets,
                assurance_credit=assurance_credit,
                impot=fiscal.impot,
                resultat_fiscal=fiscal.resultat_fiscal,
                amortissement=fiscal.amortissement,
                amortissement_utilise=fiscal.amortissement_utilise,
                amortissement_report_fin=fiscal.amortissement_report_fin,
                deficit_report_fin=fiscal.deficit_report_fin,
                cashflow_avant_impot=cashflow_avant_impot,
                cashflow_apres_impot=cashflow_apres_impot,
                cashflow_cumule=cashflow_cumule,
                patrimoine_hors_cashflow=patrimoine_hors_cashflow,
                patrimoine_net=patrimoine_net,
            )
        )
        flux_tri.append(cashflow_apres_impot)

    plus_value = calcul_plus_value(
        bien=bien,
        fiscalite=fiscalite,
        regime=fiscalite.regime,
        valeur_bien=float(projection[-1]["valeur_bien"]),
        duree_detention_annees=scenario.horizon_annees,
        frais_revente_pct=scenario.frais_revente_pct,
        amortissements_lmnp_deduits_plus_value=amortissements_lmnp_deduits_plus_value,
    )
    flux_sortie_net = round(
        plus_value.prix_cession_net - projection[-1]["capital_restant_du"] - plus_value.impot_total,
        2,
    )
    patrimoine_net_sortie = round(flux_sortie_net + cashflow_cumule, 2)
    projection[-1]["valeur_nette_revente"] = plus_value.prix_cession_net
    projection[-1]["impot_plus_value"] = plus_value.impot_total
    projection[-1]["flux_sortie_tri"] = flux_sortie_net
    projection[-1]["patrimoine_net_hors_cashflow"] = flux_sortie_net
    projection[-1]["patrimoine_net"] = patrimoine_net_sortie
    flux_tri[-1] += flux_sortie_net

    return ProjectionHorizon(
        projection_annuelle=projection,
        fiscalite_annuelle=fiscalite_annuelle,
        amortissements_fiscaux=amortissements_fiscaux,
        flux_tri=flux_tri,
        cashflow_cumule=cashflow_cumule,
        impots_total_horizon=impots_total_horizon,
        amortissements_lmnp_deduits_plus_value=amortissements_lmnp_deduits_plus_value,
        break_even_year=break_even_year,
        nb_annees_cashflow_negatif=nb_annees_cashflow_negatif,
        plus_value=plus_value,
        flux_sortie_net=flux_sortie_net,
        patrimoine_net_sortie=patrimoine_net_sortie,
    )


def _projection_initiale(
    bien: BienImmobilier,
    scenario: Scenario,
    montant_emprunte: float,
) -> dict[str, Any]:
    valeur_nette_revente = round(bien.prix_achat * (1 - scenario.frais_revente_pct / 100), 2)
    patrimoine = round(valeur_nette_revente - montant_emprunte, 2)
    return {
        "annee": 0,
        "valeur_bien": bien.prix_achat,
        "valeur_nette_revente": valeur_nette_revente,
        "capital_restant_du": montant_emprunte,
        "revenus_hc": 0.0,
        "charges": 0.0,
        "interets": 0.0,
        "assurance_credit": 0.0,
        "impot": 0.0,
        "cashflow_annuel_avant_impot": 0.0,
        "cashflow_annuel_apres_impot": 0.0,
        "cashflow_cumule_apres_impot": 0.0,
        "patrimoine_net_hors_cashflow": patrimoine,
        "patrimoine_net": patrimoine,
    }


def _credit_annee(
    credit_par_annee_map: dict[int, dict[str, float]],
    annee: int,
) -> dict[str, float]:
    return credit_par_annee_map.get(
        annee,
        {
            "interets": 0.0,
            "assurance": 0.0,
            "mensualite_totale": 0.0,
            "crd_fin": 0.0,
        },
    )


def _ligne_fiscalite_annuelle(annee: int, fiscal: ResultatFiscal) -> dict[str, Any]:
    return {
        "annee": annee,
        "regime": fiscal.regime.value,
        "revenus": fiscal.revenus,
        "charges_retenues": fiscal.charges_deductibles,
        "interets": fiscal.interets,
        "frais_deductibles_exceptionnels": fiscal.frais_deductibles_exceptionnels,
        "base_avant_amortissement": fiscal.resultat_avant_amortissement,
        "amortissement": fiscal.amortissement,
        "amortissement_utilise": fiscal.amortissement_utilise,
        "amortissement_report_fin": fiscal.amortissement_report_fin,
        "deficit_utilise": fiscal.deficit_utilise,
        "deficit_genere": fiscal.deficit_genere,
        "deficit_report_fin": fiscal.deficit_report_fin,
        "resultat_imposable": fiscal.resultat_fiscal,
        "impot": fiscal.impot,
        "eligible": fiscal.eligible,
        "avertissements": ", ".join(fiscal.avertissements),
    }


def _ligne_amortissements_fiscaux(annee: int, fiscal: ResultatFiscal) -> dict[str, Any]:
    return {
        "annee": annee,
        "regime": fiscal.regime.value,
        "bati": fiscal.amortissement_bati,
        "travaux": fiscal.amortissement_travaux,
        "meubles": fiscal.amortissement_meubles,
        "frais_acquisition": fiscal.amortissement_frais_acquisition,
        "dotation_totale": fiscal.amortissement,
        "amortissement_utilise": fiscal.amortissement_utilise,
        "amortissement_reporte": fiscal.amortissement_report_fin,
        "resultat_imposable": fiscal.resultat_fiscal,
    }


def _ligne_projection_annuelle(
    *,
    annee: int,
    valeur: float,
    valeur_nette_revente: float,
    crd: float,
    revenus: float,
    total_charges: float,
    interets: float,
    assurance_credit: float,
    impot: float,
    resultat_fiscal: float,
    amortissement: float,
    amortissement_utilise: float,
    amortissement_report_fin: float,
    deficit_report_fin: float,
    cashflow_avant_impot: float,
    cashflow_apres_impot: float,
    cashflow_cumule: float,
    patrimoine_hors_cashflow: float,
    patrimoine_net: float,
) -> dict[str, Any]:
    return {
        "annee": annee,
        "valeur_bien": valeur,
        "valeur_nette_revente": valeur_nette_revente,
        "capital_restant_du": crd,
        "revenus_hc": revenus,
        "charges": total_charges,
        "interets": interets,
        "assurance_credit": assurance_credit,
        "impot": impot,
        "resultat_fiscal": resultat_fiscal,
        "amortissement": amortissement,
        "amortissement_utilise": amortissement_utilise,
        "amortissement_report_fin": amortissement_report_fin,
        "deficit_report_fin": deficit_report_fin,
        "cashflow_annuel_avant_impot": cashflow_avant_impot,
        "cashflow_annuel_apres_impot": cashflow_apres_impot,
        "cashflow_cumule_apres_impot": cashflow_cumule,
        "patrimoine_net_hors_cashflow": patrimoine_hors_cashflow,
        "patrimoine_net": patrimoine_net,
    }
