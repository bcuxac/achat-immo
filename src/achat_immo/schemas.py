"""Schemas de frontiere pour valider entrees UI, SQL et snapshots."""

from __future__ import annotations

import math
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from achat_immo.models import EpoqueConstruction, ModeLocation, RegimeFiscal, TypeBien


class BoundaryModel(BaseModel):
    """Base souple pour les donnees venant des frontieres de l'application."""

    model_config = ConfigDict(extra="ignore", from_attributes=True)


class AnnonceRecordSchema(BoundaryModel):
    """Contrat valide pour une annonce stockee ou saisie."""

    ville: str
    surface_m2: float = Field(ge=0)
    prix_affiche: float = Field(ge=0)
    id: int | None = None
    date_creation: str = ""
    url: str = ""
    quartier: str = ""
    adresse: str = ""
    type_bien: TypeBien = TypeBien.T2
    nb_pieces: int | None = Field(default=None, gt=0)
    epoque_construction: EpoqueConstruction = EpoqueConstruction.INCONNUE
    secteur_encadrement: str = ""
    prix_negocie: float | None = Field(default=None, gt=0)
    dpe: str = ""
    description: str = ""
    statut: str = "a_verifier"
    notes: str = ""
    # Metrics
    tri_p50: float | None = None
    tri_p10: float | None = None
    probabilite_cashflow_positif: float | None = None
    prix_cible_recommande: float | None = None
    cashflow_p50: float | None = None
    coc_p50: float | None = None


class HypothesesAchatRecordSchema(BoundaryModel):
    """Contrat valide pour les hypotheses sauvegardees d'une annonce."""

    annonce_id: int | None = None
    frais_agence_achat: float = Field(default=0.0, ge=0)
    frais_notaire_estimes: float = Field(default=0.0, ge=0)
    travaux_estimes: float = Field(default=0.0, ge=0)
    meubles_estimes: float = Field(default=0.0, ge=0)
    frais_bancaires: float = Field(default=0.0, ge=0)
    garantie: float = Field(default=0.0, ge=0)
    loyer_hc_mensuel: float = Field(default=650.0, ge=0)
    mode_location: ModeLocation = ModeLocation.MEUBLEE
    charges_copro_annuelles: float = Field(default=0.0, ge=0)
    charges_recuperables_annuelles: float = Field(default=0.0, ge=0)
    taxe_fonciere: float = Field(default=0.0, ge=0)
    assurance_pno: float = Field(default=180.0, ge=0)
    assurance_gli: float = Field(default=0.0, ge=0)
    frais_gestion_pct: float = Field(default=7.0, ge=0)
    cfe_annuelle: float = Field(default=0.0, ge=0)
    comptable_lmnp: float = Field(default=500.0, ge=0)
    entretien_annuel: float = Field(default=500.0, ge=0)
    regime_fiscal: RegimeFiscal = RegimeFiscal.LMNP_REEL
    tmi_pct: float = Field(default=30.0, ge=0, le=100)
    prelevements_sociaux_pct: float = Field(default=18.6, ge=0, le=100)
    part_terrain_pct: float = Field(default=15.0, ge=0, le=100)
    duree_amortissement_bien_annees: int = Field(default=30, gt=0)
    duree_amortissement_travaux_annees: int = Field(default=15, gt=0)
    duree_amortissement_meubles_annees: int = Field(default=7, gt=0)
    abattement_micro_bic_pct: float = Field(default=50.0, ge=0, le=100)
    abattement_micro_foncier_pct: float = Field(default=30.0, ge=0, le=100)
    gestion_agence_possible: bool = True
    apport_reference: float = Field(default=15_000.0, ge=0)
    taux_credit_reference: float = Field(default=3.6, ge=0)
    duree_credit_reference: int = Field(default=20, gt=0)
    assurance_emprunteur_pct: float = Field(default=0.30, ge=0)

    @model_validator(mode="after")
    def validate_charge_split(self) -> Self:
        if self.charges_recuperables_annuelles > self.charges_copro_annuelles:
            raise ValueError("charges_recuperables_annuelles ne peut pas depasser charges_copro_annuelles.")
        return self


class ExtractionRunRecordSchema(BoundaryModel):
    """Contrat valide pour une trace d'extraction automatique."""

    annonce_id: int
    id: int | None = None
    date_run: str = ""
    source_url: str = ""
    final_url: str = ""
    status: str = ""
    model: str = ""
    input_chars: int = Field(default=0, ge=0)
    raw_content_hash: str = ""
    extracted_source: str = ""
    red_flags: str = ""
    missing_fields: str = ""
    error_message: str = ""


class AnalysisRunRecordSchema(BoundaryModel):
    """Contrat valide pour une trace d'analyse Monte Carlo et solveur."""

    annonce_id: int
    id: int | None = None
    date_run: str = ""
    status: str = ""
    scenario_seed: int = Field(default=0, ge=0)
    nb_scenarios: int = Field(default=0, ge=0)
    solver_status: str = ""
    solver_iterations: int = Field(default=0, ge=0)
    price_floor: float | None = Field(default=None, ge=0)
    price_ceiling: float | None = Field(default=None, ge=0)
    target_tri_median: float = 0.0
    target_tri_p10: float = 0.0
    target_coc: float = 0.0
    target_cashflow: float = 0.0
    tri_p50: float | None = None
    tri_p10: float | None = None
    probabilite_cashflow_positif: float | None = None
    coc_p50: float | None = None
    cashflow_p50: float | None = None
    recommended_price: float | None = Field(default=None, ge=0)
    recommended_project_cost: float | None = Field(default=None, ge=0)
    recommended_apport: float | None = Field(default=None, ge=0)
    recommended_loan_amount: float | None = Field(default=None, ge=0)
    summary_json: str = ""
    diagnostics: str = ""


class SourcingQueueRecordSchema(BoundaryModel):
    """Contrat valide pour une URL dans la file de sourcing."""

    source_url: str
    id: int | None = None
    date_creation: str = ""
    date_update: str = ""
    source: str = "manual"
    status: str = "pending"
    priority: int = 0
    attempts: int = Field(default=0, ge=0)
    annonce_id: int | None = None
    last_error: str = ""
    last_processed_at: str = ""


class SourcingRunRecordSchema(BoundaryModel):
    """Contrat valide pour une synthese de traitement de queue."""

    id: int | None = None
    date_start: str = ""
    date_end: str = ""
    status: str = "running"
    url_limit: int = Field(default=0, ge=0)
    source_limit: int | None = Field(default=None, ge=1)
    allowed_domains: str = ""
    skip_prefilter: bool = False
    pending_at_start: int = Field(default=0, ge=0)
    examined_count: int = Field(default=0, ge=0)
    processed_count: int = Field(default=0, ge=0)
    successes: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    blocked: int = Field(default=0, ge=0)
    pending_after: int = Field(default=0, ge=0)
    error_message: str = ""


class JinkaAlertRecordSchema(BoundaryModel):
    """Contrat valide pour une alerte Jinka a collecter."""

    alert_id: str = Field(min_length=8)
    id: int | None = None
    date_creation: str = ""
    date_update: str = ""
    source_url: str = ""
    source: str = "jinka_email"
    status: str = "pending"
    priority: int = 0
    attempts: int = Field(default=0, ge=0)
    last_notification_count: int | None = Field(default=None, ge=0)
    last_seen_at: str = ""
    last_collected_at: str = ""
    discovered_ads_count: int = Field(default=0, ge=0)
    last_error: str = ""


class SimulationResultRowSchema(BoundaryModel):
    """Contrat plat pour une ligne persistable de resultat de simulation."""

    scenario: str = ""
    mode_location: str = ""
    regime_fiscal: str = ""
    prix_achat: float = Field(default=0.0, ge=0)
    cout_total_projet: float = Field(default=0.0, ge=0)
    loyer_hc_mensuel: float = Field(gt=0)
    taux_credit: float = Field(ge=0)
    duree_annees: int = Field(gt=0)
    apport: float = Field(ge=0)
    vacance_mois: float = Field(ge=0, le=12)
    gestion_agence: bool
    frais_gestion_pct: float = Field(default=0.0, ge=0)
    mensualite_totale: float = Field(ge=0)
    montant_emprunte: float = Field(ge=0)
    cashflow_mensuel_avant_impot: float
    cashflow_mensuel_apres_impot: float
    effort_epargne_mensuel: float = Field(ge=0)
    rendement_net_avant_impot_pct: float
    rendement_net_net_pct: float
    tri_annuel_pct: float | None = None
    van: float | None = None
    cash_on_cash_return_pct: float | None = None
    impots_total_horizon: float = Field(default=0.0, ge=0)
    impot_plus_value: float = Field(default=0.0, ge=0)
    patrimoine_net_horizon: float
    patrimoine_net_sortie: float = 0.0
    break_even_year: int | None = None
    nb_annees_cashflow_negatif: int = Field(default=0, ge=0)
    score: int = Field(ge=0)
    decision: str
    alertes: str = ""
    diagnostics: str = ""

    @field_validator("tri_annuel_pct", "van", "cash_on_cash_return_pct", "break_even_year", mode="before")
    @classmethod
    def none_if_nan(cls, value: Any) -> Any:
        if isinstance(value, float) and math.isnan(value):
            return None
        return value
