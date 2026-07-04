#!/usr/bin/env python3
"""Construit une premiere carte de viabilite pour un segment local."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from achat_immo.city_profiles import legal_rent_caps_per_m2
from achat_immo.storage import get_investment_profile, open_database
from achat_immo.viability import (
    LocalMarketScope,
    ViabilityMapConfig,
    build_viability_map,
    viability_config_from_profile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Construire une carte de viabilite Grenoble.")
    parser.add_argument("--properties", type=int, help="Remplace le nombre de biens du profil.")
    parser.add_argument("--scenarios", type=int, help="Remplace les scenarios par bien du profil.")
    parser.add_argument("--workers", type=int, help="Remplace le nombre de workers du profil.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--database", help="Base contenant le profil actif.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/viability"))
    return parser


def default_city_config(
    *,
    profile,
    properties: int | None,
    scenarios: int | None,
    workers: int | None,
    seed: int,
) -> ViabilityMapConfig:
    """Construit la carte de la ville active avec tous ses plafonds connus."""

    market = LocalMarketScope(
        city=profile.target_city,
        legal_rent_caps_per_m2=legal_rent_caps_per_m2(profile.target_city),
    )
    return viability_config_from_profile(
        profile,
        market,
        property_count=properties,
        scenarios_per_property=scenarios,
        worker_count=workers,
        seed=seed,
    )


def map_rows(viability_map) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for point in viability_map.points:
        property_ = point.property
        rows.append(
            {
                "sample_id": property_.sample_id,
                "surface_m2": property_.surface_m2,
                "price": property_.price,
                "price_per_m2": property_.price_per_m2,
                "monthly_rent": property_.monthly_rent,
                "rent_per_m2": property_.rent_per_m2,
                "annual_charges": property_.annual_charges,
                "property_tax": property_.property_tax,
                "initial_works": property_.initial_works,
                "equity": property_.equity,
                "total_project_cost": property_.total_project_cost,
                "legal_rent_cap_per_m2": property_.legal_rent_cap_per_m2,
                "qualification": point.qualification,
                "reasons": ",".join(point.reasons),
                "tri_median": point.tri_median,
                "tri_p10": point.tri_p10,
                "cash_on_cash_median": point.cash_on_cash_median,
                "prudent_monthly_cashflow": point.prudent_monthly_cashflow,
                "positive_cashflow_probability": point.positive_cashflow_probability,
                "valid_scenarios": point.valid_scenarios,
            }
        )
    return rows


def main() -> None:
    args = build_parser().parse_args()
    conn = open_database(args.database)
    try:
        profile = get_investment_profile(conn)
    finally:
        conn.close()
    config = default_city_config(
        profile=profile,
        properties=args.properties,
        scenarios=args.scenarios,
        workers=args.workers,
        seed=args.seed,
    )
    viability_map = build_viability_map(config)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    city_slug = config.market.city.lower().replace(" ", "_")
    stem = f"{city_slug}_{config.version}_seed{config.seed}"
    csv_path = args.output_dir / f"{stem}.csv"
    metadata_path = args.output_dir / f"{stem}.json"
    pd.DataFrame(map_rows(viability_map)).to_csv(csv_path, index=False)
    metadata = {
        "config": asdict(config),
        "point_count": len(viability_map.points),
        "viable_count": viability_map.viable_count,
        "data_file": csv_path.name,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Carte generee : {len(viability_map.points)} points, "
        f"{viability_map.viable_count} robustement viables.\n{csv_path}\n{metadata_path}"
    )


if __name__ == "__main__":
    main()
