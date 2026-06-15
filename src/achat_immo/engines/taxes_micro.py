"""Regimes micro locatifs."""

from __future__ import annotations

from achat_immo.models import Fiscalite, RegimeFiscal
from achat_immo.engines.taxes_types import ResultatFiscal
from achat_immo.engines.taxes_utils import (
    impot_sur_resultat as _impot_sur_resultat,
    round_euros as _round_euros,
)


def fiscalite_micro_bic(
    revenus: float,
    fiscalite: Fiscalite,
) -> ResultatFiscal:
    eligible = revenus <= fiscalite.seuil_micro_bic
    avertissements = () if eligible else ("revenus_superieurs_seuil_micro_bic",)
    resultat = revenus * (1 - fiscalite.abattement_micro_bic_pct / 100)
    impot = _impot_sur_resultat(resultat, fiscalite)
    return ResultatFiscal(
        regime=RegimeFiscal.MICRO_BIC,
        revenus=_round_euros(revenus),
        charges_deductibles=_round_euros(revenus * fiscalite.abattement_micro_bic_pct / 100),
        interets=0.0,
        amortissement=0.0,
        resultat_avant_amortissement=_round_euros(resultat),
        resultat_fiscal=_round_euros(resultat),
        impot=impot,
        eligible=eligible,
        avertissements=avertissements,
    )


def fiscalite_micro_foncier(
    revenus: float,
    fiscalite: Fiscalite,
) -> ResultatFiscal:
    eligible = revenus <= fiscalite.seuil_micro_foncier
    avertissements = () if eligible else ("revenus_superieurs_seuil_micro_foncier",)
    resultat = revenus * (1 - fiscalite.abattement_micro_foncier_pct / 100)
    impot = _impot_sur_resultat(resultat, fiscalite)
    return ResultatFiscal(
        regime=RegimeFiscal.MICRO_FONCIER,
        revenus=_round_euros(revenus),
        charges_deductibles=_round_euros(revenus * fiscalite.abattement_micro_foncier_pct / 100),
        interets=0.0,
        amortissement=0.0,
        resultat_avant_amortissement=_round_euros(resultat),
        resultat_fiscal=_round_euros(resultat),
        impot=impot,
        eligible=eligible,
        avertissements=avertissements,
    )
