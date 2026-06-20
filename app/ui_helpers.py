"""Helpers purs de presentation pour l'application Streamlit."""

from __future__ import annotations

from typing import Any

from achat_immo.engines.fiscal_rules import prelevements_sociaux_par_regime
from achat_immo.models import Fiscalite, ModeLocation, RegimeFiscal


STATUTS = [
    "nouveau",
    "a_analyser",
    "diagnostic_incomplet",
    "donnees_insuffisantes",
    "hors_criteres",
    "a_verifier",
    "shortlist",
    "a_visiter",
    "a_negocier",
    "contacte",
    "offre_faite",
    "favori",
    "rejete",
    "archive",
]

SIMULATION_SECTION_LABELS = ("Exploitation", "Strategies testees", "Analyse")
PORTFOLIO_DECISION_LABEL = "Comparaison"

FIELD_ORIGIN = {
    "frais_notaire_estimes": "Saisi",
    "frais_agence_achat": "Saisi",
    "travaux_estimes": "Saisi",
    "meubles_estimes": "Saisi",
    "frais_bancaires": "Saisi",
    "garantie": "Saisi",
    "mode_location": "Saisi",
    "loyer_hc_mensuel": "Saisi",
    "taxe_fonciere": "Saisi",
    "charges_copro_annuelles": "Saisi",
    "charges_recuperables_annuelles": "Saisi",
    "assurance_pno": "Saisi",
    "assurance_gli": "Saisi",
    "cfe_annuelle": "Saisi",
    "comptable_lmnp": "Saisi",
    "entretien_annuel": "Saisi",
    "gestion_agence_possible": "Saisi",
    "regime_fiscal": "Saisi",
    "tmi_pct": "Saisi",
    "prelevements_sociaux_pct": "Deduit",
    "abattement_micro_bic_pct": "Deduit",
    "abattement_micro_foncier_pct": "Deduit",
    "seuil_micro_bic": "Deduit",
    "seuil_micro_foncier": "Deduit",
    "taux_impot_plus_value_pct": "Deduit",
    "taux_prelevements_sociaux_plus_value_pct": "Deduit",
    "reintegrer_amortissements_lmnp_plus_value": "Deduit",
    "cfe_neutralisee": "Deduit",
    "comptable_lmnp_neutralise": "Deduit",
    "part_terrain_pct": "Avance",
    "duree_amortissement_bien_annees": "Avance",
    "duree_amortissement_travaux_annees": "Avance",
    "duree_amortissement_meubles_annees": "Avance",
}


def field_origin(field_name: str) -> str:
    return FIELD_ORIGIN.get(field_name, "Saisi")


def is_deduced_field(field_name: str) -> bool:
    return field_origin(field_name) == "Deduit"


def is_advanced_field(field_name: str) -> bool:
    return field_origin(field_name) == "Avance"


def is_cfe_applicable(mode_location: ModeLocation) -> bool:
    return mode_location == ModeLocation.MEUBLEE


def is_comptable_lmnp_applicable(regime_fiscal: RegimeFiscal) -> bool:
    return regime_fiscal == RegimeFiscal.LMNP_REEL


def effective_cfe_value(mode_location: ModeLocation, value: float) -> float:
    return float(value) if is_cfe_applicable(mode_location) else 0.0


def effective_comptable_lmnp_value(regime_fiscal: RegimeFiscal, value: float) -> float:
    return float(value) if is_comptable_lmnp_applicable(regime_fiscal) else 0.0


def derived_fiscalite_values(regime_fiscal: RegimeFiscal) -> dict[str, float | bool]:
    defaults = Fiscalite()
    return {
        "prelevements_sociaux_pct": prelevements_sociaux_par_regime(regime_fiscal),
        "abattement_micro_bic_pct": defaults.abattement_micro_bic_pct,
        "abattement_micro_foncier_pct": defaults.abattement_micro_foncier_pct,
        "taux_impot_plus_value_pct": defaults.taux_impot_plus_value_pct,
        "taux_prelevements_sociaux_plus_value_pct": defaults.taux_prelevements_sociaux_plus_value_pct,
        "reintegrer_amortissements_lmnp_plus_value": defaults.reintegrer_amortissements_lmnp_plus_value,
    }


def enum_label(value: Any) -> str:
    return str(getattr(value, "value", value)).replace("_", " ")


def display_hypothesis_value(value: Any) -> str:
    if hasattr(value, "value"):
        return enum_label(value)
    if isinstance(value, bool):
        return "oui" if value else "non"
    if isinstance(value, float):
        return f"{value:,.1f}" if value % 1 else f"{value:,.0f}"
    return str(value)


def format_eur(value: float) -> str:
    return f"{value:,.0f} EUR"


def format_eur_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.0f} EUR"


def gestion_label(value: object) -> str:
    return "agence" if bool(value) else "directe"
