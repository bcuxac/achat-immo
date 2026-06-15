from achat_immo.models import Fiscalite, RegimeFiscal
from achat_immo.engines.taxes_micro import fiscalite_micro_bic, fiscalite_micro_foncier


def test_micro_bic_signale_le_depassement_du_seuil() -> None:
    fiscalite = Fiscalite(tmi_pct=30, prelevements_sociaux_pct=17.2, seuil_micro_bic=10_000)

    resultat = fiscalite_micro_bic(12_000, fiscalite)

    assert resultat.regime == RegimeFiscal.MICRO_BIC
    assert resultat.eligible is False
    assert resultat.avertissements == ("revenus_superieurs_seuil_micro_bic",)
    assert resultat.charges_deductibles == 6_000
    assert resultat.resultat_fiscal == 6_000
    assert resultat.impot == 2_832


def test_micro_foncier_reste_eligible_au_seuil_inclus() -> None:
    fiscalite = Fiscalite(tmi_pct=30, prelevements_sociaux_pct=17.2, seuil_micro_foncier=15_000)

    resultat = fiscalite_micro_foncier(15_000, fiscalite)

    assert resultat.regime == RegimeFiscal.MICRO_FONCIER
    assert resultat.eligible is True
    assert resultat.avertissements == ()
    assert resultat.charges_deductibles == 4_500
    assert resultat.resultat_fiscal == 10_500
    assert resultat.impot == 4_956
