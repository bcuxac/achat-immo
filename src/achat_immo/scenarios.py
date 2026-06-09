"""Simulation annuelle d'un investissement immobilier locatif."""

from __future__ import annotations

from collections.abc import Sequence

from achat_immo.cashflow import (
    appliquer_scenario_location,
    charges_annuelles,
    rendement_brut,
    rendement_net,
    revenus_annuels_hc,
    total_charges_annuelles,
)
from achat_immo.loan import tableau_amortissement
from achat_immo.models import (
    BienImmobilier,
    Financement,
    Fiscalite,
    HypothesesLocation,
    ResultatSimulation,
    Scenario,
)
from achat_immo.taxes import resultat_fiscal


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
    valeur = bien.prix_achat * (1 + scenario.appreciation_annuelle_pct / 100) ** annee
    return round(valeur, 2)


def _tri_annuel_approx(flux: Sequence[float]) -> float | None:
    """TRI annuel par recherche dichotomique, retourne un taux decimal."""

    def npv(taux: float) -> float:
        return sum(flux_t / (1 + taux) ** index for index, flux_t in enumerate(flux))

    bas = -0.95
    haut = 1.0
    npv_bas = npv(bas)
    npv_haut = npv(haut)
    if npv_bas == 0:
        return bas
    if npv_haut == 0:
        return haut
    if npv_bas * npv_haut > 0:
        return None

    for _ in range(100):
        milieu = (bas + haut) / 2
        npv_milieu = npv(milieu)
        if abs(npv_milieu) < 1e-7:
            return milieu
        if npv_bas * npv_milieu <= 0:
            haut = milieu
            npv_haut = npv_milieu
        else:
            bas = milieu
            npv_bas = npv_milieu
        _ = npv_haut
    return (bas + haut) / 2


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
    location_scenario = appliquer_scenario_location(location, scenario)
    montant_emprunte = financement.montant_emprunte(bien.cout_total_projet)
    echeances = tableau_amortissement(
        montant=montant_emprunte,
        taux_annuel_pct=financement.taux_credit_annuel_pct,
        duree_annees=financement.duree_credit_annees,
        assurance_annuelle_pct=financement.assurance_emprunteur_annuelle_pct,
    )
    mensualite_credit = echeances[0].mensualite_credit if echeances else 0.0
    mensualite_assurance = echeances[0].assurance if echeances else 0.0
    mensualite_totale = echeances[0].mensualite_totale if echeances else 0.0

    projection: list[dict[str, float]] = []
    cashflow_cumule = 0.0
    flux_tri = [-financement.apport]

    projection.append(
        {
            "annee": 0,
            "valeur_bien": bien.prix_achat,
            "valeur_nette_revente": round(bien.prix_achat * (1 - scenario.frais_revente_pct / 100), 2),
            "capital_restant_du": montant_emprunte,
            "revenus_hc": 0.0,
            "charges": 0.0,
            "interets": 0.0,
            "assurance_credit": 0.0,
            "impot": 0.0,
            "cashflow_annuel_avant_impot": 0.0,
            "cashflow_annuel_apres_impot": 0.0,
            "cashflow_cumule_apres_impot": 0.0,
            "patrimoine_net_hors_cashflow": round(
                bien.prix_achat * (1 - scenario.frais_revente_pct / 100) - montant_emprunte,
                2,
            ),
            "patrimoine_net": round(
                bien.prix_achat * (1 - scenario.frais_revente_pct / 100) - montant_emprunte,
                2,
            ),
        }
    )

    for annee in range(1, scenario.horizon_annees + 1):
        echeances_annee = [e for e in echeances if e.annee == annee]
        interets = round(sum(e.interets for e in echeances_annee), 2)
        assurance_credit = round(sum(e.assurance for e in echeances_annee), 2)
        mensualites_totales = round(sum(e.mensualite_totale for e in echeances_annee), 2)
        crd = (
            echeances[min(annee * 12, len(echeances)) - 1].crd_apres
            if echeances and annee * 12 <= len(echeances)
            else 0.0
        )
        revenus = revenus_annuels_hc(location_scenario, annee)
        charges = charges_annuelles(location_scenario, revenus, scenario)
        total_charges = total_charges_annuelles(charges)
        fiscal = resultat_fiscal(
            bien=bien,
            revenus=revenus,
            charges_deductibles=total_charges,
            interets=interets,
            fiscalite=fiscalite,
        )
        cashflow_avant_impot = round(revenus - total_charges - mensualites_totales, 2)
        cashflow_apres_impot = round(revenus - total_charges - mensualites_totales - fiscal.impot, 2)
        cashflow_cumule = round(cashflow_cumule + cashflow_apres_impot, 2)
        valeur = _valeur_bien(bien, scenario, annee)
        valeur_nette_revente = round(valeur * (1 - scenario.frais_revente_pct / 100), 2)
        patrimoine_hors_cashflow = round(valeur_nette_revente - crd, 2)
        patrimoine_net = round(patrimoine_hors_cashflow + cashflow_cumule, 2)

        projection.append(
            {
                "annee": annee,
                "valeur_bien": valeur,
                "valeur_nette_revente": valeur_nette_revente,
                "capital_restant_du": crd,
                "revenus_hc": revenus,
                "charges": total_charges,
                "interets": interets,
                "assurance_credit": assurance_credit,
                "impot": fiscal.impot,
                "resultat_fiscal": fiscal.resultat_fiscal,
                "amortissement": fiscal.amortissement,
                "cashflow_annuel_avant_impot": cashflow_avant_impot,
                "cashflow_annuel_apres_impot": cashflow_apres_impot,
                "cashflow_cumule_apres_impot": cashflow_cumule,
                "patrimoine_net_hors_cashflow": patrimoine_hors_cashflow,
                "patrimoine_net": patrimoine_net,
            }
        )
        flux_tri.append(cashflow_apres_impot)

    projection[-1]["flux_sortie_tri"] = projection[-1]["patrimoine_net_hors_cashflow"]
    flux_tri[-1] += projection[-1]["patrimoine_net_hors_cashflow"]
    tri = _tri_annuel_approx(flux_tri)

    premiere_annee = projection[1]
    rb = rendement_brut(bien, location_scenario)
    rn = rendement_net(
        bien=bien,
        revenus_hc=premiere_annee["revenus_hc"],
        charges={
            "total": premiere_annee["charges"],
        },
    )
    cashflow_mensuel_avant = round(premiere_annee["cashflow_annuel_avant_impot"] / 12, 2)
    cashflow_mensuel_apres = round(premiere_annee["cashflow_annuel_apres_impot"] / 12, 2)
    rendement_net_net = round(
        (
            premiere_annee["revenus_hc"]
            - premiere_annee["charges"]
            - premiere_annee["impot"]
        )
        / bien.cout_total_projet
        * 100,
        2,
    )

    return ResultatSimulation(
        bien=bien,
        scenario=scenario,
        cout_total_projet=bien.cout_total_projet,
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
        patrimoine_net_horizon=projection[-1]["patrimoine_net"],
        projection_annuelle=projection,
    )
