from achat_immo.engines.taxes_reports import consommer_reports, reports_valides, total_reports
from achat_immo.engines.taxes_types import ReportFiscal


def test_reports_valides_filtre_expiration_montants_nuls_et_arrondit() -> None:
    reports = [
        ReportFiscal(annee_origine=1, montant=100.456),
        ReportFiscal(annee_origine=2, montant=0),
        ReportFiscal(annee_origine=3, montant=-5),
        ReportFiscal(annee_origine=4, montant=50.123),
    ]

    valides = reports_valides(reports, annee=12, duree_annees=10)

    assert valides == [ReportFiscal(annee_origine=4, montant=50.12)]


def test_consommation_reports_utilise_les_reports_les_plus_anciens() -> None:
    reports = [
        ReportFiscal(annee_origine=1, montant=100),
        ReportFiscal(annee_origine=2, montant=50),
    ]

    utilise, restants = consommer_reports(reports, montant=120)

    assert utilise == 120
    assert restants == [ReportFiscal(annee_origine=2, montant=30)]
    assert total_reports(restants) == 30


def test_consommation_reports_ignore_les_montants_negatifs() -> None:
    reports = [ReportFiscal(annee_origine=1, montant=100)]

    utilise, restants = consommer_reports(reports, montant=-20)

    assert utilise == 0
    assert restants == reports
