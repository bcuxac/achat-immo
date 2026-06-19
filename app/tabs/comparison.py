"""Page de comparaison portefeuille et statut d'annonce."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from achat_immo.robustness import analyser_grille
from achat_immo.storage import (
    AnnonceRecord,
    DatabaseConnection,
    get_simulation_results,
    list_simulation_runs,
    update_decision,
)
from app.ui_helpers import PORTFOLIO_DECISION_LABEL, STATUTS


def comparison_page(conn: DatabaseConnection, rows: list[dict[str, Any]], annonce: AnnonceRecord | None) -> None:
    st.subheader(PORTFOLIO_DECISION_LABEL)
    st.caption("Compare uniquement les annonces pour lesquelles un snapshot de simulation a ete sauvegarde.")
    runs = list_simulation_runs(conn)
    status_by_annonce = {
        int(row["id"]): str(row.get("statut") or "")
        for row in rows
        if row.get("id") is not None
    }
    if runs:
        latest_by_annonce: dict[int, dict[str, Any]] = {}
        for run in runs:
            latest_by_annonce.setdefault(int(run["annonce_id"]), run)
        best_rows = []
        for run in latest_by_annonce.values():
            results = get_simulation_results(conn, int(run["id"]))
            if results:
                best = dict(results[0])
                robustesse = analyser_grille(results)
                annonce_id = int(run["annonce_id"])
                best["ville"] = run["ville"]
                best["quartier"] = run["quartier"]
                best["run_id"] = run["id"]
                best["statut"] = status_by_annonce.get(annonce_id, "")
                best["decision_robuste"] = robustesse.decision
                best["meilleure_strategie"] = " / ".join(
                    value for value in (str(best.get("mode_location") or ""), str(best.get("regime_fiscal") or "")) if value
                )
                best["cashflow_prudent"] = robustesse.meilleur_cashflow_prudent
                best["cashflow_median"] = robustesse.cashflow_median
                best["pct_scenarios_viables"] = robustesse.pct_viables
                best_rows.append(best)
        if best_rows:
            df = pd.DataFrame(best_rows)
            decision_cols = [
                "ville",
                "quartier",
                "statut",
                "decision_robuste",
                "meilleure_strategie",
                "tri_annuel_pct",
                "patrimoine_net_sortie",
                "cashflow_prudent",
                "cashflow_median",
                "pct_scenarios_viables",
                "score",
                "run_id",
            ]
            visible_cols = [col for col in decision_cols if col in df.columns]
            sort_cols = [col for col in ("score", "patrimoine_net_sortie", "cashflow_prudent") if col in df.columns]
            st.dataframe(
                df[visible_cols].sort_values(sort_cols, ascending=False) if sort_cols else df[visible_cols],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("Sauvegarde un snapshot depuis Simulations pour comparer les annonces.")
    else:
        st.info("Sauvegarde un snapshot depuis Simulations pour comparer les annonces.")

    if annonce is None:
        return
    st.divider()
    st.subheader("Statut de l'annonce active")
    with st.form("decision_form"):
        statut = st.selectbox(
            "Statut",
            options=STATUTS,
            index=STATUTS.index(annonce.statut) if annonce.statut in STATUTS else 0,
        )
        notes = st.text_area("Notes de decision", value=annonce.notes, height=130)
        if st.form_submit_button("Sauvegarder la decision"):
            update_decision(conn, annonce.id or 0, statut=statut, notes=notes)
            st.success("Decision sauvegardee.")
            st.rerun()
