"""Profils locaux pour les villes suivies dans l'application.

Le projet est volontairement limite aux villes réellement suivies. Ces profils
servent a borner les hypotheses de simulation et a expliciter les regles
locales connues, sans pretendre couvrir tout le territoire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import unicodedata

from achat_immo.models import (
    BienImmobilier,
    EpoqueConstruction,
    HypothesesLocation,
    ModeLocation,
    TypeBien,
)


SECTEUR_A_VERIFIER = "a_verifier"
SECTEUR_NON_CONCERNE = "non_concerne"


class RentControlKind(StrEnum):
    """Type de contrainte locale sur le loyer."""

    AUCUN = "aucun"
    ZONE_TENDUE_RELOCATION = "zone_tendue_relocation"
    LOYER_REFERENCE = "loyer_reference"


@dataclass(frozen=True, slots=True)
class RentReferenceRecord:
    """Ligne sourcee d'une grille locale de loyer de reference majore."""

    category_id: str
    sector: str
    room_count: int
    construction_period: EpoqueConstruction
    rental_mode: ModeLocation
    cap_per_m2: float
    source_url: str


@dataclass(frozen=True, slots=True)
class CityProfile:
    """Regles locales et bornes connues pour une ville cible."""

    code: str
    label: str
    zone_tendue: bool
    rent_control_kind: RentControlKind
    secteurs_encadrement: dict[str, str] = field(default_factory=dict)
    loyers_reference_majores_m2: dict[tuple[str, int, EpoqueConstruction, ModeLocation], float] = field(
        default_factory=dict
    )
    source_urls: tuple[str, ...] = ()
    note: str = ""

    @property
    def requires_rent_sector(self) -> bool:
        return self.rent_control_kind == RentControlKind.LOYER_REFERENCE


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _epoque(value: EpoqueConstruction | str) -> EpoqueConstruction:
    if isinstance(value, EpoqueConstruction):
        return value
    try:
        return EpoqueConstruction(value)
    except ValueError:
        return EpoqueConstruction.INCONNUE


def _mode(value: ModeLocation | str) -> ModeLocation:
    if isinstance(value, ModeLocation):
        return value
    try:
        return ModeLocation(value)
    except ValueError:
        return ModeLocation.MEUBLEE


def inferer_nb_pieces(type_bien: TypeBien, nb_pieces: int | None = None) -> int | None:
    """Retourne le nombre de pieces utilise par les grilles locales."""

    if nb_pieces is not None:
        return min(max(int(nb_pieces), 1), 4)
    return {
        TypeBien.STUDIO: 1,
        TypeBien.T1: 1,
        TypeBien.T2: 2,
        TypeBien.T3: 3,
    }.get(type_bien)


def _add_reference_rows(
    table: dict[tuple[str, int, EpoqueConstruction, ModeLocation], float],
    sector: str,
    rows: tuple[tuple[int, EpoqueConstruction, float, float], ...],
) -> None:
    """Ajoute des plafonds au m2 : (pieces, epoque, nu, meuble)."""

    for nb_pieces, epoque, nue, meublee in rows:
        table[(sector, nb_pieces, epoque, ModeLocation.NUE)] = nue
        table[(sector, nb_pieces, epoque, ModeLocation.MEUBLEE)] = meublee


def _grenoble_references_2026() -> dict[tuple[str, int, EpoqueConstruction, ModeLocation], float]:
    references: dict[tuple[str, int, EpoqueConstruction, ModeLocation], float] = {}
    _add_reference_rows(
        references,
        "zone_1",
        (
            (1, EpoqueConstruction.AVANT_1946, 20.0, 21.5),
            (1, EpoqueConstruction.DE_1946_1970, 19.8, 21.2),
            (1, EpoqueConstruction.DE_1971_1990, 19.7, 21.0),
            (1, EpoqueConstruction.APRES_1990, 19.8, 21.2),
            (2, EpoqueConstruction.AVANT_1946, 15.2, 16.3),
            (2, EpoqueConstruction.DE_1946_1970, 15.2, 16.3),
            (2, EpoqueConstruction.DE_1971_1990, 16.2, 17.3),
            (2, EpoqueConstruction.APRES_1990, 16.9, 18.1),
            (3, EpoqueConstruction.AVANT_1946, 13.4, 14.4),
            (3, EpoqueConstruction.DE_1946_1970, 13.8, 14.8),
            (3, EpoqueConstruction.DE_1971_1990, 13.4, 14.4),
            (3, EpoqueConstruction.APRES_1990, 14.5, 15.5),
            (4, EpoqueConstruction.AVANT_1946, 12.6, 13.4),
            (4, EpoqueConstruction.DE_1946_1970, 13.0, 13.9),
            (4, EpoqueConstruction.DE_1971_1990, 12.8, 13.7),
            (4, EpoqueConstruction.APRES_1990, 13.4, 14.4),
        ),
    )
    _add_reference_rows(
        references,
        "zone_2",
        (
            (1, EpoqueConstruction.AVANT_1946, 17.8, 19.0),
            (1, EpoqueConstruction.DE_1946_1970, 17.5, 18.7),
            (1, EpoqueConstruction.DE_1971_1990, 19.0, 20.3),
            (1, EpoqueConstruction.APRES_1990, 20.3, 21.7),
            (2, EpoqueConstruction.AVANT_1946, 14.6, 15.7),
            (2, EpoqueConstruction.DE_1946_1970, 14.3, 15.2),
            (2, EpoqueConstruction.DE_1971_1990, 14.9, 16.0),
            (2, EpoqueConstruction.APRES_1990, 15.6, 16.7),
            (3, EpoqueConstruction.AVANT_1946, 12.8, 13.7),
            (3, EpoqueConstruction.DE_1946_1970, 12.6, 13.4),
            (3, EpoqueConstruction.DE_1971_1990, 13.4, 14.4),
            (3, EpoqueConstruction.APRES_1990, 14.2, 15.1),
            (4, EpoqueConstruction.AVANT_1946, 11.8, 12.6),
            (4, EpoqueConstruction.DE_1946_1970, 12.4, 13.2),
            (4, EpoqueConstruction.DE_1971_1990, 12.2, 13.1),
            (4, EpoqueConstruction.APRES_1990, 13.4, 14.4),
        ),
    )
    _add_reference_rows(
        references,
        "zone_a",
        (
            (1, EpoqueConstruction.AVANT_1946, 17.6, 18.8),
            (1, EpoqueConstruction.DE_1946_1970, 17.8, 19.0),
            (1, EpoqueConstruction.DE_1971_1990, 17.9, 19.1),
            (1, EpoqueConstruction.APRES_1990, 19.3, 20.6),
            (2, EpoqueConstruction.AVANT_1946, 15.4, 16.4),
            (2, EpoqueConstruction.DE_1946_1970, 14.9, 16.0),
            (2, EpoqueConstruction.DE_1971_1990, 15.1, 16.2),
            (2, EpoqueConstruction.APRES_1990, 16.2, 17.3),
            (3, EpoqueConstruction.AVANT_1946, 13.2, 14.2),
            (3, EpoqueConstruction.DE_1946_1970, 13.1, 14.0),
            (3, EpoqueConstruction.DE_1971_1990, 13.0, 13.9),
            (3, EpoqueConstruction.APRES_1990, 14.5, 15.5),
            (4, EpoqueConstruction.AVANT_1946, 11.9, 12.7),
            (4, EpoqueConstruction.DE_1946_1970, 11.9, 12.7),
            (4, EpoqueConstruction.DE_1971_1990, 12.7, 13.6),
            (4, EpoqueConstruction.APRES_1990, 13.3, 14.3),
        ),
    )
    return references


CITY_PROFILES: dict[str, CityProfile] = {
    "grenoble": CityProfile(
        code="grenoble",
        label="Grenoble",
        zone_tendue=True,
        rent_control_kind=RentControlKind.LOYER_REFERENCE,
        secteurs_encadrement={
            SECTEUR_A_VERIFIER: "A verifier",
            SECTEUR_NON_CONCERNE: "Non concerne",
            "zone_1": "Grenoble - zone 1",
            "zone_2": "Grenoble - zone 2",
            "zone_a": "Metropole - zone A",
        },
        loyers_reference_majores_m2=_grenoble_references_2026(),
        source_urls=(
            "https://www.grenoblealpesmetropole.fr/940-me-renseigner-sur-l-encadrement-des-loyers.htm",
            "https://www.grenoblealpesmetropole.fr/cms_viewFile.php?idtf=6009&path=Encadrement-des-loyers-Arrete-prefectoral-du-6-janvier-2026.pdf",
        ),
        note="Encadrement local par secteur, pieces, epoque de construction et mode nu/meuble.",
    ),
    "nimes": CityProfile(
        code="nimes",
        label="Nimes",
        zone_tendue=True,
        rent_control_kind=RentControlKind.ZONE_TENDUE_RELOCATION,
        source_urls=(
            "https://www.service-public.fr/simulateur/calcul/zones-tendues",
            "https://www.service-public.fr/particuliers/vosdroits/F1314",
            "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000047998521",
        ),
        note=(
            "Zone tendue depuis le decret n° 2023-822 : absence de grille locale de loyers de "
            "reference majores. Le loyer precedent et les exceptions de relocation sont requis "
            "pour verifier le loyer legal."
        ),
    ),
}

CITY_ALIASES = {
    "grenoble": "grenoble",
    "nimes": "nimes",
    "nîmes": "nimes",
}


def supported_city_labels() -> tuple[str, ...]:
    return tuple(profile.label for profile in CITY_PROFILES.values())


def legal_rent_caps_per_m2(ville: str) -> tuple[float, ...]:
    """Retourne les plafonds numeriques distincts connus pour une ville."""

    profile = profile_for_city(ville)
    if profile is None:
        return ()
    return tuple(sorted(set(profile.loyers_reference_majores_m2.values())))


def rent_reference_records(
    ville: str,
    mode: ModeLocation,
) -> tuple[RentReferenceRecord, ...]:
    """Retourne les seules lignes reglementaires applicables au mode demande."""

    profile = profile_for_city(ville)
    if profile is None or profile.rent_control_kind != RentControlKind.LOYER_REFERENCE:
        return ()
    source_url = profile.source_urls[-1]
    rows = (
        RentReferenceRecord(
            category_id=(
                f"{sector}:{room_count}:{construction_period.value}:{rental_mode.value}"
            ),
            sector=sector,
            room_count=room_count,
            construction_period=construction_period,
            rental_mode=rental_mode,
            cap_per_m2=cap,
            source_url=source_url,
        )
        for (sector, room_count, construction_period, rental_mode), cap in (
            profile.loyers_reference_majores_m2.items()
        )
        if rental_mode == mode
    )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                row.sector,
                row.room_count,
                row.construction_period.value,
                row.rental_mode.value,
            ),
        )
    )


def profile_for_city(ville: str) -> CityProfile | None:
    code = CITY_ALIASES.get(_normalize(ville))
    if code is None:
        return None
    return CITY_PROFILES[code]


def canonical_city_label(ville: str) -> str:
    profile = profile_for_city(ville)
    return profile.label if profile else ville


def loyer_reference_majore_m2(
    bien: BienImmobilier,
    location: HypothesesLocation,
    profile: CityProfile | None = None,
) -> float | None:
    profile = profile or profile_for_city(bien.ville)
    if profile is None or profile.rent_control_kind != RentControlKind.LOYER_REFERENCE:
        return None
    if bien.secteur_encadrement in {"", SECTEUR_A_VERIFIER, SECTEUR_NON_CONCERNE}:
        return None
    nb_pieces = inferer_nb_pieces(bien.type_bien, bien.nb_pieces)
    if nb_pieces is None:
        return None
    key = (
        bien.secteur_encadrement,
        nb_pieces,
        _epoque(bien.epoque_construction),
        _mode(location.mode_location),
    )
    return profile.loyers_reference_majores_m2.get(key)


def loyer_max_hc_mensuel(
    bien: BienImmobilier,
    location: HypothesesLocation,
    profile: CityProfile | None = None,
) -> float | None:
    plafond_m2 = loyer_reference_majore_m2(bien, location, profile)
    if plafond_m2 is None:
        return None
    return round(plafond_m2 * bien.surface_m2, 2)


def borner_loyers_hc(
    loyers: tuple[float, ...],
    bien: BienImmobilier,
    location: HypothesesLocation,
    profile: CityProfile | None = None,
) -> tuple[float, ...]:
    """Filtre les loyers superieurs au plafond local calculable."""

    plafond = loyer_max_hc_mensuel(bien, location, profile)
    if plafond is None:
        return loyers
    return tuple(loyer for loyer in loyers if loyer <= plafond)
