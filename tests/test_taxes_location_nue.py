from achat_immo.models import Fiscalite, RegimeFiscal
from achat_immo.engines.taxes_location_nue import fiscalite_location_nue
from achat_immo.engines.taxes_types import EtatFiscal, ReportFiscal


def test_location_nue_expire_anciens_deficits_et_consomme_le_solde() -> None:
    fiscalite = Fiscalite(tmi_pct=30, prelevements_sociaux_pct=17.2)
    etat = EtatFiscal(
        deficit_foncier=[
            ReportFiscal(annee_origine=1, montant=1_000),
            ReportFiscal(annee_origine=4, montant=2_000),
        ]
    )

    resultat = fiscalite_location_nue(
        revenus=5_000,
        charges_deductibles=1_000,
        interets=500,
        fiscalite=fiscalite,
        annee=12,
        etat=etat,
    )

    assert resultat.regime == RegimeFiscal.LOCATION_NUE_REEL
    assert resultat.deficit_report_debut == 2_000
    assert resultat.deficit_utilise == 2_000
    assert resultat.deficit_report_fin == 0
    assert resultat.resultat_fiscal == 1_500
    assert resultat.impot == 708
    assert etat.deficit_foncier == []
