"""Modèles de données pour la simulation stochastique."""

from dataclasses import dataclass
from achat_immo.models import RegimeFiscal, ModeLocation

@dataclass(slots=True)
class Strategy:
    """Strategie d'investissement candidate de base."""
    ville: str = "Inconnue"
    surface_m2: float = 40.0
    prix_achat: float = 120_000.0
    apport: float = 15_000.0
    duree_credit_annees: int = 20
    taux_credit_pct: float = 3.5
    assurance_emprunteur_pct: float = 0.3
    tmi_pct: float = 30.0
    regime_fiscal: RegimeFiscal = RegimeFiscal.LMNP_REEL
    mode_location: ModeLocation = ModeLocation.MEUBLEE
    horizon_annees: int = 20
    loyer_hc_mensuel: float = 600.0
    charges_copro_annuelles: float = 1000.0
    taxe_fonciere: float = 800.0
    travaux_initiaux: float = 0.0
    frais_notaire_estimes: float = 0.0
    frais_agence_achat: float = 0.0
    frais_gestion_pct: float = 7.0
    gestion_agence_active: bool = False
    assurance_pno_annuelle: float = 180.0
    comptable_lmnp_annuel: float = 500.0
    entretien_annuel: float = 500.0
    cfe_annuelle: float = 0.0

@dataclass(slots=True)
class ScenarioInput:
    """Hypotheses incertaines tirees pour un scenario donne."""
    scenario_id: int
    loyer_hc_mensuel: float
    vacance_mois_par_an: float
    croissance_loyer_annuelle_pct: float
    inflation_charges_annuelle_pct: float
    travaux_imprevus_annuels: float
    appreciation_bien_annuelle_pct: float
    decote_revente_pct: float

@dataclass(slots=True)
class ScenarioOutput:
    """Sortie agregee par scenario projeté."""
    scenario_id: int
    tri_annuel_pct: float | None
    van: float | None
    cash_on_cash_return_pct: float | None
    cashflow_cumule_horizon: float
    cashflow_annuel_minimal: float
    nb_annees_cashflow_negatif: int
    patrimoine_net_horizon: float
    prix_net_revente: float
    impot_total_paye: float
    cashflow_premiere_annee: float = 0.0
    is_valid: bool = True
    error_message: str | None = None
