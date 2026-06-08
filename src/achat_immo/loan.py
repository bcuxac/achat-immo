"""Calculs de credit amortissable a taux fixe."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class EcheancePret:
    mois: int
    annee: int
    date: date | None
    mensualite_credit: float
    interets: float
    capital: float
    assurance: float
    mensualite_totale: float
    crd_avant: float
    crd_apres: float


def _round_euros(value: float) -> float:
    return round(value, 2)


def calcul_mensualite(montant: float, taux_annuel_pct: float, duree_annees: int) -> float:
    """Mensualite hors assurance d'un pret amortissable."""

    if montant < 0:
        raise ValueError("montant doit etre positif ou nul.")
    if taux_annuel_pct < 0:
        raise ValueError("taux_annuel_pct doit etre positif ou nul.")
    if duree_annees <= 0:
        raise ValueError("duree_annees doit etre strictement positive.")
    if montant == 0:
        return 0.0

    nb_mois = duree_annees * 12
    taux_mensuel = taux_annuel_pct / 100 / 12
    if taux_mensuel == 0:
        return _round_euros(montant / nb_mois)

    mensualite = montant * taux_mensuel / (1 - (1 + taux_mensuel) ** (-nb_mois))
    return _round_euros(mensualite)


def mensualite_assurance(montant: float, assurance_annuelle_pct: float) -> float:
    """Assurance mensuelle calculee sur le capital initial."""

    if montant < 0:
        raise ValueError("montant doit etre positif ou nul.")
    if assurance_annuelle_pct < 0:
        raise ValueError("assurance_annuelle_pct doit etre positif ou nul.")
    return _round_euros(montant * assurance_annuelle_pct / 100 / 12)


def capital_restant_du(
    montant: float,
    taux_annuel_pct: float,
    duree_annees: int,
    mois_ecoules: int,
) -> float:
    """Capital restant du apres un nombre de mensualites."""

    if mois_ecoules < 0:
        raise ValueError("mois_ecoules doit etre positif ou nul.")
    nb_mois = duree_annees * 12
    if mois_ecoules == 0:
        return _round_euros(montant)
    if mois_ecoules >= nb_mois:
        return 0.0
    if montant == 0:
        return 0.0

    mensualite = calcul_mensualite(montant, taux_annuel_pct, duree_annees)
    taux_mensuel = taux_annuel_pct / 100 / 12
    if taux_mensuel == 0:
        crd = montant * (1 - mois_ecoules / nb_mois)
    else:
        mois_restants = nb_mois - mois_ecoules
        crd = mensualite * (1 - (1 + taux_mensuel) ** (-mois_restants)) / taux_mensuel
    return _round_euros(max(crd, 0.0))


def _add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, 28)
    return date(year, month, day)


def tableau_amortissement(
    montant: float,
    taux_annuel_pct: float,
    duree_annees: int,
    assurance_annuelle_pct: float = 0.0,
    date_debut: date | None = None,
) -> list[EcheancePret]:
    """Tableau mensuel d'amortissement.

    Le dernier mois ajuste la part capital pour eviter un reliquat du aux arrondis.
    """

    nb_mois = duree_annees * 12
    mensualite = calcul_mensualite(montant, taux_annuel_pct, duree_annees)
    assurance = mensualite_assurance(montant, assurance_annuelle_pct)
    taux_mensuel = taux_annuel_pct / 100 / 12
    crd = _round_euros(montant)
    echeances: list[EcheancePret] = []

    for mois in range(1, nb_mois + 1):
        crd_avant = crd
        interets = _round_euros(crd_avant * taux_mensuel)
        capital = _round_euros(mensualite - interets)
        if mois == nb_mois or capital > crd_avant:
            capital = crd_avant
            mensualite_credit = _round_euros(capital + interets)
        else:
            mensualite_credit = mensualite
        crd = _round_euros(max(crd_avant - capital, 0.0))
        echeances.append(
            EcheancePret(
                mois=mois,
                annee=(mois - 1) // 12 + 1,
                date=_add_months(date_debut, mois - 1) if date_debut else None,
                mensualite_credit=mensualite_credit,
                interets=interets,
                capital=capital,
                assurance=assurance,
                mensualite_totale=_round_euros(mensualite_credit + assurance),
                crd_avant=crd_avant,
                crd_apres=crd,
            )
        )
    return echeances


def interets_par_annee(echeances: list[EcheancePret]) -> dict[int, float]:
    """Agrege les interets payes par annee de pret."""

    resultats: dict[int, float] = {}
    for echeance in echeances:
        resultats[echeance.annee] = resultats.get(echeance.annee, 0.0) + echeance.interets
    return {annee: _round_euros(total) for annee, total in resultats.items()}
