"""Analyse robuste d'une grille de scenarios.

Cette couche evite de motiver la decision par le meilleur cas uniquement. Elle
resume la distribution des scenarios et explicite les conditions de validite.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from achat_immo.comparison import SeuilsDecision


CRITICAL_MISSING_CODES = frozenset(
    {
        "dpe_manquant",
        "ville_non_referencee",
        "secteur_encadrement_manquant",
        "epoque_construction_manquante",
        "loyer_plafond_non_calcule",
    }
)

BLOCKING_CODES = frozenset(
    {
        "dpe_g_interdit_location",
        "loyer_superieur_plafond_local",
        "surface_non_decente",
    }
)


@dataclass(frozen=True, slots=True)
class RobustesseGrille:
    """Synthese lisible d'une grille complete de scenarios."""

    nb_scenarios: int
    nb_viables: int
    nb_positifs: int
    pct_viables: float
    pct_positifs: float
    cashflow_min: float | None
    cashflow_p10: float | None
    cashflow_median: float | None
    cashflow_p90: float | None
    cashflow_max: float | None
    meilleur_cashflow_prudent: float | None
    meilleur_cashflow_agence: float | None
    prix_max_viable: float | None
    prix_min_simule: float | None
    decision: str
    raisons: tuple[str, ...] = ()
    conditions_validite: tuple[str, ...] = ()
    diagnostics_critiques: tuple[str, ...] = ()
    seuil_cashflow_min: float = -200.0
    seuil_cashflow_cible: float = 0.0

    @property
    def diagnostic_incomplet(self) -> bool:
        return bool(self.diagnostics_critiques)


def _codes(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {part.strip() for part in value.split(",") if part.strip()}
    if isinstance(value, Iterable):
        return {str(part).strip() for part in value if str(part).strip()}
    return {str(value).strip()}


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


def _min_or_none(values: Iterable[float]) -> float | None:
    values_tuple = tuple(values)
    return min(values_tuple) if values_tuple else None


def _max_or_none(values: Iterable[float]) -> float | None:
    values_tuple = tuple(values)
    return max(values_tuple) if values_tuple else None


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "vrai", "yes", "oui"}


def _conditions(rows: list[Mapping[str, Any]], seuils: SeuilsDecision) -> tuple[str, ...]:
    viables = [row for row in rows if float(row["cashflow_mensuel_apres_impot"]) >= seuils.cashflow_mensuel_min]
    positifs = [row for row in rows if float(row["cashflow_mensuel_apres_impot"]) >= seuils.cashflow_mensuel_cible]
    if not viables:
        return (f"Aucun scenario n'atteint {seuils.cashflow_mensuel_min:,.0f} EUR/mois.",)

    conditions = [
        f"Loyer HC >= {_min_or_none(float(row['loyer_hc_mensuel']) for row in viables):,.0f} EUR",
        f"Apport >= {_min_or_none(float(row['apport']) for row in viables):,.0f} EUR",
        f"Duree credit >= {_min_or_none(float(row['duree_annees']) for row in viables):.0f} ans",
        f"Taux credit <= {_max_or_none(float(row['taux_credit']) for row in viables):.2f} %",
        f"Vacance <= {_max_or_none(float(row['vacance_mois']) for row in viables):g} mois/an",
    ]
    prix_viables = [float(row.get("prix_achat", 0.0)) for row in viables if float(row.get("prix_achat", 0.0)) > 0]
    if prix_viables:
        conditions.insert(0, f"Prix achat <= {max(prix_viables):,.0f} EUR")
    if any(_bool_value(row["gestion_agence"]) for row in viables):
        conditions.append("Au moins un scenario reste viable avec gestion agence.")
    else:
        conditions.append("Aucun scenario viable avec gestion agence.")
    if positifs:
        conditions.append(
            f"Cash-flow positif observe seulement a partir de "
            f"{_min_or_none(float(row['loyer_hc_mensuel']) for row in positifs):,.0f} EUR de loyer HC."
        )
    else:
        conditions.append("Aucun scenario ne produit un cash-flow positif.")
    return tuple(conditions)


def analyser_grille(
    rows: Iterable[Mapping[str, Any]],
    seuils: SeuilsDecision | None = None,
) -> RobustesseGrille:
    """Analyse une grille plate issue de `GrilleResultat.to_dict()` ou SQLite."""

    seuils = seuils or SeuilsDecision()
    lignes = [dict(row) for row in rows]
    if not lignes:
        return RobustesseGrille(
            nb_scenarios=0,
            nb_viables=0,
            nb_positifs=0,
            pct_viables=0.0,
            pct_positifs=0.0,
            cashflow_min=None,
            cashflow_p10=None,
            cashflow_median=None,
        cashflow_p90=None,
        cashflow_max=None,
        meilleur_cashflow_prudent=None,
        meilleur_cashflow_agence=None,
        prix_max_viable=None,
        prix_min_simule=None,
        decision="diagnostic_incomplet",
            raisons=("Aucun scenario disponible.",),
            conditions_validite=("Relancer une simulation avec des parametres valides.",),
            seuil_cashflow_min=seuils.cashflow_mensuel_min,
            seuil_cashflow_cible=seuils.cashflow_mensuel_cible,
        )

    cashflows = [float(row["cashflow_mensuel_apres_impot"]) for row in lignes]
    viables = [row for row in lignes if float(row["cashflow_mensuel_apres_impot"]) >= seuils.cashflow_mensuel_min]
    positifs = [row for row in lignes if float(row["cashflow_mensuel_apres_impot"]) >= seuils.cashflow_mensuel_cible]
    diagnostics = set().union(*(_codes(row.get("diagnostics", "")) for row in lignes))
    alertes = set().union(*(_codes(row.get("alertes", "")) for row in lignes))
    critiques = tuple(sorted((diagnostics | alertes) & CRITICAL_MISSING_CODES))
    blocages = tuple(sorted((diagnostics | alertes) & BLOCKING_CODES))
    pct_viables = len(viables) / len(lignes) * 100
    pct_positifs = len(positifs) / len(lignes) * 100
    prudent_rows = [row for row in lignes if float(row["vacance_mois"]) >= 1.0]
    agence_rows = [row for row in lignes if _bool_value(row["gestion_agence"])]
    prix_simules = [float(row.get("prix_achat", 0.0)) for row in lignes if float(row.get("prix_achat", 0.0)) > 0]
    prix_viables = [float(row.get("prix_achat", 0.0)) for row in viables if float(row.get("prix_achat", 0.0)) > 0]

    raisons: list[str] = []
    if blocages:
        decision = "a_rejeter"
        raisons.append("Contrainte bloquante detectee : " + ", ".join(blocages) + ".")
    elif critiques:
        decision = "diagnostic_incomplet"
        raisons.append("Donnees critiques manquantes : " + ", ".join(critiques) + ".")
    elif not viables:
        decision = "a_rejeter"
        raisons.append("Aucun scenario ne reste au-dessus du cash-flow minimum.")
    elif pct_viables < 35:
        decision = "a_negocier"
        raisons.append("Trop peu de scenarios restent viables.")
    elif _percentile(cashflows, 0.5) is not None and _percentile(cashflows, 0.5) < seuils.cashflow_mensuel_min:
        decision = "a_negocier"
        raisons.append("Le cash-flow median est sous le seuil minimum.")
    elif pct_positifs >= 50 and _percentile(cashflows, 0.1) is not None and _percentile(cashflows, 0.1) >= seuils.cashflow_mensuel_min:
        decision = "interessant"
        raisons.append("La majorite des scenarios sont positifs et le bas de distribution reste viable.")
    else:
        decision = "a_creuser"
        raisons.append("Les scenarios viables existent, mais la robustesse reste incomplete.")

    return RobustesseGrille(
        nb_scenarios=len(lignes),
        nb_viables=len(viables),
        nb_positifs=len(positifs),
        pct_viables=round(pct_viables, 1),
        pct_positifs=round(pct_positifs, 1),
        cashflow_min=round(min(cashflows), 2),
        cashflow_p10=_percentile(cashflows, 0.1),
        cashflow_median=_percentile(cashflows, 0.5),
        cashflow_p90=_percentile(cashflows, 0.9),
        cashflow_max=round(max(cashflows), 2),
        meilleur_cashflow_prudent=(
            round(max(float(row["cashflow_mensuel_apres_impot"]) for row in prudent_rows), 2)
            if prudent_rows
            else None
        ),
        meilleur_cashflow_agence=(
            round(max(float(row["cashflow_mensuel_apres_impot"]) for row in agence_rows), 2)
            if agence_rows
            else None
        ),
        prix_max_viable=round(max(prix_viables), 2) if prix_viables else None,
        prix_min_simule=round(min(prix_simules), 2) if prix_simules else None,
        decision=decision,
        raisons=tuple(raisons),
        conditions_validite=_conditions(lignes, seuils),
        diagnostics_critiques=critiques,
        seuil_cashflow_min=seuils.cashflow_mensuel_min,
        seuil_cashflow_cible=seuils.cashflow_mensuel_cible,
    )
