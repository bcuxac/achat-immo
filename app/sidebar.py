"""Sidebar Streamlit de selection des annonces."""

from __future__ import annotations

from typing import Any

import streamlit as st

from achat_immo.city_profiles import SECTEUR_A_VERIFIER
from achat_immo.storage import (
    AnnonceRecord,
    HypothesesAchatRecord,
    get_annonce_bundle,
    list_annonces,
    save_annonce,
)


def annonce_label(row: dict[str, Any]) -> str:
    quartier = f" - {row['quartier']}" if row.get("quartier") else ""
    return f"#{row['id']} {row['ville']}{quartier} - {row['surface_m2']:.0f} m2 - {row['prix_affiche']:,.0f} EUR"


def create_blank_annonce(conn: Any) -> int:
    return save_annonce(
        conn,
        AnnonceRecord(
            ville="Grenoble",
            surface_m2=30.0,
            prix_affiche=80_000.0,
            nb_pieces=2,
            secteur_encadrement=SECTEUR_A_VERIFIER,
            statut="a_analyser",
        ),
        HypothesesAchatRecord(loyer_hc_mensuel=500.0),
    )


def sidebar(conn: Any) -> tuple[list[dict[str, Any]], int | None]:
    st.sidebar.subheader("Annonces")
    if st.sidebar.button("Nouvelle annonce", type="primary", width="stretch"):
        annonce_id = create_blank_annonce(conn)
        st.session_state["selected_annonce_id"] = annonce_id
        st.rerun()

    rows = list_annonces(conn)
    if not rows:
        st.sidebar.info("Cree une annonce pour commencer.")
        return rows, None

    ids = [int(row["id"]) for row in rows]
    default_id = st.session_state.get("selected_annonce_id", ids[0])
    index = ids.index(default_id) if default_id in ids else 0
    selected = st.sidebar.selectbox(
        "Annonce active",
        options=ids,
        index=index,
        format_func=lambda annonce_id: annonce_label(next(row for row in rows if row["id"] == annonce_id)),
    )
    st.session_state["selected_annonce_id"] = selected
    return rows, selected


def load_bundle(conn: Any, annonce_id: int | None) -> tuple[AnnonceRecord | None, HypothesesAchatRecord | None]:
    if annonce_id is None:
        return None, None
    return get_annonce_bundle(conn, annonce_id)
