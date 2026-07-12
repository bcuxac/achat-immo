"""Validation hors echantillon de l'interpolation numerique d'une carte."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from achat_immo.viability.models import ViabilityMap
from achat_immo.viability.query import PropertyObservation, estimate_observation


@dataclass(frozen=True, slots=True)
class ValidationReport:
    sample_count: int
    estimated_count: int
    tri_median_mae: float | None
    tri_median_p95_absolute_error: float | None
    tri_p10_mae: float | None
    first_year_cashflow_p10_mae: float | None
    mean_nearest_distance: float | None


def validate_viability_map(reference: ViabilityMap, held_out: ViabilityMap) -> ValidationReport:
    """Mesure l'erreur d'interpolation, sans appliquer de seuil de decision."""

    tri_errors: list[float] = []
    tri_p10_errors: list[float] = []
    cashflow_errors: list[float] = []
    distances: list[float] = []
    estimated_count = 0
    for point in held_out.points:
        property_ = point.property
        estimate = estimate_observation(
            reference,
            PropertyObservation(
                surface_m2=property_.surface_m2,
                price=property_.price,
                monthly_rent=property_.monthly_rent,
                annual_charges=property_.annual_charges,
                property_tax=property_.property_tax,
                initial_works=property_.initial_works,
                legal_rent_cap_per_m2=property_.legal_rent_cap_per_m2,
                previous_monthly_rent=property_.monthly_rent,
            ),
        )
        estimated_count += int(estimate.status == "estimated")
        if estimate.nearest_distance is not None:
            distances.append(estimate.nearest_distance)
        if estimate.tri_median is not None and point.tri_median is not None:
            tri_errors.append(abs(estimate.tri_median - point.tri_median))
        if estimate.tri_p10 is not None and point.tri_p10 is not None:
            tri_p10_errors.append(abs(estimate.tri_p10 - point.tri_p10))
        if (
            estimate.first_year_monthly_cashflow_p10 is not None
            and point.first_year_monthly_cashflow_p10 is not None
        ):
            cashflow_errors.append(
                abs(
                    estimate.first_year_monthly_cashflow_p10
                    - point.first_year_monthly_cashflow_p10
                )
            )
    return ValidationReport(
        sample_count=len(held_out.points),
        estimated_count=estimated_count,
        tri_median_mae=_mean(tri_errors),
        tri_median_p95_absolute_error=_percentile(tri_errors, 95),
        tri_p10_mae=_mean(tri_p10_errors),
        first_year_cashflow_p10_mae=_mean(cashflow_errors),
        mean_nearest_distance=_mean(distances),
    )


def _mean(values: list[float]) -> float | None:
    return round(float(np.mean(values)), 4) if values else None


def _percentile(values: list[float], percentile: float) -> float | None:
    return round(float(np.percentile(values, percentile)), 4) if values else None
