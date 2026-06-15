"""Fiscalite LMNP reel et amortissements associes."""

from __future__ import annotations

from achat_immo.models import BienImmobilier, Fiscalite, RegimeFiscal
from achat_immo.engines.taxes_reports import (
    consommer_reports as _consommer_reports,
    reports_valides as _reports_valides,
    total_reports as _total_reports,
)
from achat_immo.engines.taxes_types import AMORTISSEMENT_COMPONENTS, EtatFiscal, ReportFiscal, ResultatFiscal
from achat_immo.engines.taxes_utils import (
    frais_acquisition as _frais_acquisition,
    frais_emprunt as _frais_emprunt,
    impot_sur_resultat as _impot_sur_resultat,
    round_euros as _round_euros,
)


def amortissements_lmnp_par_composant(
    bien: BienImmobilier,
    fiscalite: Fiscalite,
    annee: int = 1,
) -> dict[str, float]:
    """Dotations annuelles LMNP reel par composant."""

    bati = 0.0
    if annee <= fiscalite.duree_amortissement_bien_annees:
        base_bien = bien.prix_achat * (1 - fiscalite.part_terrain_pct / 100)
        bati = base_bien / fiscalite.duree_amortissement_bien_annees

    travaux = 0.0
    if annee <= fiscalite.duree_amortissement_travaux_annees:
        travaux = bien.travaux_estimes / fiscalite.duree_amortissement_travaux_annees

    meubles = 0.0
    if annee <= fiscalite.duree_amortissement_meubles_annees:
        meubles = bien.meubles_estimes / fiscalite.duree_amortissement_meubles_annees

    frais_acquisition = 0.0
    if (
        fiscalite.option_frais_acquisition == "amortir_5_ans"
        and annee <= fiscalite.duree_amortissement_frais_acquisition_annees
    ):
        frais_acquisition = _frais_acquisition(bien) / fiscalite.duree_amortissement_frais_acquisition_annees

    return {
        "bati": _round_euros(bati),
        "travaux": _round_euros(travaux),
        "frais_acquisition": _round_euros(frais_acquisition),
        "meubles": _round_euros(meubles),
    }


def amortissement_lmnp(bien: BienImmobilier, fiscalite: Fiscalite) -> float:
    """Amortissement annuel LMNP reel historique, hors frais d'acquisition."""

    base_bien = bien.prix_achat * (1 - fiscalite.part_terrain_pct / 100)
    amortissement = (
        base_bien / fiscalite.duree_amortissement_bien_annees
        + bien.travaux_estimes / fiscalite.duree_amortissement_travaux_annees
        + bien.meubles_estimes / fiscalite.duree_amortissement_meubles_annees
    )
    return _round_euros(amortissement)


def fiscalite_lmnp_reel(
    revenus: float,
    charges_deductibles: float,
    interets: float,
    amortissement: float,
    fiscalite: Fiscalite,
) -> ResultatFiscal:
    """Fiscalite LMNP reel sans etat de report, conservee pour compatibilite."""

    resultat_avant_amortissement = revenus - charges_deductibles - interets
    base_amortissable = max(resultat_avant_amortissement, 0.0)
    amortissement_utilise = min(amortissement, base_amortissable)
    resultat_fiscal_value = max(resultat_avant_amortissement - amortissement_utilise, 0.0)
    amortissement_non_utilise = max(amortissement - amortissement_utilise, 0.0)
    deficit_genere = max(-resultat_avant_amortissement, 0.0)
    impot = _impot_sur_resultat(resultat_fiscal_value, fiscalite)
    return ResultatFiscal(
        regime=RegimeFiscal.LMNP_REEL,
        revenus=_round_euros(revenus),
        charges_deductibles=_round_euros(charges_deductibles),
        interets=_round_euros(interets),
        amortissement=_round_euros(amortissement),
        resultat_avant_amortissement=_round_euros(resultat_avant_amortissement),
        resultat_fiscal=_round_euros(resultat_fiscal_value),
        impot=impot,
        amortissement_non_utilise=_round_euros(amortissement_non_utilise),
        amortissement_utilise=_round_euros(amortissement_utilise),
        amortissement_report_fin=_round_euros(amortissement_non_utilise),
        amortissement_deduit=_round_euros(amortissement_utilise),
        deficit_genere=_round_euros(deficit_genere),
    )


def fiscalite_lmnp_reel_annuelle(
    bien: BienImmobilier,
    revenus: float,
    charges_deductibles: float,
    interets: float,
    fiscalite: Fiscalite,
    annee: int,
    etat: EtatFiscal,
) -> ResultatFiscal:
    dotations = amortissements_lmnp_par_composant(bien, fiscalite, annee)
    amortissement_courant = _round_euros(sum(dotations.values()))
    amortissement_report_debut = _round_euros(sum(etat.amortissement_reports.values()))
    available_by_component = {
        component: _round_euros(etat.amortissement_reports.get(component, 0.0) + dotations[component])
        for component in AMORTISSEMENT_COMPONENTS
    }

    etat.deficit_lmnp = _reports_valides(etat.deficit_lmnp, annee, 10)
    deficit_report_debut = _total_reports(etat.deficit_lmnp)
    frais_exceptionnels = _frais_exceptionnels_lmnp(bien, fiscalite, annee)
    resultat_avant_deficit = revenus - charges_deductibles - interets - frais_exceptionnels

    if resultat_avant_deficit < 0:
        deficit_genere = _round_euros(-resultat_avant_deficit)
        etat.deficit_lmnp.append(ReportFiscal(annee, deficit_genere))
        etat.amortissement_reports = available_by_component
        deficit_report_fin = _total_reports(etat.deficit_lmnp)
        return ResultatFiscal(
            regime=RegimeFiscal.LMNP_REEL,
            revenus=_round_euros(revenus),
            charges_deductibles=_round_euros(charges_deductibles),
            interets=_round_euros(interets),
            amortissement=amortissement_courant,
            resultat_avant_amortissement=_round_euros(resultat_avant_deficit),
            resultat_fiscal=0.0,
            impot=0.0,
            amortissement_non_utilise=_round_euros(sum(available_by_component.values())),
            amortissement_report_debut=amortissement_report_debut,
            amortissement_report_fin=_round_euros(sum(available_by_component.values())),
            deficit_report_debut=deficit_report_debut,
            deficit_report_fin=deficit_report_fin,
            deficit_genere=deficit_genere,
            frais_deductibles_exceptionnels=frais_exceptionnels,
            amortissement_bati=dotations["bati"],
            amortissement_travaux=dotations["travaux"],
            amortissement_meubles=dotations["meubles"],
            amortissement_frais_acquisition=dotations["frais_acquisition"],
        )

    deficit_utilise, reports_restants = _consommer_reports(etat.deficit_lmnp, resultat_avant_deficit)
    base_avant_amortissement = max(resultat_avant_deficit - deficit_utilise, 0.0)
    amortissement_utilisable = min(base_avant_amortissement, sum(available_by_component.values()))
    amortissement_used, amortissement_reports_fin = _allouer_amortissement(
        available_by_component,
        amortissement_utilisable,
    )
    resultat_taxable = max(base_avant_amortissement - sum(amortissement_used.values()), 0.0)

    etat.deficit_lmnp = reports_restants
    etat.amortissement_reports = amortissement_reports_fin
    amortissement_deduit_plus_value = (
        amortissement_used["bati"]
        + amortissement_used["travaux"]
        + amortissement_used["frais_acquisition"]
    )

    return ResultatFiscal(
        regime=RegimeFiscal.LMNP_REEL,
        revenus=_round_euros(revenus),
        charges_deductibles=_round_euros(charges_deductibles),
        interets=_round_euros(interets),
        amortissement=amortissement_courant,
        resultat_avant_amortissement=_round_euros(base_avant_amortissement),
        resultat_fiscal=_round_euros(resultat_taxable),
        impot=_impot_sur_resultat(resultat_taxable, fiscalite),
        amortissement_non_utilise=_round_euros(sum(amortissement_reports_fin.values())),
        amortissement_utilise=_round_euros(sum(amortissement_used.values())),
        amortissement_report_debut=amortissement_report_debut,
        amortissement_report_fin=_round_euros(sum(amortissement_reports_fin.values())),
        amortissement_deduit=_round_euros(sum(amortissement_used.values())),
        amortissement_deduit_plus_value=_round_euros(amortissement_deduit_plus_value),
        deficit_report_debut=deficit_report_debut,
        deficit_report_fin=_total_reports(etat.deficit_lmnp),
        deficit_utilise=deficit_utilise,
        frais_deductibles_exceptionnels=frais_exceptionnels,
        amortissement_bati=dotations["bati"],
        amortissement_travaux=dotations["travaux"],
        amortissement_meubles=dotations["meubles"],
        amortissement_frais_acquisition=dotations["frais_acquisition"],
        amortissement_bati_deduit=amortissement_used["bati"],
        amortissement_travaux_deduit=amortissement_used["travaux"],
        amortissement_meubles_deduit=amortissement_used["meubles"],
        amortissement_frais_acquisition_deduit=amortissement_used["frais_acquisition"],
    )


def _frais_exceptionnels_lmnp(bien: BienImmobilier, fiscalite: Fiscalite, annee: int) -> float:
    frais = 0.0
    if fiscalite.option_frais_acquisition == "deduire_annee_1" and annee == 1:
        frais += _frais_acquisition(bien)
    if fiscalite.option_frais_emprunt == "deduire_annee_1" and annee == 1:
        frais += _frais_emprunt(bien)
    elif fiscalite.option_frais_emprunt == "etaler" and annee <= 5:
        frais += _frais_emprunt(bien) / 5
    return _round_euros(frais)


def _allouer_amortissement(
    available_by_component: dict[str, float],
    montant_a_utiliser: float,
) -> tuple[dict[str, float], dict[str, float]]:
    used = dict.fromkeys(AMORTISSEMENT_COMPONENTS, 0.0)
    remaining_reports = dict.fromkeys(AMORTISSEMENT_COMPONENTS, 0.0)
    restant = max(montant_a_utiliser, 0.0)
    for component in AMORTISSEMENT_COMPONENTS:
        disponible = _round_euros(available_by_component.get(component, 0.0))
        consommation = min(disponible, restant)
        used[component] = _round_euros(consommation)
        remaining_reports[component] = _round_euros(disponible - consommation)
        restant -= consommation
    return used, remaining_reports
