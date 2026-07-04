"""Modeles de donnees propres a l'acquisition d'annonces."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CandidateProperty:
    """Donnees extraites d'une annonce avant conversion en strategie."""

    source: str
    url: str
    ville: str
    quartier: str
    prix: float
    surface: float
    charges_mensuelles: float | None
    taxe_fonciere: float | None
    dpe: str
    etage: int | None
    ascenseur: bool | None
    loyer_estime: float | None
    confiance_loyer: str
    travaux_visibles: float | None
    red_flags: list[str]
    donnees_manquantes: list[str]

    @property
    def prix_m2(self) -> float:
        return self.prix / self.surface if self.surface > 0 else 0.0
