"""Pilotage Streamlit de la queue de sourcing."""

from __future__ import annotations

from collections import Counter
import os
from typing import Any

import pandas as pd
import streamlit as st

from achat_immo.sourcing_agents.orchestrator import SourcingOrchestrator
from achat_immo.sourcing_agents.prefilter import UrlPrefilterPolicy
from achat_immo.sourcing_queue_actions import process_sourcing_queue_item
from achat_immo.storage import (
    DatabaseConnection,
    enqueue_sourcing_url,
    get_sourcing_queue_item,
    list_sourcing_queue,
    mark_sourcing_url_pending,
    mark_sourcing_url_skipped,
    update_sourcing_queue_item,
)


QUEUE_STATUSES = ("pending", "processing", "done", "failed", "blocked", "skipped")


def sourcing_queue_page(conn: DatabaseConnection) -> None:
    st.subheader("Queue sourcing")
    _render_enqueue_form(conn)

    rows = list_sourcing_queue(conn)
    if not rows:
        st.info("Aucune URL en queue.")
        return

    _render_status_metrics(rows)
    selected_statuses = st.multiselect(
        "Statuts",
        options=QUEUE_STATUSES,
        default=("pending", "failed", "blocked", "skipped"),
    )
    filtered_rows = [row for row in rows if not selected_statuses or row["status"] in selected_statuses]
    if filtered_rows:
        st.dataframe(_queue_dataframe(filtered_rows), hide_index=True, width="stretch")
    else:
        st.info("Aucune URL pour ce filtre.")

    selected_id = st.selectbox(
        "URL selectionnee",
        options=[int(row["id"]) for row in rows],
        format_func=lambda queue_id: _queue_label(rows, queue_id),
    )
    selected = get_sourcing_queue_item(conn, int(selected_id))
    if selected is None:
        st.warning("URL introuvable.")
        return
    _render_selected_item_actions(conn, selected)


def _render_enqueue_form(conn: DatabaseConnection) -> None:
    with st.form("enqueue_sourcing_urls"):
        urls_text = st.text_area("URLs", height=110)
        c1, c2 = st.columns(2)
        source = c1.text_input("Source", value="manual")
        priority = c2.number_input("Priorite", value=0, step=1)
        submitted = st.form_submit_button("Ajouter a la queue")
    if not submitted:
        return

    urls = [line.strip() for line in urls_text.splitlines() if line.strip() and not line.strip().startswith("#")]
    if not urls:
        st.error("Ajoute au moins une URL.")
        return
    queue_ids = []
    for url in urls:
        try:
            queue_ids.append(enqueue_sourcing_url(conn, url, source=source.strip() or "manual", priority=int(priority)))
        except ValueError as exc:
            st.error(f"URL ignoree : {exc}")
    if queue_ids:
        st.success(f"{len(queue_ids)} URL(s) en queue.")
        st.rerun()


def _render_status_metrics(rows: list[dict[str, Any]]) -> None:
    counts = Counter(str(row["status"]) for row in rows)
    cols = st.columns(len(QUEUE_STATUSES))
    for col, status in zip(cols, QUEUE_STATUSES, strict=True):
        col.metric(status, counts.get(status, 0))


def _render_selected_item_actions(conn: DatabaseConnection, item: dict[str, Any]) -> None:
    st.subheader("Action")
    st.write(
        {
            "id": item["id"],
            "status": item["status"],
            "source": item["source"],
            "priority": item["priority"],
            "url": item["source_url"],
            "last_error": item["last_error"],
        }
    )

    with st.form(f"edit_queue_{item['id']}"):
        c1, c2 = st.columns(2)
        source = c1.text_input("Source", value=str(item["source"]))
        priority = c2.number_input("Priorite", value=int(item["priority"]), step=1)
        if st.form_submit_button("Mettre a jour"):
            update_sourcing_queue_item(conn, int(item["id"]), source=source.strip() or "manual", priority=int(priority))
            st.success("Queue mise a jour.")
            st.rerun()

    skip_reason = st.text_input("Raison d'ignore", value=str(item["last_error"] or "Ignore manuellement."))
    c1, c2, c3 = st.columns(3)
    if c1.button("Remettre en attente", width="stretch"):
        mark_sourcing_url_pending(conn, int(item["id"]))
        st.success("URL remise en attente.")
        st.rerun()
    if c2.button("Marquer ignoree", width="stretch"):
        mark_sourcing_url_skipped(conn, int(item["id"]), skip_reason.strip() or "Ignore manuellement.")
        st.success("URL ignoree.")
        st.rerun()
    if c3.button("Traiter maintenant", type="primary", width="stretch"):
        _process_selected_item(conn, item)


def _process_selected_item(conn: DatabaseConnection, item: dict[str, Any]) -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        st.error("GEMINI_API_KEY est requis dans l'environnement ou Streamlit secrets.")
        return
    with st.spinner("Traitement de l'URL en cours..."):
        orchestrator = SourcingOrchestrator()
        result = process_sourcing_queue_item(
            conn,
            item,
            orchestrator,
            prefilter_policy=UrlPrefilterPolicy(),
        )
    if result.status == "done":
        st.success(f"Annonce #{result.annonce_id} sauvegardee.")
    elif result.status == "skipped":
        st.warning(result.message)
    elif result.status == "blocked":
        st.warning(result.message)
    else:
        st.error(result.message)
    st.rerun()


def _queue_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    columns = [
        "id",
        "status",
        "priority",
        "source",
        "source_url",
        "attempts",
        "annonce_id",
        "last_error",
        "last_processed_at",
    ]
    return pd.DataFrame(rows)[columns]


def _queue_label(rows: list[dict[str, Any]], queue_id: int) -> str:
    row = next(row for row in rows if int(row["id"]) == queue_id)
    return f"#{row['id']} {row['status']} p{row['priority']} - {row['source_url']}"
