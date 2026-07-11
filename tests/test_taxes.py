from achat_immo.engines import taxes
from achat_immo.models import BienImmobilier, Fiscalite, RegimeFiscal, TypeBien
from achat_immo.engines.taxes import (
    EtatFiscal,
    abattement_plus_value_ir_pct,
    abattement_plus_value_ps_pct,
    amortissement_lmnp,
    calcul_plus_value,
    fiscalite_lmnp_reel,
    resultat_fiscal,
)
from achat_immo.engines.taxes_lmnp import amortissement_lmnp as lmnp_amortissement_lmnp
from achat_immo.engines.taxes_location_nue import fiscalite_location_nue as location_nue_reelle
from achat_immo.engines.taxes_micro import fiscalite_micro_bic as micro_bic
from achat_immo.engines.taxes_plus_value import calcul_plus_value as plus_value_calcul


def test_amortissement_lmnp_separe_bien_travaux_meubles() -> None:
    bien = BienImmobilier(
        ville="Nimes",
        surface_m2=40,
        prix_affiche=100_000,
        type_bien=TypeBien.T2,
        travaux_estimes=15_000,
        meubles_estimes=7_000,
    )
    fiscalite = Fiscalite()

    assert amortissement_lmnp(bien, fiscalite) == 4_833.33


def test_lmnp_reel_ne_cree_pas_impot_si_amortissement_suffisant() -> None:
    fiscalite = Fiscalite(tmi_pct=30, prelevements_sociaux_pct=17.2)
    resultat = fiscalite_lmnp_reel(
        revenus=7_000,
        charges_deductibles=2_000,
        interets=2_000,
        amortissement=4_000,
        fiscalite=fiscalite,
    )

    assert resultat.resultat_avant_amortissement == 3_000
    assert resultat.resultat_fiscal == 0
    assert resultat.impot == 0
    assert resultat.amortissement_non_utilise == 1_000


def test_routeur_micro_bic() -> None:
    bien = BienImmobilier(ville="Nimes", surface_m2=30, prix_affiche=80_000)
    fiscalite = Fiscalite(regime=RegimeFiscal.MICRO_BIC, tmi_pct=30)

    resultat = resultat_fiscal(
        bien=bien,
        revenus=6_000,
        charges_deductibles=2_500,
        interets=1_000,
        fiscalite=fiscalite,
    )

    assert resultat.regime == RegimeFiscal.MICRO_BIC
    assert resultat.resultat_fiscal == 3_000
    assert resultat.impot == 1_458


def test_lmnp_reel_reporte_deficit_et_amortissements() -> None:
    bien = BienImmobilier(
        ville="Nimes",
        surface_m2=40,
        prix_affiche=100_000,
        type_bien=TypeBien.T2,
        frais_notaire_estimes=8_000,
        travaux_estimes=15_000,
        meubles_estimes=7_000,
    )
    fiscalite = Fiscalite(tmi_pct=30, prelevements_sociaux_pct=18.6)
    etat = EtatFiscal()

    annee_1 = resultat_fiscal(
        bien=bien,
        revenus=5_000,
        charges_deductibles=9_000,
        interets=2_000,
        fiscalite=fiscalite,
        annee=1,
        etat=etat,
    )
    annee_2 = resultat_fiscal(
        bien=bien,
        revenus=12_000,
        charges_deductibles=1_000,
        interets=1_000,
        fiscalite=fiscalite,
        annee=2,
        etat=etat,
    )

    assert annee_1.deficit_genere == 6_000
    assert annee_1.amortissement_utilise == 0
    assert annee_1.amortissement_report_fin > 0
    assert annee_2.deficit_utilise == 6_000
    assert annee_2.amortissement_utilise == 4_000
    assert annee_2.resultat_fiscal == 0
    assert annee_2.amortissement_report_fin > annee_1.amortissement_report_fin


def test_location_nue_reel_sans_amortissement_et_micro_foncier() -> None:
    bien = BienImmobilier(ville="Nimes", surface_m2=30, prix_affiche=80_000)
    fiscalite_nue = Fiscalite(regime=RegimeFiscal.LOCATION_NUE_REEL, tmi_pct=30, prelevements_sociaux_pct=17.2)
    fiscalite_micro = Fiscalite(regime=RegimeFiscal.MICRO_FONCIER, tmi_pct=30, prelevements_sociaux_pct=17.2)

    nue = resultat_fiscal(
        bien=bien,
        revenus=6_000,
        charges_deductibles=2_000,
        interets=1_000,
        fiscalite=fiscalite_nue,
    )
    micro = resultat_fiscal(
        bien=bien,
        revenus=6_000,
        charges_deductibles=2_000,
        interets=1_000,
        fiscalite=fiscalite_micro,
    )

    assert nue.amortissement == 0
    assert nue.resultat_fiscal == 3_000
    assert micro.charges_deductibles == 1_800
    assert micro.resultat_fiscal == 4_200


def test_plus_value_abattements_et_reintegration_lmnp() -> None:
    bien = BienImmobilier(
        ville="Nimes",
        surface_m2=40,
        prix_affiche=100_000,
        frais_notaire_estimes=8_000,
        travaux_estimes=15_000,
    )
    fiscalite = Fiscalite()

    assert abattement_plus_value_ir_pct(5) == 0
    assert abattement_plus_value_ir_pct(22) == 100
    assert abattement_plus_value_ps_pct(30) == 100

    plus_value = calcul_plus_value(
        bien=bien,
        fiscalite=fiscalite,
        regime=RegimeFiscal.LMNP_REEL,
        valeur_bien=160_000,
        duree_detention_annees=10,
        frais_revente_pct=0.0,
        amortissements_lmnp_deduits_plus_value=10_000,
    )
    moins_value = calcul_plus_value(
        bien=bien,
        fiscalite=fiscalite,
        regime=RegimeFiscal.MICRO_BIC,
        valeur_bien=90_000,
        duree_detention_annees=10,
        frais_revente_pct=0.0,
    )

    assert plus_value.prix_acquisition_fiscal == 113_000
    assert plus_value.amortissements_reintegres == 10_000
    assert plus_value.plus_value_brute == 47_000
    assert plus_value.abattement_ir_pct == 30
    assert plus_value.impot_total == 13_668.07
    assert moins_value.impot_total == 0


def test_taxes_facade_reexporte_les_modules_fiscaux() -> None:
    assert taxes.amortissement_lmnp is lmnp_amortissement_lmnp
    assert taxes.fiscalite_location_nue is location_nue_reelle
    assert taxes.fiscalite_micro_bic is micro_bic
    assert taxes.calcul_plus_value is plus_value_calcul
