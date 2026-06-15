"""Page historique des snapshots de simulation."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from achat_immo.storage import DatabaseConnection, get_simulation_results, list_simulation_runs


def history_page(conn: DatabaseConnection, annonce_id: int | None) -> None:
    runs = list_simulation_runs(conn, annonce_id)
    if not runs:
        st.info("Pas encore d'historique.")
        return
    st.dataframe(pd.DataFrame(runs), hide_index=True, width="stretch")
    run_id = st.selectbox("Inspecter un snapshot", [int(run["id"]) for run in runs])
    st.dataframe(pd.DataFrame(get_simulation_results(conn, run_id)).head(100), hide_index=True, width="stretch")
