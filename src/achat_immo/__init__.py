"""Moteur de simulation d'investissement immobilier locatif."""

from achat_immo.models import (
    BienImmobilier,
    EpoqueConstruction,
    Financement,
    Fiscalite,
    HypothesesLocation,
    ModeLocation,
    RegimeFiscal,
    ResultatSimulation,
    Scenario,
    TypeBien,
)
from achat_immo.grids import GrilleParametres, GrilleResultat, simuler_grille_annonce
from achat_immo.city_profiles import (
    CityProfile,
    canonical_city_label,
    loyer_max_hc_mensuel,
    profile_for_city,
    supported_city_labels,
)
from achat_immo.diagnostics import DiagnosticItem, DiagnosticStatus, diagnostiquer_annonce
from achat_immo.hypothesis_inference import (
    HypothesisSuggestion,
    appliquer_suggestions,
    inferer_hypotheses_depuis_annonce,
)
from achat_immo.fiscal_rules import (
    prelevements_sociaux_par_regime,
    regime_fiscal_recommande,
    regimes_compatibles,
)
from achat_immo.robustness import RobustesseGrille, analyser_grille
from achat_immo.storage import fiscalite_from_hypotheses
from achat_immo.scenarios import (
    scenario_central,
    scenario_optimiste,
    scenario_pessimiste,
    simuler_bien_sur_horizon,
)

__all__ = [
    "BienImmobilier",
    "CityProfile",
    "DiagnosticItem",
    "DiagnosticStatus",
    "EpoqueConstruction",
    "Financement",
    "Fiscalite",
    "GrilleParametres",
    "GrilleResultat",
    "HypothesesLocation",
    "HypothesisSuggestion",
    "ModeLocation",
    "RegimeFiscal",
    "ResultatSimulation",
    "RobustesseGrille",
    "Scenario",
    "TypeBien",
    "analyser_grille",
    "appliquer_suggestions",
    "canonical_city_label",
    "diagnostiquer_annonce",
    "fiscalite_from_hypotheses",
    "inferer_hypotheses_depuis_annonce",
    "loyer_max_hc_mensuel",
    "prelevements_sociaux_par_regime",
    "profile_for_city",
    "regime_fiscal_recommande",
    "regimes_compatibles",
    "scenario_central",
    "scenario_optimiste",
    "scenario_pessimiste",
    "simuler_grille_annonce",
    "simuler_bien_sur_horizon",
    "supported_city_labels",
]
