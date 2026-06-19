"""Comparaison des runs d'analyse successifs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DeltaField:
    field: str
    label: str
    unit: str = ""
    higher_is_better: bool | None = True


NUMERIC_DELTA_FIELDS: tuple[DeltaField, ...] = (
    DeltaField("tri_p50", "TRI median", "pt", True),
    DeltaField("tri_p10", "TRI P10", "pt", True),
    DeltaField("probabilite_cashflow_positif", "Proba CF positif", "pt", True),
    DeltaField("coc_p50", "Cash-on-Cash median", "pt", True),
    DeltaField("cashflow_p50", "Cashflow median", "EUR", True),
    DeltaField("recommended_price", "Prix recommande", "EUR", None),
    DeltaField("recommended_project_cost", "Cout projet recommande", "EUR", None),
    DeltaField("recommended_apport", "Apport recommande", "EUR", None),
    DeltaField("recommended_loan_amount", "Emprunt recommande", "EUR", None),
)

STATUS_FIELDS: dict[str, str] = {
    "status": "Statut analyse",
    "solver_status": "Statut solveur",
}


def compare_latest_analysis_runs(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compare les deux analyses les plus recentes d'une annonce.

    Les runs doivent etre fournis du plus recent au plus ancien, comme
    `list_analysis_runs` le fait deja.
    """

    if len(runs) < 2:
        return None
    latest = runs[0]
    previous = runs[1]
    numeric_deltas = [_numeric_delta(latest, previous, field) for field in NUMERIC_DELTA_FIELDS]
    numeric_deltas = [delta for delta in numeric_deltas if delta is not None]
    status_changes = [
        {
            "champ": label,
            "precedent": previous.get(field) or "",
            "nouveau": latest.get(field) or "",
        }
        for field, label in STATUS_FIELDS.items()
        if (previous.get(field) or "") != (latest.get(field) or "")
    ]
    return {
        "latest_run_id": latest.get("id"),
        "previous_run_id": previous.get("id"),
        "numeric_deltas": numeric_deltas,
        "status_changes": status_changes,
    }


def _numeric_delta(
    latest: dict[str, Any],
    previous: dict[str, Any],
    field: DeltaField,
) -> dict[str, Any] | None:
    latest_value = _as_float(latest.get(field.field))
    previous_value = _as_float(previous.get(field.field))
    if latest_value is None or previous_value is None:
        return None
    delta = round(latest_value - previous_value, 4)
    return {
        "champ": field.label,
        "precedent": previous_value,
        "nouveau": latest_value,
        "delta": delta,
        "unite": field.unit,
        "impact": _impact(delta, field.higher_is_better),
    }


def _impact(delta: float, higher_is_better: bool | None) -> str:
    if abs(delta) < 1e-9:
        return "stable"
    if higher_is_better is None:
        return "info"
    is_better = delta > 0 if higher_is_better else delta < 0
    return "amelioration" if is_better else "degradation"


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
