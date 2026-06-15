from achat_immo.models import BienImmobilier, Fiscalite, TypeBien
from achat_immo.engines.taxes_lmnp import fiscalite_lmnp_reel_annuelle
from achat_immo.engines.taxes_types import EtatFiscal


def _bien_avec_frais() -> BienImmobilier:
    return BienImmobilier(
        ville="Nimes",
        surface_m2=40,
        prix_affiche=100_000,
        type_bien=TypeBien.T2,
        frais_agence_achat=2_000,
        frais_notaire_estimes=8_000,
        travaux_estimes=15_000,
        meubles_estimes=7_000,
        frais_bancaires=1_000,
        garantie=500,
    )


def test_lmnp_amortit_frais_acquisition_et_deduit_frais_emprunt_annee_1() -> None:
    fiscalite = Fiscalite(tmi_pct=30, prelevements_sociaux_pct=17.2)

    resultat = fiscalite_lmnp_reel_annuelle(
        bien=_bien_avec_frais(),
        revenus=10_000,
        charges_deductibles=1_000,
        interets=500,
        fiscalite=fiscalite,
        annee=1,
        etat=EtatFiscal(),
    )

    assert resultat.frais_deductibles_exceptionnels == 1_500
    assert resultat.amortissement_frais_acquisition == 2_000
    assert resultat.amortissement_frais_acquisition_deduit == 2_000
    assert resultat.amortissement_deduit_plus_value == 5_833.33
    assert resultat.resultat_fiscal == 166.67
    assert resultat.impot == 78.67


def test_lmnp_deduit_frais_acquisition_annee_1_et_etale_frais_emprunt() -> None:
    fiscalite = Fiscalite(
        option_frais_acquisition="deduire_annee_1",
        option_frais_emprunt="etaler",
    )

    resultat = fiscalite_lmnp_reel_annuelle(
        bien=_bien_avec_frais(),
        revenus=12_000,
        charges_deductibles=1_000,
        interets=500,
        fiscalite=fiscalite,
        annee=1,
        etat=EtatFiscal(),
    )

    assert resultat.frais_deductibles_exceptionnels == 10_300
    assert resultat.amortissement_frais_acquisition == 0
    assert resultat.amortissement_bati_deduit == 200
    assert resultat.amortissement_report_fin == 4_633.33
    assert resultat.resultat_fiscal == 0
