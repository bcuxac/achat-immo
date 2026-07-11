"""Objets de transfert pour les lignes persistantes."""

from __future__ import annotations

from dataclasses import dataclass

from achat_immo.models import (
    EpoqueConstruction,
    ModeLocation,
    RegimeFiscal,
    TypeBien,
)


@dataclass(slots=True)
class AnnonceRecord:
    """Annonce suivie dans l'application."""

    ville: str
    surface_m2: float
    prix_affiche: float
    id: int | None = None
    date_creation: str = ""
    url: str = ""
    quartier: str = ""
    adresse: str = ""
    type_bien: TypeBien = TypeBien.T2
    nb_pieces: int | None = None
    epoque_construction: EpoqueConstruction = EpoqueConstruction.INCONNUE
    secteur_encadrement: str = ""
    prix_negocie: float | None = None
    dpe: str = ""
    description: str = ""
    statut: str = "a_verifier"
    notes: str = ""
    # Metrics pre-calculees par l'Orchestrateur (Monte Carlo & Solveur)
    tri_p50: float | None = None
    tri_p10: float | None = None
    probabilite_cashflow_positif: float | None = None
    prix_cible_recommande: float | None = None
    cashflow_p50: float | None = None
    coc_p50: float | None = None


@dataclass(slots=True)
class HypothesesAchatRecord:
    """Hypotheses propres a l'annonce, hors grille automatique."""

    annonce_id: int | None = None
    frais_agence_achat: float = 0.0
    frais_notaire_estimes: float = 0.0
    travaux_estimes: float = 0.0
    meubles_estimes: float = 0.0
    frais_bancaires: float = 0.0
    garantie: float = 0.0
    loyer_hc_mensuel: float = 650.0
    mode_location: ModeLocation = ModeLocation.MEUBLEE
    charges_copro_annuelles: float = 0.0
    charges_recuperables_annuelles: float = 0.0
    taxe_fonciere: float = 0.0
    assurance_pno: float = 180.0
    assurance_gli: float = 0.0
    frais_gestion_pct: float = 7.0
    cfe_annuelle: float = 0.0
    comptable_lmnp: float = 500.0
    entretien_annuel: float = 500.0
    regime_fiscal: RegimeFiscal = RegimeFiscal.LMNP_REEL
    tmi_pct: float = 30.0
    prelevements_sociaux_pct: float = 18.6
    part_terrain_pct: float = 15.0
    duree_amortissement_bien_annees: int = 30
    duree_amortissement_travaux_annees: int = 15
    duree_amortissement_meubles_annees: int = 7
    abattement_micro_bic_pct: float = 50.0
    abattement_micro_foncier_pct: float = 30.0
    gestion_agence_possible: bool = True
    apport_reference: float = 15_000.0
    taux_credit_reference: float = 3.6
    duree_credit_reference: int = 20
    assurance_emprunteur_pct: float = 0.30


@dataclass(slots=True)
class ExtractionRunRecord:
    """Trace d'une extraction IA ou scraping associee a une annonce."""

    annonce_id: int
    id: int | None = None
    date_run: str = ""
    source_url: str = ""
    final_url: str = ""
    status: str = ""
    model: str = ""
    input_chars: int = 0
    raw_content_hash: str = ""
    extracted_source: str = ""
    red_flags: str = ""
    missing_fields: str = ""
    error_message: str = ""


@dataclass(slots=True)
class AnalysisRunRecord:
    """Trace d'une analyse Monte Carlo et solveur inverse."""

    annonce_id: int
    id: int | None = None
    date_run: str = ""
    status: str = ""
    scenario_seed: int = 0
    nb_scenarios: int = 0
    solver_status: str = ""
    solver_iterations: int = 0
    price_floor: float | None = None
    price_ceiling: float | None = None
    target_tri_median: float = 0.0
    target_tri_p10: float = 0.0
    target_coc: float = 0.0
    target_cashflow: float = 0.0
    tri_p50: float | None = None
    tri_p10: float | None = None
    probabilite_cashflow_positif: float | None = None
    coc_p50: float | None = None
    cashflow_p50: float | None = None
    recommended_price: float | None = None
    recommended_project_cost: float | None = None
    recommended_apport: float | None = None
    recommended_loan_amount: float | None = None
    summary_json: str = ""
    diagnostics: str = ""


@dataclass(slots=True)
class SourcingQueueRecord:
    """URL en attente ou deja traitee par l'aspirateur."""

    source_url: str
    id: int | None = None
    date_creation: str = ""
    date_update: str = ""
    source: str = "manual"
    status: str = "pending"
    priority: int = 0
    attempts: int = 0
    annonce_id: int | None = None
    last_error: str = ""
    last_processed_at: str = ""


@dataclass(slots=True)
class SourcingRunRecord:
    """Synthese d'un traitement de file de sourcing."""

    id: int | None = None
    date_start: str = ""
    date_end: str = ""
    status: str = "running"
    url_limit: int = 0
    source_limit: int | None = None
    allowed_domains: str = ""
    skip_prefilter: bool = False
    pending_at_start: int = 0
    examined_count: int = 0
    processed_count: int = 0
    successes: int = 0
    failures: int = 0
    skipped: int = 0
    blocked: int = 0
    pending_after: int = 0
    error_message: str = ""


@dataclass(slots=True)
class JinkaAlertRecord:
    """Alerte Jinka a developper en URLs d'annonces."""

    alert_id: str
    id: int | None = None
    date_creation: str = ""
    date_update: str = ""
    source_url: str = ""
    source: str = "jinka_email"
    status: str = "pending"
    priority: int = 0
    attempts: int = 0
    last_notification_count: int | None = None
    last_seen_at: str = ""
    last_collected_at: str = ""
    discovered_ads_count: int = 0
    last_error: str = ""
