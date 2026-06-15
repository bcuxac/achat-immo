"""Fiscalite de sortie et plus-value immobiliere."""

from __future__ import annotations

from dataclasses import dataclass

from achat_immo.models import BienImmobilier, Fiscalite, RegimeFiscal
from achat_immo.engines.taxes_utils import round_euros as _round_euros


@dataclass(frozen=True, slots=True)
class PlusValueResult:
    regime: RegimeFiscal
    prix_cession_net: float
    prix_acquisition_fiscal: float
    amortissements_reintegres: float
    plus_value_brute: float
    abattement_ir_pct: float
    abattement_ps_pct: float
    base_ir: float
    base_ps: float
    impot_ir: float
    prelevements_sociaux: float
    surtaxe: float
    impot_total: float

    def to_dict(self) -> dict[str, float | str]:
        return {
            "regime": self.regime.value,
            "prix_cession_net": self.prix_cession_net,
            "prix_acquisition_fiscal": self.prix_acquisition_fiscal,
            "amortissements_reintegres": self.amortissements_reintegres,
            "plus_value_brute": self.plus_value_brute,
            "abattement_ir_pct": self.abattement_ir_pct,
            "abattement_ps_pct": self.abattement_ps_pct,
            "base_ir": self.base_ir,
            "base_ps": self.base_ps,
            "impot_ir": self.impot_ir,
            "prelevements_sociaux": self.prelevements_sociaux,
            "surtaxe": self.surtaxe,
            "impot_total": self.impot_total,
        }


def abattement_plus_value_ir_pct(duree_detention_annees: int) -> float:
    annees_6_a_21 = min(max(duree_detention_annees - 5, 0), 16)
    abattement = annees_6_a_21 * 6
    if duree_detention_annees >= 22:
        abattement += 4
    return min(round(abattement, 2), 100.0)


def abattement_plus_value_ps_pct(duree_detention_annees: int) -> float:
    annees_6_a_21 = min(max(duree_detention_annees - 5, 0), 16)
    abattement = annees_6_a_21 * 1.65
    if duree_detention_annees >= 22:
        abattement += 1.60
    if duree_detention_annees >= 23:
        abattement += min(duree_detention_annees - 22, 8) * 9
    return min(round(abattement, 2), 100.0)


def surtaxe_plus_value_elevee(base_ir: float) -> float:
    """Surtaxe simplifiee des plus-values immobilieres superieures a 50 kEUR."""

    if base_ir <= 50_000:
        return 0.0
    if base_ir <= 60_000:
        return _round_euros(base_ir * 0.02 - (60_000 - base_ir) * 0.05)
    if base_ir <= 100_000:
        return _round_euros(base_ir * 0.02)
    if base_ir <= 110_000:
        return _round_euros(base_ir * 0.03 - (110_000 - base_ir) * 0.10)
    if base_ir <= 150_000:
        return _round_euros(base_ir * 0.03)
    if base_ir <= 160_000:
        return _round_euros(base_ir * 0.04 - (160_000 - base_ir) * 0.15)
    if base_ir <= 200_000:
        return _round_euros(base_ir * 0.04)
    if base_ir <= 210_000:
        return _round_euros(base_ir * 0.05 - (210_000 - base_ir) * 0.20)
    if base_ir <= 250_000:
        return _round_euros(base_ir * 0.05)
    if base_ir <= 260_000:
        return _round_euros(base_ir * 0.06 - (260_000 - base_ir) * 0.25)
    return _round_euros(base_ir * 0.06)


def calcul_plus_value(
    bien: BienImmobilier,
    fiscalite: Fiscalite,
    regime: RegimeFiscal,
    valeur_bien: float,
    duree_detention_annees: int,
    frais_revente_pct: float,
    *,
    amortissements_lmnp_deduits_plus_value: float = 0.0,
) -> PlusValueResult:
    """Calcule l'impot de sortie utilise dans le flux terminal.
    
    IMPORTANT - Optisation fiscale (Forfaits) :
    La loi francaise permet de majorer le prix d'acquisition pour reduire la plus-value taxable :
    - Forfait acquisition : on retient le maximum entre les frais reels (notaire+agence) et un forfait fixe de 7.5% du prix d'achat, sans justificatif.
    - Forfait travaux : si le bien est detenu depuis au moins 5 ans, on retient le maximum entre les travaux reels et un forfait de 15% du prix d'achat, sans aucun justificatif requis.
    Le simulateur applique automatiquement ces forfaits si cela est mathematiquement avantageux pour maximiser le TRI.
    """

    prix_cession_net = _round_euros(valeur_bien * (1 - frais_revente_pct / 100))
    
    frais_acq_reels = bien.frais_agence_achat + bien.frais_notaire_estimes
    frais_acq = max(frais_acq_reels, bien.prix_achat * 0.075)

    frais_travaux = bien.travaux_estimes
    if duree_detention_annees >= 5:
        frais_travaux = max(frais_travaux, bien.prix_achat * 0.15)

    prix_acquisition_total = _round_euros(
        bien.prix_achat
        + frais_acq
        + frais_travaux
    )
    amortissements_reintegres = 0.0
    if regime == RegimeFiscal.LMNP_REEL and fiscalite.reintegrer_amortissements_lmnp_plus_value:
        amortissements_reintegres = _round_euros(amortissements_lmnp_deduits_plus_value)
    prix_acquisition_fiscal = _round_euros(max(prix_acquisition_total - amortissements_reintegres, 0.0))
    plus_value_brute = _round_euros(prix_cession_net - prix_acquisition_fiscal)
    if plus_value_brute <= 0:
        return PlusValueResult(
            regime=regime,
            prix_cession_net=prix_cession_net,
            prix_acquisition_fiscal=prix_acquisition_fiscal,
            amortissements_reintegres=amortissements_reintegres,
            plus_value_brute=plus_value_brute,
            abattement_ir_pct=0.0,
            abattement_ps_pct=0.0,
            base_ir=0.0,
            base_ps=0.0,
            impot_ir=0.0,
            prelevements_sociaux=0.0,
            surtaxe=0.0,
            impot_total=0.0,
        )

    abattement_ir = abattement_plus_value_ir_pct(duree_detention_annees)
    abattement_ps = abattement_plus_value_ps_pct(duree_detention_annees)
    base_ir = _round_euros(plus_value_brute * (1 - abattement_ir / 100))
    base_ps = _round_euros(plus_value_brute * (1 - abattement_ps / 100))
    impot_ir = _round_euros(base_ir * fiscalite.taux_impot_plus_value_pct / 100)
    prelevements_sociaux = _round_euros(base_ps * fiscalite.taux_prelevements_sociaux_plus_value_pct / 100)
    surtaxe = surtaxe_plus_value_elevee(base_ir) if fiscalite.surtaxe_plus_value_active else 0.0

    return PlusValueResult(
        regime=regime,
        prix_cession_net=prix_cession_net,
        prix_acquisition_fiscal=prix_acquisition_fiscal,
        amortissements_reintegres=amortissements_reintegres,
        plus_value_brute=plus_value_brute,
        abattement_ir_pct=abattement_ir,
        abattement_ps_pct=abattement_ps,
        base_ir=base_ir,
        base_ps=base_ps,
        impot_ir=impot_ir,
        prelevements_sociaux=prelevements_sociaux,
        surtaxe=surtaxe,
        impot_total=_round_euros(impot_ir + prelevements_sociaux + surtaxe),
    )
