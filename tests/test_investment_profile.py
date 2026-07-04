from dataclasses import replace
from pathlib import Path

import pytest

from achat_immo.investment_profile import InvestmentProfile
from achat_immo.storage import (
    get_active_viability_map,
    get_investment_profile,
    list_investment_profile_versions,
    open_database,
    save_investment_profile,
    save_viability_map,
)
from achat_immo.viability import LocalMarketScope, ViabilityMapConfig, build_viability_map


def test_profile_roundtrip_json_et_derive_les_cibles() -> None:
    profile = InvestmentProfile(credit_duration_years=15, target_tri_p10=4.0)

    restored = InvestmentProfile.from_json(profile.to_json())

    assert restored == profile
    assert restored.analysis_targets.target_tri_p10 == 4.0
    assert restored.analysis_targets.n_scenarios == 1_000
    assert len(restored.fingerprint) == 64


def test_profile_valide_les_plages_structurantes() -> None:
    with pytest.raises(ValueError, match="budget total"):
        InvestmentProfile(total_budget_min=120_000, total_budget_max=80_000)
    with pytest.raises(ValueError, match="apport maximal"):
        InvestmentProfile(equity_max=130_000)
    with pytest.raises(ValueError, match="probabilite minimale"):
        InvestmentProfile(min_positive_cashflow_probability=1.1)


def test_storage_historise_uniquement_les_changements(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    initial = get_investment_profile(conn)

    first_id = save_investment_profile(conn, initial)
    duplicate_id = save_investment_profile(conn, initial)
    changed = replace(initial, credit_duration_years=12)
    changed_id = save_investment_profile(conn, changed)

    assert duplicate_id == first_id
    assert changed_id != first_id
    assert get_investment_profile(conn) == changed
    versions = list_investment_profile_versions(conn)
    assert [row["id"] for row in versions] == [changed_id, first_id]
    assert versions[0]["config_hash"] == changed.fingerprint


def test_storage_persiste_et_recharge_une_carte(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    profile = InvestmentProfile(map_property_count=2, map_scenarios_per_property=2, map_worker_count=1)
    config = ViabilityMapConfig(
        market=LocalMarketScope(city="Grenoble", legal_rent_caps_per_m2=(15.0, 18.0)),
        profile_fingerprint=profile.fingerprint,
        property_count=2,
        scenarios_per_property=2,
    )
    viability_map = build_viability_map(config)

    map_id = save_viability_map(conn, viability_map)
    loaded = get_active_viability_map(conn, "Grenoble", profile.fingerprint)

    assert loaded is not None
    assert loaded[0] == map_id
    assert loaded[1] == viability_map
