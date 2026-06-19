"""Page tableau de bord de l'application Streamlit."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from achat_immo.decision_cockpit import FUNNEL_ORDER, build_cockpit_snapshot
from achat_immo.storage import (
    DatabaseConnection,
    list_analysis_runs,
    list_extraction_runs,
    list_sourcing_queue,
    list_simulation_runs,
    list_sourcing_runs,
)


def dashboard_page(conn: DatabaseConnection, rows: list[dict[str, Any]]) -> None:
    st.subheader("Cockpit de decision")
    runs = list_simulation_runs(conn)
    extraction_runs = list_extraction_runs(conn)
    analysis_runs = list_analysis_runs(conn)
    sourcing_queue = list_sourcing_queue(conn)
    sourcing_runs = list_sourcing_runs(conn, limit=10)
    snapshot = build_cockpit_snapshot(rows, extraction_runs, analysis_runs, sourcing_queue, sourcing_runs)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Annonces", snapshot.totals["annonces"])
    c2.metric("Actives", snapshot.totals["actives"])
    c3.metric("Shortlist", snapshot.totals["shortlist"])
    c4.metric("Queue pending", snapshot.totals["queue_pending"])
    c5.metric("Queue bloquee", snapshot.totals["queue_blocked"])

    for start in range(0, len(FUNNEL_ORDER), 5):
        funnel_slice = FUNNEL_ORDER[start : start + 5]
        funnel_cols = st.columns(len(funnel_slice))
        for column, stage in zip(funnel_cols, funnel_slice, strict=True):
            column.metric(stage.replace("_", " "), snapshot.funnel_counts.get(stage, 0))

    priority_df = pd.DataFrame(snapshot.priority_items)
    if not priority_df.empty:
        st.subheader("Priorites")
        priority_columns = [
            "id",
            "etape",
            "ville",
            "quartier",
            "prix_affiche",
            "prix_cible_recommande",
            "ecart_prix_pct",
            "tri_p50",
            "cashflow_p50",
            "signal",
            "action",
        ]
        st.dataframe(priority_df[priority_columns].head(25), hide_index=True, width="stretch")

    queue_counts = pd.DataFrame(
        [{"status": status, "count": count} for status, count in sorted(snapshot.queue_counts.items())]
    )
    if not queue_counts.empty:
        st.subheader("Queue sourcing")
        st.dataframe(queue_counts, hide_index=True, width="stretch")

    if snapshot.latest_sourcing_run:
        st.subheader("Dernier run sourcing")
        st.dataframe(pd.DataFrame([snapshot.latest_sourcing_run]), hide_index=True, width="stretch")

    if rows:
        st.subheader("Annonces")
        df = pd.DataFrame(rows)
        st.dataframe(
            df[
                [
                    "id",
                    "statut",
                    "ville",
                    "quartier",
                    "adresse",
                    "type_bien",
                    "nb_pieces",
                    "epoque_construction",
                    "secteur_encadrement",
                    "surface_m2",
                    "prix_affiche",
                    "dpe",
                ]
            ],
            hide_index=True,
            width="stretch",
        )
    if runs:
        st.subheader("Derniers snapshots de simulation")
        st.dataframe(pd.DataFrame(runs).head(10), hide_index=True, width="stretch")
