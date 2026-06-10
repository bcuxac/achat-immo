from achat_immo.grids import (
    GrilleParametres,
    compter_scenarios_grille,
    generer_plage_float,
    generer_plage_int,
    grille_to_dataframe,
    simuler_grille_annonce,
)
from achat_immo.models import BienImmobilier, Fiscalite, HypothesesLocation, ModeLocation, RegimeFiscal, TypeBien


def test_generer_plages_inclusives() -> None:
    assert generer_plage_float(3.3, 3.32, 0.01) == (3.3, 3.31, 3.32)
    assert generer_plage_int(15, 17, 1) == (15, 16, 17)


def test_simuler_grille_annonce_genere_toutes_les_combinaisons() -> None:
    bien = BienImmobilier(
        ville="Grenoble",
        quartier="Gare",
        surface_m2=38,
        prix_affiche=105_000,
        type_bien=TypeBien.T2,
        frais_notaire_estimes=8_400,
        meubles_estimes=4_000,
    )
    location = HypothesesLocation(loyer_hc_mensuel=680, taxe_fonciere=900)
    parametres = GrilleParametres(
        taux_credit=(3.3, 3.6),
        durees_annees=(20, 25),
        loyers_hc_mensuels=(660, 680),
        apports=(15_000, 20_000),
        vacances_mois=(1.0, 2.0),
        gestions_agence=(False, True),
        frais_gestion_pct=(7.0,),
        horizon_annees=10,
    )

    resultats = simuler_grille_annonce(
        bien=bien,
        location=location,
        fiscalite=Fiscalite(),
        parametres=parametres,
        gestion_agence_possible=True,
    )

    assert len(resultats) == 128
    assert compter_scenarios_grille(bien, location, parametres, fiscalite=Fiscalite()) == 128
    assert resultats[0].score >= resultats[-1].score
    assert resultats[0].to_dict()["cashflow_mensuel_apres_impot"] is not None
    assert {resultat.regime_fiscal for resultat in resultats} == {RegimeFiscal.LMNP_REEL, RegimeFiscal.MICRO_BIC}


def test_grille_respecte_gestion_agence_impossible() -> None:
    bien = BienImmobilier(ville="Nimes", surface_m2=40, prix_affiche=90_000)
    location = HypothesesLocation(loyer_hc_mensuel=620)
    parametres = GrilleParametres(
        taux_credit=(3.6,),
        durees_annees=(20,),
        apports=(15_000,),
        vacances_mois=(1.0,),
        gestions_agence=(False, True),
        frais_gestion_pct=(7.0,),
        horizon_annees=5,
    )

    resultats = simuler_grille_annonce(
        bien=bien,
        location=location,
        parametres=parametres,
        gestion_agence_possible=False,
    )

    assert len(resultats) == 2
    assert resultats[0].gestion_agence is False


def test_grille_itere_les_prix_d_achat() -> None:
    bien = BienImmobilier(ville="Nimes", surface_m2=40, prix_affiche=90_000)
    location = HypothesesLocation(loyer_hc_mensuel=620)
    parametres = GrilleParametres(
        prix_achats=(85_000, 90_000),
        taux_credit=(3.6,),
        durees_annees=(20,),
        apports=(15_000,),
        vacances_mois=(1.0,),
        gestions_agence=(False,),
        frais_gestion_pct=(7.0,),
        horizon_annees=5,
    )

    resultats = simuler_grille_annonce(bien, location, parametres=parametres)

    assert {resultat.prix_achat for resultat in resultats} == {85_000, 90_000}
    assert {resultat.to_dict()["cout_total_projet"] for resultat in resultats} == {85_000, 90_000}
    assert compter_scenarios_grille(bien, location, parametres) == 4


def test_grille_to_dataframe() -> None:
    bien = BienImmobilier(ville="Nimes", surface_m2=40, prix_affiche=90_000)
    location = HypothesesLocation(loyer_hc_mensuel=620)
    parametres = GrilleParametres(
        taux_credit=(3.6,),
        durees_annees=(20,),
        apports=(15_000,),
        vacances_mois=(1.0,),
        gestions_agence=(False,),
        frais_gestion_pct=(7.0,),
        horizon_annees=5,
    )

    df = grille_to_dataframe(simuler_grille_annonce(bien, location, parametres=parametres))

    assert len(df) == 2
    assert df.loc[0, "taux_credit"] == 3.6
    assert df.loc[0, "prix_achat"] == 90_000
    assert df.loc[0, "loyer_hc_mensuel"] == 620
    assert "mode_location" in df.columns
    assert "regime_fiscal" in df.columns
    assert "montant_emprunte" in df.columns
    assert "patrimoine_net_horizon" in df.columns
    assert "ecart_vs_alternative" not in df.columns


def test_grille_compare_meuble_et_nue_si_demande() -> None:
    bien = BienImmobilier(ville="Nimes", surface_m2=40, prix_affiche=90_000, meubles_estimes=4_000)
    location = HypothesesLocation(loyer_hc_mensuel=620)
    parametres = GrilleParametres(
        taux_credit=(3.6,),
        durees_annees=(20,),
        apports=(15_000,),
        vacances_mois=(1.0,),
        gestions_agence=(False,),
        frais_gestion_pct=(7.0,),
        horizon_annees=5,
        modes_location=(ModeLocation.MEUBLEE, ModeLocation.NUE),
    )

    resultats = simuler_grille_annonce(bien, location, parametres=parametres)

    assert {resultat.mode_location for resultat in resultats} == {ModeLocation.MEUBLEE, ModeLocation.NUE}
    assert {resultat.regime_fiscal for resultat in resultats} == {
        RegimeFiscal.LMNP_REEL,
        RegimeFiscal.MICRO_BIC,
        RegimeFiscal.LOCATION_NUE_REEL,
        RegimeFiscal.MICRO_FONCIER,
    }
