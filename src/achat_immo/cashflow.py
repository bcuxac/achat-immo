"""Revenus, charges et indicateurs d'exploitation locative."""

from __future__ import annotations

from dataclasses import replace

from achat_immo.models import BienImmobilier, HypothesesLocation, Scenario


def appliquer_scenario_location(
    location: HypothesesLocation,
    scenario: Scenario,
) -> HypothesesLocation:
    """Retourne des hypotheses ajustees par un scenario."""

    return replace(
        location,
        loyer_hc_mensuel=location.loyer_hc_mensuel * scenario.loyer_multiplicateur,
        vacance_mois_par_an=(
            scenario.vacance_mois_par_an
            if scenario.vacance_mois_par_an is not None
            else location.vacance_mois_par_an
        ),
    )


def revenus_annuels_hc(
    location: HypothesesLocation,
    annee: int = 1,
) -> float:
    """Loyers hors charges encaisses apres vacance."""

    croissance = (1 + location.evolution_loyer_annuelle_pct / 100) ** max(annee - 1, 0)
    mois_loues = max(12 - location.vacance_mois_par_an, 0)
    return round(location.loyer_hc_mensuel * croissance * mois_loues, 2)


def vacance_locative(location: HypothesesLocation, annee: int = 1) -> float:
    """Perte annuelle de loyer hors charges liee a la vacance."""

    croissance = (1 + location.evolution_loyer_annuelle_pct / 100) ** max(annee - 1, 0)
    return round(location.loyer_hc_mensuel * croissance * location.vacance_mois_par_an, 2)


def charges_annuelles(
    location: HypothesesLocation,
    revenus_hc: float,
    scenario: Scenario | None = None,
    annee: int = 1,
) -> dict[str, float]:
    """Charges annuelles supportees par le bailleur."""

    multiplicateur = scenario.charges_multiplicateur if scenario else 1.0
    croissance_charges = (1 + location.evolution_charges_annuelles_pct / 100) ** max(annee - 1, 0)
    charges_non_recuperables = max(
        location.charges_copro_annuelles - location.charges_recuperables_annuelles,
        0.0,
    )
    frais_gestion = (
        revenus_hc * location.frais_gestion_pct / 100 + location.frais_mise_location_annuels
        if location.gestion_agence_active
        else 0.0
    )
    charges = {
        "charges_non_recuperables": charges_non_recuperables * croissance_charges,
        "taxe_fonciere": location.taxe_fonciere * croissance_charges,
        "assurance_pno": location.assurance_pno * croissance_charges,
        "assurance_gli": location.assurance_gli * croissance_charges,
        "gestion_locative": frais_gestion,
        "cfe": location.cfe_annuelle * croissance_charges,
        "comptable_lmnp": location.comptable_lmnp * croissance_charges,
        "entretien": location.entretien_annuel * croissance_charges,
        "travaux_futurs": location.travaux_futurs_annuels * croissance_charges,
        "autres": location.autres_charges_annuelles * croissance_charges,
    }
    return {key: round(value * multiplicateur, 2) for key, value in charges.items()}


def total_charges_annuelles(charges: dict[str, float]) -> float:
    return round(sum(charges.values()), 2)


def rendement_brut(bien: BienImmobilier, location: HypothesesLocation) -> float:
    """Rendement brut conventionnel, hors vacance et hors charges."""

    return round(location.loyer_hc_mensuel * 12 / bien.cout_total_projet * 100, 2)


def rendement_net(
    bien: BienImmobilier,
    revenus_hc: float,
    charges: dict[str, float],
) -> float:
    """Rendement net avant credit et avant impot."""

    return round((revenus_hc - total_charges_annuelles(charges)) / bien.cout_total_projet * 100, 2)


def cashflow_annuel(
    revenus_hc: float,
    charges: dict[str, float],
    mensualite_totale: float,
    impot: float = 0.0,
) -> float:
    """Cash-flow annuel apres credit et impot."""

    return round(revenus_hc - total_charges_annuelles(charges) - mensualite_totale * 12 - impot, 2)


def cashflow_mensuel(
    revenus_hc: float,
    charges: dict[str, float],
    mensualite_totale: float,
    impot: float = 0.0,
) -> float:
    return round(cashflow_annuel(revenus_hc, charges, mensualite_totale, impot) / 12, 2)
