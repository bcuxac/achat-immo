"""Interface CLI minimale pour simuler des annonces depuis un CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from achat_immo.export import export_csv, export_excel
from achat_immo.models import (
    BienImmobilier,
    Financement,
    Fiscalite,
    HypothesesLocation,
    TypeBien,
)
from achat_immo.scenarios import scenario_central, simuler_bien_sur_horizon


def _float(row: pd.Series, column: str, default: float = 0.0) -> float:
    value = row.get(column, default)
    if pd.isna(value):
        return default
    return float(value)


def _bool(row: pd.Series, column: str, default: bool = False) -> bool:
    value = row.get(column, default)
    if pd.isna(value):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "vrai", "yes", "oui"}


def _type_bien(value: object) -> TypeBien:
    try:
        return TypeBien(str(value))
    except ValueError:
        return TypeBien.AUTRE


def charger_annonces(path: str | Path) -> list[tuple[BienImmobilier, HypothesesLocation, Financement]]:
    """Charge un CSV proche des colonnes de travail proposees."""

    df = pd.read_csv(path)
    annonces = []
    for _, row in df.iterrows():
        bien = BienImmobilier(
            ville=str(row.get("ville", "")),
            quartier=str(row.get("quartier", "")),
            adresse_approx=str(row.get("adresse_approx", "")),
            lien=str(row.get("lien", "")),
            surface_m2=_float(row, "surface_m2"),
            prix_affiche=_float(row, "prix_affiche"),
            prix_negocie=_float(row, "prix_negocie", 0.0) or None,
            type_bien=_type_bien(row.get("type_bien", "T2")),
            dpe=str(row.get("dpe", "")) or None,
            frais_agence_achat=_float(row, "frais_agence_achat"),
            frais_notaire_estimes=_float(row, "frais_notaire_estimes"),
            travaux_estimes=_float(row, "travaux_estimes"),
            meubles_estimes=_float(row, "meubles_estimes"),
            frais_bancaires=_float(row, "frais_bancaires"),
            garantie=_float(row, "garantie"),
        )
        location = HypothesesLocation(
            loyer_hc_mensuel=_float(row, "loyer_hc_estime"),
            vacance_mois_par_an=max(_float(row, "vacance_mois_par_an", 1.0), 1.0),
            charges_copro_annuelles=_float(row, "charges_copro_annuelles"),
            charges_recuperables_annuelles=_float(row, "charges_recuperables_annuelles"),
            taxe_fonciere=_float(row, "taxe_fonciere"),
            gestion_agence_active=_bool(row, "gestion_agence_bool", False),
            frais_gestion_pct=_float(row, "frais_gestion_pct", 7.0),
            assurance_pno=_float(row, "assurance_pno", 180.0),
            assurance_gli=_float(row, "assurance_gli"),
            comptable_lmnp=_float(row, "comptable_lmnp", 500.0),
        )
        financement = Financement(
            apport=_float(row, "apport"),
            taux_credit_annuel_pct=_float(row, "taux_credit", 3.6),
            duree_credit_annees=int(_float(row, "duree_credit_annees", 20)),
            assurance_emprunteur_annuelle_pct=_float(row, "assurance_emprunteur_pct", 0.30),
        )
        annonces.append((bien, location, financement))
    return annonces


def main() -> None:
    parser = argparse.ArgumentParser(description="Simule des annonces locatives.")
    parser.add_argument("annonces", type=Path, help="CSV d'annonces a analyser")
    parser.add_argument("--output", type=Path, default=Path("outputs/comparaison_scenarios.xlsx"))
    parser.add_argument("--horizon", type=int, default=20)
    args = parser.parse_args()

    resultats = []
    for bien, location, financement in charger_annonces(args.annonces):
        resultats.append(
            simuler_bien_sur_horizon(
                bien=bien,
                location=location,
                financement=financement,
                fiscalite=Fiscalite(),
                scenario=scenario_central(args.horizon),
            )
        )

    if args.output.suffix.lower() == ".csv":
        export_csv(resultats, args.output)
    else:
        export_excel(resultats, args.output)


if __name__ == "__main__":
    main()
