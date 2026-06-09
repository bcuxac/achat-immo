"""Objets metier du simulateur locatif.

Les valeurs monétaires sont exprimées en euros. Les taux stockés dans les
dataclasses sont exprimés en pourcentage annuel, sauf mention contraire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TypeBien(StrEnum):
    """Type de bien cible pour l'investissement."""

    STUDIO = "studio"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    AUTRE = "autre"


class ModeLocation(StrEnum):
    """Mode de location envisage pour le bien."""

    NUE = "nue"
    MEUBLEE = "meublee"


class EpoqueConstruction(StrEnum):
    """Tranches utilisees par les dispositifs locaux d'encadrement."""

    AVANT_1946 = "avant_1946"
    DE_1946_1970 = "1946_1970"
    DE_1971_1990 = "1971_1990"
    APRES_1990 = "apres_1990"
    INCONNUE = "inconnue"


class RegimeFiscal(StrEnum):
    """Regimes fiscaux modelises."""

    LMNP_REEL = "lmnp_reel"
    LOCATION_NUE_REEL = "location_nue_reel"
    MICRO_BIC = "micro_bic"
    MICRO_FONCIER = "micro_foncier"


def _must_be_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} doit etre strictement positif.")


def _must_be_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} doit etre positif ou nul.")


@dataclass(slots=True)
class BienImmobilier:
    """Caracteristiques stables d'une annonce ou d'un bien cible."""

    ville: str
    surface_m2: float
    prix_affiche: float
    type_bien: TypeBien = TypeBien.T2
    quartier: str = ""
    adresse_approx: str = ""
    lien: str = ""
    prix_negocie: float | None = None
    nb_pieces: int | None = None
    etage: str | None = None
    dpe: str | None = None
    epoque_construction: EpoqueConstruction = EpoqueConstruction.INCONNUE
    secteur_encadrement: str = ""
    frais_agence_achat: float = 0.0
    frais_notaire_estimes: float = 0.0
    travaux_estimes: float = 0.0
    meubles_estimes: float = 0.0
    frais_bancaires: float = 0.0
    garantie: float = 0.0

    def __post_init__(self) -> None:
        _must_be_positive("surface_m2", self.surface_m2)
        _must_be_positive("prix_affiche", self.prix_affiche)
        for name in (
            "frais_agence_achat",
            "frais_notaire_estimes",
            "travaux_estimes",
            "meubles_estimes",
            "frais_bancaires",
            "garantie",
        ):
            _must_be_non_negative(name, getattr(self, name))
        if self.prix_negocie is not None:
            _must_be_positive("prix_negocie", self.prix_negocie)
        if self.nb_pieces is not None and self.nb_pieces <= 0:
            raise ValueError("nb_pieces doit etre strictement positif.")

    @property
    def prix_achat(self) -> float:
        """Prix retenu pour la simulation, apres negociation eventuelle."""

        return self.prix_negocie if self.prix_negocie is not None else self.prix_affiche

    @property
    def prix_m2(self) -> float:
        return self.prix_achat / self.surface_m2

    @property
    def cout_total_projet(self) -> float:
        """Budget complet a financer, avant deduction de l'apport."""

        return (
            self.prix_achat
            + self.frais_agence_achat
            + self.frais_notaire_estimes
            + self.travaux_estimes
            + self.meubles_estimes
            + self.frais_bancaires
            + self.garantie
        )


@dataclass(slots=True)
class HypothesesLocation:
    """Hypotheses d'exploitation locative, prudentes par defaut."""

    loyer_hc_mensuel: float
    mode_location: ModeLocation = ModeLocation.MEUBLEE
    charges_recuperables_mensuelles: float = 0.0
    vacance_mois_par_an: float = 1.0
    evolution_loyer_annuelle_pct: float = 0.0
    charges_copro_annuelles: float = 0.0
    charges_recuperables_annuelles: float = 0.0
    taxe_fonciere: float = 0.0
    assurance_pno: float = 180.0
    assurance_gli: float = 0.0
    gestion_agence_active: bool = False
    frais_gestion_pct: float = 7.0
    frais_mise_location_annuels: float = 0.0
    cfe_annuelle: float = 0.0
    comptable_lmnp: float = 500.0
    entretien_annuel: float = 500.0
    travaux_futurs_annuels: float = 0.0
    autres_charges_annuelles: float = 0.0

    def __post_init__(self) -> None:
        _must_be_positive("loyer_hc_mensuel", self.loyer_hc_mensuel)
        for name in (
            "charges_recuperables_mensuelles",
            "vacance_mois_par_an",
            "charges_copro_annuelles",
            "charges_recuperables_annuelles",
            "taxe_fonciere",
            "assurance_pno",
            "assurance_gli",
            "frais_gestion_pct",
            "frais_mise_location_annuels",
            "cfe_annuelle",
            "comptable_lmnp",
            "entretien_annuel",
            "travaux_futurs_annuels",
            "autres_charges_annuelles",
        ):
            _must_be_non_negative(name, getattr(self, name))
        if self.vacance_mois_par_an > 12:
            raise ValueError("vacance_mois_par_an ne peut pas depasser 12.")

    @property
    def loyer_cc_mensuel(self) -> float:
        return self.loyer_hc_mensuel + self.charges_recuperables_mensuelles


@dataclass(slots=True)
class Financement:
    """Parametres du credit immobilier."""

    apport: float
    taux_credit_annuel_pct: float = 3.6
    duree_credit_annees: int = 20
    assurance_emprunteur_annuelle_pct: float = 0.30

    def __post_init__(self) -> None:
        _must_be_non_negative("apport", self.apport)
        _must_be_non_negative("taux_credit_annuel_pct", self.taux_credit_annuel_pct)
        _must_be_non_negative(
            "assurance_emprunteur_annuelle_pct",
            self.assurance_emprunteur_annuelle_pct,
        )
        if self.duree_credit_annees <= 0:
            raise ValueError("duree_credit_annees doit etre strictement positive.")

    def montant_emprunte(self, cout_total_projet: float) -> float:
        montant = cout_total_projet - self.apport
        if montant < 0:
            raise ValueError("L'apport ne peut pas depasser le cout total du projet.")
        return montant


@dataclass(slots=True)
class Fiscalite:
    """Hypotheses fiscales simplifiees et extensibles."""

    regime: RegimeFiscal = RegimeFiscal.LMNP_REEL
    tmi_pct: float = 30.0
    prelevements_sociaux_pct: float = 18.6
    part_terrain_pct: float = 15.0
    duree_amortissement_bien_annees: int = 30
    duree_amortissement_travaux_annees: int = 15
    duree_amortissement_meubles_annees: int = 7
    abattement_micro_bic_pct: float = 50.0
    abattement_micro_foncier_pct: float = 30.0

    def __post_init__(self) -> None:
        for name in (
            "tmi_pct",
            "prelevements_sociaux_pct",
            "part_terrain_pct",
            "abattement_micro_bic_pct",
            "abattement_micro_foncier_pct",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 100:
                raise ValueError(f"{name} doit etre compris entre 0 et 100.")
        for name in (
            "duree_amortissement_bien_annees",
            "duree_amortissement_travaux_annees",
            "duree_amortissement_meubles_annees",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} doit etre strictement positif.")

    @property
    def taux_global_imposition_pct(self) -> float:
        return self.tmi_pct + self.prelevements_sociaux_pct


@dataclass(slots=True)
class Scenario:
    """Scenario de marche et d'exploitation applique a un bien."""

    nom: str = "central"
    horizon_annees: int = 20
    appreciation_annuelle_pct: float = 0.5
    loyer_multiplicateur: float = 1.0
    charges_multiplicateur: float = 1.0
    vacance_mois_par_an: float | None = None
    frais_revente_pct: float = 7.0

    def __post_init__(self) -> None:
        if self.horizon_annees <= 0:
            raise ValueError("horizon_annees doit etre strictement positif.")
        _must_be_positive("loyer_multiplicateur", self.loyer_multiplicateur)
        _must_be_positive("charges_multiplicateur", self.charges_multiplicateur)
        _must_be_non_negative("frais_revente_pct", self.frais_revente_pct)
        if self.vacance_mois_par_an is not None and not 0 <= self.vacance_mois_par_an <= 12:
            raise ValueError("vacance_mois_par_an doit etre entre 0 et 12.")


@dataclass(slots=True)
class ResultatSimulation:
    """Synthese d'une simulation, avec projection annuelle detaillee."""

    bien: BienImmobilier
    scenario: Scenario
    cout_total_projet: float
    montant_emprunte: float
    mensualite_credit: float
    mensualite_assurance: float
    mensualite_totale: float
    rendement_brut_pct: float
    rendement_net_avant_impot_pct: float
    rendement_net_net_pct: float
    cashflow_mensuel_avant_impot: float
    cashflow_mensuel_apres_impot: float
    effort_epargne_mensuel: float
    tri_annuel_approx_pct: float | None
    patrimoine_net_horizon: float
    projection_annuelle: list[dict[str, Any]] = field(default_factory=list)

    @property
    def indicateurs(self) -> dict[str, float | None]:
        return {
            "rendement_brut_pct": self.rendement_brut_pct,
            "rendement_net_avant_impot_pct": self.rendement_net_avant_impot_pct,
            "rendement_net_net_pct": self.rendement_net_net_pct,
            "cashflow_mensuel_avant_impot": self.cashflow_mensuel_avant_impot,
            "cashflow_mensuel_apres_impot": self.cashflow_mensuel_apres_impot,
            "effort_epargne_mensuel": self.effort_epargne_mensuel,
            "tri_annuel_approx_pct": self.tri_annuel_approx_pct,
            "patrimoine_net_horizon": self.patrimoine_net_horizon,
        }
