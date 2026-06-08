"""Fiscalite locative simplifiee.

Ce module vise une approximation prudente et lisible, pas un rescrit fiscal.
Les fonctions retournent aussi les bases intermediaires pour audit.
"""

from __future__ import annotations

from dataclasses import dataclass

from achat_immo.models import BienImmobilier, Fiscalite, RegimeFiscal


@dataclass(frozen=True, slots=True)
class ResultatFiscal:
    regime: RegimeFiscal
    revenus: float
    charges_deductibles: float
    interets: float
    amortissement: float
    resultat_avant_amortissement: float
    resultat_fiscal: float
    impot: float
    amortissement_non_utilise: float = 0.0


def amortissement_lmnp(bien: BienImmobilier, fiscalite: Fiscalite) -> float:
    """Amortissement annuel LMNP reel simplifie.

    Hypothese prudente :
    - le terrain n'est pas amortissable ;
    - le prix du bien est amorti sur 30 ans par defaut ;
    - les travaux et meubles sont amortis separement.
    """

    base_bien = bien.prix_achat * (1 - fiscalite.part_terrain_pct / 100)
    amortissement = (
        base_bien / fiscalite.duree_amortissement_bien_annees
        + bien.travaux_estimes / fiscalite.duree_amortissement_travaux_annees
        + bien.meubles_estimes / fiscalite.duree_amortissement_meubles_annees
    )
    return round(amortissement, 2)


def _impot_sur_resultat(resultat_fiscal: float, fiscalite: Fiscalite) -> float:
    if resultat_fiscal <= 0:
        return 0.0
    return round(resultat_fiscal * fiscalite.taux_global_imposition_pct / 100, 2)


def fiscalite_lmnp_reel(
    revenus: float,
    charges_deductibles: float,
    interets: float,
    amortissement: float,
    fiscalite: Fiscalite,
) -> ResultatFiscal:
    """Fiscalite LMNP reel.

    L'amortissement LMNP ne cree pas de deficit fiscal dans cette version
    simplifiee : il ramene le resultat taxable a zero et l'excedent est suivi.
    """

    resultat_avant_amortissement = revenus - charges_deductibles - interets
    amortissement_utilisable = max(resultat_avant_amortissement, 0.0)
    resultat_fiscal = max(resultat_avant_amortissement - amortissement, 0.0)
    amortissement_non_utilise = max(amortissement - amortissement_utilisable, 0.0)
    impot = _impot_sur_resultat(resultat_fiscal, fiscalite)
    return ResultatFiscal(
        regime=RegimeFiscal.LMNP_REEL,
        revenus=round(revenus, 2),
        charges_deductibles=round(charges_deductibles, 2),
        interets=round(interets, 2),
        amortissement=round(amortissement, 2),
        resultat_avant_amortissement=round(resultat_avant_amortissement, 2),
        resultat_fiscal=round(resultat_fiscal, 2),
        impot=impot,
        amortissement_non_utilise=round(amortissement_non_utilise, 2),
    )


def fiscalite_location_nue(
    revenus: float,
    charges_deductibles: float,
    interets: float,
    fiscalite: Fiscalite,
) -> ResultatFiscal:
    """Location nue au reel, sans modelisation fine du report de deficit."""

    resultat = revenus - charges_deductibles - interets
    resultat_taxable = max(resultat, 0.0)
    impot = _impot_sur_resultat(resultat_taxable, fiscalite)
    return ResultatFiscal(
        regime=RegimeFiscal.LOCATION_NUE_REEL,
        revenus=round(revenus, 2),
        charges_deductibles=round(charges_deductibles, 2),
        interets=round(interets, 2),
        amortissement=0.0,
        resultat_avant_amortissement=round(resultat, 2),
        resultat_fiscal=round(resultat_taxable, 2),
        impot=impot,
    )


def fiscalite_micro_bic(
    revenus: float,
    fiscalite: Fiscalite,
) -> ResultatFiscal:
    resultat = revenus * (1 - fiscalite.abattement_micro_bic_pct / 100)
    impot = _impot_sur_resultat(resultat, fiscalite)
    return ResultatFiscal(
        regime=RegimeFiscal.MICRO_BIC,
        revenus=round(revenus, 2),
        charges_deductibles=round(revenus * fiscalite.abattement_micro_bic_pct / 100, 2),
        interets=0.0,
        amortissement=0.0,
        resultat_avant_amortissement=round(resultat, 2),
        resultat_fiscal=round(resultat, 2),
        impot=impot,
    )


def fiscalite_micro_foncier(
    revenus: float,
    fiscalite: Fiscalite,
) -> ResultatFiscal:
    resultat = revenus * (1 - fiscalite.abattement_micro_foncier_pct / 100)
    impot = _impot_sur_resultat(resultat, fiscalite)
    return ResultatFiscal(
        regime=RegimeFiscal.MICRO_FONCIER,
        revenus=round(revenus, 2),
        charges_deductibles=round(revenus * fiscalite.abattement_micro_foncier_pct / 100, 2),
        interets=0.0,
        amortissement=0.0,
        resultat_avant_amortissement=round(resultat, 2),
        resultat_fiscal=round(resultat, 2),
        impot=impot,
    )


def resultat_fiscal(
    bien: BienImmobilier,
    revenus: float,
    charges_deductibles: float,
    interets: float,
    fiscalite: Fiscalite,
) -> ResultatFiscal:
    """Routeur fiscal selon le regime choisi."""

    if fiscalite.regime == RegimeFiscal.LMNP_REEL:
        return fiscalite_lmnp_reel(
            revenus=revenus,
            charges_deductibles=charges_deductibles,
            interets=interets,
            amortissement=amortissement_lmnp(bien, fiscalite),
            fiscalite=fiscalite,
        )
    if fiscalite.regime == RegimeFiscal.LOCATION_NUE_REEL:
        return fiscalite_location_nue(revenus, charges_deductibles, interets, fiscalite)
    if fiscalite.regime == RegimeFiscal.MICRO_BIC:
        return fiscalite_micro_bic(revenus, fiscalite)
    if fiscalite.regime == RegimeFiscal.MICRO_FONCIER:
        return fiscalite_micro_foncier(revenus, fiscalite)
    raise ValueError(f"Regime fiscal non supporte : {fiscalite.regime}")
