"""Tests pour le moteur probabiliste."""

import numpy as np
from achat_immo.stochastic.distributions import TriangularDist, ConstantDist
from achat_immo.stochastic.models import Strategy
from achat_immo.stochastic.scenario_generator import ScenarioGenerator
from achat_immo.stochastic.monte_carlo import MonteCarloRunner
from achat_immo.analysis.metrics import summarize_monte_carlo_outputs
from achat_immo.search_policy.financing import FinancingPolicy, project_cost
from achat_immo.search_policy.inverse_solver import InverseSolver

def test_distributions():
    dist = TriangularDist(0.0, 5.0, 10.0)
    rng = np.random.default_rng(42)
    val = dist.sample(rng)
    assert 0.0 <= val <= 10.0
    
    dist_c = ConstantDist(42.0)
    assert dist_c.sample(rng) == 42.0

def test_scenario_generator_reproducibility():
    config = {
        "loyer_hc_mensuel": TriangularDist(500, 600, 700)
    }
    strategy = Strategy(loyer_hc_mensuel=600.0)
    
    gen1 = ScenarioGenerator(config, seed=42)
    s1 = gen1.sample(1, strategy)
    
    gen2 = ScenarioGenerator(config, seed=42)
    s2 = gen2.sample(1, strategy)
    
    assert s1.loyer_hc_mensuel == s2.loyer_hc_mensuel

def test_monte_carlo_runner():
    config = {
        "loyer_hc_mensuel": ConstantDist(600.0),
        "vacance_mois_par_an": ConstantDist(1.0)
    }
    strategy = Strategy(
        ville="Grenoble",
        surface_m2=40.0,
        prix_achat=100_000,
        loyer_hc_mensuel=600.0
    )
    
    gen = ScenarioGenerator(config, seed=42)
    runner = MonteCarloRunner()
    
    outputs = runner.run(strategy, gen, n_scenarios=5)
    assert len(outputs) == 5
    
    summary = summarize_monte_carlo_outputs(outputs)
    assert summary["nb_scenarios_valides"] == 5
    assert summary["tri_median"] is not None


def test_monte_carlo_runner_reuse_des_scenarios_pretires():
    config = {
        "loyer_hc_mensuel": ConstantDist(650.0),
        "vacance_mois_par_an": ConstantDist(1.0),
        "croissance_loyer_annuelle_pct": ConstantDist(1.0),
        "inflation_charges_annuelle_pct": ConstantDist(2.0),
        "travaux_imprevus_annuels": ConstantDist(250.0),
        "appreciation_bien_annuelle_pct": ConstantDist(0.5),
        "decote_revente_pct": ConstantDist(7.0),
    }
    strategy = Strategy(ville="Grenoble", surface_m2=40.0, prix_achat=110_000, loyer_hc_mensuel=650.0)
    generator = ScenarioGenerator(config, seed=42)
    runner = MonteCarloRunner()
    scenarios_input = generator.sample_many(5, strategy)

    first_outputs = runner.run_inputs(strategy, scenarios_input)
    second_outputs = runner.run_inputs(strategy, scenarios_input)

    assert [output.tri_annuel_pct for output in first_outputs] == [
        output.tri_annuel_pct for output in second_outputs
    ]


def test_inverse_solver_cherche_un_prix_cible_sur_scenarios_figes():
    config = {
        "loyer_hc_mensuel": ConstantDist(700.0),
        "vacance_mois_par_an": ConstantDist(1.0),
        "croissance_loyer_annuelle_pct": ConstantDist(1.0),
        "inflation_charges_annuelle_pct": ConstantDist(2.0),
        "travaux_imprevus_annuels": ConstantDist(300.0),
        "appreciation_bien_annuelle_pct": ConstantDist(0.5),
        "decote_revente_pct": ConstantDist(7.0),
    }
    strategy = Strategy(
        ville="Grenoble",
        surface_m2=40.0,
        prix_achat=160_000.0,
        apport=15_000.0,
        loyer_hc_mensuel=700.0,
        charges_copro_annuelles=900.0,
        taxe_fonciere=850.0,
        travaux_initiaux=5_000.0,
    )
    generator = ScenarioGenerator(config, seed=42)
    solver = InverseSolver(MonteCarloRunner(), generator)

    criteria = solver.find_criteria(
        strategy,
        target_tri_median=6.0,
        target_tri_p10=6.0,
        min_prob_positive_cashflow=0.0,
        min_coc_median=-10.0,
        min_monthly_cashflow_median=-200.0,
        n_scenarios_per_eval=10,
        price_tolerance=1_000.0,
    )

    assert criteria is not None
    assert criteria.status == "solved"
    assert criteria.n_scenarios == 10
    assert 75_000 <= criteria.max_price <= 95_000
    assert criteria.summary["tri_median"] >= 6.0


def test_financing_policy_recalcule_apport_quand_le_prix_baisse():
    strategy = Strategy(
        prix_achat=160_000.0,
        apport=15_000.0,
        frais_notaire_estimes=12_800.0,
        travaux_initiaux=5_000.0,
    )
    policy = FinancingPolicy.from_strategy(strategy, min_equity_ratio_pct=10.0, min_cash_apport=5_000.0)
    cheaper_strategy = Strategy(
        prix_achat=80_000.0,
        apport=15_000.0,
        frais_notaire_estimes=6_400.0,
        travaux_initiaux=5_000.0,
    )

    adjusted = policy.apply(cheaper_strategy)

    assert project_cost(strategy) == 177_800.0
    assert policy.effective_equity_ratio_pct == 10.0
    assert adjusted.apport == 9_140.0


def test_inverse_solver_applique_financement_dynamique_et_frais_proportionnels():
    config = {
        "loyer_hc_mensuel": ConstantDist(700.0),
        "vacance_mois_par_an": ConstantDist(1.0),
        "croissance_loyer_annuelle_pct": ConstantDist(1.0),
        "inflation_charges_annuelle_pct": ConstantDist(2.0),
        "travaux_imprevus_annuels": ConstantDist(300.0),
        "appreciation_bien_annuelle_pct": ConstantDist(0.5),
        "decote_revente_pct": ConstantDist(7.0),
    }
    strategy = Strategy(
        ville="Grenoble",
        surface_m2=40.0,
        prix_achat=160_000.0,
        apport=15_000.0,
        loyer_hc_mensuel=700.0,
        charges_copro_annuelles=900.0,
        taxe_fonciere=850.0,
        travaux_initiaux=5_000.0,
        frais_notaire_estimes=12_800.0,
    )
    policy = FinancingPolicy.from_strategy(strategy, min_equity_ratio_pct=10.0, min_cash_apport=5_000.0)
    solver = InverseSolver(MonteCarloRunner(), ScenarioGenerator(config, seed=42))

    criteria = solver.find_criteria(
        strategy,
        target_tri_median=6.0,
        target_tri_p10=6.0,
        min_prob_positive_cashflow=0.0,
        min_coc_median=-10.0,
        min_monthly_cashflow_median=-200.0,
        n_scenarios_per_eval=10,
        price_tolerance=1_000.0,
        financing_policy=policy,
    )

    assert criteria is not None
    assert 65_000 <= criteria.max_price <= 75_000
    assert criteria.project_cost == criteria.max_price * 1.08 + strategy.travaux_initiaux
    assert criteria.apport == round(criteria.project_cost * 0.10, 2)
    assert criteria.apport < strategy.apport
    assert criteria.financing_policy == "ratio_apport=10.00%, apport_min=5000 EUR"
