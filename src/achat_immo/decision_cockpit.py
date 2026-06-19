"""Synthese decisionnelle pour le cockpit Streamlit."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any


FUNNEL_LABELS: dict[str, str] = {
    "nouveau": "Nouveau",
    "extraction_bloquee": "Extraction bloquee",
    "donnees_insuffisantes": "Donnees insuffisantes",
    "hors_criteres": "Hors criteres",
    "a_verifier": "A verifier",
    "shortlist": "Shortlist",
    "contacte": "Contacte",
    "offre_faite": "Offre faite",
    "rejete": "Rejete",
    "archive": "Archive",
}

FUNNEL_ORDER: tuple[str, ...] = (
    "nouveau",
    "extraction_bloquee",
    "donnees_insuffisantes",
    "hors_criteres",
    "a_verifier",
    "shortlist",
    "contacte",
    "offre_faite",
    "rejete",
    "archive",
)

STATUS_TO_STAGE: dict[str, str] = {
    "diagnostic_incomplet": "donnees_insuffisantes",
    "donnees_insuffisantes": "donnees_insuffisantes",
    "hors_criteres": "hors_criteres",
    "a_analyser": "a_verifier",
    "a_verifier": "a_verifier",
    "a_visiter": "shortlist",
    "a_negocier": "shortlist",
    "favori": "shortlist",
    "shortlist": "shortlist",
    "contacte": "contacte",
    "offre_faite": "offre_faite",
    "rejete": "rejete",
    "archive": "archive",
}

ACTIVE_STAGES: set[str] = {"nouveau", "extraction_bloquee", "donnees_insuffisantes", "a_verifier", "shortlist"}


@dataclass(frozen=True, slots=True)
class CockpitSnapshot:
    funnel_counts: dict[str, int]
    priority_items: list[dict[str, Any]]
    queue_counts: dict[str, int]
    latest_sourcing_run: dict[str, Any] | None
    totals: dict[str, int]


def build_cockpit_snapshot(
    annonces: list[dict[str, Any]],
    extraction_runs: list[dict[str, Any]],
    analysis_runs: list[dict[str, Any]],
    sourcing_queue: list[dict[str, Any]],
    sourcing_runs: list[dict[str, Any]],
) -> CockpitSnapshot:
    """Agrege les donnees stockees en vue cockpit."""

    latest_extraction = _latest_by_annonce(extraction_runs)
    latest_analysis = _latest_by_annonce(analysis_runs)
    blocked_queue_by_annonce = _blocked_queue_by_annonce(sourcing_queue)

    items = [
        _build_priority_item(
            annonce,
            latest_extraction.get(int(annonce["id"])),
            latest_analysis.get(int(annonce["id"])),
            blocked_queue_by_annonce.get(int(annonce["id"])),
        )
        for annonce in annonces
        if annonce.get("id") is not None
    ]
    funnel_counts = {stage: 0 for stage in FUNNEL_ORDER}
    funnel_counts.update(Counter(item["stage"] for item in items))
    queue_counts = dict(Counter(str(row.get("status") or "unknown") for row in sourcing_queue))
    active_count = sum(1 for item in items if item["stage"] in ACTIVE_STAGES)

    return CockpitSnapshot(
        funnel_counts=funnel_counts,
        priority_items=sorted(items, key=_priority_sort_key),
        queue_counts=queue_counts,
        latest_sourcing_run=sourcing_runs[0] if sourcing_runs else None,
        totals={
            "annonces": len(annonces),
            "actives": active_count,
            "queue_pending": queue_counts.get("pending", 0),
            "queue_blocked": queue_counts.get("blocked", 0),
            "shortlist": funnel_counts.get("shortlist", 0),
        },
    )


def _build_priority_item(
    annonce: dict[str, Any],
    extraction: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
    blocked_queue: dict[str, Any] | None,
) -> dict[str, Any]:
    missing_fields = _missing_fields(annonce, extraction)
    stage = _stage_for_annonce(annonce, extraction, analysis, blocked_queue, missing_fields)
    tri_p50 = _optional_float(annonce.get("tri_p50"))
    cashflow_p50 = _optional_float(annonce.get("cashflow_p50"))
    coc_p50 = _optional_float(annonce.get("coc_p50"))
    recommended_price = _optional_float(annonce.get("prix_cible_recommande"))
    price = _optional_float(annonce.get("prix_affiche")) or 0.0
    discount_pct = ((recommended_price - price) / price * 100) if recommended_price is not None and price > 0 else None

    return {
        "id": int(annonce["id"]),
        "stage": stage,
        "etape": FUNNEL_LABELS.get(stage, stage),
        "ville": annonce.get("ville") or "",
        "quartier": annonce.get("quartier") or "",
        "prix_affiche": price,
        "prix_cible_recommande": recommended_price,
        "ecart_prix_pct": discount_pct,
        "tri_p50": tri_p50,
        "cashflow_p50": cashflow_p50,
        "coc_p50": coc_p50,
        "dpe": annonce.get("dpe") or "",
        "statut": annonce.get("statut") or "",
        "donnees_manquantes": ", ".join(missing_fields),
        "signal": _signal_for_item(stage, missing_fields, extraction, analysis, blocked_queue),
        "action": _action_for_stage(stage),
        "score_tri": _opportunity_score(tri_p50, cashflow_p50, coc_p50, discount_pct),
    }


def _stage_for_annonce(
    annonce: dict[str, Any],
    extraction: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
    blocked_queue: dict[str, Any] | None,
    missing_fields: list[str],
) -> str:
    if blocked_queue is not None:
        return "extraction_bloquee"

    status = str(annonce.get("statut") or "")
    if status in {"rejete", "archive", "contacte", "offre_faite", "shortlist", "favori", "a_visiter", "a_negocier"}:
        return STATUS_TO_STAGE[status]

    analysis_status = str((analysis or {}).get("status") or "")
    if status == "hors_criteres" or analysis_status == "hors_criteres":
        return "hors_criteres"

    if len(missing_fields) >= 2 or status in {"diagnostic_incomplet", "donnees_insuffisantes"}:
        return "donnees_insuffisantes"

    if analysis is not None or extraction is not None or status in {"a_analyser", "a_verifier"}:
        return "a_verifier"

    return "nouveau"


def _missing_fields(annonce: dict[str, Any], extraction: dict[str, Any] | None) -> list[str]:
    missing: list[str] = []
    if not annonce.get("dpe"):
        missing.append("DPE")
    if _optional_float(annonce.get("loyer_hc_mensuel")) in {None, 0.0}:
        missing.append("Loyer")
    if _optional_float(annonce.get("taxe_fonciere")) in {None, 0.0}:
        missing.append("Taxe fonciere")
    if extraction and extraction.get("missing_fields"):
        for value in str(extraction["missing_fields"]).split(","):
            cleaned = value.strip()
            if cleaned and cleaned not in missing:
                missing.append(cleaned)
    return missing


def _signal_for_item(
    stage: str,
    missing_fields: list[str],
    extraction: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
    blocked_queue: dict[str, Any] | None,
) -> str:
    if blocked_queue is not None:
        return str(blocked_queue.get("last_error") or "Source bloquee.")
    if missing_fields:
        return "Champs a completer: " + ", ".join(missing_fields[:4])
    if extraction and extraction.get("red_flags"):
        return "Red flags: " + str(extraction["red_flags"])
    if analysis and analysis.get("solver_status"):
        return "Solveur: " + str(analysis["solver_status"])
    return FUNNEL_LABELS.get(stage, stage)


def _action_for_stage(stage: str) -> str:
    actions = {
        "nouveau": "Lancer extraction/analyse",
        "extraction_bloquee": "Changer source ou importer texte",
        "donnees_insuffisantes": "Completer hypotheses",
        "hors_criteres": "Archiver ou surveiller prix",
        "a_verifier": "Verifier preuves et hypotheses",
        "shortlist": "Preparer contact",
        "contacte": "Relancer vendeur",
        "offre_faite": "Suivre offre",
        "rejete": "Aucune action",
        "archive": "Aucune action",
    }
    return actions.get(stage, "Verifier")


def _latest_by_annonce(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    latest: dict[int, dict[str, Any]] = {}
    for row in rows:
        annonce_id = row.get("annonce_id")
        if annonce_id is not None:
            latest.setdefault(int(annonce_id), row)
    return latest


def _blocked_queue_by_annonce(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    blocked: dict[int, dict[str, Any]] = {}
    for row in rows:
        annonce_id = row.get("annonce_id")
        if annonce_id is not None and row.get("status") == "blocked":
            blocked.setdefault(int(annonce_id), row)
    return blocked


def _opportunity_score(
    tri_p50: float | None,
    cashflow_p50: float | None,
    coc_p50: float | None,
    discount_pct: float | None,
) -> float:
    score = 0.0
    if tri_p50 is not None:
        score += tri_p50 * 10
    if coc_p50 is not None:
        score += coc_p50 * 4
    if cashflow_p50 is not None:
        score += cashflow_p50 / 8
    if discount_pct is not None:
        score += max(0.0, -discount_pct)
    return round(score, 1)


def _priority_sort_key(item: dict[str, Any]) -> tuple[int, float, int]:
    stage_priority = {
        "shortlist": 0,
        "a_verifier": 1,
        "donnees_insuffisantes": 2,
        "extraction_bloquee": 3,
        "nouveau": 4,
        "contacte": 5,
        "offre_faite": 6,
        "hors_criteres": 7,
        "rejete": 8,
        "archive": 9,
    }
    return (stage_priority.get(str(item["stage"]), 99), -float(item.get("score_tri") or 0.0), -int(item["id"]))


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
