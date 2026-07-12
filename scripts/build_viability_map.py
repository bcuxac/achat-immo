#!/usr/bin/env python3
"""Construit une premiere carte de viabilite pour un segment local."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import pandas as pd

from achat_immo.city_profiles import profile_for_city, rent_reference_records
from achat_immo.models import ModeLocation, RegimeFiscal
from achat_immo.storage import get_investment_profile, open_database, save_simulation_map
from achat_immo.viability import (
    LocalMarketScope,
    RentCapCategory,
    ViabilityMapConfig,
    build_viability_map,
    viability_config_from_profile,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Construire une carte de viabilite locale.")
    parser.add_argument("--properties", type=int, help="Remplace le nombre de biens du profil.")
    parser.add_argument("--scenarios", type=int, help="Remplace les scenarios par bien du profil.")
    parser.add_argument("--workers", type=int, help="Remplace le nombre de workers du profil.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--database", help="Base contenant le profil actif.")
    parser.add_argument("--no-persist", action="store_true", help="N'enregistre pas la carte dans la base.")
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
    """Construit la carte avec les seules lignes legales applicables au mode fiscal."""

    city_profile = profile_for_city(profile.target_city)
    mode = (
        ModeLocation.MEUBLEE
        if profile.reference_tax_regime in {RegimeFiscal.LMNP_REEL, RegimeFiscal.MICRO_BIC}
        else ModeLocation.NUE
    )
    records = rent_reference_records(profile.target_city, mode)
    market = LocalMarketScope(
        city=profile.target_city,
        rent_cap_categories=tuple(
            RentCapCategory(
                category_id=record.category_id,
                sector=record.sector,
                room_count=record.room_count,
                construction_period=record.construction_period.value,
                rental_mode=record.rental_mode,
                cap_per_m2=record.cap_per_m2,
                source_url=record.source_url,
            )
            for record in records
        ),
        rent_control_kind=(city_profile.rent_control_kind.value if city_profile else "inconnu"),
        source_urls=(city_profile.source_urls if city_profile else ()),
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
                "rent_cap_category_id": property_.rent_cap_category_id,
                "rent_sector": property_.rent_sector,
                "room_count": property_.room_count,
                "construction_period": property_.construction_period,
                "rent_legality_verifiable": property_.rent_legality_verifiable,
                "sample_kind": property_.sample_kind,
                "calculation_status": point.calculation_status,
                "warnings": ",".join(point.warnings),
                "tri_median": point.tri_median,
                "tri_p10": point.tri_p10,
                "cash_on_cash_median": point.cash_on_cash_median,
                "prudent_monthly_cashflow": point.prudent_monthly_cashflow,
                "positive_cashflow_probability": point.positive_cashflow_probability,
                "first_year_monthly_cashflow_median": point.first_year_monthly_cashflow_median,
                "first_year_monthly_cashflow_p10": point.first_year_monthly_cashflow_p10,
                "all_years_positive_cashflow_probability": (
                    point.all_years_positive_cashflow_probability
                ),
                "cumulative_positive_cashflow_probability": (
                    point.cumulative_positive_cashflow_probability
                ),
                "valid_scenarios": point.valid_scenarios,
            }
        )
    return rows


def main() -> None:
    args = build_parser().parse_args()
    conn = open_database(args.database)
    try:
        profile = get_investment_profile(conn)
        config = default_city_config(
            profile=profile,
            properties=args.properties,
            scenarios=args.scenarios,
            workers=args.workers,
            seed=args.seed,
        )
        viability_map = build_viability_map(config)
        map_id = None if args.no_persist else save_simulation_map(conn, viability_map)
    finally:
        conn.close()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    city_slug = config.market.city.lower().replace(" ", "_")
    stem = f"{city_slug}_{config.version}_seed{config.seed}"
    csv_path = args.output_dir / f"{stem}.csv"
    metadata_path = args.output_dir / f"{stem}.json"
    pd.DataFrame(map_rows(viability_map)).to_csv(csv_path, index=False)
    metadata = {
        "config": asdict(config),
        "point_count": len(viability_map.points),
        "calculated_count": viability_map.calculated_count,
        "data_file": csv_path.name,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Carte generee : {len(viability_map.points)} points, "
        f"{viability_map.calculated_count} calcules sans qualification, "
        f"base={'non persistee' if map_id is None else f'carte #{map_id}'}.\n{csv_path}\n{metadata_path}"
    )


if __name__ == "__main__":
    main()
