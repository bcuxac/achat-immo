"""Simulation annuelle d'un investissement immobilier locatif."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from achat_immo.cashflow import (
    appliquer_scenario_location,
    charges_annuelles,
    rendement_brut,
    rendement_net,
    revenus_annuels_hc,
    total_charges_annuelles,
)
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
from achat_immo.taxes import EtatFiscal, calcul_plus_value, resultat_fiscal


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


def _van(flux: Sequence[float], taux_actualisation_pct: float) -> float:
    taux = taux_actualisation_pct / 100
    return round(sum(flux_t / (1 + taux) ** index for index, flux_t in enumerate(flux)), 2)


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
    if fiscalite.regime != RegimeFiscal.LMNP_REEL and location_scenario.comptable_lmnp:
        location_scenario = replace(location_scenario, comptable_lmnp=0.0)
    if location_scenario.mode_location == ModeLocation.NUE and location_scenario.cfe_annuelle:
        location_scenario = replace(location_scenario, cfe_annuelle=0.0)
    if location_scenario.mode_location == ModeLocation.NUE and bien.meubles_estimes:
        bien = replace(bien, meubles_estimes=0.0)
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
    credit_annuel = credit_par_annee(echeances)
    credit_par_annee_map = {row["annee"]: row for row in credit_annuel}

    projection: list[dict[str, float]] = []
    fiscalite_annuelle: list[dict[str, float | str | bool]] = []
    amortissements_fiscaux: list[dict[str, float | str]] = []
    cashflow_cumule = 0.0
    impots_total_horizon = 0.0
    amortissements_lmnp_deduits_plus_value = 0.0
    break_even_year: int | None = None
    nb_annees_cashflow_negatif = 0
    flux_tri = [-financement.apport]
    etat_fiscal = EtatFiscal()

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
        credit_annee = credit_par_annee_map.get(
            annee,
            {
                "interets": 0.0,
                "assurance": 0.0,
                "mensualite_totale": 0.0,
                "crd_fin": 0.0,
            },
        )
        interets = float(credit_annee["interets"])
        assurance_credit = float(credit_annee["assurance"])
        mensualites_totales = float(credit_annee["mensualite_totale"])
        crd = (
            float(credit_annee["crd_fin"])
            if annee in credit_par_annee_map
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
            annee=annee,
            etat=etat_fiscal,
            mode_location=location_scenario.mode_location,
        )
        cashflow_avant_impot = round(revenus - total_charges - mensualites_totales, 2)
        cashflow_apres_impot = round(revenus - total_charges - mensualites_totales - fiscal.impot, 2)
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
        valeur = _valeur_bien(bien, scenario, annee)
        valeur_nette_revente = round(valeur * (1 - scenario.frais_revente_pct / 100), 2)
        patrimoine_hors_cashflow = round(valeur_nette_revente - crd, 2)
        patrimoine_net = round(patrimoine_hors_cashflow + cashflow_cumule, 2)
        fiscalite_annuelle.append(
            {
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
        )
        amortissements_fiscaux.append(
            {
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
        )

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
                "amortissement_utilise": fiscal.amortissement_utilise,
                "amortissement_report_fin": fiscal.amortissement_report_fin,
                "deficit_report_fin": fiscal.deficit_report_fin,
                "cashflow_annuel_avant_impot": cashflow_avant_impot,
                "cashflow_annuel_apres_impot": cashflow_apres_impot,
                "cashflow_cumule_apres_impot": cashflow_cumule,
                "patrimoine_net_hors_cashflow": patrimoine_hors_cashflow,
                "patrimoine_net": patrimoine_net,
            }
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
    flux_sortie_net = round(plus_value.prix_cession_net - projection[-1]["capital_restant_du"] - plus_value.impot_total, 2)
    patrimoine_net_sortie = round(flux_sortie_net + cashflow_cumule, 2)
    projection[-1]["valeur_nette_revente"] = plus_value.prix_cession_net
    projection[-1]["impot_plus_value"] = plus_value.impot_total
    projection[-1]["flux_sortie_tri"] = flux_sortie_net
    projection[-1]["patrimoine_net_hors_cashflow"] = flux_sortie_net
    projection[-1]["patrimoine_net"] = patrimoine_net_sortie
    flux_tri[-1] += flux_sortie_net
    tri = _tri_annuel_approx(flux_tri)
    van = _van(flux_tri, getattr(scenario, "taux_actualisation_pct", 4.0))

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
    cash_on_cash_return_pct = (
        round(premiere_annee["cashflow_annuel_apres_impot"] / financement.apport * 100, 2)
        if financement.apport > 0
        else None
    )
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
        mode_location=location_scenario.mode_location,
        regime_fiscal=fiscalite.regime,
        tri_annuel_pct=round(tri * 100, 2) if tri is not None else None,
        van=van,
        cash_on_cash_return_pct=cash_on_cash_return_pct,
        cashflow_cumule_horizon=cashflow_cumule,
        patrimoine_net_sortie=patrimoine_net_sortie,
        flux_sortie_net=flux_sortie_net,
        impot_plus_value=plus_value.impot_total,
        impots_total_horizon=round(impots_total_horizon + plus_value.impot_total, 2),
        break_even_year=break_even_year,
        nb_annees_cashflow_negatif=nb_annees_cashflow_negatif,
        fiscalite_annuelle=fiscalite_annuelle,
        amortissements_fiscaux=amortissements_fiscaux,
        credit_annuel=credit_annuel,
        plus_value=plus_value.to_dict(),
    )
