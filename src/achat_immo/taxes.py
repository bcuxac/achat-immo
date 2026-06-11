"""Fiscalite locative annuelle.

Ce module reste une approximation de simulation. Il suit les mecanismes qui
faussent le plus les decisions : reports LMNP, amortissements non createurs de
deficit, regimes micro, deficit foncier suivi separement et fiscalite de sortie.
"""

from __future__ import annotations

from achat_immo.models import BienImmobilier, Fiscalite, ModeLocation, RegimeFiscal
from achat_immo.taxes_location_nue import fiscalite_location_nue as fiscalite_location_nue
from achat_immo.taxes_lmnp import (
    amortissement_lmnp as amortissement_lmnp,
    amortissements_lmnp_par_composant as amortissements_lmnp_par_composant,
    fiscalite_lmnp_reel as fiscalite_lmnp_reel,
    fiscalite_lmnp_reel_annuelle as _fiscalite_lmnp_reel_annuelle,
)
from achat_immo.taxes_micro import (
    fiscalite_micro_bic as fiscalite_micro_bic,
    fiscalite_micro_foncier as fiscalite_micro_foncier,
)
from achat_immo.taxes_plus_value import (
    PlusValueResult as PlusValueResult,
    abattement_plus_value_ir_pct as abattement_plus_value_ir_pct,
    abattement_plus_value_ps_pct as abattement_plus_value_ps_pct,
    calcul_plus_value as calcul_plus_value,
    surtaxe_plus_value_elevee as surtaxe_plus_value_elevee,
)
from achat_immo.taxes_types import (
    EtatFiscal as EtatFiscal,
    ResultatFiscal as ResultatFiscal,
)


def resultat_fiscal(
    bien: BienImmobilier,
    revenus: float,
    charges_deductibles: float,
    interets: float,
    fiscalite: Fiscalite,
    *,
    annee: int = 1,
    etat: EtatFiscal | None = None,
    mode_location: ModeLocation = ModeLocation.MEUBLEE,
) -> ResultatFiscal:
    """Routeur fiscal selon le regime choisi."""

    etat = etat or EtatFiscal()
    _ = mode_location
    if fiscalite.regime == RegimeFiscal.LMNP_REEL:
        return _fiscalite_lmnp_reel_annuelle(
            bien=bien,
            revenus=revenus,
            charges_deductibles=charges_deductibles,
            interets=interets,
            fiscalite=fiscalite,
            annee=annee,
            etat=etat,
        )
    if fiscalite.regime == RegimeFiscal.LOCATION_NUE_REEL:
        return fiscalite_location_nue(
            revenus,
            charges_deductibles,
            interets,
            fiscalite,
            annee=annee,
            etat=etat,
        )
    if fiscalite.regime == RegimeFiscal.MICRO_BIC:
        return fiscalite_micro_bic(revenus, fiscalite)
    if fiscalite.regime == RegimeFiscal.MICRO_FONCIER:
        return fiscalite_micro_foncier(revenus, fiscalite)
    raise ValueError(f"Regime fiscal non supporte : {fiscalite.regime}")
