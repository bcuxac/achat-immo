"""Actions de workflow pour une fiche annonce."""

from __future__ import annotations

import streamlit as st

from achat_immo.analysis.manual_analysis import rerun_financial_analysis
from achat_immo.investment_profile import InvestmentProfile
from achat_immo.qualification import AnalysisTargets
from achat_immo.storage import (
    AnnonceRecord,
    DatabaseConnection,
    HypothesesAchatRecord,
    enqueue_sourcing_url,
    get_investment_profile,
)
from app.navigation import SOURCING_QUEUE_PAGE_LABEL


def property_workflow_actions(
    conn: DatabaseConnection,
    annonce: AnnonceRecord,
    hypotheses: HypothesesAchatRecord,
) -> None:
    st.subheader("Actions d'analyse")
    profile = get_investment_profile(conn)
    target_tri, target_tri_p10, target_coc, target_cf, target_probability = _analysis_targets_inputs(
        annonce,
        profile,
    )
    targets = AnalysisTargets(
        target_tri_median=float(target_tri),
        target_tri_p10=float(target_tri_p10),
        target_coc=float(target_coc),
        target_cashflow=float(target_cf),
        min_prob_positive_cashflow=float(target_probability) / 100,
        n_scenarios=profile.detailed_scenario_count,
        n_solver_scenarios=profile.solver_scenario_count,
    )

    analysis_col, queue_col = st.columns(2)
    if analysis_col.button(
        "Relancer l'analyse financiere",
        type="primary",
        width="stretch",
        key=f"rerun_financial_analysis_{annonce.id}",
    ):
        _rerun_financial_analysis(conn, annonce, hypotheses, targets, profile)

    if queue_col.button(
        "Renvoyer l'URL a analyser",
        width="stretch",
        key=f"enqueue_source_url_{annonce.id}",
    ):
        _enqueue_current_url(conn, annonce)


def _analysis_targets_inputs(
    annonce: AnnonceRecord,
    profile: InvestmentProfile,
) -> tuple[float, float, float, float, float]:
    c1, c2, c3, c4, c5 = st.columns(5)
    target_tri = c1.number_input(
        "TRI median cible (%)",
        value=profile.target_tri_median,
        step=0.5,
        key=f"target_tri_{annonce.id}",
    )
    target_tri_p10 = c2.number_input(
        "TRI P10 cible (%)",
        value=profile.target_tri_p10,
        step=0.5,
        key=f"target_tri_p10_{annonce.id}",
    )
    target_coc = c3.number_input(
        "CoC cible (%)",
        value=profile.target_cash_on_cash,
        step=0.5,
        key=f"target_coc_{annonce.id}",
    )
    target_cf = c4.number_input(
        "Cashflow cible",
        value=profile.target_monthly_cashflow,
        step=25.0,
        key=f"target_cf_{annonce.id}",
    )
    target_probability = c5.number_input(
        "Probabilite CF+ (%)",
        min_value=0.0,
        max_value=100.0,
        value=profile.min_positive_cashflow_probability * 100,
        step=5.0,
        key=f"target_probability_{annonce.id}",
    )
    return (
        float(target_tri),
        float(target_tri_p10),
        float(target_coc),
        float(target_cf),
        float(target_probability),
    )


def _rerun_financial_analysis(
    conn: DatabaseConnection,
    annonce: AnnonceRecord,
    hypotheses: HypothesesAchatRecord,
    targets: AnalysisTargets,
    profile: InvestmentProfile,
) -> None:
    with st.spinner("Analyse Monte Carlo et solveur en cours..."):
        try:
            result = rerun_financial_analysis(
                conn,
                annonce,
                hypotheses,
                targets=targets,
                profile=profile,
                run_source="streamlit_manual",
            )
        except Exception as exc:
            st.error(f"Analyse impossible : {exc}")
            return
    st.success(f"Analyse sauvegardee. Run #{result.analysis_run_id}, statut {result.status}.")
    st.rerun()


def _enqueue_current_url(conn: DatabaseConnection, annonce: AnnonceRecord) -> None:
    if not annonce.url:
        st.error("Aucune URL n'est associee a cette annonce.")
        return
    try:
        queue_id = enqueue_sourcing_url(
            conn,
            annonce.url,
            source=f"fiche_annonce_{annonce.id}",
            priority=10,
        )
    except ValueError as exc:
        st.error(f"URL invalide : {exc}")
        return

    st.session_state["current_page"] = SOURCING_QUEUE_PAGE_LABEL
    st.success(f"URL ajoutee aux URLs a analyser. Reference #{queue_id}.")
    st.rerun()
