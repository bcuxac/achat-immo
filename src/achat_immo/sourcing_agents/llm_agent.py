"""Agent de sourcing basé sur un LLM pour extraire les données d'annonces immobilières."""

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from google import genai
from typing import Optional, List
import os
import json
from pathlib import Path
import re
from shutil import which
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

from achat_immo.jinka_collect import DEFAULT_JINKA_STORAGE_STATE
from achat_immo.sourcing_agents.models import CandidateProperty


CHROMIUM_CANDIDATES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")
CHROMIUM_CONTAINER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]
JINKA_HOSTS = {"jinka.fr", "www.jinka.fr"}
CONSENT_BUTTON_PATTERNS = (
    "Continuer sans accepter",
    "Tout refuser",
    "Refuser",
    "Accepter et fermer",
    "Tout accepter",
    "Accepter",
    "J'accepte",
)


def resolve_chromium_executable() -> str | None:
    """Retourne un Chromium systeme quand le cache Playwright n'est pas disponible."""

    explicit_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "").strip()
    if explicit_path:
        return explicit_path

    for candidate in CHROMIUM_CANDIDATES:
        executable_path = which(candidate)
        if executable_path:
            return executable_path
    return None


def chromium_launch_options() -> dict[str, object]:
    options: dict[str, object] = {"headless": True, "args": CHROMIUM_CONTAINER_ARGS}
    executable_path = resolve_chromium_executable()
    if executable_path:
        options["executable_path"] = executable_path
    return options


def browser_context_options(url: str) -> dict[str, object]:
    """Retourne les options de contexte Playwright adaptees a l'URL chargee."""

    options: dict[str, object] = {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1280, "height": 720},
    }
    storage_state_path = jinka_storage_state_path_for_url(url)
    if storage_state_path is not None:
        options["storage_state"] = str(storage_state_path)
    return options


def jinka_storage_state_path_for_url(url: str) -> Path | None:
    """Retourne le fichier de session Jinka a reutiliser pour une fiche Jinka."""

    hostname = (urlsplit(url).hostname or "").lower()
    if hostname not in JINKA_HOSTS:
        return None
    configured = os.environ.get("JINKA_STORAGE_STATE_PATH", "").strip()
    storage_state_path = Path(configured) if configured else DEFAULT_JINKA_STORAGE_STATE
    return storage_state_path if storage_state_path.exists() else None


def dismiss_consent_wall(page) -> bool:  # noqa: ANN001
    """Ferme une banniere de consentement si elle masque le contenu."""

    for label in CONSENT_BUTTON_PATTERNS:
        label_pattern = re.compile(re.escape(label), re.IGNORECASE)
        if _try_click_locator(page.get_by_role("button", name=label_pattern)):
            return True
        if _try_click_locator(page.get_by_role("link", name=label_pattern)):
            return True
        if _try_click_locator(page.get_by_text(label_pattern)):
            return True
    for selector in (
        "button.iubenda-cs-reject-btn",
        "button.iubenda-cs-accept-btn",
        ".iubenda-cs-reject-btn",
        ".iubenda-cs-accept-btn",
    ):
        if _try_click_locator(page.locator(selector)):
            return True
    return False


def _try_click_locator(locator) -> bool:  # noqa: ANN001
    try:
        if locator.count() == 0:
            return False
        locator.first.click(timeout=1200)
        return True
    except Exception:
        return False


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
                browser = p.chromium.launch(**chromium_launch_options())
                context = browser.new_context(**browser_context_options(url))
                page = context.new_page()
                Stealth().apply_stealth_sync(page)
                
                try:
                    # networkidle attend que les requetes reseaux soient terminees (pour laisser le JS bosser)
                    page.goto(url, wait_until="networkidle", timeout=15000)
                except PlaywrightTimeoutError:
                    # Si timeout, on recupere quand meme ce qu'on a pu charger (souvent suffisant)
                    pass
                
                # Attendre un peu plus pour les SPAs recalcitrantes si besoin, ou scroll down
                dismissed_consent = dismiss_consent_wall(page)
                if dismissed_consent:
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except PlaywrightTimeoutError:
                        pass
                    storage_state_path = jinka_storage_state_path_for_url(url)
                    if storage_state_path is not None:
                        context.storage_state(path=str(storage_state_path))
                html_content = page.content()
                context.close()
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
