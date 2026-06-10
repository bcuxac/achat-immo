"""Fiscalite locative annuelle.

Ce module reste une approximation de simulation. Il suit les mecanismes qui
faussent le plus les decisions : reports LMNP, amortissements non createurs de
deficit, regimes micro, deficit foncier suivi separement et fiscalite de sortie.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from achat_immo.models import BienImmobilier, Fiscalite, ModeLocation, RegimeFiscal


AMORTISSEMENT_COMPONENTS = ("bati", "travaux", "frais_acquisition", "meubles")


@dataclass(slots=True)
class ReportFiscal:
    annee_origine: int
    montant: float


@dataclass(slots=True)
class EtatFiscal:
    """Etat fiscal reporte d'une annee a l'autre pour une simulation."""

    amortissement_reports: dict[str, float] = field(default_factory=dict)
    deficit_lmnp: list[ReportFiscal] = field(default_factory=list)
    deficit_foncier: list[ReportFiscal] = field(default_factory=list)


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
    amortissement_utilise: float = 0.0
    amortissement_report_debut: float = 0.0
    amortissement_report_fin: float = 0.0
    amortissement_deduit: float = 0.0
    amortissement_deduit_plus_value: float = 0.0
    deficit_report_debut: float = 0.0
    deficit_report_fin: float = 0.0
    deficit_utilise: float = 0.0
    deficit_genere: float = 0.0
    frais_deductibles_exceptionnels: float = 0.0
    amortissement_bati: float = 0.0
    amortissement_travaux: float = 0.0
    amortissement_meubles: float = 0.0
    amortissement_frais_acquisition: float = 0.0
    amortissement_bati_deduit: float = 0.0
    amortissement_travaux_deduit: float = 0.0
    amortissement_meubles_deduit: float = 0.0
    amortissement_frais_acquisition_deduit: float = 0.0
    eligible: bool = True
    avertissements: tuple[str, ...] = ()


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


def _round_euros(value: float) -> float:
    return round(value, 2)


def _impot_sur_resultat(resultat_fiscal: float, fiscalite: Fiscalite) -> float:
    if resultat_fiscal <= 0:
        return 0.0
    return _round_euros(resultat_fiscal * fiscalite.taux_global_imposition_pct / 100)


def _frais_acquisition(bien: BienImmobilier) -> float:
    return bien.frais_agence_achat + bien.frais_notaire_estimes


def _frais_emprunt(bien: BienImmobilier) -> float:
    return bien.frais_bancaires + bien.garantie


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


def _frais_exceptionnels_lmnp(bien: BienImmobilier, fiscalite: Fiscalite, annee: int) -> float:
    frais = 0.0
    if fiscalite.option_frais_acquisition == "deduire_annee_1" and annee == 1:
        frais += _frais_acquisition(bien)
    if fiscalite.option_frais_emprunt == "deduire_annee_1" and annee == 1:
        frais += _frais_emprunt(bien)
    elif fiscalite.option_frais_emprunt == "etaler" and annee <= 5:
        frais += _frais_emprunt(bien) / 5
    return _round_euros(frais)


def _reports_valides(reports: list[ReportFiscal], annee: int, duree_annees: int) -> list[ReportFiscal]:
    return [
        ReportFiscal(report.annee_origine, _round_euros(report.montant))
        for report in reports
        if report.montant > 0 and annee - report.annee_origine <= duree_annees
    ]


def _total_reports(reports: list[ReportFiscal]) -> float:
    return _round_euros(sum(report.montant for report in reports))


def _consommer_reports(reports: list[ReportFiscal], montant: float) -> tuple[float, list[ReportFiscal]]:
    restant_a_utiliser = max(montant, 0.0)
    utilise = 0.0
    reports_restants: list[ReportFiscal] = []
    for report in reports:
        if restant_a_utiliser <= 0:
            reports_restants.append(report)
            continue
        consommation = min(report.montant, restant_a_utiliser)
        utilise += consommation
        restant = _round_euros(report.montant - consommation)
        restant_a_utiliser -= consommation
        if restant > 0:
            reports_restants.append(ReportFiscal(report.annee_origine, restant))
    return _round_euros(utilise), reports_restants


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


def _fiscalite_lmnp_reel_annuelle(
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
    """Calcule l'impot de sortie utilise dans le flux terminal."""

    prix_cession_net = _round_euros(valeur_bien * (1 - frais_revente_pct / 100))
    prix_acquisition_total = _round_euros(
        bien.prix_achat
        + bien.frais_agence_achat
        + bien.frais_notaire_estimes
        + bien.travaux_estimes
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
