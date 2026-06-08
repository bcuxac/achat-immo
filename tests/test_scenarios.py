from achat_immo.models import (
    AlternativeInvestissement,
    BienImmobilier,
    Financement,
    Fiscalite,
    HypothesesLocation,
    TypeBien,
)
from achat_immo.scenarios import (
    comparer_immo_vs_bourse,
    scenario_central,
    simuler_alternative_bourse,
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
        alternative=AlternativeInvestissement(rendement_annuel_pct=8),
    )

    assert resultat.cout_total_projet == 127_800
    assert resultat.montant_emprunte == 109_800
    assert resultat.rendement_brut_pct > 6
    assert resultat.cashflow_mensuel_apres_impot < 0
    assert resultat.effort_epargne_mensuel > 0
    assert len(resultat.projection_annuelle) == 11
    assert resultat.alternative_horizon is not None


def test_alternative_bourse_capitalise_apport_et_effort_epargne() -> None:
    projection = simuler_alternative_bourse(
        capital_initial=20_000,
        alternative=AlternativeInvestissement(rendement_annuel_pct=6),
        horizon_annees=5,
        versements_mensuels=[200] * 5,
    )

    assert len(projection) == 6
    assert projection[-1]["capital_net"] > 20_000 + 200 * 12 * 5


def test_comparaison_multihorizons() -> None:
    resultats = comparer_immo_vs_bourse(
        bien=_bien_grenoble(),
        location=HypothesesLocation(loyer_hc_mensuel=700, taxe_fonciere=900),
        financement=Financement(apport=18_000),
        fiscalite=Fiscalite(),
        rendements_alternatifs_pct=(4, 8),
        horizons_annees=(5, 10),
    )

    assert len(resultats) == 4
    assert {r.scenario.horizon_annees for r in resultats} == {5, 10}
