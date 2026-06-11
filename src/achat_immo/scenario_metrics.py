"""Metriques financieres utilisees par les scenarios."""

from __future__ import annotations

from collections.abc import Sequence

from achat_immo.models import BienImmobilier, Scenario


def valeur_bien(bien: BienImmobilier, scenario: Scenario, annee: int) -> float:
    valeur = bien.prix_achat * (1 + scenario.appreciation_annuelle_pct / 100) ** annee
    return round(valeur, 2)


def tri_annuel_approx(flux: Sequence[float]) -> float | None:
    """TRI annuel par recherche dichotomique, retourne un taux decimal."""

    def npv(taux: float) -> float:
        return sum(flux_t / (1 + taux) ** index for index, flux_t in enumerate(flux))

    bas = -0.95
    haut = 1.0
    npv_bas = npv(bas)
    npv_haut = npv(haut)
    if npv_bas == 0:
        return bas
    if npv_haut == 0:
        return haut
    if npv_bas * npv_haut > 0:
        return None

    for _ in range(100):
        milieu = (bas + haut) / 2
        npv_milieu = npv(milieu)
        if abs(npv_milieu) < 1e-7:
            return milieu
        if npv_bas * npv_milieu <= 0:
            haut = milieu
        else:
            bas = milieu
            npv_bas = npv_milieu
    return (bas + haut) / 2


def van(flux: Sequence[float], taux_actualisation_pct: float) -> float:
    taux = taux_actualisation_pct / 100
    return round(sum(flux_t / (1 + taux) ** index for index, flux_t in enumerate(flux)), 2)
