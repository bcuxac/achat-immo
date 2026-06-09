from achat_immo.models import (
    BienImmobilier,
    Financement,
    Fiscalite,
    HypothesesLocation,
    TypeBien,
)
from achat_immo.scenarios import (
    scenario_central,
    simuler_bien_sur_horizon,
)


def _bien_grenoble() -> BienImmobilier:
    return BienImmobilier(
        ville="Grenoble",
        quartier="Championnet",
        surface_m2=42,
        prix_affiche=110_000,
        type_bien=TypeBien.T2,
        frais_notaire_estimes=8_800,
        travaux_estimes=5_000,
        meubles_estimes=4_000,
        dpe="D",
    )


def test_simulation_locative_produit_indicateurs_prudents() -> None:
    resultat = simuler_bien_sur_horizon(
        bien=_bien_grenoble(),
        location=HypothesesLocation(
            loyer_hc_mensuel=700,
            charges_copro_annuelles=1_200,
            charges_recuperables_annuelles=500,
            taxe_fonciere=900,
            gestion_agence_active=True,
            comptable_lmnp=500,
        ),
        financement=Financement(apport=18_000, taux_credit_annuel_pct=3.6, duree_credit_annees=20),
        fiscalite=Fiscalite(),
        scenario=scenario_central(horizon_annees=10),
    )

    assert resultat.cout_total_projet == 127_800
    assert resultat.montant_emprunte == 109_800
    assert resultat.rendement_brut_pct > 6
    assert resultat.cashflow_mensuel_apres_impot < 0
    assert resultat.effort_epargne_mensuel > 0
    assert len(resultat.projection_annuelle) == 11
    assert resultat.patrimoine_net_horizon == resultat.projection_annuelle[-1]["patrimoine_net"]


def test_simulation_sur_plusieurs_horizons() -> None:
    resultats = [
        simuler_bien_sur_horizon(
            bien=_bien_grenoble(),
            location=HypothesesLocation(loyer_hc_mensuel=700, taxe_fonciere=900),
            financement=Financement(apport=18_000),
            fiscalite=Fiscalite(),
            scenario=scenario_central(horizon_annees=horizon),
        )
        for horizon in (5, 10)
    ]

    assert [r.scenario.horizon_annees for r in resultats] == [5, 10]
    assert [len(r.projection_annuelle) for r in resultats] == [6, 11]
