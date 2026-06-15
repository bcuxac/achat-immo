"""Exemple de simulation Monte Carlo sur Grenoble."""

from achat_immo.models import RegimeFiscal
from achat_immo.stochastic.models import Strategy
from achat_immo.stochastic.distributions import TriangularDist, TruncatedNormalDist
from achat_immo.stochastic.scenario_generator import ScenarioGenerator
from achat_immo.stochastic.monte_carlo import MonteCarloRunner
from achat_immo.analysis.metrics import summarize_monte_carlo_outputs
from achat_immo.analysis.sensitivity import analyze_sensitivity
from achat_immo.search_policy.inverse_solver import InverseSolver

def main():
    print("=== Simulation Monte Carlo - Grenoble ===")
    
    # 1. Définition de la stratégie de base
    strategy = Strategy(
        ville="Grenoble",
        surface_m2=40.0,
        prix_achat=120_000.0,
        apport=15_000.0,
        regime_fiscal=RegimeFiscal.LMNP_REEL,
        horizon_annees=20,
        loyer_hc_mensuel=650.0,
        charges_copro_annuelles=900.0,
        taxe_fonciere=850.0,
        travaux_initiaux=5000.0
    )
    
    # 2. Configuration Stochastique (Distributions d'incertitude)
    stochastic_config = {
        "loyer_hc_mensuel": TriangularDist(600.0, 650.0, 750.0),
        "vacance_mois_par_an": TruncatedNormalDist(mean=1.0, std=1.0, low=0.0, high=12.0),
        "croissance_loyer_annuelle_pct": TruncatedNormalDist(mean=1.5, std=0.5, low=0.0, high=3.0),
        "inflation_charges_annuelle_pct": TruncatedNormalDist(mean=2.5, std=1.0, low=0.0, high=5.0),
        "travaux_imprevus_annuels": TriangularDist(0.0, 200.0, 1500.0),
        "appreciation_bien_annuelle_pct": TruncatedNormalDist(mean=1.0, std=1.5, low=-2.0, high=4.0),
    }
    
    generator = ScenarioGenerator(stochastic_config, seed=42)
    runner = MonteCarloRunner()
    
    print(f"\nGénération et exécution de 1000 scénarios...")
    outputs = runner.run(strategy, generator, n_scenarios=1000)
    
    # 3. Analyse des résultats
    summary = summarize_monte_carlo_outputs(outputs)
    
    print("\n--- Résultats Agrégés ---")
    print(f"TRI Moyen: {summary['tri_moyen']:.2f}%")
    print(f"TRI Médian (P50): {summary['tri_median']:.2f}%")
    print(f"TRI P10 (Pessimiste): {summary['tri_p10']:.2f}%")
    print(f"TRI P90 (Optimiste): {summary['tri_p90']:.2f}%")
    print(f"Probabilité TRI négatif: {summary['probabilite_tri_negatif']*100:.1f}%")
    print(f"Probabilité Cashflow Cumulé positif: {summary['probabilite_cashflow_cumule_positif']*100:.1f}%")
    
    # 4. Analyse de Sensibilité
    # On génère un nouvel ensemble de scénarios pour corréler les entrées et sorties (car le runner actuel retourne juste les outputs)
    inputs = generator.sample_many(1000, strategy)
    # Refaisons le run zip-é pour être propre
    paired_outputs = []
    for i_in in inputs:
        paired_outputs.append(runner._run_single(strategy, i_in))
        
    sensitivity = analyze_sensitivity(inputs, paired_outputs, target_metric="tri_annuel_pct")
    print("\n--- Sensibilité (Drivers de risque) ---")
    for var_name, corr in sensitivity[:3]:
        print(f"  {var_name}: {corr:.2f}")
        
    # 5. Inverse Solving (Génération de critères de recherche)
    print("\nRecherche de la zone cible robuste...")
    solver = InverseSolver(runner, generator)
    criteria = solver.find_criteria(
        base_strategy=strategy,
        target_tri_median=6.0,
        target_tri_p10=2.0,
        min_prob_positive_cashflow=0.4,
        n_scenarios_per_eval=200
    )
    
    if criteria:
        print("\n--- Critères de Recherche Actionnables ---")
        print(f"Prix max: {criteria.max_price:.0f} € ({criteria.max_price_per_m2:.0f} €/m2)")
        print(f"Loyer min: {criteria.min_monthly_rent:.0f} €")
        print(f"Charges max: {criteria.max_monthly_charges:.0f} €/mois")
        print(f"Taxe foncière max: {criteria.max_property_tax:.0f} €")
        print(f"Travaux max: {criteria.max_initial_works:.0f} €")
        print(f"Régime fiscal recommandé: {criteria.preferred_tax_regime}")
    else:
        print("\nAucun critère satisfaisant n'a été trouvé autour de la stratégie.")

if __name__ == "__main__":
    main()
