"""Vue Fiche annonce : tout ce qui concerne une seule annonce."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class PropertyDecisionSummary:
    verdict: str
    reason: str
    next_actions: tuple[str, ...]


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
    summary_tab, data_tab, assumptions_tab, analysis_tab, evidence_tab, decision_tab = st.tabs(
        [
            "Synthese",
            "Donnees",
            "Hypotheses",
            "Analyse financiere",
            "Preuves",
            "Decision",
        ]
    )

    with summary_tab:
        _summary_page(conn, annonce, hypotheses)
    with data_tab:
        property_data_section(conn, annonce, hypotheses)
    with assumptions_tab:
        property_assumptions_section(conn, annonce, hypotheses)
    with analysis_tab:
        property_workflow_actions(conn, annonce, hypotheses)
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
    decision_summary = build_property_decision_summary(annonce, hypotheses, extraction_runs, analysis_runs)
    c0, c1, c2 = st.columns([1.4, 2.4, 1.2])
    c0.metric("Verdict", decision_summary.verdict)
    c1.write(decision_summary.reason)
    c2.metric("Statut", annonce.statut.replace("_", " "))

    if decision_summary.next_actions:
        st.markdown("**Prochaines actions**")
        for action in decision_summary.next_actions:
            st.write(f"- {action}")

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("TRI median", _format_pct(annonce.tri_p50))
    c2.metric("TRI P10", _format_pct(annonce.tri_p10))
    c3.metric("Cashflow P50", format_eur_optional(annonce.cashflow_p50))
    c4.metric("Prix cible", format_eur_optional(annonce.prix_cible_recommande))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Cash-on-cash", _format_pct(annonce.coc_p50))
    c6.metric("Cashflow positif", _format_probability_pct(annonce.probabilite_cashflow_positif))
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
        "snapshots_financiers": len(simulation_runs),
    }
    st.dataframe(pd.DataFrame([facts]), hide_index=True, width="stretch")

    if annonce.notes:
        st.subheader("Notes de decision")
        st.write(annonce.notes)


def build_property_decision_summary(
    annonce: AnnonceRecord,
    hypotheses: HypothesesAchatRecord,
    extraction_runs: list[dict[str, Any]],
    analysis_runs: list[dict[str, Any]],
) -> PropertyDecisionSummary:
    missing_fields = _missing_decision_fields(annonce, hypotheses)
    latest_extraction = extraction_runs[0] if extraction_runs else {}
    latest_analysis = analysis_runs[0] if analysis_runs else {}
    status = str(annonce.statut or "")
    red_flags = _split_evidence_list(latest_extraction.get("red_flags"))
    solver_status = str(latest_analysis.get("solver_status") or "")
    tri_p50 = _first_float(annonce.tri_p50, latest_analysis.get("tri_p50"))
    cashflow_p50 = _first_float(annonce.cashflow_p50, latest_analysis.get("cashflow_p50"))
    cashflow_probability_pct = _normalize_probability_pct(
        _first_float(
            annonce.probabilite_cashflow_positif,
            latest_analysis.get("probabilite_cashflow_positif"),
        )
    )

    if status in {"rejete", "archive", "hors_criteres"}:
        return PropertyDecisionSummary(
            verdict="Ecarter",
            reason="L'annonce est deja classee hors flux actif.",
            next_actions=("Conserver seulement si une nouvelle information justifie une reouverture.",),
        )

    if missing_fields:
        return PropertyDecisionSummary(
            verdict="Verifier",
            reason="Des donnees bloquent encore une decision fiable : " + ", ".join(missing_fields) + ".",
            next_actions=("Completer les donnees et hypotheses manquantes.", "Relancer l'analyse financiere ensuite."),
        )

    if (annonce.dpe or "").upper().startswith("G"):
        return PropertyDecisionSummary(
            verdict="Ecarter",
            reason="Le DPE G est un risque bloquant pour la mise en location.",
            next_actions=("Verifier le DPE a la source.", "Rejeter sauf scenario travaux explicite."),
        )

    if red_flags:
        return PropertyDecisionSummary(
            verdict="Verifier",
            reason="L'extraction IA a remonte des signaux a controler : " + ", ".join(red_flags[:3]) + ".",
            next_actions=("Lire les preuves d'extraction.", "Confirmer ou corriger les donnees factuelles."),
        )

    if solver_status and solver_status not in {"ok", "optimal", "success", "solved", "already_viable"}:
        return PropertyDecisionSummary(
            verdict="Verifier",
            reason=f"Le solveur indique un statut a controler : {solver_status}.",
            next_actions=("Lire les preuves d'analyse.", "Relancer l'analyse apres correction des hypotheses."),
        )

    if tri_p50 is not None and tri_p50 < 4.0:
        return PropertyDecisionSummary(
            verdict="Ecarter",
            reason=f"Le TRI median ressort faible ({tri_p50:.1f} %).",
            next_actions=("Comparer avec les autres opportunites.", "Rejeter sauf avantage qualitatif fort."),
        )

    if cashflow_p50 is not None and cashflow_p50 < -200:
        return PropertyDecisionSummary(
            verdict="Ecarter",
            reason=f"Le cashflow median est trop negatif ({cashflow_p50:,.0f} EUR/mois).",
            next_actions=("Tester uniquement si le prix baisse fortement.", "Sinon rejeter."),
        )

    if cashflow_probability_pct is not None and cashflow_probability_pct < 35:
        return PropertyDecisionSummary(
            verdict="Negocier",
            reason=f"La probabilite de cashflow positif est basse ({cashflow_probability_pct:.0f} %).",
            next_actions=("Chercher le prix cible.", "Negocier avant tout contact engageant."),
        )

    if annonce.prix_cible_recommande and annonce.prix_affiche:
        discount = (float(annonce.prix_cible_recommande) - float(annonce.prix_affiche)) / float(annonce.prix_affiche)
        if discount < -0.03:
            return PropertyDecisionSummary(
                verdict="Negocier",
                reason="Le prix cible ressort sous le prix affiche.",
                next_actions=("Preparer une offre argumentee.", "Comparer avec les autres opportunites shortlistees."),
            )

    if status in {"shortlist", "favori", "a_visiter", "contacte", "offre_faite"}:
        return PropertyDecisionSummary(
            verdict="Suivre",
            reason="L'annonce est deja dans le flux de contact ou de suivi.",
            next_actions=("Mettre a jour les notes de decision.", "Planifier la prochaine relance."),
        )

    if latest_analysis or annonce.tri_p50 is not None:
        return PropertyDecisionSummary(
            verdict="Decider",
            reason="Les donnees principales et une analyse existent. La decision humaine peut etre tranchee.",
            next_actions=("Lire les conditions de robustesse.", "Passer en shortlist, negocier ou rejeter."),
        )

    return PropertyDecisionSummary(
        verdict="Analyser",
        reason="La fiche est suffisamment structuree pour lancer ou relancer l'analyse.",
        next_actions=("Relancer l'analyse financiere.", "Verifier ensuite les preuves et le prix cible."),
    )


def _first_float(*values: object) -> float | None:
    for value in values:
        if value is None or value == "":
            continue
        return float(value)
    return None


def _split_evidence_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    if isinstance(value, list | tuple | set):
        return [str(part).strip() for part in value if str(part).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _missing_decision_fields(annonce: AnnonceRecord, hypotheses: HypothesesAchatRecord) -> list[str]:
    missing: list[str] = []
    if not annonce.dpe:
        missing.append("DPE")
    if annonce.surface_m2 <= 0:
        missing.append("surface")
    if annonce.prix_affiche <= 0:
        missing.append("prix")
    if hypotheses.loyer_hc_mensuel <= 0:
        missing.append("loyer")
    if hypotheses.taxe_fonciere <= 0:
        missing.append("taxe fonciere")
    return missing


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


def _format_probability_pct(value: float | None) -> str:
    probability_pct = _normalize_probability_pct(value)
    return "n/a" if probability_pct is None else f"{probability_pct:,.1f} %"


def _normalize_probability_pct(value: float | None) -> float | None:
    if value is None:
        return None
    if 0 <= value <= 1:
        return value * 100
    return value


def _row_for_id(rows: list[dict[str, Any]], annonce_id: int) -> dict[str, Any]:
    return next(row for row in rows if int(row["id"]) == int(annonce_id))
