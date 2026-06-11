"""Page tableau de bord de l'application Streamlit."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from achat_immo.storage import DatabaseConnection, list_simulation_runs


def dashboard_page(conn: DatabaseConnection, rows: list[dict[str, Any]]) -> None:
    st.subheader("Vue base SQLite")
    st.caption("Cette page sert a voir ce qui est stocke : annonces suivies, decisions et derniers runs.")
    runs = list_simulation_runs(conn)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Annonces", len(rows))
    c2.metric("Runs sauvegardes", len(runs))
    c3.metric("Favorites", sum(1 for row in rows if row["statut"] == "favori"))
    c4.metric("Rejetees", sum(1 for row in rows if row["statut"] == "rejete"))

    if rows:
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
        st.subheader("Derniers runs")
        st.dataframe(pd.DataFrame(runs).head(10), hide_index=True, width="stretch")
