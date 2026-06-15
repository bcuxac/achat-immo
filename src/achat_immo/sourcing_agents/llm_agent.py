"""Agent de sourcing basé sur un LLM pour extraire les données d'annonces immobilières."""

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from google import genai
from typing import Optional, List
import os
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

from achat_immo.deal_scoring.candidate_property import CandidateProperty

class LLMPropertySchema(BaseModel):
    """Schéma de données attendu par l'IA lors de la lecture d'une annonce."""
    source: str = Field(description="La source de l'annonce, ex: Leboncoin, SeLoger, BienIci, Jinka, etc. 'Inconnu' si non déterminé.")
    ville: str = Field(description="La ville où se situe le bien. Essentiel.")
    quartier: str = Field(description="Le quartier, si précisé. Sinon 'Inconnu'.")
    prix: float = Field(description="Le prix d'achat FAI total demandé, en euros. Ne pas inclure les frais de notaire.")
    surface: float = Field(description="La surface du bien en m2. Si plage, prendre la moyenne.")
    charges_mensuelles: Optional[float] = Field(description="Les charges de copropriété mensuelles en euros. null si non précisé.")
    taxe_fonciere: Optional[float] = Field(description="La taxe foncière annuelle en euros. null si non précisé.")
    dpe: str = Field(description="La lettre du DPE (A, B, C, D, E, F, G). 'Inconnu' si non précisé.")
    etage: Optional[int] = Field(description="L'étage du bien. 0 pour RDC. null si non précisé.")
    ascenseur: Optional[bool] = Field(description="Présence d'un ascenseur. true, false ou null.")
    loyer_estime: Optional[float] = Field(description="Le loyer mensuel HC si le bien est déjà loué ou si une estimation est donnée. null sinon.")
    confiance_loyer: str = Field(description="Niveau de confiance dans l'estimation du loyer: 'haute' (loué actuellement), 'moyenne' (estimé par agence), 'basse' (aucune idée ou deviné).")
    travaux_visibles: Optional[float] = Field(description="Budget travaux en euros suggéré ou évident d'après l'annonce (ex: 'à rénover'). 0 si refait à neuf. null si inconnu.")
    red_flags: List[str] = Field(description="Liste de signaux d'alerte (ex: 'Passoire thermique DPE G', 'Vendu occupé', 'Gros travaux de copro à venir', 'Rez de chaussée sur rue').")
    donnees_manquantes: List[str] = Field(description="Liste des informations cruciales manquantes (ex: 'Taxe foncière absente', 'Charges de copro absentes').")


class LLMSourcingAgent:
    """Agent capable de parser du texte brut ou de fetcher une URL et d'extraire les métadonnées via Gemini."""
    
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("Une clé d'API GEMINI_API_KEY est requise (variable d'environnement).")
        self.client = genai.Client(api_key=self.api_key)
        
    def fetch_url(self, url: str) -> str:
        """Tente de récupérer le contenu textuel d'une URL via Playwright."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                page = context.new_page()
                Stealth().apply_stealth_sync(page)
                
                try:
                    # networkidle attend que les requetes reseaux soient terminees (pour laisser le JS bosser)
                    page.goto(url, wait_until="networkidle", timeout=15000)
                except PlaywrightTimeoutError:
                    # Si timeout, on recupere quand meme ce qu'on a pu charger (souvent suffisant)
                    pass
                
                # Attendre un peu plus pour les SPAs recalcitrantes si besoin, ou scroll down
                html_content = page.content()
                browser.close()
                
            # Nettoyage avec BeautifulSoup pour ne garder que le texte visible (et les attributs href des liens)
            soup = BeautifulSoup(html_content, 'html.parser')
            for script in soup(["script", "style", "noscript", "meta"]):
                script.decompose()
                
            # Extraire le texte avec les URLs
            text = soup.get_text(separator='\n', strip=True)
            
            # On ajoute aussi tous les liens a la fin pour etre sur que Gemini les voit
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('http') and 'jinka' not in href.lower():
                    links.append(href)
            
            if links:
                text += "\n\n--- LIENS DETECTES DANS LA PAGE ---\n" + "\n".join(list(set(links))[:20])
                
            return text
            
        except Exception as e:
            raise RuntimeError(f"Erreur Playwright lors de la récupération de {url}: {e}")

    def extract_original_link(self, aggregator_text: str) -> Optional[str]:
        """Demande à Gemini de trouver le lien source original dans le texte/liens d'un agrégateur."""
        prompt = f"""
        Tu es un assistant qui doit trouver le lien de l'annonce immobilière originale (agence, leboncoin, seloger, etc.) 
        à partir du contenu d'une page d'un agrégateur (comme Jinka ou Castorus).
        
        Regarde les liens détectés à la fin du texte ou dans le texte.
        Retourne UNIQUEMENT l'URL complète (commençant par http). S'il n'y en a pas d'évidente, retourne la chaîne "NOT_FOUND".
        Ne réponds rien d'autre que l'URL.
        
        TEXTE DE L'AGRÉGATEUR :
        ---
        {aggregator_text[:15000]}
        ---
        """
        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.0
            ),
        )
        url = response.text.strip()
        if url == "NOT_FOUND" or not url.startswith("http"):
            return None
        return url

    def extract_from_text(self, text: str, source_url: str = "Texte brut") -> CandidateProperty:
        """Demande à Gemini d'extraire les données structurées du texte brut."""
        
        prompt = f"""
        Tu es un expert immobilier. Lis l'annonce immobilière suivante et extrais toutes les informations demandées avec précision.
        Sois conservateur : si une donnée (comme les charges ou la taxe foncière) n'est pas explicitement mentionnée, mets 'null' et ajoute-la dans 'donnees_manquantes'.
        Si l'annonce mentionne 'DPE G' ou 'DPE F', ajoute un red_flag "Passoire thermique".
        Si l'annonce est 'à rénover' ou nécessite des travaux sans budget précisé, essaie de deviner un petit budget ou met 5000 dans travaux_visibles.
        
        TEXTE DE L'ANNONCE :
        ---
        {text[:15000]} # Limite pour éviter un prompt trop massif si le site est pollué
        ---
        """
        
        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=LLMPropertySchema,
                temperature=0.0
            ),
        )
        
        # Le SDK renvoie soit directement un objet parsé (selon version), soit du JSON dans text
        try:
            data = json.loads(response.text)
            parsed = LLMPropertySchema(**data)
        except Exception:
            raise ValueError(f"Impossible de parser la réponse du modèle: {response.text}")
            
        # Conversion du modèle Pydantic vers notre dataclass CandidateProperty
        return CandidateProperty(
            source=parsed.source,
            url=source_url,
            ville=parsed.ville,
            quartier=parsed.quartier,
            prix=parsed.prix,
            surface=parsed.surface,
            charges_mensuelles=parsed.charges_mensuelles,
            taxe_fonciere=parsed.taxe_fonciere,
            dpe=parsed.dpe,
            etage=parsed.etage,
            ascenseur=parsed.ascenseur,
            loyer_estime=parsed.loyer_estime,
            confiance_loyer=parsed.confiance_loyer,
            travaux_visibles=parsed.travaux_visibles,
            red_flags=parsed.red_flags,
            donnees_manquantes=parsed.donnees_manquantes
        )
