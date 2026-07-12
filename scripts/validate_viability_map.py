#!/usr/bin/env python3
"""Valide une carte active sur un nouvel echantillon Sobol."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json

from achat_immo.investment_profile import InvestmentProfile
from achat_immo.storage import get_active_simulation_map, get_investment_profile, open_database
from achat_immo.viability.builder import build_viability_map
from achat_immo.viability.validation import validate_viability_map


def main() -> None:
    parser = argparse.ArgumentParser(description="Validation hors echantillon d'une carte de viabilite.")
    parser.add_argument("--database", help="Base contenant la carte active.")
    parser.add_argument("--properties", type=int, default=16)
    parser.add_argument("--scenarios", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1042)
    parser.add_argument("--max-tri-mae", type=float, default=2.0)
    args = parser.parse_args()

    conn = open_database(args.database)
    try:
        profile: InvestmentProfile = get_investment_profile(conn)
        active = get_active_simulation_map(conn, profile.target_city, profile.simulation_fingerprint)
    finally:
        conn.close()
    if active is None:
        raise SystemExit("Aucune carte active ne correspond au profil courant.")
    _, reference = active
    held_out_config = replace(
        reference.config,
        property_count=args.properties,
        scenarios_per_property=args.scenarios,
        worker_count=1,
        # La validation cible volontairement la frontiere d'opportunite : un echantillon
        # aleatoire general contient trop peu de cas rentables pour mesurer le rappel.
        frontier_share=1.0,
        seed=args.seed,
    )
    held_out = build_viability_map(held_out_config)
    report = validate_viability_map(reference, held_out)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    if report.tri_median_mae is not None and report.tri_median_mae > args.max_tri_mae:
        raise SystemExit(
            f"Erreur TRI median excessive : {report.tri_median_mae:.2f} points, "
            f"maximum {args.max_tri_mae:.2f}."
        )


if __name__ == "__main__":
    main()
