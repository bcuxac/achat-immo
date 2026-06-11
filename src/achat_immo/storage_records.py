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
    statut: str = "a_analyser"
    notes: str = ""


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
