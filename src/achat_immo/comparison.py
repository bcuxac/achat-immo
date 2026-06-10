"""Scoring et classement des biens simules."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from achat_immo.diagnostics import DiagnosticItem, DiagnosticStatus
from achat_immo.models import RegimeFiscal, ResultatSimulation


@dataclass(frozen=True, slots=True)
class SeuilsDecision:
    rendement_brut_min_pct: float = 6.0
    rendement_net_min_pct: float = 4.5
    cashflow_mensuel_min: float = -200.0
    cashflow_mensuel_cible: float = 0.0
    dpe_a_eviter: tuple[str, ...] = ("F", "G")


def scorer_bien(
    resultat: ResultatSimulation,
    seuils: SeuilsDecision | None = None,
    diagnostics: Sequence[DiagnosticItem] = (),
) -> dict[str, object]:
    """Score interpretable sur 100 points."""

    seuils = seuils or SeuilsDecision()
    score = 100
    alertes: list[str] = []

    if resultat.rendement_brut_pct < seuils.rendement_brut_min_pct:
        score -= 20
        alertes.append("rendement_brut_insuffisant")
    if resultat.rendement_net_avant_impot_pct < seuils.rendement_net_min_pct:
        score -= 25
        alertes.append("rendement_net_insuffisant")
    if resultat.cashflow_mensuel_apres_impot < seuils.cashflow_mensuel_min:
        score -= 25
        alertes.append("cashflow_trop_negatif")
    elif resultat.cashflow_mensuel_apres_impot < seuils.cashflow_mensuel_cible:
        score -= 10
        alertes.append("cashflow_negatif")
    if resultat.regime_fiscal == RegimeFiscal.LMNP_REEL:
        score -= 5
        alertes.append("complexite_lmnp_reel")
    elif resultat.regime_fiscal == RegimeFiscal.LOCATION_NUE_REEL:
        score -= 3
        alertes.append("complexite_nue_reel")
    elif resultat.regime_fiscal in {RegimeFiscal.MICRO_BIC, RegimeFiscal.MICRO_FONCIER}:
        score -= 1
    dpe = (resultat.bien.dpe or "").upper()[:1]
    if dpe == "G":
        score = 0
        alertes.append("dpe_g_interdit_location")
    elif dpe in seuils.dpe_a_eviter:
        score -= 20
        alertes.append("dpe_a_risque")

    for item in diagnostics:
        if item.status == DiagnosticStatus.OK:
            continue
        if item.code not in alertes:
            alertes.append(item.code)
        if item.status == DiagnosticStatus.BLOCKING:
            score = 0
        elif item.status == DiagnosticStatus.MISSING:
            score -= 15
        elif item.status == DiagnosticStatus.WARNING:
            score -= 10

    score = max(score, 0)
    if any(item.status == DiagnosticStatus.BLOCKING for item in diagnostics) or "dpe_g_interdit_location" in alertes:
        decision = "a_rejeter"
    elif score >= 75 and not alertes:
        decision = "interessant"
    elif score >= 55:
        decision = "a_creuser"
    else:
        decision = "a_rejeter"

    return {
        "score": score,
        "decision": decision,
        "alertes": alertes,
    }


def filtrer_biens_invalides(
    resultats: list[ResultatSimulation],
    seuils: SeuilsDecision | None = None,
) -> list[ResultatSimulation]:
    """Supprime les biens qui franchissent un seuil bloquant."""

    seuils = seuils or SeuilsDecision()
    valides: list[ResultatSimulation] = []
    for resultat in resultats:
        dpe_risque = resultat.bien.dpe and resultat.bien.dpe.upper()[:1] in seuils.dpe_a_eviter
        cashflow_bloquant = resultat.cashflow_mensuel_apres_impot < seuils.cashflow_mensuel_min
        if not dpe_risque and not cashflow_bloquant:
            valides.append(resultat)
    return valides


def classer_biens(
    resultats: list[ResultatSimulation],
    seuils: SeuilsDecision | None = None,
) -> list[dict[str, object]]:
    """Classe les biens par score puis patrimoine net a horizon."""

    lignes = []
    for resultat in resultats:
        score = scorer_bien(resultat, seuils)
        lignes.append(
            {
                "ville": resultat.bien.ville,
                "quartier": resultat.bien.quartier,
                "type_bien": resultat.bien.type_bien.value,
                "scenario": resultat.scenario.nom,
                "score": score["score"],
                "decision": score["decision"],
                "alertes": ", ".join(score["alertes"]),
                **resultat.indicateurs,
            }
        )
    return sorted(
        lignes,
        key=lambda row: (float(row["score"]), float(row["patrimoine_net_horizon"])),
        reverse=True,
    )
