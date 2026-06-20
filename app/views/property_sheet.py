"""Vue Fiche annonce : tout ce qui concerne une seule annonce."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from achat_immo.storage import (
    AnnonceRecord,
    DatabaseConnection,
    HypothesesAchatRecord,
    get_annonce_bundle,
    list_analysis_runs,
    list_extraction_runs,
    list_simulation_runs,
    update_decision,
)
from app.navigation import SOURCING_QUEUE_PAGE_LABEL
from app.sidebar import annonce_label
from app.sections.financial_analysis import financial_analysis_section
from app.sections.property_assumptions import property_assumptions_section
from app.sections.property_data import property_data_section
from app.sections.property_evidence import property_evidence_section
from app.ui_helpers import STATUTS, format_eur_optional
from app.views.property_workflow import property_workflow_actions


def property_sheet_page(conn: DatabaseConnection, rows: list[dict[str, Any]]) -> None:
    """Affiche une fiche complete centree sur une annonce."""

    st.header("Fiche annonce")
    if not rows:
        st.info("Aucune annonce disponible. La saisie principale commence par des URLs dans Queue sourcing.")
        if st.button("Aller a Queue sourcing"):
            st.session_state["current_page"] = SOURCING_QUEUE_PAGE_LABEL
            st.rerun()
        return

    selected_id = _select_annonce(rows)
    try:
        annonce, hypotheses = get_annonce_bundle(conn, selected_id)
    except KeyError as exc:
        st.error(str(exc))
        return

    _render_header(annonce, hypotheses)
    summary_tab, data_tab, analysis_tab, evidence_tab, decision_tab = st.tabs(
        [
            "Synthese",
            "Donnees extraites",
            "Analyse financiere",
            "Runs / preuves",
            "Decision",
        ]
    )

    with summary_tab:
        _summary_page(conn, annonce, hypotheses)
    with data_tab:
        property_data_section(conn, annonce, hypotheses)
    with analysis_tab:
        property_workflow_actions(conn, annonce, hypotheses)
        st.divider()
        property_assumptions_section(conn, annonce, hypotheses)
        st.divider()
        financial_analysis_section(conn, annonce, hypotheses)
    with evidence_tab:
        property_evidence_section(conn, selected_id, include_global_sourcing_runs=False)
    with decision_tab:
        _decision_page(conn, annonce)


def _select_annonce(rows: list[dict[str, Any]]) -> int:
    ids = [int(row["id"]) for row in rows if row.get("id") is not None]
    default_id = st.session_state.get("selected_annonce_id", ids[0])
    index = ids.index(default_id) if default_id in ids else 0
    selected_id = st.selectbox(
        "Annonce",
        options=ids,
        index=index,
        format_func=lambda annonce_id: annonce_label(_row_for_id(rows, annonce_id)),
        key="property_sheet_annonce_id",
    )
    st.session_state["selected_annonce_id"] = int(selected_id)
    return int(selected_id)


def _render_header(annonce: AnnonceRecord, hypotheses: HypothesesAchatRecord) -> None:
    title_parts = [
        f"#{annonce.id}",
        annonce.ville or "Ville a verifier",
        annonce.quartier or "",
    ]
    st.subheader(" - ".join(part for part in title_parts if part))
    columns = st.columns(5)
    columns[0].metric("Statut", annonce.statut.replace("_", " "))
    columns[1].metric("Prix affiche", format_eur_optional(annonce.prix_affiche))
    columns[2].metric("Surface", f"{annonce.surface_m2:,.0f} m2")
    columns[3].metric("Loyer HC", format_eur_optional(hypotheses.loyer_hc_mensuel))
    columns[4].metric("DPE", annonce.dpe or "n/a")


def _summary_page(
    conn: DatabaseConnection,
    annonce: AnnonceRecord,
    hypotheses: HypothesesAchatRecord,
) -> None:
    extraction_runs = list_extraction_runs(conn, annonce.id)
    analysis_runs = list_analysis_runs(conn, annonce.id)
    simulation_runs = list_simulation_runs(conn, annonce.id)

    st.subheader("Lecture rapide")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("TRI median", _format_pct(annonce.tri_p50))
    c2.metric("TRI P10", _format_pct(annonce.tri_p10))
    c3.metric("Cashflow P50", format_eur_optional(annonce.cashflow_p50))
    c4.metric("Prix cible", format_eur_optional(annonce.prix_cible_recommande))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Cash-on-cash", _format_pct(annonce.coc_p50))
    c6.metric("Cashflow positif", _format_pct(annonce.probabilite_cashflow_positif))
    c7.metric("Extractions", len(extraction_runs))
    c8.metric("Analyses", len(analysis_runs))

    facts = {
        "url": annonce.url or "n/a",
        "adresse": annonce.adresse or "n/a",
        "type_bien": str(getattr(annonce.type_bien, "value", annonce.type_bien)),
        "pieces": annonce.nb_pieces or "n/a",
        "construction": str(getattr(annonce.epoque_construction, "value", annonce.epoque_construction)),
        "mode_location": str(getattr(hypotheses.mode_location, "value", hypotheses.mode_location)),
        "regime_fiscal": str(getattr(hypotheses.regime_fiscal, "value", hypotheses.regime_fiscal)),
        "snapshots_simulation": len(simulation_runs),
    }
    st.dataframe(pd.DataFrame([facts]), hide_index=True, width="stretch")

    if annonce.notes:
        st.subheader("Notes de decision")
        st.write(annonce.notes)


def _decision_page(conn: DatabaseConnection, annonce: AnnonceRecord) -> None:
    st.subheader("Decision annonce")
    with st.form(f"decision_form_{annonce.id}"):
        statut = st.selectbox(
            "Statut",
            options=STATUTS,
            index=STATUTS.index(annonce.statut) if annonce.statut in STATUTS else 0,
        )
        notes = st.text_area("Notes de decision", value=annonce.notes, height=180)
        if st.form_submit_button("Sauvegarder la decision", type="primary"):
            update_decision(conn, annonce.id or 0, statut=statut, notes=notes)
            st.success("Decision sauvegardee.")
            st.rerun()


def _format_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.1f} %"


def _row_for_id(rows: list[dict[str, Any]], annonce_id: int) -> dict[str, Any]:
    return next(row for row in rows if int(row["id"]) == int(annonce_id))
