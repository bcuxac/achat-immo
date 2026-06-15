"""Gestion des reports fiscaux."""

from __future__ import annotations

from achat_immo.engines.taxes_types import ReportFiscal
from achat_immo.engines.taxes_utils import round_euros as _round_euros


def reports_valides(reports: list[ReportFiscal], annee: int, duree_annees: int) -> list[ReportFiscal]:
    return [
        ReportFiscal(report.annee_origine, _round_euros(report.montant))
        for report in reports
        if report.montant > 0 and annee - report.annee_origine <= duree_annees
    ]


def total_reports(reports: list[ReportFiscal]) -> float:
    return _round_euros(sum(report.montant for report in reports))


def consommer_reports(reports: list[ReportFiscal], montant: float) -> tuple[float, list[ReportFiscal]]:
    restant_a_utiliser = max(montant, 0.0)
    utilise = 0.0
    reports_restants: list[ReportFiscal] = []
    for report in reports:
        if restant_a_utiliser <= 0:
            reports_restants.append(report)
            continue
        consommation = min(report.montant, restant_a_utiliser)
        utilise += consommation
        restant = _round_euros(report.montant - consommation)
        restant_a_utiliser -= consommation
        if restant > 0:
            reports_restants.append(ReportFiscal(report.annee_origine, restant))
    return _round_euros(utilise), reports_restants
