"""Helpers de libelle pour les annonces dans l'UI Streamlit."""

from __future__ import annotations

from typing import Any


def annonce_label(row: dict[str, Any]) -> str:
    quartier = f" - {row['quartier']}" if row.get("quartier") else ""
    return f"#{row['id']} {row['ville']}{quartier} - {row['surface_m2']:.0f} m2 - {row['prix_affiche']:,.0f} EUR"
