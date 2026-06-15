"""Regles fiscales transverses partagees par le moteur et l'interface."""

from __future__ import annotations

from achat_immo.models import ModeLocation, RegimeFiscal


def regimes_compatibles(mode_location: ModeLocation) -> tuple[RegimeFiscal, ...]:
    """Regimes modelises compatibles avec un mode de location."""

    if mode_location == ModeLocation.NUE:
        return (RegimeFiscal.LOCATION_NUE_REEL, RegimeFiscal.MICRO_FONCIER)
    return (RegimeFiscal.LMNP_REEL, RegimeFiscal.MICRO_BIC)


def regime_fiscal_recommande(mode_location: ModeLocation, revenus_hc_annuels: float) -> RegimeFiscal:
    """Choisit un regime prudent pour un investissement locatif classique."""

    _ = revenus_hc_annuels
    if mode_location == ModeLocation.NUE:
        return RegimeFiscal.LOCATION_NUE_REEL
    return RegimeFiscal.LMNP_REEL


def prelevements_sociaux_par_regime(regime: RegimeFiscal) -> float:
    """Taux sociaux 2026 pour les regimes locatifs modelises."""

    if regime in {RegimeFiscal.LMNP_REEL, RegimeFiscal.MICRO_BIC}:
        return 18.6
    return 17.2
