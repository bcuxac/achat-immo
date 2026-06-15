from pathlib import Path

import pandas as pd

from achat_immo.comparison import classer_biens, scorer_bien
from achat_immo.export import export_csv, export_excel
from achat_immo.models import BienImmobilier, Financement, Fiscalite, HypothesesLocation
from achat_immo.engines.scenarios import scenario_central, simuler_bien_sur_horizon


def test_score_rejette_cashflow_trop_negatif() -> None:
    resultat = simuler_bien_sur_horizon(
        bien=BienImmobilier(
            ville="Fontainebleau",
            surface_m2=35,
            prix_affiche=210_000,
            frais_notaire_estimes=16_000,
            dpe="E",
        ),
        location=HypothesesLocation(loyer_hc_mensuel=750, taxe_fonciere=1_100),
        financement=Financement(apport=15_000, taux_credit_annuel_pct=4.0, duree_credit_annees=20),
        fiscalite=Fiscalite(),
        scenario=scenario_central(10),
    )

    score = scorer_bien(resultat)

    assert score["decision"] == "a_rejeter"
    assert "cashflow_trop_negatif" in score["alertes"]


def test_score_bloque_dpe_g() -> None:
    resultat = simuler_bien_sur_horizon(
        bien=BienImmobilier(
            ville="Nimes",
            surface_m2=35,
            prix_affiche=90_000,
            dpe="G",
        ),
        location=HypothesesLocation(loyer_hc_mensuel=650, taxe_fonciere=900),
        financement=Financement(apport=15_000, taux_credit_annuel_pct=3.6, duree_credit_annees=20),
        fiscalite=Fiscalite(),
        scenario=scenario_central(10),
    )

    score = scorer_bien(resultat)

    assert score["score"] == 0
    assert score["decision"] == "a_rejeter"
    assert "dpe_g_interdit_location" in score["alertes"]


def test_classement_et_export_csv(tmp_path: Path) -> None:
    resultat = simuler_bien_sur_horizon(
        bien=BienImmobilier(
            ville="Nimes",
            surface_m2=40,
            prix_affiche=90_000,
            frais_notaire_estimes=7_200,
            meubles_estimes=4_000,
        ),
        location=HypothesesLocation(loyer_hc_mensuel=620, taxe_fonciere=850),
        financement=Financement(apport=18_000),
        fiscalite=Fiscalite(),
        scenario=scenario_central(5),
    )

    classement = classer_biens([resultat])
    output = export_csv([resultat], tmp_path / "resultats.csv")

    assert classement[0]["ville"] == "Nimes"
    assert output.exists()


def test_export_excel(tmp_path: Path) -> None:
    resultat = simuler_bien_sur_horizon(
        bien=BienImmobilier(
            ville="Grenoble",
            surface_m2=40,
            prix_affiche=100_000,
            frais_notaire_estimes=8_000,
        ),
        location=HypothesesLocation(loyer_hc_mensuel=650, taxe_fonciere=850),
        financement=Financement(apport=15_000),
        fiscalite=Fiscalite(),
        scenario=scenario_central(5),
    )

    output = export_excel([resultat], tmp_path / "comparaison.xlsx")

    assert output.exists()
    workbook = pd.ExcelFile(output)
    assert {"Credit", "Fiscalite annuelle", "Amortissements fiscaux"}.issubset(set(workbook.sheet_names))
