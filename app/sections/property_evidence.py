"""Section de preuves et audit d'une fiche annonce."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from achat_immo.analysis.run_deltas import compare_latest_analysis_runs
from achat_immo.storage import (
    DatabaseConnection,
    get_simulation_results,
    list_analysis_runs,
    list_extraction_runs,
    list_map_estimate_runs,
    list_simulation_runs,
    list_sourcing_runs,
)


def property_evidence_section(
    conn: DatabaseConnection,
    annonce_id: int | None,
    *,
    include_global_sourcing_runs: bool = True,
) -> None:
    simulation_runs = list_simulation_runs(conn, annonce_id)
    extraction_runs = list_extraction_runs(conn, annonce_id)
    analysis_runs = list_analysis_runs(conn, annonce_id)
    map_estimate_runs = list_map_estimate_runs(conn, annonce_id)
    sourcing_runs = list_sourcing_runs(conn) if include_global_sourcing_runs else []
    if not simulation_runs and not extraction_runs and not analysis_runs and not map_estimate_runs and not sourcing_runs:
        st.info("Pas encore de preuve enregistree.")
        return

    _render_evidence_summary(extraction_runs, analysis_runs, simulation_runs)
    if map_estimate_runs:
        st.subheader("Estimations numeriques de la carte")
        st.dataframe(pd.DataFrame(map_estimate_runs).head(10), hide_index=True, width="stretch")

    if annonce_id is not None and (extraction_runs or analysis_runs):
        delta_snapshot = compare_latest_analysis_runs(analysis_runs)
        if delta_snapshot:
            st.subheader("Evolution depuis l'analyse precedente")
            numeric_deltas = delta_snapshot["numeric_deltas"]
            status_changes = delta_snapshot["status_changes"]
            if numeric_deltas:
                st.dataframe(pd.DataFrame(numeric_deltas), hide_index=True, width="stretch")
            if status_changes:
                st.dataframe(pd.DataFrame(status_changes), hide_index=True, width="stretch")

    with st.expander("Voir les journaux techniques", expanded=False):
        _render_evidence_logs(
            conn,
            simulation_runs,
            extraction_runs,
            analysis_runs,
            sourcing_runs,
            include_global_sourcing_runs,
        )


def _render_evidence_summary(
    extraction_runs: list[dict[str, object]],
    analysis_runs: list[dict[str, object]],
    simulation_runs: list[dict[str, object]],
) -> None:
    extraction = extraction_runs[0] if extraction_runs else {}
    analysis = analysis_runs[0] if analysis_runs else {}
    missing_fields = _split_evidence_list(extraction.get("missing_fields"))
    red_flags = _split_evidence_list(extraction.get("red_flags"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Extraction", str(extraction.get("status") or "non extraite"))
    c2.metric("Donnees manquantes", len(missing_fields))
    c3.metric("Analyse", str(analysis.get("status") or "absente"))
    c4.metric("Snapshots financiers", len(simulation_runs))

    if red_flags:
        st.warning("Points a verifier dans l'extraction")
        for flag in red_flags:
            st.write(f"- {flag}")
    if missing_fields:
        st.markdown("**Donnees a completer**")
        for field in missing_fields:
            st.write(f"- {field}")
    if analysis:
        summary = {
            "TRI P50": analysis.get("tri_p50"),
            "TRI P10": analysis.get("tri_p10"),
            "Cashflow P50": analysis.get("cashflow_p50"),
            "Prix recommande": analysis.get("recommended_price"),
            "Solveur": analysis.get("solver_status") or "",
        }
        st.dataframe(pd.DataFrame([summary]), hide_index=True, width="stretch")


def _split_evidence_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    if isinstance(value, list | tuple | set):
        return [str(part).strip() for part in value if str(part).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _render_evidence_logs(
    conn: DatabaseConnection,
    simulation_runs: list[dict[str, object]],
    extraction_runs: list[dict[str, object]],
    analysis_runs: list[dict[str, object]],
    sourcing_runs: list[dict[str, object]],
    include_global_sourcing_runs: bool,
) -> None:
    tab_labels = ["Snapshots financiers", "Extractions IA", "Analyses auto"]
    if include_global_sourcing_runs:
        tab_labels.append("Runs sourcing")
    tabs = st.tabs(tab_labels)
    tab_simulation, tab_extraction, tab_analysis = tabs[:3]
    with tab_simulation:
        if not simulation_runs:
            st.info("Aucun snapshot financier.")
        else:
            st.dataframe(pd.DataFrame(simulation_runs), hide_index=True, width="stretch")
            run_id = st.selectbox("Inspecter un snapshot", [int(run["id"]) for run in simulation_runs])
            st.dataframe(pd.DataFrame(get_simulation_results(conn, run_id)).head(100), hide_index=True, width="stretch")

    with tab_extraction:
        if not extraction_runs:
            st.info("Aucune extraction IA tracee.")
        else:
            st.dataframe(pd.DataFrame(extraction_runs), hide_index=True, width="stretch")

    with tab_analysis:
        if not analysis_runs:
            st.info("Aucune analyse automatique tracee.")
        else:
            st.dataframe(pd.DataFrame(analysis_runs), hide_index=True, width="stretch")

    if include_global_sourcing_runs:
        with tabs[3]:
            if not sourcing_runs:
                st.info("Aucun run de sourcing trace.")
            else:
                st.caption("Runs globaux de traitement de queue, non limites a l'annonce selectionnee.")
                st.dataframe(pd.DataFrame(sourcing_runs), hide_index=True, width="stretch")
