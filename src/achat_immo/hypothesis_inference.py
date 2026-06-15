"""Inference auditable des hypotheses depuis une annonce.

Les suggestions ne remplacent pas une verification documentaire. Elles servent
a pre-remplir les champs avec des valeurs explicables et faciles a corriger.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
import re
import unicodedata

from achat_immo.city_profiles import loyer_max_hc_mensuel, profile_for_city
from achat_immo.engines.fiscal_rules import (
    prelevements_sociaux_par_regime,
    regime_fiscal_recommande,
    regimes_compatibles as _regimes_compatibles,
)
from achat_immo.models import (
    BienImmobilier,
    ModeLocation,
    RegimeFiscal,
    TypeBien,
)
from achat_immo.storage import AnnonceRecord, HypothesesAchatRecord, to_domain_models


SOURCE_REGIMES = "https://www.impots.gouv.fr/particulier/les-regimes-dimposition"
SOURCE_PRELEVEMENTS = (
    "https://www.impots.gouv.fr/particulier/questions/"
    "je-donne-un-bien-en-location-dois-je-payer-des-prelevements-sociaux"
)
SOURCE_CFE = (
    "https://www.impots.gouv.fr/particulier/questions/"
    "je-fais-de-la-location-meublee-dois-je-payer-de-la-cfe-cotisation-fonciere-des"
)
SOURCE_MICRO_FONCIER = "https://bofip.impots.gouv.fr/bofip/3973-PGP.html"
SOURCE_GRENOBLE_LOYERS = (
    "https://www.grenoblealpesmetropole.fr/940-me-renseigner-sur-l-encadrement-des-loyers.htm"
)


@dataclass(frozen=True, slots=True)
class HypothesisSuggestion:
    """Valeur proposee pour un champ d'hypothese."""

    field: str
    value: Any
    confidence: str
    source: str
    reason: str


def regimes_compatibles(mode_location: ModeLocation) -> tuple[RegimeFiscal, ...]:
    """Compatibilite historique : utiliser `achat_immo.engines.fiscal_rules` directement."""

    return _regimes_compatibles(mode_location)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _round_to(value: float, step: float) -> float:
    return round(value / step) * step


def _amount_from_segment(segment: str) -> float | None:
    match = re.search(r"([0-9][0-9 .,\u00a0]*)\s*(?:eur|euros?|\u20ac)", segment)
    if not match:
        return None
    raw = match.group(1).replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _amount_near(text: str, keywords: tuple[str, ...], *, window: int = 120) -> float | None:
    for keyword in keywords:
        index = text.find(keyword)
        if index == -1:
            continue
        amount = _amount_from_segment(text[index : index + window])
        if amount is not None:
            return amount
    return None


def _monthly_context(text: str, keywords: tuple[str, ...], *, window: int = 140) -> bool:
    for keyword in keywords:
        index = text.find(keyword)
        if index == -1:
            continue
        segment = text[index : index + window]
        if "mois" in segment or "mensuel" in segment:
            return True
    return False


def _mode_location_suggere(annonce: AnnonceRecord, hypotheses: HypothesesAchatRecord) -> ModeLocation:
    text = _normalize_text(f"{annonce.description} {annonce.notes}")
    if "non meuble" in text or "location nue" in text:
        return ModeLocation.NUE
    if "meuble" in text or "lmnp" in text:
        return ModeLocation.MEUBLEE
    return hypotheses.mode_location


def _meubles_estimes(type_bien: TypeBien, surface_m2: float, mode_location: ModeLocation) -> float:
    if mode_location == ModeLocation.NUE:
        return 0.0
    by_type = {
        TypeBien.STUDIO: 2_500.0,
        TypeBien.T1: 2_500.0,
        TypeBien.T2: 4_000.0,
        TypeBien.T3: 5_500.0,
    }
    return max(by_type.get(type_bien, 4_500.0), _round_to(surface_m2 * 110.0, 250.0))


def _travaux_estimes(annonce: AnnonceRecord) -> tuple[float, str, str]:
    text = _normalize_text(annonce.description)
    surface = annonce.surface_m2
    dpe = (annonce.dpe or "").strip().upper()[:1]
    if dpe == "G":
        return max(15_000.0, _round_to(surface * 550.0, 500.0)), "moyenne", "DPE G : enveloppe prudente de travaux energetiques."
    if dpe == "F":
        return max(10_000.0, _round_to(surface * 400.0, 500.0)), "moyenne", "DPE F : risque de travaux avant interdiction de louer."
    if dpe == "E":
        return max(5_000.0, _round_to(surface * 180.0, 500.0)), "faible", "DPE E : reserve de travaux a horizon long."
    if any(keyword in text for keyword in ("travaux", "renover", "rafraichir", "a refaire")):
        return max(8_000.0, _round_to(surface * 300.0, 500.0)), "moyenne", "Description mentionnant des travaux ou un rafraichissement."
    if any(keyword in text for keyword in ("renove", "refait", "bon etat", "aucun travaux")):
        return 0.0, "moyenne", "Description indiquant un etat renove ou sans travaux."
    return max(0.0, hypotheses_default_travaux(surface)), "faible", "Reserve minimale faute d'information travaux."


def hypotheses_default_travaux(surface_m2: float) -> float:
    return _round_to(max(1_000.0, surface_m2 * 40.0), 500.0)


def _loyer_hc_estime(
    bien: BienImmobilier,
    mode_location: ModeLocation,
    hypotheses: HypothesesAchatRecord,
) -> tuple[float, str, str, str]:
    location = to_domain_models(
        AnnonceRecord(
            ville=bien.ville,
            surface_m2=bien.surface_m2,
            prix_affiche=bien.prix_affiche,
            type_bien=bien.type_bien,
            nb_pieces=bien.nb_pieces,
            epoque_construction=bien.epoque_construction,
            secteur_encadrement=bien.secteur_encadrement,
            dpe=bien.dpe or "",
        ),
        replace(hypotheses, mode_location=mode_location),
    )[1]
    plafond = loyer_max_hc_mensuel(bien, location)
    if plafond is not None:
        return _round_to(plafond * 0.95, 10.0), "forte", SOURCE_GRENOBLE_LOYERS, "95 % du plafond local calcule, pour garder une marge juridique."

    profile = profile_for_city(bien.ville)
    city = profile.code if profile else ""
    small = bien.type_bien in {TypeBien.STUDIO, TypeBien.T1}
    if city == "grenoble":
        price_m2 = 18.5 if small else 15.5
    elif city == "nimes":
        price_m2 = 14.0 if small else 12.0
    else:
        price_m2 = 13.0 if small else 11.5
    if mode_location == ModeLocation.MEUBLEE:
        price_m2 *= 1.05
    return _round_to(bien.surface_m2 * price_m2, 10.0), "faible", "estimation interne par ville et surface", "Estimation de marche faute de plafond calculable ou de loyer annonce."


def _frais_agence_achat(text: str, prix_affiche: float) -> tuple[float, str, str]:
    if "charge vendeur" in text or "honoraires vendeur" in text or "fai" in text:
        return 0.0, "moyenne", "Prix annonce suppose frais d'agence inclus ou a charge vendeur."
    if "charge acquereur" in text or "honoraires acquereur" in text:
        segment_start = min(
            index for index in (text.find("charge acquereur"), text.find("honoraires acquereur")) if index >= 0
        )
        segment = text[segment_start : segment_start + 160]
        amount = _amount_from_segment(segment)
        if amount is not None:
            return _round_to(amount, 100.0), "forte", "Montant d'honoraires acquereur detecte dans l'annonce."
        percent = re.search(r"([0-9]+(?:[,.][0-9]+)?)\s*%", segment)
        if percent:
            pct = float(percent.group(1).replace(",", "."))
            return _round_to(prix_affiche * pct / 100, 100.0), "moyenne", "Pourcentage d'honoraires acquereur detecte dans l'annonce."
    return 0.0, "faible", "Aucun honoraire acquereur detecte ; le prix est suppose FAI."


def inferer_hypotheses_depuis_annonce(
    annonce: AnnonceRecord,
    hypotheses: HypothesesAchatRecord,
) -> dict[str, HypothesisSuggestion]:
    """Retourne des suggestions de pre-remplissage pour une annonce."""

    bien, _, _ = to_domain_models(annonce, hypotheses)
    text = _normalize_text(f"{annonce.description} {annonce.notes}")
    mode_location = _mode_location_suggere(annonce, hypotheses)
    loyer, loyer_confidence, loyer_source, loyer_reason = _loyer_hc_estime(
        bien,
        mode_location,
        hypotheses,
    )
    revenus_annuels = loyer * 12
    regime = regime_fiscal_recommande(mode_location, revenus_annuels)
    frais_agence, frais_agence_confidence, frais_agence_reason = _frais_agence_achat(text, annonce.prix_affiche)
    notaire_rate = 0.025 if "vefa" in text or "neuf" in text else 0.08
    travaux, travaux_confidence, travaux_reason = _travaux_estimes(annonce)

    taxe_fonciere = _amount_near(text, ("taxe fonciere", "foncier"))
    if taxe_fonciere is None:
        taxe_m2 = 22.0 if profile_for_city(annonce.ville) and profile_for_city(annonce.ville).code == "nimes" else 18.0
        taxe_fonciere = max(450.0, _round_to(annonce.surface_m2 * taxe_m2, 50.0))
        taxe_reason = "Estimation par ville et surface faute de taxe fonciere detectee."
        taxe_confidence = "faible"
    else:
        taxe_fonciere = _round_to(taxe_fonciere, 50.0)
        taxe_reason = "Montant detecte dans la description de l'annonce."
        taxe_confidence = "forte"

    charges_copro = _amount_near(text, ("charges copro", "charges de copro", "copropriete"))
    if charges_copro is None:
        charges_copro = _round_to(max(300.0, annonce.surface_m2 * 26.0), 50.0)
        charges_reason = "Estimation prudente par surface faute de charges de copro detectees."
        charges_confidence = "faible"
    else:
        if _monthly_context(text, ("charges copro", "charges de copro", "copropriete")):
            charges_copro *= 12
        charges_copro = _round_to(charges_copro, 50.0)
        charges_reason = "Montant de charges detecte dans la description de l'annonce."
        charges_confidence = "moyenne"

    cfe = 0.0
    cfe_reason = "Location nue : CFE non appliquee dans ce modele."
    if mode_location == ModeLocation.MEUBLEE and revenus_annuels > 5_000:
        cfe = 300.0
        cfe_reason = "Location meublee avec recettes superieures a 5 000 EUR : provision CFE minimale a verifier par commune."

    suggestions = {
        "mode_location": HypothesisSuggestion(
            "mode_location",
            mode_location,
            "moyenne",
            "description de l'annonce",
            "Detection des mentions meuble/non meuble, sinon conservation du mode courant.",
        ),
        "frais_notaire_estimes": HypothesisSuggestion(
            "frais_notaire_estimes",
            _round_to(annonce.prix_affiche * notaire_rate, 100.0),
            "moyenne",
            "estimation interne",
            "Taux 8 % en ancien, 2,5 % si l'annonce mentionne neuf ou VEFA.",
        ),
        "frais_agence_achat": HypothesisSuggestion(
            "frais_agence_achat",
            frais_agence,
            frais_agence_confidence,
            "description de l'annonce",
            frais_agence_reason,
        ),
        "travaux_estimes": HypothesisSuggestion(
            "travaux_estimes",
            travaux,
            travaux_confidence,
            "description et DPE",
            travaux_reason,
        ),
        "meubles_estimes": HypothesisSuggestion(
            "meubles_estimes",
            _round_to(_meubles_estimes(annonce.type_bien, annonce.surface_m2, mode_location), 250.0),
            "moyenne",
            "estimation interne",
            "Budget mobilier selon type, surface et mode de location.",
        ),
        "frais_bancaires": HypothesisSuggestion(
            "frais_bancaires",
            1_000.0,
            "faible",
            "estimation interne",
            "Frais de dossier et frais bancaires usuels pour un premier chiffrage.",
        ),
        "garantie": HypothesisSuggestion(
            "garantie",
            _round_to(max(800.0, annonce.prix_affiche * 0.01), 100.0),
            "faible",
            "estimation interne",
            "Provision pour cautionnement ou garantie bancaire, a remplacer par l'offre de pret.",
        ),
        "loyer_hc_mensuel": HypothesisSuggestion(
            "loyer_hc_mensuel",
            max(1.0, loyer),
            loyer_confidence,
            loyer_source,
            loyer_reason,
        ),
        "taxe_fonciere": HypothesisSuggestion(
            "taxe_fonciere",
            taxe_fonciere,
            taxe_confidence,
            "annonce ou estimation ville",
            taxe_reason,
        ),
        "charges_copro_annuelles": HypothesisSuggestion(
            "charges_copro_annuelles",
            charges_copro,
            charges_confidence,
            "annonce ou estimation surface",
            charges_reason,
        ),
        "charges_recuperables_annuelles": HypothesisSuggestion(
            "charges_recuperables_annuelles",
            _round_to(charges_copro * 0.55, 50.0),
            "faible",
            "estimation interne",
            "55 % des charges de copro supposees recuperables faute de decompte bailleur/locataire.",
        ),
        "assurance_pno": HypothesisSuggestion(
            "assurance_pno",
            _round_to(max(160.0, annonce.surface_m2 * 5.0), 20.0),
            "moyenne",
            "estimation interne",
            "Provision annuelle PNO selon surface.",
        ),
        "assurance_gli": HypothesisSuggestion(
            "assurance_gli",
            0.0,
            "moyenne",
            "choix de gestion",
            "GLI laissee a 0 par defaut ; si activee, utiliser environ 2,5 a 4 % des loyers charges comprises.",
        ),
        "cfe_annuelle": HypothesisSuggestion(
            "cfe_annuelle",
            cfe,
            "moyenne" if cfe else "forte",
            SOURCE_CFE,
            cfe_reason,
        ),
        "comptable_lmnp": HypothesisSuggestion(
            "comptable_lmnp",
            500.0 if regime == RegimeFiscal.LMNP_REEL else 0.0,
            "moyenne",
            SOURCE_REGIMES,
            "Provision expert-comptable en LMNP reel ; inutile dans les regimes micro.",
        ),
        "entretien_annuel": HypothesisSuggestion(
            "entretien_annuel",
            _round_to(max(300.0, annonce.surface_m2 * 12.0), 50.0),
            "faible",
            "estimation interne",
            "Reserve annuelle pour petit entretien courant non planifie.",
        ),
        "regime_fiscal": HypothesisSuggestion(
            "regime_fiscal",
            regime,
            "moyenne",
            SOURCE_REGIMES,
            "Regime reel recommande par defaut pour une simulation precise d'investissement.",
        ),
        "prelevements_sociaux_pct": HypothesisSuggestion(
            "prelevements_sociaux_pct",
            prelevements_sociaux_par_regime(regime),
            "forte",
            SOURCE_PRELEVEMENTS,
            "Taux 2026 : 18,6 % en meuble, 17,2 % en location nue.",
        ),
        "part_terrain_pct": HypothesisSuggestion(
            "part_terrain_pct",
            15.0,
            "faible",
            SOURCE_REGIMES,
            "Part non amortissable indicative, a ajuster avec l'expert-comptable.",
        ),
        "duree_amortissement_bien_annees": HypothesisSuggestion(
            "duree_amortissement_bien_annees",
            30,
            "moyenne",
            SOURCE_REGIMES,
            "Duree indicative d'amortissement du bati pour le LMNP reel simplifie.",
        ),
        "duree_amortissement_travaux_annees": HypothesisSuggestion(
            "duree_amortissement_travaux_annees",
            15,
            "moyenne",
            SOURCE_REGIMES,
            "Duree indicative pour lisser les travaux immobilises.",
        ),
        "duree_amortissement_meubles_annees": HypothesisSuggestion(
            "duree_amortissement_meubles_annees",
            7,
            "moyenne",
            SOURCE_REGIMES,
            "Duree indicative pour le mobilier en location meublee.",
        ),
        "abattement_micro_bic_pct": HypothesisSuggestion(
            "abattement_micro_bic_pct",
            50.0,
            "forte",
            SOURCE_REGIMES,
            "Abattement micro-BIC usuel des locations meublees longue duree.",
        ),
        "abattement_micro_foncier_pct": HypothesisSuggestion(
            "abattement_micro_foncier_pct",
            30.0,
            "forte",
            SOURCE_MICRO_FONCIER,
            "Abattement micro-foncier representatif de l'ensemble des charges.",
        ),
    }
    return suggestions


def appliquer_suggestions(
    hypotheses: HypothesesAchatRecord,
    suggestions: dict[str, HypothesisSuggestion],
    *,
    only_empty: bool = False,
) -> HypothesesAchatRecord:
    """Applique les suggestions a un record d'hypotheses."""

    changes: dict[str, Any] = {}
    for field, suggestion in suggestions.items():
        current = getattr(hypotheses, field)
        if only_empty and current not in (0, 0.0, "", None):
            continue
        changes[field] = suggestion.value
    return replace(hypotheses, **changes)
