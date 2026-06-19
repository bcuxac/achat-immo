"""Script de test de l'agent de sourcing IA."""

import os
import sys
from dotenv import load_dotenv
from achat_immo.sourcing_agents.llm_agent import LLMSourcingAgent

load_dotenv()

def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("Erreur : La variable d'environnement GEMINI_API_KEY n'est pas définie.")
        print("Veuillez l'exporter dans votre terminal : export GEMINI_API_KEY='votre_cle'")
        print("Ou lancez le script ainsi : GEMINI_API_KEY='votre_cle' uv run python scripts/test_llm_extraction.py")
        sys.exit(1)

    print("=== Test de l'Agent LLM (Gemini) ===")
    agent = LLMSourcingAgent()
    
    # Test avec un texte brut (Option A)
    # Imaginons un texte copié-collé typique de Leboncoin
    annonce_brute = """
    Vends charmant T2 de 45m2 au centre-ville de Grenoble (quartier Championnet).
    Idéal investisseur ou premier achat.
    Prix : 135 000 euros FAI (honoraires charge vendeur).
    L'appartement est situé au 3ème étage sans ascenseur, dans un bel immeuble ancien.
    Des travaux de rafraîchissement sont à prévoir (peintures, salle d'eau).
    DPE : F (logement à consommation énergétique excessive).
    Actuellement loué 650€ charges comprises.
    Charges de copropriété : 85€ / mois.
    Agences s'abstenir.
    """
    
    print("\n[Texte Brut fourni à l'IA]")
    print(annonce_brute)
    print("\nExtraction en cours par Gemini 2.5 Flash...")
    
    try:
        property = agent.extract_from_text(annonce_brute, source_url="Texte brut")
        
        print("\n=== Résultat de l'Extraction (CandidateProperty) ===")
        print(f"Source: {property.source}")
        print(f"Lieu: {property.ville} ({property.quartier})")
        print(f"Prix: {property.prix} €")
        print(f"Surface: {property.surface} m2")
        print(f"DPE: {property.dpe}")
        print(f"Etage: {property.etage} (Ascenseur: {property.ascenseur})")
        print(f"Loyer Estimé: {property.loyer_estime} € (Confiance: {property.confiance_loyer})")
        print(f"Charges Mensuelles: {property.charges_mensuelles} €")
        print(f"Taxe Foncière: {property.taxe_fonciere} €")
        print(f"Travaux visuels: {property.travaux_visibles} €")
        print(f"Red Flags: {', '.join(property.red_flags) if property.red_flags else 'Aucun'}")
        print(f"Données manquantes: {', '.join(property.donnees_manquantes) if property.donnees_manquantes else 'Aucune'}")
        
    except Exception as e:
        print(f"\n[Erreur lors de l'extraction] {e}")
        
    print("\n--------------------------------------------------")
    print("Test de l'Architecture à Deux Vitesses (Radar -> Extraction)")
    
    # URL Jinka fournie par l'utilisateur
    jinka_url = "https://www.jinka.fr/ad/954ca383-7d9b-4d29-a323-c527f442a993?alert_id=9aa8e8eab78a4e21034e334d90719be0"
    print("\n[PHASE 1 : LE RADAR]")
    print(f"Fetch de l'agrégateur: {jinka_url}")
    
    try:
        jinka_html = agent.fetch_url(jinka_url)
        print("Succès du fetch (Jinka) ! Recherche du lien original...")
        
        original_url = agent.extract_original_link(jinka_html)
        
        if not original_url:
            print("Impossible de trouver le lien original dans la page Jinka.")
        else:
            print(f"Lien original trouvé : {original_url}")
            
            print("\n[PHASE 2 : L'ENRICHISSEMENT]")
            print(f"Fetch du site de l'agence: {original_url}")
            agency_html = agent.fetch_url(original_url)
            print("Succès du fetch (Agence) ! Envoi à Gemini pour extraction des données...")
            
            property_url = agent.extract_from_text(agency_html, source_url=original_url)
            
            print("\n=== Résultat de l'Extraction Profonde ===")
            print(f"Source: {property_url.source}")
            print(f"Lieu: {property_url.ville} ({property_url.quartier})")
            print(f"Prix: {property_url.prix} €")
            print(f"Surface: {property_url.surface} m2")
            print(f"DPE: {property_url.dpe}")
            print(f"Etage: {property_url.etage} (Ascenseur: {property_url.ascenseur})")
            print(f"Loyer Estimé: {property_url.loyer_estime} € (Confiance: {property_url.confiance_loyer})")
            print(f"Charges Mensuelles: {property_url.charges_mensuelles} €")
            print(f"Taxe Foncière: {property_url.taxe_fonciere} €")
            print(f"Travaux visuels: {property_url.travaux_visibles} €")
            print(f"Red Flags: {', '.join(property_url.red_flags) if property_url.red_flags else 'Aucun'}")
            print(f"Données manquantes: {', '.join(property_url.donnees_manquantes) if property_url.donnees_manquantes else 'Aucune'}")
        
    except PermissionError as e:
        print(f"\n[Bloqué par sécurité (403)]\n{e}")
        print("L'approche directe est bloquée par ce site. Il faudra utiliser ScrapingBee, une API mobile cachée, ou copier-coller le texte.")
    except Exception as e:
        print(f"\n[Erreur] {e}")

    print("\n--------------------------------------------------")
    print("Test Phase 3 : SPA Javascript Difficile (BienIci)")
    
    bienici_url = "https://www.bienici.com/annonce/safti-1-1672709"
    print(f"Fetch du site SPA: {bienici_url}")
    
    try:
        bienici_html = agent.fetch_url(bienici_url)
        print(f"Succès du fetch ! {len(bienici_html)} caractères récupérés via Playwright. Envoi à Gemini...")
        
        property_bienici = agent.extract_from_text(bienici_html, source_url=bienici_url)
        print("\n=== Résultat de l'Extraction BienIci ===")
        print(f"Prix: {property_bienici.prix} € | Surface: {property_bienici.surface} m2")
        print(f"DPE: {property_bienici.dpe}")
        
    except Exception as e:
        print(f"\n[Erreur Playwright/Gemini] {e}")

if __name__ == "__main__":
    main()
