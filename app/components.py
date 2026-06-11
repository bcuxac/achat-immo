"""Composants visuels Streamlit reutilisables."""

from __future__ import annotations

import streamlit as st

from achat_immo.diagnostics import DiagnosticStatus
from app.ui_helpers import field_origin


def badge_caption(field_name: str) -> None:
    st.caption(f"Champ {field_origin(field_name)}")


def readonly_field(label: str, value: str, field_name: str, help_text: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{label}**")
        st.write(value)
        st.caption(f"Champ {field_origin(field_name)} - {help_text}")


def decision_robuste_status(decision: str) -> str:
    return {
        "interessant": "OK",
        "a_creuser": "Attention",
        "a_negocier": "Attention",
        "diagnostic_incomplet": "A verifier",
        "a_rejeter": "Bloquant",
    }.get(decision, "Neutre")


def _status_style(status: str) -> str:
    return {
        "OK": "background:#dcfce7;color:#166534;border:1px solid #86efac;",
        "Attention": "background:#fef3c7;color:#92400e;border:1px solid #fcd34d;",
        "Bloquant": "background:#fee2e2;color:#991b1b;border:1px solid #fecaca;",
        "Neutre": "background:#e2e8f0;color:#475569;border:1px solid #cbd5e1;",
        "A verifier": "background:#e0f2fe;color:#075985;border:1px solid #7dd3fc;",
    }.get(status, "background:#e2e8f0;color:#475569;border:1px solid #cbd5e1;")


def decision_factor(title: str, value: str, status: str, detail: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.markdown(
            f"<span style='display:inline-block;padding:2px 8px;border-radius:999px;{_status_style(status)}'>{status}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(value)
        st.caption(detail)


def diagnostic_status_label(status: DiagnosticStatus) -> str:
    return {
        DiagnosticStatus.OK: "OK",
        DiagnosticStatus.WARNING: "Attention",
        DiagnosticStatus.BLOCKING: "Bloquant",
        DiagnosticStatus.MISSING: "A verifier",
    }[status]
