"""Exemple de branchement d'un agent de sourcing et scoring des annonces."""

from achat_immo.sourcing_agents.dummy_agent import DummySourcingAgent
from achat_immo.deal_scoring.score import compute_deal_score
from achat_immo.stochastic.models import Strategy
from achat_immo.stochastic.distributions import TriangularDist, TruncatedNormalDist, ConstantDist
from achat_immo.stochastic.scenario_generator import ScenarioGenerator
from achat_immo.stochastic.monte_carlo import MonteCarloRunner
from achat_immo.analysis.metrics import summarize_monte_carlo_outputs

def main():
    print("=== Sourcing et Scoring d'Annonces ===")
    
    # 1. On lance l'agent pour récolter 20 annonces sur Grenoble
    agent = DummySourcingAgent(seed=123)
    listings = agent.fetch_listings("Grenoble", n_listings=20)
    
    print(f"{len(listings)} annonces trouvées.\n")
    
    # 2. On prépare le moteur Monte Carlo
    # On définit une stratégie de base commune (apport, crédit, fiscalité...)
    base_strategy = Strategy(
        ville="Grenoble",
        apport=15_000.0,
        duree_credit_annees=20,
        taux_credit_pct=3.5,
        horizon_annees=15,
        frais_gestion_pct=7.0,
        gestion_agence_active=True
    )
    
    # Configurations stochastiques communes
    config = {
        "vacance_mois_par_an": TruncatedNormalDist(1.0, 0.5, 0.0, 12.0),
        "croissance_loyer_annuelle_pct": TruncatedNormalDist(1.5, 0.5, 0.0, 3.0),
        "inflation_charges_annuelle_pct": TruncatedNormalDist(2.5, 1.0, 0.0, 5.0),
        "appreciation_bien_annuelle_pct": TruncatedNormalDist(0.5, 1.0, -2.0, 3.0),
    }
    
    generator = ScenarioGenerator(config, seed=42)
    runner = MonteCarloRunner()
    
    # 3. On score chaque annonce
    scored_listings = []
    
    for i, listing in enumerate(listings):
        # On adapte la stratégie à l'annonce
        # Pour les données incertaines de l'annonce, on peut élargir la distribution
        loyer_base = listing.loyer_estime or 500.0
        
        # Si la confiance est basse, on met une distribution de loyer très large
        if listing.confiance_loyer == "basse":
            dist_loyer = TriangularDist(loyer_base * 0.7, loyer_base, loyer_base * 1.1)
        elif listing.confiance_loyer == "moyenne":
            dist_loyer = TriangularDist(loyer_base * 0.85, loyer_base, loyer_base * 1.05)
        else:
            dist_loyer = TriangularDist(loyer_base * 0.95, loyer_base, loyer_base * 1.02)
            
        # Pareil pour les charges et taxes si elles sont manquantes
        charges_annuelles = (listing.charges_mensuelles * 12) if listing.charges_mensuelles else 1000.0
        taxe_fonciere = listing.taxe_fonciere or 800.0
        
        # S'il y a des travaux, on ajoute une incertitude de dépassement de budget
        travaux_imprevus = TriangularDist(0.0, listing.travaux_visibles * 0.2, listing.travaux_visibles * 0.5) if listing.travaux_visibles else ConstantDist(0.0)
        
        # Mise à jour config
        listing_config = config.copy()
        listing_config["loyer_hc_mensuel"] = dist_loyer
        listing_config["travaux_imprevus_annuels"] = travaux_imprevus
        
        # Mise à jour stratégie
        listing_strategy = Strategy(
            ville=listing.ville,
            surface_m2=listing.surface,
            prix_achat=listing.prix,
            apport=base_strategy.apport,
            duree_credit_annees=base_strategy.duree_credit_annees,
            taux_credit_pct=base_strategy.taux_credit_pct,
            horizon_annees=base_strategy.horizon_annees,
            charges_copro_annuelles=charges_annuelles,
            taxe_fonciere=taxe_fonciere,
            travaux_initiaux=listing.travaux_visibles or 0.0,
            gestion_agence_active=base_strategy.gestion_agence_active
        )
        
        listing_gen = ScenarioGenerator(listing_config, seed=42+i)
        
        # Exécution MC
        outputs = runner.run(listing_strategy, listing_gen, n_scenarios=200) # 200 par annonce pour être rapide
        summary = summarize_monte_carlo_outputs(outputs)
        
        # Calcul du score global
        score = compute_deal_score(listing, summary)
        
        scored_listings.append({
            "listing": listing,
            "summary": summary,
            "score": score
        })

    # 4. On affiche le top 3
    scored_listings.sort(key=lambda x: x["score"], reverse=True)
    
    print("--- TOP 3 ANNONCES ---")
    for i, item in enumerate(scored_listings[:3]):
        L = item["listing"]
        S = item["summary"]
        print(f"\n#{i+1} Score: {item['score']:.0f} | {L.surface}m2 à {L.quartier} - {L.prix}€ ({L.prix_m2:.0f}€/m2)")
        print(f"Lien: {L.url}")
        print(f"DPE: {L.dpe} | Travaux: {L.travaux_visibles}€ | Loyer espéré: ~{L.loyer_estime}€ (Confiance: {L.confiance_loyer})")
        if L.red_flags or L.donnees_manquantes:
            print(f"Attention: {', '.join(L.red_flags + L.donnees_manquantes)}")
        print(f"Monte Carlo: TRI P50 = {S.get('tri_median', 0):.1f}% | TRI P10 = {S.get('tri_p10', 0):.1f}% | Prob CF+ = {S.get('probabilite_cashflow_cumule_positif', 0)*100:.0f}%")
        
    print("\n--- PIRES ANNONCES (Bottom 2) ---")
    for i, item in enumerate(scored_listings[-2:]):
        L = item["listing"]
        print(f"Score: {item['score']:.0f} | {L.surface}m2 à {L.quartier} - {L.prix}€")
        if L.red_flags or L.donnees_manquantes:
            print(f"Problèmes: {', '.join(L.red_flags + L.donnees_manquantes)}")

if __name__ == "__main__":
    main()
