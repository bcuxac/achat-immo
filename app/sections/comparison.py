"""Page d'arbitrage entre plusieurs annonces."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from achat_immo.robustness import analyser_grille
from achat_immo.storage import DatabaseConnection, get_simulation_results, list_simulation_runs
from app.navigation import PROPERTY_SHEET_PAGE_LABEL
from app.ui_helpers import PORTFOLIO_DECISION_LABEL


TERMINAL_STATUSES = {"archive", "rejete"}
COMPARABLE_STATUSES = {"shortlist", "favori", "a_visiter", "a_negocier", "contacte", "offre_faite"}
DECISION_ORDER = {
    "interessant": 0,
    "a_creuser": 1,
    "a_negocier": 2,
    "diagnostic_incomplet": 3,
    "a_rejeter": 4,
}
DECISION_COLUMNS = [
    "rang",
    "annonce_id",
    "ville",
    "quartier",
    "statut",
    "decision_robuste",
    "meilleure_strategie",
    "tri_annuel_pct",
    "cashflow_prudent",
    "cashflow_median",
    "pct_scenarios_viables",
    "patrimoine_net_sortie",
    "score",
    "run_id",
]


def comparison_page(conn: DatabaseConnection, rows: list[dict[str, Any]]) -> None:
    st.subheader(PORTFOLIO_DECISION_LABEL)
    runs = list_simulation_runs(conn)
    results_by_run = {int(run["id"]): get_simulation_results(conn, int(run["id"])) for run in runs}
    comparison_rows = build_comparison_rows(runs, rows, results_by_run)
    if not comparison_rows:
        st.info("Passe une annonce en shortlist puis sauvegarde un snapshot financier pour arbitrer.")
        _render_missing_snapshot_table(rows, comparison_rows)
        return

    filtered_rows = _render_filters(comparison_rows)
    if not filtered_rows:
        st.info("Aucune annonce ne correspond a ces filtres.")
        _render_missing_snapshot_table(rows, comparison_rows)
        return

    _render_recommended_opportunity(filtered_rows)
    _render_open_sheet_control(filtered_rows)
    df = pd.DataFrame(filtered_rows)
    visible_cols = [col for col in DECISION_COLUMNS if col in df.columns]
    st.dataframe(df[visible_cols], hide_index=True, width="stretch")
    _render_missing_snapshot_table(rows, comparison_rows)


def build_comparison_rows(
    runs: list[Mapping[str, Any]],
    property_rows: list[Mapping[str, Any]],
    results_by_run: Mapping[int, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    status_by_annonce = {
        int(row["id"]): str(row.get("statut") or "")
        for row in property_rows
        if row.get("id") is not None
    }
    latest_by_annonce: dict[int, Mapping[str, Any]] = {}
    for run in runs:
        latest_by_annonce.setdefault(int(run["annonce_id"]), run)

    comparison_rows: list[dict[str, Any]] = []
    for run in latest_by_annonce.values():
        run_id = int(run["id"])
        results = results_by_run.get(run_id, [])
        if not results:
            continue

        best = dict(results[0])
        robustesse = analyser_grille(results)
        annonce_id = int(run["annonce_id"])
        statut = status_by_annonce.get(annonce_id, "")
        if statut not in COMPARABLE_STATUSES:
            continue
        decision_rank = DECISION_ORDER.get(robustesse.decision, 99)
        best.update(
            {
                "annonce_id": annonce_id,
                "ville": run.get("ville") or "",
                "quartier": run.get("quartier") or "",
                "run_id": run_id,
                "statut": statut,
                "decision_robuste": robustesse.decision,
                "rang_decision": decision_rank,
                "meilleure_strategie": " / ".join(
                    value
                    for value in (
                        str(best.get("mode_location") or ""),
                        str(best.get("regime_fiscal") or ""),
                    )
                    if value
                ),
                "cashflow_prudent": robustesse.meilleur_cashflow_prudent,
                "cashflow_median": robustesse.cashflow_median,
                "pct_scenarios_viables": robustesse.pct_viables,
            }
        )
        comparison_rows.append(best)

    return _rank_comparison_rows(comparison_rows)


def filter_comparison_rows(
    rows: list[dict[str, Any]],
    *,
    selected_decisions: tuple[str, ...],
    selected_statuses: tuple[str, ...],
    require_positive_prudent_cashflow: bool,
) -> list[dict[str, Any]]:
    decisions = set(selected_decisions)
    statuses = set(selected_statuses)
    return _rank_comparison_rows(
        [
            row
            for row in rows
            if str(row.get("decision_robuste") or "") in decisions
            and str(row.get("statut") or "non renseigne") in statuses
            and (
                not require_positive_prudent_cashflow
                or _optional_float(row.get("cashflow_prudent")) is not None
                and _optional_float(row.get("cashflow_prudent")) >= 0
            )
        ]
    )


def _render_filters(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decision_options = tuple(
        decision for decision in DECISION_ORDER if any(row.get("decision_robuste") == decision for row in rows)
    )
    unknown_decisions = tuple(
        sorted({str(row.get("decision_robuste") or "") for row in rows} - set(decision_options) - {""})
    )
    decision_options = (*decision_options, *unknown_decisions)
    status_options = tuple(sorted({str(row.get("statut") or "non renseigne") for row in rows}))
    active_statuses = tuple(status for status in status_options if status not in TERMINAL_STATUSES)

    c1, c2, c3 = st.columns([2, 2, 1])
    selected_decisions = c1.multiselect(
        "Decisions robustes",
        options=decision_options,
        default=decision_options,
        key="comparison_decision_filter",
    )
    selected_statuses = c2.multiselect(
        "Statuts",
        options=status_options,
        default=active_statuses or status_options,
        key="comparison_status_filter",
    )
    require_positive = c3.checkbox(
        "Cashflow prudent positif",
        value=False,
        key="comparison_positive_prudent_cashflow",
    )
    return filter_comparison_rows(
        rows,
        selected_decisions=tuple(selected_decisions),
        selected_statuses=tuple(selected_statuses),
        require_positive_prudent_cashflow=bool(require_positive),
    )


def _render_recommended_opportunity(rows: list[dict[str, Any]]) -> None:
    best = rows[0]
    st.subheader("Priorite")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Annonce", f"#{best['annonce_id']}")
    c2.metric("Decision", str(best.get("decision_robuste") or "n/a").replace("_", " "))
    c3.metric("Cashflow prudent", _format_optional_eur(best.get("cashflow_prudent")))
    c4.metric("Scenarios viables", _format_optional_pct(best.get("pct_scenarios_viables")))


def _render_open_sheet_control(rows: list[dict[str, Any]]) -> None:
    ids = [int(row["annonce_id"]) for row in rows if row.get("annonce_id") is not None]
    selected_id = st.selectbox(
        "Ouvrir une opportunite",
        options=ids,
        format_func=lambda annonce_id: _comparison_label(rows, annonce_id),
        key="comparison_annonce_id",
    )
    if st.button("Ouvrir la fiche annonce", type="primary"):
        st.session_state["selected_annonce_id"] = int(selected_id)
        st.session_state["current_page"] = PROPERTY_SHEET_PAGE_LABEL
        st.rerun()


def _render_missing_snapshot_table(
    property_rows: list[Mapping[str, Any]],
    comparison_rows: list[Mapping[str, Any]],
) -> None:
    compared_ids = {int(row["annonce_id"]) for row in comparison_rows if row.get("annonce_id") is not None}
    missing_rows = [
        row
        for row in property_rows
        if row.get("id") is not None
        and int(row["id"]) not in compared_ids
        and str(row.get("statut") or "") in COMPARABLE_STATUSES
    ]
    if not missing_rows:
        return

    with st.expander("Opportunites shortlistees sans snapshot", expanded=False):
        df = pd.DataFrame(missing_rows)
        columns = [column for column in ("id", "statut", "ville", "quartier", "prix_affiche") if column in df.columns]
        st.dataframe(df[columns], hide_index=True, width="stretch")


def _rank_comparison_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=_comparison_sort_key)
    for index, row in enumerate(ranked, start=1):
        row["rang"] = index
    return ranked


def _comparison_sort_key(row: Mapping[str, Any]) -> tuple[float, float, float, float, float]:
    decision_rank = row.get("rang_decision")
    if decision_rank is None:
        decision_rank = DECISION_ORDER.get(str(row.get("decision_robuste") or ""), 99)
    return (
        float(decision_rank),
        -float(row.get("pct_scenarios_viables") or 0.0),
        -float(row.get("cashflow_prudent") or -1_000_000.0),
        -float(row.get("tri_annuel_pct") or -1_000_000.0),
        -float(row.get("score") or 0.0),
    )


def _comparison_label(rows: list[dict[str, Any]], annonce_id: int) -> str:
    row = next(row for row in rows if int(row["annonce_id"]) == int(annonce_id))
    location = " - ".join(value for value in (str(row.get("ville") or ""), str(row.get("quartier") or "")) if value)
    return f"#{annonce_id} {location} - {str(row.get('decision_robuste') or 'n/a').replace('_', ' ')}"


def _format_optional_eur(value: Any) -> str:
    numeric = _optional_float(value)
    return "n/a" if numeric is None else f"{numeric:,.0f} EUR"


def _format_optional_pct(value: Any) -> str:
    numeric = _optional_float(value)
    return "n/a" if numeric is None else f"{numeric:,.1f} %"


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
