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


@dataclass(frozen=True, slots=True)
class FastQualification:
    qualification: str
    viable_neighbor_ratio: float | None
    distance_to_viable: float | None
    estimated_max_price: float | None
    missing_fields: tuple[str, ...]
    reasons: tuple[str, ...]


def qualify_observation(
    viability_map: ViabilityMap,
    observation: PropertyObservation,
    *,
    neighbor_count: int = 15,
) -> FastQualification:
    if observation.surface_m2 <= 0 or observation.price <= 0:
        raise ValueError("La surface et le prix doivent etre strictement positifs.")
    if not viability_map.points:
        return FastQualification("carte_indisponible", None, None, None, (), ("carte_vide",))

    vector, known, missing = _observation_vector(viability_map, observation)
    point_matrix = np.asarray([_point_vector(viability_map, point) for point in viability_map.points])
    distances = np.sqrt(np.mean((point_matrix[:, known] - vector[known]) ** 2, axis=1))
    neighbor_count = min(max(neighbor_count, 1), len(viability_map.points))
    neighbor_indexes = np.argsort(distances)[:neighbor_count]
    viable_mask = np.asarray(
        [point.qualification == "robustement_viable" for point in viability_map.points],
        dtype=bool,
    )
    ratio = float(np.mean(viable_mask[neighbor_indexes]))
    viable_indexes = np.flatnonzero(viable_mask)
    if len(viable_indexes) == 0:
        return FastQualification(
            "carte_non_conclusive",
            ratio,
            None,
            None,
            missing,
            ("aucun_point_viable_carte_a_renforcer",),
        )

    viable_distances = distances[viable_indexes]
    closest_order = viable_indexes[np.argsort(viable_distances)]
    closest_viable = closest_order[: min(10, len(closest_order))]
    distance_to_viable = float(np.min(viable_distances))
    estimated_max_price = float(max(viability_map.points[index].property.price for index in closest_viable))

    if missing:
        qualification = "a_enrichir"
        reasons = ("donnees_manquantes",)
    elif ratio >= 0.6:
        qualification = "robustement_viable"
        reasons = ("voisinage_majoritairement_viable",)
    elif ratio >= 0.2:
        qualification = "potentiellement_viable"
        reasons = ("voisinage_partiellement_viable",)
    else:
        qualification = "non_viable"
        reasons = ("voisinage_non_viable",)
    return FastQualification(
        qualification,
        round(ratio, 4),
        round(distance_to_viable, 6),
        round(estimated_max_price, 2),
        missing,
        reasons,
    )


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
        config.annual_charges_per_m2,
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
