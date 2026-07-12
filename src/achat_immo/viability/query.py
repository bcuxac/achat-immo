"""Interrogation rapide d'une carte avec des donnees completes ou partielles."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from achat_immo.viability.models import ParameterRange, ViabilityMap, ViabilityPoint


@dataclass(frozen=True, slots=True)
class PropertyObservation:
    surface_m2: float
    price: float
    monthly_rent: float | None = None
    annual_charges: float | None = None
    property_tax: float | None = None
    initial_works: float | None = None
    legal_rent_cap_per_m2: float | None = None
    previous_monthly_rent: float | None = None


@dataclass(frozen=True, slots=True)
class MapEstimate:
    status: str
    neighbor_count: int
    nearest_distance: float | None
    tri_median: float | None
    tri_p10: float | None
    cash_on_cash_median: float | None
    first_year_monthly_cashflow_median: float | None
    first_year_monthly_cashflow_p10: float | None
    prudent_monthly_cashflow: float | None
    cumulative_positive_cashflow_probability: float | None
    tri_percentile: float | None
    missing_fields: tuple[str, ...]
    warnings: tuple[str, ...]


def estimate_observation(
    viability_map: ViabilityMap,
    observation: PropertyObservation,
    *,
    neighbor_count: int = 15,
) -> MapEstimate:
    if observation.surface_m2 <= 0 or observation.price <= 0:
        raise ValueError("La surface et le prix doivent etre strictement positifs.")
    if not viability_map.points:
        return MapEstimate(
            "map_unavailable",
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            (),
            ("carte_vide",),
        )

    vector, known, missing = _observation_vector(viability_map, observation)
    warnings: list[str] = []
    if (
        viability_map.config.market.rent_control_kind == "zone_tendue_relocation"
        and observation.previous_monthly_rent is None
    ):
        missing = (*missing, "loyer_precedent")
        warnings.append("loyer_legal_non_verifiable_sans_bail_precedent")
    point_matrix = np.asarray([_point_vector(viability_map, point) for point in viability_map.points])
    distances = np.sqrt(np.mean((point_matrix[:, known] - vector[known]) ** 2, axis=1))
    neighbor_count = min(max(neighbor_count, 1), len(viability_map.points))
    neighbor_indexes = np.argsort(distances)[:neighbor_count]
    selected_distances = distances[neighbor_indexes]
    weights = 1.0 / np.maximum(selected_distances, 1e-9)
    points = [viability_map.points[index] for index in neighbor_indexes]
    tri_median = _weighted_optional([point.tri_median for point in points], weights)
    all_tri = np.asarray(
        [point.tri_median for point in viability_map.points if point.tri_median is not None],
        dtype=float,
    )
    tri_percentile = (
        float(np.mean(all_tri <= tri_median)) if tri_median is not None and len(all_tri) else None
    )
    if missing:
        warnings.append("estimation_partielle_donnees_manquantes")
    return MapEstimate(
        "partial_estimate" if missing else "estimated",
        neighbor_count,
        round(float(selected_distances[0]), 6),
        _rounded(tri_median),
        _rounded(_weighted_optional([point.tri_p10 for point in points], weights)),
        _rounded(_weighted_optional([point.cash_on_cash_median for point in points], weights)),
        _rounded(
            _weighted_optional(
                [point.first_year_monthly_cashflow_median for point in points], weights
            )
        ),
        _rounded(
            _weighted_optional([point.first_year_monthly_cashflow_p10 for point in points], weights)
        ),
        _rounded(_weighted_optional([point.prudent_monthly_cashflow for point in points], weights)),
        _rounded(
            _weighted_optional(
                [point.cumulative_positive_cashflow_probability for point in points], weights
            ),
            digits=4,
        ),
        _rounded(tri_percentile, digits=4),
        missing,
        tuple(warnings),
    )


def _weighted_optional(values: list[float | None], weights: np.ndarray) -> float | None:
    known = np.asarray([value is not None for value in values], dtype=bool)
    if not np.any(known):
        return None
    numeric = np.asarray([0.0 if value is None else value for value in values], dtype=float)
    return float(np.average(numeric[known], weights=weights[known]))


def _rounded(value: float | None, *, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def _observation_vector(
    viability_map: ViabilityMap,
    observation: PropertyObservation,
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    config = viability_map.config
    surface = observation.surface_m2
    has_local_caps = bool(config.market.legal_rent_caps_per_m2)
    cap_value = observation.legal_rent_cap_per_m2 if has_local_caps else 0.5
    values: list[float | None] = [
        surface,
        observation.price / surface,
        observation.monthly_rent / surface if observation.monthly_rent is not None else None,
        observation.annual_charges / surface if observation.annual_charges is not None else None,
        observation.property_tax / surface if observation.property_tax is not None else None,
        observation.initial_works / surface if observation.initial_works is not None else None,
        (config.equity.minimum + config.equity.maximum) / 2,
        (
            observation.price * (1 + config.investor.notary_cost_pct / 100) + observation.initial_works
            if observation.initial_works is not None
            else None
        ),
        cap_value,
    ]
    names = (
        "surface",
        "prix_m2",
        "loyer",
        "charges",
        "taxe_fonciere",
        "travaux",
        "apport",
        "cout_total",
        "plafond_loyer",
    )
    bounds = _feature_bounds(viability_map)
    normalized = np.asarray(
        [_normalize(value, bound) if value is not None else 0.0 for value, bound in zip(values, bounds, strict=True)]
    )
    known = np.asarray([value is not None for value in values], dtype=bool)
    missing = tuple(name for name, value in zip(names, values, strict=True) if value is None)
    return normalized, known, missing


def _point_vector(viability_map: ViabilityMap, point: ViabilityPoint) -> list[float]:
    property_ = point.property
    values = (
        property_.surface_m2,
        property_.price_per_m2,
        property_.rent_per_m2,
        property_.annual_charges / property_.surface_m2,
        property_.property_tax / property_.surface_m2,
        property_.initial_works / property_.surface_m2,
        property_.equity,
        property_.total_project_cost,
        property_.legal_rent_cap_per_m2,
    )
    return [
        _normalize(value if value is not None else _midpoint(bound), bound)
        for value, bound in zip(values, _feature_bounds(viability_map), strict=True)
    ]


def _feature_bounds(viability_map: ViabilityMap) -> tuple[ParameterRange, ...]:
    config = viability_map.config
    caps = config.market.legal_rent_caps_per_m2
    cap_bounds = ParameterRange(min(caps), max(caps)) if len(caps) > 1 else ParameterRange(0.0, max(caps[0], 1.0)) if caps else ParameterRange(0.0, 1.0)
    return (
        config.surface_m2,
        config.price_per_m2,
        config.rent_per_m2,
        config.annual_nonrecoverable_charges_per_m2,
        config.property_tax_per_m2,
        config.initial_works_per_m2,
        config.equity,
        config.total_project_budget,
        cap_bounds,
    )


def _normalize(value: float, bounds: ParameterRange) -> float:
    return (value - bounds.minimum) / (bounds.maximum - bounds.minimum)


def _midpoint(bounds: ParameterRange) -> float:
    return math.fsum((bounds.minimum, bounds.maximum)) / 2
