"""Validation hors echantillon du prefiltre de viabilite."""

from __future__ import annotations

from dataclasses import dataclass

from achat_immo.viability.models import ViabilityMap
from achat_immo.viability.query import PropertyObservation, qualify_observation


@dataclass(frozen=True, slots=True)
class ValidationReport:
    sample_count: int
    truly_viable: int
    predicted_positive: int
    true_positives: int
    false_negatives: int
    recall: float | None
    precision: float | None
    deep_analysis_ratio: float


def validate_viability_map(reference: ViabilityMap, held_out: ViabilityMap) -> ValidationReport:
    true_positives = 0
    false_negatives = 0
    predicted_positive = 0
    truly_viable = 0
    positive_labels = {"robustement_viable", "potentiellement_viable", "a_enrichir"}
    for point in held_out.points:
        property_ = point.property
        result = qualify_observation(
            reference,
            PropertyObservation(
                surface_m2=property_.surface_m2,
                price=property_.price,
                monthly_rent=property_.monthly_rent,
                annual_charges=property_.annual_charges,
                property_tax=property_.property_tax,
                initial_works=property_.initial_works,
                legal_rent_cap_per_m2=property_.legal_rent_cap_per_m2,
            ),
        )
        truth = point.qualification in {
            "rentable_et_autofinance",
            "rentable_cashflow_initial_positif",
            "rentable_avec_effort_epargne",
        }
        predicted = result.qualification in positive_labels
        truly_viable += int(truth)
        predicted_positive += int(predicted)
        true_positives += int(truth and predicted)
        false_negatives += int(truth and not predicted)
    recall = true_positives / truly_viable if truly_viable else None
    precision = true_positives / predicted_positive if predicted_positive else None
    count = len(held_out.points)
    return ValidationReport(
        sample_count=count,
        truly_viable=truly_viable,
        predicted_positive=predicted_positive,
        true_positives=true_positives,
        false_negatives=false_negatives,
        recall=recall,
        precision=precision,
        deep_analysis_ratio=predicted_positive / count if count else 0.0,
    )
