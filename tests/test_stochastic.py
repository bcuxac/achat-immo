"""Tests pour le moteur probabiliste."""

import numpy as np
from achat_immo.stochastic.distributions import TriangularDist, ConstantDist
from achat_immo.stochastic.models import Strategy
from achat_immo.stochastic.scenario_generator import ScenarioGenerator
from achat_immo.stochastic.monte_carlo import MonteCarloRunner
from achat_immo.analysis.metrics import summarize_monte_carlo_outputs

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
