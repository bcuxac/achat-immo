"""Agent de sourcing factice générant des annonces immobilières aléatoires."""

import random
from typing import List
from achat_immo.deal_scoring.candidate_property import CandidateProperty

class DummySourcingAgent:
    """Simule un agent récoltant des annonces immobilières sur internet."""
    
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        
    def fetch_listings(self, city: str, n_listings: int = 10) -> List[CandidateProperty]:
        """Génère N annonces fictives pour une ville donnée."""
        
        listings = []
        quartiers = ["Centre Ville", "Gare", "Nord", "Sud", "Est", "Ouest", "Périphérie"]
        dpes = ["A", "B", "C", "D", "E", "F", "G"]
        sources = ["Leboncoin", "SeLoger", "BienIci"]
        
        for i in range(n_listings):
            surface = round(self.rng.uniform(15.0, 80.0), 1)
            prix_m2 = self.rng.uniform(1500.0, 5000.0)
            prix = round(surface * prix_m2 / 100) * 100.0 # arrondi à la centaine
            
            # Plus la surface est petite, plus le loyer/m2 est cher
            loyer_m2 = self.rng.uniform(10.0, 25.0) * (50.0 / (surface + 20.0)) 
            loyer_estime = round(surface * loyer_m2 / 10) * 10.0
            
            confiance = self.rng.choice(["haute", "moyenne", "basse"])
            
            dpe = self.rng.choice(dpes)
            
            # Données parfois manquantes
            charges_mensuelles = round(self.rng.uniform(30.0, 150.0), 1) if self.rng.random() > 0.2 else None
            taxe_fonciere = round(self.rng.uniform(400.0, 1500.0)) if self.rng.random() > 0.4 else None
            
            travaux = round(self.rng.uniform(0.0, 20000.0)) if dpe in ["F", "G"] or self.rng.random() > 0.7 else 0.0
            
            red_flags = []
            donnees_manquantes = []
            
            if charges_mensuelles is None:
                donnees_manquantes.append("Charges de copropriété inconnues")
            if taxe_fonciere is None:
                donnees_manquantes.append("Taxe foncière inconnue")
            if dpe in ["F", "G"]:
                red_flags.append(f"Passoire thermique (DPE {dpe})")
            if confiance == "basse":
                red_flags.append("Loyer très incertain")
                
            property = CandidateProperty(
                source=self.rng.choice(sources),
                url=f"https://dummy-immo.com/listing/{i}",
                ville=city,
                quartier=self.rng.choice(quartiers),
                prix=prix,
                surface=surface,
                charges_mensuelles=charges_mensuelles,
                taxe_fonciere=taxe_fonciere,
                dpe=dpe,
                etage=self.rng.randint(0, 5),
                ascenseur=self.rng.choice([True, False, None]),
                loyer_estime=loyer_estime,
                confiance_loyer=confiance,
                travaux_visibles=travaux,
                red_flags=red_flags,
                donnees_manquantes=donnees_manquantes
            )
            listings.append(property)
            
        return listings
