from pathlib import Path

import pytest

from achat_immo.analysis.manual_analysis import (
    AnalysisTargets,
    rerun_financial_analysis,
    strategy_from_records,
)
from achat_immo.storage import (
    AnnonceRecord,
    HypothesesAchatRecord,
    get_annonce_bundle,
    list_analysis_runs,
    open_database,
    save_annonce,
)


def _targets() -> AnalysisTargets:
    return AnalysisTargets(
        target_tri_median=-100.0,
        target_tri_p10=-100.0,
        target_coc=-100.0,
        target_cashflow=-10_000.0,
        min_prob_positive_cashflow=0.0,
        n_scenarios=20,
        n_solver_scenarios=10,
    )


def test_strategy_from_records_applique_les_hypotheses_stockees() -> None:
    annonce = AnnonceRecord(ville="Grenoble", surface_m2=42, prix_affiche=110_000, prix_negocie=100_000)
    hypotheses = HypothesesAchatRecord(
        loyer_hc_mensuel=760,
        charges_copro_annuelles=1_200,
        taxe_fonciere=900,
        travaux_estimes=4_000,
        apport_reference=12_000,
        taux_credit_reference=3.4,
        duree_credit_reference=22,
    )

    strategy = strategy_from_records(annonce, hypotheses)

    assert strategy.prix_achat == 100_000
    assert strategy.frais_notaire_estimes == 8_000
    assert strategy.loyer_hc_mensuel == 760
    assert strategy.apport == 12_000
    assert strategy.duree_credit_annees == 22


def test_rerun_financial_analysis_sauvegarde_un_run_et_met_a_jour_l_annonce(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(
            ville="Grenoble",
            surface_m2=42,
            prix_affiche=100_000,
            dpe="D",
            url="https://example.test/a",
        ),
        HypothesesAchatRecord(
            loyer_hc_mensuel=850,
            charges_copro_annuelles=900,
            taxe_fonciere=700,
            apport_reference=12_000,
        ),
    )
    annonce, hypotheses = get_annonce_bundle(conn, annonce_id)

    result = rerun_financial_analysis(conn, annonce, hypotheses, targets=_targets())
    updated_annonce, _ = get_annonce_bundle(conn, annonce_id)
    runs = list_analysis_runs(conn, annonce_id)

    assert result.annonce_id == annonce_id
    assert result.analysis_run_id == runs[0]["id"]
    assert updated_annonce.tri_p50 is not None
    assert updated_annonce.prix_cible_recommande is not None
    assert updated_annonce.statut == "a_verifier"
    assert runs[0]["scenario_seed"] == result.scenario_seed
    assert runs[0]["diagnostics"].startswith("source=streamlit_manual")


def test_rerun_financial_analysis_preserve_les_statuts_humains(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(ville="Grenoble", surface_m2=42, prix_affiche=100_000, statut="contacte"),
        HypothesesAchatRecord(loyer_hc_mensuel=850, taxe_fonciere=700),
    )
    annonce, hypotheses = get_annonce_bundle(conn, annonce_id)

    result = rerun_financial_analysis(conn, annonce, hypotheses, targets=_targets())
    updated_annonce, _ = get_annonce_bundle(conn, annonce_id)

    assert result.status == "contacte"
    assert updated_annonce.statut == "contacte"


def test_rerun_financial_analysis_refuse_les_donnees_incompletes(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(ville="Grenoble", surface_m2=42, prix_affiche=100_000),
        HypothesesAchatRecord(loyer_hc_mensuel=0),
    )
    annonce, hypotheses = get_annonce_bundle(conn, annonce_id)

    with pytest.raises(ValueError, match="Loyer mensuel positif"):
        rerun_financial_analysis(conn, annonce, hypotheses, targets=_targets())
