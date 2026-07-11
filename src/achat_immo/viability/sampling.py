"""Plan d'experiences des biens hypothetiques."""

from __future__ import annotations

import math

from scipy.stats import qmc

from achat_immo.viability.models import (
    HypotheticalProperty,
    ParameterRange,
    RentCapCategory,
    ViabilityMapConfig,
)


DIMENSIONS = 8


def sample_hypothetical_properties(config: ViabilityMapConfig) -> tuple[HypotheticalProperty, ...]:
    """Genere un echantillon Sobol reproductible et respecte le plafond local."""

    exponent = math.ceil(math.log2(config.property_count * 16))
    unit_samples = qmc.Sobol(d=DIMENSIONS, scramble=True, seed=config.seed).random_base2(exponent)
    ranges = (
        config.surface_m2,
        config.price_per_m2,
        config.annual_nonrecoverable_charges_per_m2,
        config.property_tax_per_m2,
        config.initial_works_per_m2,
        config.equity,
    )
    frontier_limit = round(config.property_count * config.frontier_share)
    properties = list(_frontier_properties(config, limit=frontier_limit))
    if len(properties) == config.property_count:
        return tuple(properties)
    for sample in unit_samples:
        surface, price_m2, charges_m2, tax_m2, works_m2, equity = (
            _scale(float(value), bounds)
            for value, bounds in zip(
                (sample[0], sample[1], sample[3], sample[4], sample[5], sample[6]),
                ranges,
                strict=True,
            )
        )
        rent_category = _sample_rent_category(config, len(properties))
        legal_rent_cap = (
            rent_category.cap_per_m2
            if rent_category is not None
            else _sample_legacy_rent_cap(config, float(sample[7]))
        )
        rent_maximum = min(config.rent_per_m2.maximum, legal_rent_cap or float("inf"))
        if rent_maximum <= config.rent_per_m2.minimum:
            continue
        rent_m2 = config.rent_per_m2.minimum + float(sample[2]) * (
            rent_maximum - config.rent_per_m2.minimum
        )
        price = surface * price_m2
        initial_works = surface * works_m2
        total_project_cost = price * (1 + config.investor.notary_cost_pct / 100) + initial_works
        if not config.total_project_budget.minimum <= total_project_cost <= config.total_project_budget.maximum:
            continue
        properties.append(
            HypotheticalProperty(
                sample_id=len(properties),
                surface_m2=round(surface, 2),
                price=round(price, 2),
                monthly_rent=round(surface * rent_m2, 2),
                annual_charges=round(surface * charges_m2, 2),
                property_tax=round(surface * tax_m2, 2),
                initial_works=round(initial_works, 2),
                equity=round(equity, 2),
                total_project_cost=round(total_project_cost, 2),
                legal_rent_cap_per_m2=legal_rent_cap,
                rent_cap_category_id=(rent_category.category_id if rent_category else None),
                rent_sector=(rent_category.sector if rent_category else None),
                room_count=(rent_category.room_count if rent_category else None),
                construction_period=(rent_category.construction_period if rent_category else None),
                rent_legality_verifiable=config.market.legal_rent_is_verifiable_without_previous_lease,
                sample_kind="sobol",
            )
        )
        if len(properties) == config.property_count:
            break
    if len(properties) < config.property_count:
        raise ValueError(
            "Le plan Sobol n'a pas produit assez de biens dans la plage de budget total ; "
            "elargis les plages structurelles ou reduis le nombre de points."
        )
    return tuple(properties)


def _frontier_properties(
    config: ViabilityMapConfig,
    *,
    limit: int,
) -> tuple[HypotheticalProperty, ...]:
    """Ajoute les bornes favorables explicites de chaque categorie reglementaire."""

    categories = config.market.rent_cap_categories
    if not categories or limit <= 0:
        return ()
    properties: list[HypotheticalProperty] = []
    acquisition_factor = 1 + config.investor.notary_cost_pct / 100
    surface_count = math.ceil(limit / len(categories))
    surface_exponent = math.ceil(math.log2(surface_count)) if surface_count > 1 else 0
    surface_positions = qmc.Sobol(d=1, scramble=True, seed=config.seed + 10_000).random_base2(
        surface_exponent
    )[:surface_count, 0]
    for surface_position in surface_positions:
        surface = _scale(surface_position, config.surface_m2)
        for category in categories:
            rent_m2 = min(config.rent_per_m2.maximum, category.cap_per_m2)
            if rent_m2 < config.rent_per_m2.minimum:
                continue
            initial_works = surface * config.initial_works_per_m2.minimum
            price = max(
                surface * config.price_per_m2.minimum,
                (config.total_project_budget.minimum - initial_works) / acquisition_factor,
            )
            if price > surface * config.price_per_m2.maximum:
                continue
            total_project_cost = price * acquisition_factor + initial_works
            if total_project_cost > config.total_project_budget.maximum:
                continue
            properties.append(
                HypotheticalProperty(
                    sample_id=len(properties),
                    surface_m2=round(surface, 2),
                    price=round(price, 2),
                    monthly_rent=round(surface * rent_m2, 2),
                    annual_charges=round(
                        surface * config.annual_nonrecoverable_charges_per_m2.minimum,
                        2,
                    ),
                    property_tax=round(surface * config.property_tax_per_m2.minimum, 2),
                    initial_works=round(initial_works, 2),
                    equity=round(config.equity.maximum, 2),
                    total_project_cost=round(total_project_cost, 2),
                    legal_rent_cap_per_m2=category.cap_per_m2,
                    rent_cap_category_id=category.category_id,
                    rent_sector=category.sector,
                    room_count=category.room_count,
                    construction_period=category.construction_period,
                    rent_legality_verifiable=True,
                    sample_kind="favorable_frontier",
                )
            )
            if len(properties) == min(limit, config.property_count):
                return tuple(properties)
    return tuple(properties)


def _scale(value: float, bounds: ParameterRange) -> float:
    return bounds.minimum + value * (bounds.maximum - bounds.minimum)


def _sample_rent_category(
    config: ViabilityMapConfig,
    accepted_property_index: int,
) -> RentCapCategory | None:
    categories = config.market.rent_cap_categories
    if not categories:
        return None
    return categories[accepted_property_index % len(categories)]


def _sample_legacy_rent_cap(config: ViabilityMapConfig, unit_value: float) -> float | None:
    caps = config.market.legal_rent_caps_per_m2
    if not caps:
        return None
    index = min(int(unit_value * len(caps)), len(caps) - 1)
    return caps[index]
