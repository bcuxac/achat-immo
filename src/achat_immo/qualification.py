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
            "cashflow_mensuel_minimal_median",
            targets.target_cashflow,
            "cashflow_prudent_insuffisant",
        ),
        (
            "probabilite_cashflow_cumule_positif",
            targets.min_prob_positive_cashflow,
            "probabilite_cashflow_insuffisante",
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
