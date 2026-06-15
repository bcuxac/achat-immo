"""Représentation d'une annonce immobilière candidate pour le scoring."""

from dataclasses import dataclass

@dataclass(slots=True)
class CandidateProperty:
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
    confiance_loyer: str # 'haute', 'moyenne', 'basse'
    travaux_visibles: float | None
    red_flags: list[str]
    donnees_manquantes: list[str]
    
    @property
    def prix_m2(self) -> float:
        return self.prix / self.surface if self.surface > 0 else 0.0
