"""Moteur de simulation d'investissement immobilier locatif."""

from achat_immo.models import (
    AlternativeInvestissement,
    BienImmobilier,
    Financement,
    Fiscalite,
    HypothesesLocation,
    RegimeFiscal,
    ResultatSimulation,
    Scenario,
    TypeBien,
)
from achat_immo.scenarios import (
    comparer_immo_vs_bourse,
    scenario_central,
    scenario_optimiste,
    scenario_pessimiste,
    simuler_alternative_bourse,
    simuler_bien_sur_horizon,
)

__all__ = [
    "AlternativeInvestissement",
    "BienImmobilier",
    "Financement",
    "Fiscalite",
    "HypothesesLocation",
    "RegimeFiscal",
    "ResultatSimulation",
    "Scenario",
    "TypeBien",
    "comparer_immo_vs_bourse",
    "scenario_central",
    "scenario_optimiste",
    "scenario_pessimiste",
    "simuler_alternative_bourse",
    "simuler_bien_sur_horizon",
]
