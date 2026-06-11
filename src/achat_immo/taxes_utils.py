"""Utilitaires internes de fiscalite."""

from __future__ import annotations

from achat_immo.models import BienImmobilier, Fiscalite


def round_euros(value: float) -> float:
    return round(value, 2)


def impot_sur_resultat(resultat_fiscal: float, fiscalite: Fiscalite) -> float:
    if resultat_fiscal <= 0:
        return 0.0
    return round_euros(resultat_fiscal * fiscalite.taux_global_imposition_pct / 100)


def frais_acquisition(bien: BienImmobilier) -> float:
    return bien.frais_agence_achat + bien.frais_notaire_estimes


def frais_emprunt(bien: BienImmobilier) -> float:
    return bien.frais_bancaires + bien.garantie
