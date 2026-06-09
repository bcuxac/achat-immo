from achat_immo.models import BienImmobilier, Fiscalite, RegimeFiscal, TypeBien
from achat_immo.taxes import amortissement_lmnp, fiscalite_lmnp_reel, resultat_fiscal


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
