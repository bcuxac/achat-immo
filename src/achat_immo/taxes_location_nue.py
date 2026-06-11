"""Fiscalite de la location nue au reel."""

from __future__ import annotations

from achat_immo.models import Fiscalite, RegimeFiscal
from achat_immo.taxes_reports import (
    consommer_reports as _consommer_reports,
    reports_valides as _reports_valides,
    total_reports as _total_reports,
)
from achat_immo.taxes_types import EtatFiscal, ReportFiscal, ResultatFiscal
from achat_immo.taxes_utils import (
    impot_sur_resultat as _impot_sur_resultat,
    round_euros as _round_euros,
)


def fiscalite_location_nue(
    revenus: float,
    charges_deductibles: float,
    interets: float,
    fiscalite: Fiscalite,
    *,
    annee: int = 1,
    etat: EtatFiscal | None = None,
) -> ResultatFiscal:
    """Location nue au reel, avec report de deficit foncier sans imputation globale."""

    etat = etat or EtatFiscal()
    etat.deficit_foncier = _reports_valides(etat.deficit_foncier, annee, 10)
    deficit_report_debut = _total_reports(etat.deficit_foncier)
    resultat = revenus - charges_deductibles - interets
    if resultat < 0:
        deficit_genere = _round_euros(-resultat)
        etat.deficit_foncier.append(ReportFiscal(annee, deficit_genere))
        return ResultatFiscal(
            regime=RegimeFiscal.LOCATION_NUE_REEL,
            revenus=_round_euros(revenus),
            charges_deductibles=_round_euros(charges_deductibles),
            interets=_round_euros(interets),
            amortissement=0.0,
            resultat_avant_amortissement=_round_euros(resultat),
            resultat_fiscal=0.0,
            impot=0.0,
            deficit_report_debut=deficit_report_debut,
            deficit_report_fin=_total_reports(etat.deficit_foncier),
            deficit_genere=deficit_genere,
        )

    deficit_utilise, reports_restants = _consommer_reports(etat.deficit_foncier, resultat)
    etat.deficit_foncier = reports_restants
    resultat_taxable = max(resultat - deficit_utilise, 0.0)
    return ResultatFiscal(
        regime=RegimeFiscal.LOCATION_NUE_REEL,
        revenus=_round_euros(revenus),
        charges_deductibles=_round_euros(charges_deductibles),
        interets=_round_euros(interets),
        amortissement=0.0,
        resultat_avant_amortissement=_round_euros(resultat),
        resultat_fiscal=_round_euros(resultat_taxable),
        impot=_impot_sur_resultat(resultat_taxable, fiscalite),
        deficit_report_debut=deficit_report_debut,
        deficit_report_fin=_total_reports(etat.deficit_foncier),
        deficit_utilise=deficit_utilise,
    )
