"""Exports CSV, Excel et Markdown."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from achat_immo.comparison import scorer_bien
from achat_immo.models import ResultatSimulation


def resultats_to_dataframe(resultats: Iterable[ResultatSimulation]) -> pd.DataFrame:
    """Table de synthese exploitable en CSV ou Excel."""

    lignes = []
    for resultat in resultats:
        score = scorer_bien(resultat)
        lignes.append(
            {
                "ville": resultat.bien.ville,
                "quartier": resultat.bien.quartier,
                "adresse_approx": resultat.bien.adresse_approx,
                "lien": resultat.bien.lien,
                "type_bien": resultat.bien.type_bien.value,
                "surface_m2": resultat.bien.surface_m2,
                "prix_achat": resultat.bien.prix_achat,
                "prix_m2": resultat.bien.prix_m2,
                "cout_total_projet": resultat.cout_total_projet,
                "scenario": resultat.scenario.nom,
                "montant_emprunte": resultat.montant_emprunte,
                "mensualite_totale": resultat.mensualite_totale,
                "rendement_brut_pct": resultat.rendement_brut_pct,
                "rendement_net_avant_impot_pct": resultat.rendement_net_avant_impot_pct,
                "rendement_net_net_pct": resultat.rendement_net_net_pct,
                "cashflow_mensuel_avant_impot": resultat.cashflow_mensuel_avant_impot,
                "cashflow_mensuel_apres_impot": resultat.cashflow_mensuel_apres_impot,
                "effort_epargne_mensuel": resultat.effort_epargne_mensuel,
                "tri_annuel_approx_pct": resultat.tri_annuel_approx_pct,
                "patrimoine_net_horizon": resultat.patrimoine_net_horizon,
                "alternative_horizon": resultat.alternative_horizon,
                "ecart_vs_alternative": resultat.ecart_vs_alternative,
                "score": score["score"],
                "decision": score["decision"],
                "alertes": ", ".join(score["alertes"]),
            }
        )
    return pd.DataFrame(lignes)


def projection_to_dataframe(resultat: ResultatSimulation) -> pd.DataFrame:
    df = pd.DataFrame(resultat.projection_annuelle)
    df.insert(0, "scenario", resultat.scenario.nom)
    df.insert(0, "ville", resultat.bien.ville)
    df.insert(1, "quartier", resultat.bien.quartier)
    return df


def export_csv(resultats: Iterable[ResultatSimulation], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    resultats_to_dataframe(resultats).to_csv(path, index=False)
    return path


def export_excel(resultats: Iterable[ResultatSimulation], path: str | Path) -> Path:
    """Exporte une synthese et les projections annuelles dans un classeur Excel."""

    resultats = list(resultats)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            resultats_to_dataframe(resultats).to_excel(writer, sheet_name="Synthese", index=False)
            projections = (
                pd.concat(
                    [projection_to_dataframe(resultat) for resultat in resultats],
                    ignore_index=True,
                )
                if resultats
                else pd.DataFrame()
            )
            projections.to_excel(writer, sheet_name="Projections", index=False)
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "L'export Excel necessite openpyxl. Installe-le avec `uv add openpyxl`."
        ) from exc
    return path


def export_resume_markdown(resultats: Iterable[ResultatSimulation], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = resultats_to_dataframe(resultats)
    headers = list(df.columns)
    rows = df.astype(object).where(pd.notna(df), "").values.tolist()
    contenu = [
        "# Comparaison des biens",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    contenu.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    contenu.append("")
    path.write_text("\n".join(contenu), encoding="utf-8")
    return path
