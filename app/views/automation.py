"""Vue Parametres / Automatisation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from achat_immo.storage import DatabaseConnection, list_sourcing_queue, list_sourcing_runs
from app.runtime_config import configured_database_url, configured_gemini_api_key


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCING_WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "sourcing.yml"
DEFAULT_ALLOWED_DOMAINS = "jinka.fr,leboncoin.fr,seloger.com,bienici.com,pap.fr"


def automation_page(conn: DatabaseConnection, *, database_target: str) -> None:
    st.header("Parametres / Automatisation")
    _render_runtime_status(database_target)
    _render_github_actions_status(conn)
    _render_sourcing_policy()


def _render_runtime_status(database_target: str) -> None:
    st.subheader("Configuration runtime")
    rows = [
        {
            "element": "DATABASE_URL",
            "statut": _configured_label(bool(configured_database_url())),
            "usage": "Base partagee entre Streamlit, CLI et GitHub Actions",
        },
        {
            "element": "GEMINI_API_KEY",
            "statut": _configured_label(bool(configured_gemini_api_key())),
            "usage": "Extraction LLM et traitement de la queue",
        },
        {
            "element": "Base active",
            "statut": "PostgreSQL" if configured_database_url() else "SQLite",
            "usage": _database_target_label(database_target),
        },
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _render_github_actions_status(conn: DatabaseConnection) -> None:
    st.subheader("GitHub Actions")
    queue_rows = list_sourcing_queue(conn)
    run_rows = list_sourcing_runs(conn, limit=10)
    pending_count = sum(1 for row in queue_rows if row.get("status") == "pending")
    blocked_count = sum(1 for row in queue_rows if row.get("status") == "blocked")
    failed_count = sum(1 for row in queue_rows if row.get("status") == "failed")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Workflow", "present" if SOURCING_WORKFLOW_PATH.exists() else "absent")
    c2.metric("URLs pending", pending_count)
    c3.metric("URLs bloquees", blocked_count)
    c4.metric("URLs en erreur", failed_count)

    if run_rows:
        st.dataframe(pd.DataFrame(run_rows).head(10), hide_index=True, width="stretch")
    else:
        st.info("Aucun run de sourcing trace.")


def _render_sourcing_policy() -> None:
    st.subheader("Politique de sourcing")
    allowed_domains = os.environ.get("SOURCING_ALLOWED_DOMAINS", DEFAULT_ALLOWED_DOMAINS)
    rows: list[dict[str, Any]] = [
        {
            "parametre": "Domaines autorises",
            "valeur": allowed_domains,
        },
        {
            "parametre": "Limite URLs par run",
            "valeur": os.environ.get("SOURCING_LIMIT", "20"),
        },
        {
            "parametre": "Limite par source",
            "valeur": os.environ.get("SOURCING_SOURCE_LIMIT", "3"),
        },
        {
            "parametre": "Prefiltre URL",
            "valeur": "actif",
        },
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _configured_label(is_configured: bool) -> str:
    return "configure" if is_configured else "absent"


def _database_target_label(database_target: str) -> str:
    if configured_database_url():
        return "URL configuree"
    return database_target
