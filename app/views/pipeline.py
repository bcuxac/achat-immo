"""Vue Pipeline : lecture multi-annonces orientee action."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from achat_immo.decision_cockpit import (
    FUNNEL_LABELS,
    FUNNEL_ORDER,
    build_cockpit_snapshot,
)
from achat_immo.storage import (
    DatabaseConnection,
    list_analysis_runs,
    list_extraction_runs,
    list_qualification_runs,
    list_sourcing_queue,
    list_sourcing_runs,
)
from app.navigation import PROPERTY_SHEET_PAGE_LABEL


TERMINAL_STATUSES = {"archive", "rejete"}
PRIORITY_COLUMNS = [
    "id",
    "etape",
    "ville",
    "quartier",
    "prix_affiche",
    "prix_cible_recommande",
    "qualification_rapide",
    "ratio_voisins_viables",
    "ecart_prix_pct",
    "tri_p50",
    "cashflow_p50",
    "signal",
    "action",
]
OPPORTUNITY_COLUMNS = [
    "id",
    "statut",
    "ville",
    "quartier",
    "adresse",
    "type_bien",
    "nb_pieces",
    "surface_m2",
    "prix_affiche",
    "loyer_hc_mensuel",
    "tri_p50",
    "cashflow_p50",
    "prix_cible_recommande",
    "dpe",
]


def pipeline_page(conn: DatabaseConnection, rows: list[dict[str, Any]]) -> None:
    """Affiche le pipeline d'opportunites et les prochaines actions."""

    st.header("A traiter maintenant")
    extraction_runs = list_extraction_runs(conn)
    analysis_runs = list_analysis_runs(conn)
    sourcing_queue = list_sourcing_queue(conn)
    sourcing_runs = list_sourcing_runs(conn, limit=10)
    qualification_runs = list_qualification_runs(conn)
    snapshot = build_cockpit_snapshot(
        rows,
        extraction_runs,
        analysis_runs,
        sourcing_queue,
        sourcing_runs,
        qualification_runs,
    )

    _render_attention_metrics(snapshot.totals, snapshot.funnel_counts)
    _render_priority_actions(snapshot.priority_items)
    with st.expander("Voir l'entonnoir complet", expanded=False):
        _render_funnel(snapshot.funnel_counts)
    with st.expander("Voir toutes les opportunites", expanded=False):
        _render_opportunity_table(rows)


def _render_attention_metrics(totals: dict[str, int], funnel_counts: dict[str, int]) -> None:
    columns = st.columns(5)
    columns[0].metric("A verifier", funnel_counts.get("a_verifier", 0))
    columns[1].metric("A completer", funnel_counts.get("donnees_insuffisantes", 0))
    columns[2].metric("Sources bloquees", funnel_counts.get("extraction_bloquee", 0))
    columns[3].metric("Shortlist", totals.get("shortlist", 0))
    columns[4].metric("URLs en attente", totals.get("queue_pending", 0))


def _render_funnel(funnel_counts: dict[str, int]) -> None:
    st.subheader("Entonnoir")
    for start in range(0, len(FUNNEL_ORDER), 5):
        stages = FUNNEL_ORDER[start : start + 5]
        columns = st.columns(len(stages))
        for column, stage in zip(columns, stages, strict=True):
            column.metric(FUNNEL_LABELS.get(stage, stage), funnel_counts.get(stage, 0))


def _render_priority_actions(priority_items: list[dict[str, Any]]) -> None:
    st.subheader("Prochaines decisions")
    if not priority_items:
        st.info("Aucune action prioritaire.")
        return

    stage_options = _stage_filter_options(priority_items)
    selected_stages = st.multiselect(
        "Etapes",
        options=list(stage_options),
        default=list(stage_options),
        format_func=lambda stage: stage_options[stage],
        key="pipeline_stage_filter",
    )
    include_terminal = st.checkbox(
        "Inclure annonces rejetees et archivees",
        value=False,
        key="pipeline_include_terminal",
    )
    filtered_items = filter_pipeline_items(
        priority_items,
        selected_stages=tuple(selected_stages),
        include_terminal=include_terminal,
    )
    if not filtered_items:
        st.info("Aucune annonce pour ces filtres.")
        return

    for item in filtered_items[:6]:
        _render_priority_card(item)
    with st.expander("Table detaillee", expanded=False):
        _render_priority_table(filtered_items)


def _render_priority_table(items: list[dict[str, Any]]) -> None:
    df = priority_dataframe(items)
    visible_columns = [column for column in PRIORITY_COLUMNS if column in df.columns]
    st.dataframe(df[visible_columns].head(30), hide_index=True, width="stretch")


def _render_priority_card(item: dict[str, Any]) -> None:
    with st.container(border=True):
        location = " - ".join(
            value for value in (str(item.get("ville") or ""), str(item.get("quartier") or "")) if value
        )
        title = f"#{item.get('id')} {location or 'Adresse a verifier'}"
        st.markdown(f"**{title}**")
        c1, c2, c3 = st.columns([1.2, 1.4, 2.4])
        c1.metric("Etape", str(item.get("etape") or "A verifier"))
        c2.metric("TRI median", _format_optional_pct(item.get("tri_p50")))
        c3.write(str(item.get("signal") or item.get("action") or "Verifier la fiche."))
        st.caption(str(item.get("action") or "Ouvrir la fiche pour decider."))
        if st.button("Ouvrir cette fiche", type="primary", key=f"pipeline_open_{item.get('id')}"):
            st.session_state["selected_annonce_id"] = int(item["id"])
            st.session_state["current_page"] = PROPERTY_SHEET_PAGE_LABEL
            st.rerun()


def _format_optional_pct(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    return f"{float(value):,.1f} %"


def _render_opportunity_table(rows: list[dict[str, Any]]) -> None:
    st.subheader("Opportunites")
    if not rows:
        return

    status_options = tuple(sorted({str(row.get("statut") or "non renseigne") for row in rows}))
    active_statuses = tuple(status for status in status_options if status not in TERMINAL_STATUSES)
    selected_statuses = st.multiselect(
        "Statuts",
        options=status_options,
        default=active_statuses or status_options,
        key="pipeline_status_filter",
    )
    filtered_rows = [row for row in rows if str(row.get("statut") or "non renseigne") in selected_statuses]
    if not filtered_rows:
        st.info("Aucune opportunite pour ces statuts.")
        return

    df = pd.DataFrame(filtered_rows)
    visible_columns = [column for column in OPPORTUNITY_COLUMNS if column in df.columns]
    st.dataframe(df[visible_columns], hide_index=True, width="stretch")


def filter_pipeline_items(
    items: list[dict[str, Any]],
    *,
    selected_stages: tuple[str, ...],
    include_terminal: bool,
) -> list[dict[str, Any]]:
    selected = set(selected_stages)
    return [
        item
        for item in items
        if str(item.get("stage") or "") in selected
        and (include_terminal or str(item.get("statut") or "") not in TERMINAL_STATUSES)
    ]


def priority_dataframe(items: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(items)


def _stage_filter_options(items: list[dict[str, Any]]) -> dict[str, str]:
    stages = [stage for stage in FUNNEL_ORDER if any(item.get("stage") == stage for item in items)]
    unknown_stages = sorted({str(item.get("stage") or "") for item in items} - set(stages) - {""})
    return {stage: FUNNEL_LABELS.get(stage, stage) for stage in [*stages, *unknown_stages]}
