from achat_immo.investment_profile import InvestmentProfile
from achat_immo.qualification import ProfitabilityTargets
from achat_immo.viability import LocalMarketScope, ViabilityMapConfig, build_viability_map
from achat_immo.viability.sampling import sample_hypothetical_properties
from achat_immo.viability.scenarios import generate_common_scenario_shocks, scenario_inputs_for_property
from achat_immo.viability.profile_config import viability_config_from_profile
from achat_immo.viability.artifact import deserialize_viability_config, serialize_viability_config
from achat_immo.viability.query import PropertyObservation, qualify_observation
from achat_immo.viability.validation import validate_viability_map


def _config(**overrides) -> ViabilityMapConfig:
    values = {
        "market": LocalMarketScope(
            city="Grenoble",
            legal_rent_caps_per_m2=(12.6, 18.1),
        ),
        "property_count": 4,
        "scenarios_per_property": 3,
        "seed": 123,
        "targets": ProfitabilityTargets(
            target_tri_median=-100.0,
            target_tri_p10=-100.0,
            target_coc=-100.0,
            target_cashflow=-100_000.0,
            min_prob_positive_cashflow=0.0,
        ),
    }
    values.update(overrides)
    return ViabilityMapConfig(**values)


def test_sobol_est_reproductible_et_respecte_le_plafond_local() -> None:
    first = sample_hypothetical_properties(_config())
    second = sample_hypothetical_properties(_config())

    assert first == second
    assert len(first) == 4
    assert all(
        property_.legal_rent_cap_per_m2 is not None
        and property_.rent_per_m2 <= property_.legal_rent_cap_per_m2
        for property_ in first
    )
    assert all(80_000 <= property_.total_project_cost <= 120_000 for property_ in first)
    assert all(15_000 <= property_.equity <= 20_000 for property_ in first)


def test_scenarios_communs_appliquent_les_memes_chocs_relatifs() -> None:
    first, second = sample_hypothetical_properties(_config())[:2]
    shocks = generate_common_scenario_shocks(3, seed=456)

    first_inputs = scenario_inputs_for_property(first, shocks)
    second_inputs = scenario_inputs_for_property(second, shocks)

    assert [row.vacance_mois_par_an for row in first_inputs] == [
        row.vacance_mois_par_an for row in second_inputs
    ]
    assert first_inputs[0].loyer_hc_mensuel / first.monthly_rent == (
        second_inputs[0].loyer_hc_mensuel / second.monthly_rent
    )


def test_construction_carte_est_reproductible() -> None:
    first = build_viability_map(_config())
    second = build_viability_map(_config())

    assert first == second
    assert len(first.points) == 4
    assert first.viable_count == 4
    assert all(point.valid_scenarios == 3 for point in first.points)
    assert all(point.tri_median is not None for point in first.points)


def test_construction_parallele_conserve_les_resultats_et_l_ordre() -> None:
    sequential = build_viability_map(_config(worker_count=1))
    parallel = build_viability_map(_config(worker_count=2))

    assert sequential.points == parallel.points


def test_configuration_carte_derive_du_profil_actif() -> None:
    profile = InvestmentProfile(
        total_budget_min=90_000,
        total_budget_max=110_000,
        equity_min=16_000,
        equity_max=18_000,
        credit_duration_years=15,
        credit_rate_pct=4.1,
        map_property_count=8,
        map_scenarios_per_property=5,
        map_worker_count=2,
    )
    market = _config().market

    config = viability_config_from_profile(profile, market, seed=9)

    assert config.total_project_budget.minimum == 90_000
    assert config.total_project_budget.maximum == 110_000
    assert config.equity.minimum == 16_000
    assert config.investor.credit_duration_years == 15
    assert config.investor.credit_rate_pct == 4.1
    assert config.property_count == 8
    assert config.profile_fingerprint == profile.fingerprint


def test_configuration_carte_supporte_un_roundtrip_serialise() -> None:
    config = _config()

    restored = deserialize_viability_config(serialize_viability_config(config))

    assert restored == config


def test_requete_partielle_demande_un_enrichissement() -> None:
    viability_map = build_viability_map(_config())
    observation = PropertyObservation(surface_m2=30, price=80_000)

    result = qualify_observation(viability_map, observation)

    assert result.qualification in {"a_enrichir", "carte_non_conclusive"}
    assert "loyer" in result.missing_fields


def test_validation_hors_echantillon_mesure_le_rappel() -> None:
    reference = build_viability_map(_config())
    held_out = build_viability_map(_config(seed=456))

    report = validate_viability_map(reference, held_out)

    assert report.sample_count == 4
    assert report.truly_viable == 4
    assert report.recall is not None
    assert 0 <= report.recall <= 1
    assert report.false_negatives == report.truly_viable - report.true_positives
