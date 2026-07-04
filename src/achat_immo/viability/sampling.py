"""Plan d'experiences des biens hypothetiques."""

from __future__ import annotations

import math

from scipy.stats import qmc

from achat_immo.viability.models import HypotheticalProperty, ParameterRange, ViabilityMapConfig


DIMENSIONS = 8


def sample_hypothetical_properties(config: ViabilityMapConfig) -> tuple[HypotheticalProperty, ...]:
    """Genere un echantillon Sobol reproductible et respecte le plafond local."""

    exponent = math.ceil(math.log2(config.property_count * 16))
    unit_samples = qmc.Sobol(d=DIMENSIONS, scramble=True, seed=config.seed).random_base2(exponent)
    ranges = (
        config.surface_m2,
        config.price_per_m2,
        config.annual_charges_per_m2,
        config.property_tax_per_m2,
        config.initial_works_per_m2,
        config.equity,
    )
    properties: list[HypotheticalProperty] = []
    for sample in unit_samples:
        surface, price_m2, charges_m2, tax_m2, works_m2, equity = (
            _scale(float(value), bounds)
            for value, bounds in zip(
                (sample[0], sample[1], sample[3], sample[4], sample[5], sample[6]),
                ranges,
                strict=True,
            )
        )
        legal_rent_cap = _sample_rent_cap(config, float(sample[7]))
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


def _scale(value: float, bounds: ParameterRange) -> float:
    return bounds.minimum + value * (bounds.maximum - bounds.minimum)


def _sample_rent_cap(config: ViabilityMapConfig, unit_value: float) -> float | None:
    caps = config.market.legal_rent_caps_per_m2
    if not caps:
        return None
    index = min(int(unit_value * len(caps)), len(caps) - 1)
    return caps[index]
