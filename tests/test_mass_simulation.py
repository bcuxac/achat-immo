"""Tests unitaires pour la simulation de masse."""

import pandas as pd
from achat_immo.mass_simulation import generer_bien_aleatoire, executer_simulation_masse

def test_generer_bien_aleatoire() -> None:
    bien, location = generer_bien_aleatoire(
        surface_min=20, surface_max=30,
        prix_m2_min=2000, prix_m2_max=3000,
        loyer_m2_min=15, loyer_m2_max=20,
        travaux_pct_min=10, travaux_pct_max=20,
    )
    
    assert 20 <= bien.surface_m2 <= 30
    assert 2000 <= bien.prix_achat / bien.surface_m2 <= 3000
    assert 15 <= location.loyer_hc_mensuel / bien.surface_m2 <= 20
    assert 0.1 <= bien.travaux_estimes / bien.prix_achat <= 0.2
    assert bien.frais_notaire_estimes == round(bien.prix_achat * 0.08, 2)
    assert location.gestion_agence_active is True

def test_executer_simulation_masse() -> None:
    # On simule 2 biens pour verifier que le dataframe de sortie est bien construit
    df = executer_simulation_masse(nb_simulations=2, workers=1)
    
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    # Verifier la presence de metriques d'entree injectees
    assert "bien_surface_m2" in df.columns
    assert "bien_prix_m2" in df.columns
    assert "bien_loyer_m2" in df.columns
    assert "bien_travaux_pct" in df.columns
    # Verifier la presence de metriques de sortie financieres
    assert "tri_annuel_pct" in df.columns
    assert "effort_epargne_mensuel" in df.columns
    assert "regime_fiscal" in df.columns
