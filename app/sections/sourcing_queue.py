"""Page d'import et de suivi des URLs a sourcer."""

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
from app.navigation import PROPERTY_SHEET_PAGE_LABEL


QUEUE_STATUSES = ("pending", "processing", "done", "failed", "blocked", "skipped")
QUEUE_STATUS_LABELS = {
    "pending": "A analyser",
    "processing": "En cours",
    "done": "Annonce creee",
    "failed": "A corriger",
    "blocked": "Source bloquee",
    "skipped": "Ignoree",
}
QUEUE_VIEW_FILTERS = {
    "URLs a analyser": ("pending", "processing"),
    "A corriger": ("failed", "blocked"),
    "Annonces creees": ("done",),
    "Ignorees": ("skipped",),
    "Toutes": QUEUE_STATUSES,
}


def sourcing_queue_page(conn: DatabaseConnection) -> None:
    st.header("Importer des URLs")
    _render_enqueue_form(conn)

    rows = list_sourcing_queue(conn)
    if not rows:
        st.info("Aucune URL en queue.")
        return

    _render_status_metrics(rows)
    view = st.radio(
        "Vue",
        options=tuple(QUEUE_VIEW_FILTERS),
        horizontal=True,
        key="sourcing_queue_view",
    )
    filtered_rows = queue_rows_for_view(rows, view)
    if filtered_rows:
        st.dataframe(_queue_dataframe(filtered_rows), hide_index=True, width="stretch")
    else:
        st.info("Aucune URL dans cette vue.")
        return

    selected_id = st.selectbox(
        "URL selectionnee",
        options=[int(row["id"]) for row in filtered_rows],
        format_func=lambda queue_id: _queue_label(filtered_rows, queue_id),
    )
    selected = get_sourcing_queue_item(conn, int(selected_id))
    if selected is None:
        st.warning("URL introuvable.")
        return
    _render_selected_item_actions(conn, selected)


def _render_enqueue_form(conn: DatabaseConnection) -> None:
    with st.expander("Ajouter des URLs", expanded=True):
        _enqueue_form(conn)


def _enqueue_form(conn: DatabaseConnection) -> None:
    with st.form("enqueue_sourcing_urls"):
        urls_text = st.text_area("URLs", height=110)
        with st.expander("Options avancees", expanded=False):
            c1, c2 = st.columns(2)
            source = c1.text_input("Source", value="manual")
            priority = c2.number_input("Priorite", value=0, step=1)
        submitted = st.form_submit_button("Ajouter aux URLs a analyser")
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
    visible_statuses = ("pending", "processing", "failed", "blocked", "done")
    cols = st.columns(len(visible_statuses))
    for col, status in zip(cols, visible_statuses, strict=True):
        col.metric(QUEUE_STATUS_LABELS[status], counts.get(status, 0))


def _render_selected_item_actions(conn: DatabaseConnection, item: dict[str, Any]) -> None:
    st.subheader("Action URL")
    _render_selected_item_summary(item)

    skip_reason = st.text_input("Raison d'ignore", value=str(item["last_error"] or "Ignore manuellement."))
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Remettre en attente", width="stretch"):
        mark_sourcing_url_pending(conn, int(item["id"]))
        st.success("URL remise en attente.")
        st.rerun()
    if c2.button("Marquer ignoree", width="stretch"):
        mark_sourcing_url_skipped(conn, int(item["id"]), skip_reason.strip() or "Ignore manuellement.")
        st.success("URL ignoree.")
        st.rerun()
    with c3:
        if st.button("Depanner maintenant", width="stretch"):
            _process_selected_item(conn, item)
        st.caption("Action manuelle exceptionnelle. Le traitement normal passe par GitHub Actions.")
    if c4.button(
        "Ouvrir la fiche",
        width="stretch",
        disabled=item.get("annonce_id") is None,
    ):
        st.session_state["selected_annonce_id"] = int(item["annonce_id"])
        st.session_state["current_page"] = PROPERTY_SHEET_PAGE_LABEL
        st.rerun()

    with st.expander("Details techniques", expanded=False):
        with st.form(f"edit_queue_{item['id']}"):
            c1, c2 = st.columns(2)
            source = c1.text_input("Source", value=str(item["source"]))
            priority = c2.number_input("Priorite", value=int(item["priority"]), step=1)
            if st.form_submit_button("Mettre a jour"):
                update_sourcing_queue_item(
                    conn,
                    int(item["id"]),
                    source=source.strip() or "manual",
                    priority=int(priority),
                )
                st.success("URL mise a jour.")
                st.rerun()
        _render_technical_summary(item)


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
    return pd.DataFrame(
        [
            {
                "etat": QUEUE_STATUS_LABELS.get(str(row.get("status") or ""), str(row.get("status") or "")),
                "url": row.get("source_url") or "",
                "annonce": f"#{row['annonce_id']}" if row.get("annonce_id") else "",
                "probleme": row.get("last_error") or "",
                "dernier_traitement": row.get("last_processed_at") or "",
            }
            for row in rows
        ]
    )


def queue_rows_for_view(rows: list[dict[str, Any]], view: str) -> list[dict[str, Any]]:
    statuses = set(QUEUE_VIEW_FILTERS.get(view, QUEUE_STATUSES))
    return [row for row in rows if str(row.get("status") or "") in statuses]


def _queue_label(rows: list[dict[str, Any]], queue_id: int) -> str:
    row = next(row for row in rows if int(row["id"]) == queue_id)
    status = QUEUE_STATUS_LABELS.get(str(row["status"]), str(row["status"]))
    return f"#{row['id']} {status} - {row['source_url']}"


def _render_selected_item_summary(item: dict[str, Any]) -> None:
    summary = {
        "etat": QUEUE_STATUS_LABELS.get(str(item["status"]), str(item["status"])),
        "url": item["source_url"],
        "annonce": f"#{item['annonce_id']}" if item.get("annonce_id") else "",
        "probleme": item["last_error"],
    }
    st.dataframe(pd.DataFrame([summary]), hide_index=True, width="stretch")


def _render_technical_summary(item: dict[str, Any]) -> None:
    technical = {
        "id": item["id"],
        "status": item["status"],
        "source": item["source"],
        "priority": item["priority"],
        "attempts": item["attempts"],
        "annonce_id": item["annonce_id"] or "",
        "last_processed_at": item["last_processed_at"],
    }
    st.dataframe(pd.DataFrame([technical]), hide_index=True, width="stretch")
