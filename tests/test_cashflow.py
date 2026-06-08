from achat_immo.cashflow import (
    cashflow_mensuel,
    charges_annuelles,
    rendement_brut,
    rendement_net,
    revenus_annuels_hc,
    vacance_locative,
)
from achat_immo.models import BienImmobilier, HypothesesLocation, TypeBien


def test_revenus_integrent_un_mois_de_vacance_par_defaut() -> None:
    location = HypothesesLocation(loyer_hc_mensuel=650)

    assert revenus_annuels_hc(location) == 7_150
    assert vacance_locative(location) == 650


def test_charges_et_cashflow_avec_gestion_agence() -> None:
    location = HypothesesLocation(
        loyer_hc_mensuel=650,
        charges_copro_annuelles=1_200,
        charges_recuperables_annuelles=500,
        taxe_fonciere=900,
        gestion_agence_active=True,
        frais_gestion_pct=7,
        comptable_lmnp=500,
        entretien_annuel=400,
    )
    revenus = revenus_annuels_hc(location)
    charges = charges_annuelles(location, revenus)

    assert charges["charges_non_recuperables"] == 700
    assert charges["gestion_locative"] == 500.5
    assert cashflow_mensuel(revenus, charges, mensualite_totale=650, impot=0) < 0


def test_rendements_sur_cout_total_projet() -> None:
    bien = BienImmobilier(
        ville="Grenoble",
        surface_m2=42,
        prix_affiche=110_000,
        type_bien=TypeBien.T2,
        frais_notaire_estimes=8_800,
        travaux_estimes=5_000,
        meubles_estimes=4_000,
    )
    location = HypothesesLocation(loyer_hc_mensuel=700, taxe_fonciere=900)
    revenus = revenus_annuels_hc(location)
    charges = charges_annuelles(location, revenus)

    assert rendement_brut(bien, location) == 6.57
    assert rendement_net(bien, revenus, charges) < rendement_brut(bien, location)
