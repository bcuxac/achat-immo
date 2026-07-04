"""Serialisation versionnee des configurations de cartographie."""

from __future__ import annotations

from dataclasses import asdict
import json

from achat_immo.models import RegimeFiscal
from achat_immo.qualification import ProfitabilityTargets
from achat_immo.stochastic.assumptions import StochasticAssumptions
from achat_immo.viability.models import (
    InvestorProfile,
    LocalMarketScope,
    ParameterRange,
    ViabilityMapConfig,
)


def serialize_viability_config(config: ViabilityMapConfig) -> str:
    return json.dumps(asdict(config), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deserialize_viability_config(payload: str) -> ViabilityMapConfig:
    data = json.loads(payload)
    investor = dict(data["investor"])
    investor["tax_regime"] = RegimeFiscal(investor["tax_regime"])
    range_fields = {
        name: ParameterRange(**data[name])
        for name in (
            "total_project_budget",
            "equity",
            "surface_m2",
            "price_per_m2",
            "rent_per_m2",
            "annual_charges_per_m2",
            "property_tax_per_m2",
            "initial_works_per_m2",
        )
    }
    return ViabilityMapConfig(
        market=LocalMarketScope(
            city=data["market"]["city"],
            legal_rent_caps_per_m2=tuple(data["market"].get("legal_rent_caps_per_m2", ())),
        ),
        investor=InvestorProfile(**investor),
        targets=ProfitabilityTargets(**data["targets"]),
        risk_assumptions=StochasticAssumptions(**data["risk_assumptions"]),
        property_count=int(data["property_count"]),
        scenarios_per_property=int(data["scenarios_per_property"]),
        worker_count=int(data["worker_count"]),
        seed=int(data["seed"]),
        profile_fingerprint=str(data.get("profile_fingerprint", "")),
        version=str(data.get("version", "viability_map_v1")),
        **range_fields,
    )
