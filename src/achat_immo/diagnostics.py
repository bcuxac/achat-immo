"""Diagnostics metier avant decision d'investissement."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from achat_immo.city_profiles import (
    RentControlKind,
    SECTEUR_A_VERIFIER,
    SECTEUR_NON_CONCERNE,
    loyer_max_hc_mensuel,
    profile_for_city,
)
from achat_immo.models import BienImmobilier, EpoqueConstruction, HypothesesLocation


class DiagnosticStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    BLOCKING = "blocking"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class DiagnosticItem:
    code: str
    status: DiagnosticStatus
    message: str
    valeur: float | str | None = None
    seuil: float | str | None = None


def _dpe_letter(dpe: str | None) -> str:
    return (dpe or "").strip().upper()[:1]


def diagnostiquer_annonce(
    bien: BienImmobilier,
    location: HypothesesLocation,
) -> tuple[DiagnosticItem, ...]:
    """Retourne les points bloquants, incomplets ou prudents pour une annonce."""

    diagnostics: list[DiagnosticItem] = []

    if bien.surface_m2 < 9:
        diagnostics.append(
            DiagnosticItem(
                code="surface_non_decente",
                status=DiagnosticStatus.BLOCKING,
                message="Surface inferieure au minimum usuel de 9 m2 pour une location.",
                valeur=round(bien.surface_m2, 2),
                seuil=9.0,
            )
        )

    dpe = _dpe_letter(bien.dpe)
    if not dpe:
        diagnostics.append(
            DiagnosticItem(
                code="dpe_manquant",
                status=DiagnosticStatus.MISSING,
                message="DPE absent : la louabilite et le calendrier de travaux ne sont pas auditables.",
            )
        )
    elif dpe == "G":
        diagnostics.append(
            DiagnosticItem(
                code="dpe_g_interdit_location",
                status=DiagnosticStatus.BLOCKING,
                message="DPE G : location bloquante en residence principale depuis 2025 en metropole.",
                valeur=dpe,
            )
        )
    elif dpe == "F":
        diagnostics.append(
            DiagnosticItem(
                code="dpe_f_risque_2028",
                status=DiagnosticStatus.WARNING,
                message="DPE F : risque majeur de travaux ou d'interdiction de louer a partir de 2028.",
                valeur=dpe,
            )
        )
    elif dpe == "E":
        diagnostics.append(
            DiagnosticItem(
                code="dpe_e_risque_2034",
                status=DiagnosticStatus.WARNING,
                message="DPE E : risque a horizon long, a integrer dans les travaux et la revente.",
                valeur=dpe,
            )
        )

    profile = profile_for_city(bien.ville)
    if profile is None:
        diagnostics.append(
            DiagnosticItem(
                code="ville_non_referencee",
                status=DiagnosticStatus.MISSING,
                message="Ville hors liste cible : les regles locales ne sont pas modelisees.",
                valeur=bien.ville,
            )
        )
        return tuple(diagnostics)

    if profile.rent_control_kind == RentControlKind.LOYER_REFERENCE:
        if bien.secteur_encadrement in {"", SECTEUR_A_VERIFIER}:
            diagnostics.append(
                DiagnosticItem(
                    code="secteur_encadrement_manquant",
                    status=DiagnosticStatus.MISSING,
                    message="Secteur d'encadrement inconnu : le plafond legal du loyer ne peut pas etre calcule.",
                    valeur=bien.secteur_encadrement or SECTEUR_A_VERIFIER,
                )
            )
        elif bien.secteur_encadrement != SECTEUR_NON_CONCERNE:
            if bien.epoque_construction == EpoqueConstruction.INCONNUE:
                diagnostics.append(
                    DiagnosticItem(
                        code="epoque_construction_manquante",
                        status=DiagnosticStatus.MISSING,
                        message="Epoque de construction inconnue : le loyer de reference majore n'est pas calculable.",
                    )
                )
            plafond = loyer_max_hc_mensuel(bien, location, profile)
            if plafond is None:
                diagnostics.append(
                    DiagnosticItem(
                        code="loyer_plafond_non_calcule",
                        status=DiagnosticStatus.MISSING,
                        message="Plafond local non calcule : pieces, secteur, epoque ou mode de location a verifier.",
                    )
                )
            elif location.loyer_hc_mensuel > plafond:
                diagnostics.append(
                    DiagnosticItem(
                        code="loyer_superieur_plafond_local",
                        status=DiagnosticStatus.BLOCKING,
                        message="Loyer HC superieur au loyer de reference majore local.",
                        valeur=round(location.loyer_hc_mensuel, 2),
                        seuil=plafond,
                    )
                )
            else:
                diagnostics.append(
                    DiagnosticItem(
                        code="loyer_plafond_local_ok",
                        status=DiagnosticStatus.OK,
                        message="Loyer HC inferieur ou egal au plafond local calcule.",
                        valeur=round(location.loyer_hc_mensuel, 2),
                        seuil=plafond,
                    )
                )

    if profile.rent_control_kind == RentControlKind.ZONE_TENDUE_RELOCATION:
        diagnostics.append(
            DiagnosticItem(
                code="zone_tendue_relocation_a_verifier",
                status=DiagnosticStatus.WARNING,
                message="Zone tendue : verifier le precedent loyer et les exceptions de relocation.",
                valeur=profile.label,
            )
        )

    return tuple(diagnostics)


def has_blocking_diagnostic(diagnostics: tuple[DiagnosticItem, ...]) -> bool:
    return any(item.status == DiagnosticStatus.BLOCKING for item in diagnostics)


def has_missing_diagnostic(diagnostics: tuple[DiagnosticItem, ...]) -> bool:
    return any(item.status == DiagnosticStatus.MISSING for item in diagnostics)
