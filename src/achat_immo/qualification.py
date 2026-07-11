"""Criteres canoniques de qualification des analyses probabilistes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ProfitabilityTargets:
    """Seuils financiers communs au sourcing, au solveur et aux relances."""

    target_tri_median: float = 6.0
    target_tri_p10: float = 3.0
    target_coc: float = 0.0
    target_cashflow: float = 0.0
    min_prob_positive_cashflow: float = 0.5

    def __post_init__(self) -> None:
        if not 0 <= self.min_prob_positive_cashflow <= 1:
            raise ValueError("min_prob_positive_cashflow doit etre compris entre 0 et 1.")


@dataclass(frozen=True, slots=True)
class AnalysisTargets(ProfitabilityTargets):
    """Seuils financiers et budget de calcul d'une analyse approfondie."""

    n_scenarios: int = 1000
    n_solver_scenarios: int = 300

    def __post_init__(self) -> None:
        ProfitabilityTargets.__post_init__(self)
        if self.n_scenarios <= 0 or self.n_solver_scenarios <= 0:
            raise ValueError("Les nombres de scenarios doivent etre strictement positifs.")


@dataclass(frozen=True, slots=True)
class QualificationEvaluation:
    """Resultat explicable de l'application des seuils a un resume Monte Carlo."""

    meets_targets: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfitabilityClassification:
    """Qualification separee de la rentabilite et de l'autofinancement."""

    qualification: str
    reasons: tuple[str, ...]


def evaluate_monte_carlo_summary(
    summary: Mapping[str, Any],
    targets: ProfitabilityTargets,
) -> QualificationEvaluation:
    """Evalue toutes les metriques canoniques sans en omettre silencieusement."""

    checks = (
        ("tri_median", targets.target_tri_median, "tri_median_insuffisant"),
        ("tri_p10", targets.target_tri_p10, "tri_p10_insuffisant"),
        ("coc_median", targets.target_coc, "cash_on_cash_insuffisant"),
        (
            "cashflow_premiere_annee_mensuel_p10",
            targets.target_cashflow,
            "cashflow_premiere_annee_p10_insuffisant",
        ),
        (
            "probabilite_cashflow_premiere_annee_positif",
            targets.min_prob_positive_cashflow,
            "probabilite_cashflow_premiere_annee_insuffisante",
        ),
    )
    reasons: list[str] = []
    for metric, threshold, failure_reason in checks:
        value = summary.get(metric)
        if value is None:
            reasons.append(f"metrique_absente:{metric}")
        elif float(value) < threshold:
            reasons.append(failure_reason)
    return QualificationEvaluation(meets_targets=not reasons, reasons=tuple(reasons))


def classify_monte_carlo_summary(
    summary: Mapping[str, Any],
    targets: ProfitabilityTargets,
) -> ProfitabilityClassification:
    """Classe sans confondre rendement patrimonial et besoin de tresorerie."""

    tri_median = summary.get("tri_median")
    tri_p10 = summary.get("tri_p10")
    reasons: list[str] = []
    if tri_median is None or float(tri_median) < targets.target_tri_median:
        reasons.append("tri_median_insuffisant")
        if tri_p10 is None or float(tri_p10) < targets.target_tri_p10:
            reasons.append("tri_p10_insuffisant")
        return ProfitabilityClassification("sous_objectif_rentabilite", tuple(reasons))
    if tri_p10 is None or float(tri_p10) < targets.target_tri_p10:
        return ProfitabilityClassification("rentabilite_fragile", ("tri_p10_insuffisant",))

    full_evaluation = evaluate_monte_carlo_summary(summary, targets)
    cashflow_reasons = tuple(
        reason
        for reason in full_evaluation.reasons
        if reason not in {"tri_median_insuffisant", "tri_p10_insuffisant"}
    )
    if cashflow_reasons:
        return ProfitabilityClassification("rentable_avec_effort_epargne", cashflow_reasons)
    worst_year_cashflow = summary.get("cashflow_mensuel_minimal_median")
    all_years_probability = summary.get("probabilite_toutes_annees_cashflow_positif")
    if (
        worst_year_cashflow is not None
        and float(worst_year_cashflow) >= targets.target_cashflow
        and all_years_probability is not None
        and float(all_years_probability) >= targets.min_prob_positive_cashflow
    ):
        return ProfitabilityClassification("rentable_et_autofinance", ())
    return ProfitabilityClassification(
        "rentable_cashflow_initial_positif",
        ("cashflow_futur_non_autofinance",),
    )
