"""Page historique des snapshots de simulation."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from achat_immo.analysis.run_deltas import compare_latest_analysis_runs
from achat_immo.storage import (
    DatabaseConnection,
    get_simulation_results,
    list_analysis_runs,
    list_extraction_runs,
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
    sourcing_runs = list_sourcing_runs(conn) if include_global_sourcing_runs else []
    if not simulation_runs and not extraction_runs and not analysis_runs and not sourcing_runs:
        st.info("Pas encore d'historique.")
        return

    if annonce_id is not None and (extraction_runs or analysis_runs):
        st.subheader("Preuves annonce active")
        cols = st.columns(2)
        if extraction_runs:
            extraction = extraction_runs[0]
            cols[0].metric("Derniere extraction", extraction.get("status") or "n/a")
            cols[0].write(
                {
                    "source": extraction.get("extracted_source") or "",
                    "red_flags": extraction.get("red_flags") or "",
                    "donnees_manquantes": extraction.get("missing_fields") or "",
                    "erreur": extraction.get("error_message") or "",
                }
            )
        if analysis_runs:
            analysis = analysis_runs[0]
            cols[1].metric("Derniere analyse", analysis.get("status") or "n/a")
            cols[1].write(
                {
                    "tri_p50": analysis.get("tri_p50"),
                    "tri_p10": analysis.get("tri_p10"),
                    "cashflow_p50": analysis.get("cashflow_p50"),
                    "prix_recommande": analysis.get("recommended_price"),
                    "solveur": analysis.get("solver_status") or "",
                }
            )
        delta_snapshot = compare_latest_analysis_runs(analysis_runs)
        if delta_snapshot:
            st.subheader("Evolution depuis l'analyse precedente")
            numeric_deltas = delta_snapshot["numeric_deltas"]
            status_changes = delta_snapshot["status_changes"]
            if numeric_deltas:
                st.dataframe(pd.DataFrame(numeric_deltas), hide_index=True, width="stretch")
            if status_changes:
                st.dataframe(pd.DataFrame(status_changes), hide_index=True, width="stretch")

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
