from achat_immo.engines.loan import (
    capital_restant_du,
    calcul_mensualite,
    credit_par_annee,
    interets_par_annee,
    mensualite_assurance,
    tableau_amortissement,
    taux_mensuel_effectif,
)


def test_calcul_mensualite_pret_amortissable() -> None:
    mensualite = calcul_mensualite(100_000, taux_annuel_pct=3.6, duree_annees=20)

    assert mensualite == 582.12
    assert round(taux_mensuel_effectif(3.6), 10) == 0.0029516094


def test_tableau_amortissement_solde_le_credit() -> None:
    echeances = tableau_amortissement(
        montant=100_000,
        taux_annuel_pct=3.6,
        duree_annees=20,
        assurance_annuelle_pct=0.30,
    )

    assert len(echeances) == 240
    assert echeances[0].interets == 295.16
    assert echeances[0].assurance == 25.0
    assert echeances[-1].crd_apres == 0.0
    assert sum(e.capital for e in echeances) == 100_000.0


def test_capital_restant_du_et_interets_annuels() -> None:
    echeances = tableau_amortissement(120_000, 3.0, 15)
    interets = interets_par_annee(echeances)

    assert capital_restant_du(120_000, 3.0, 15, 0) == 120_000
    assert capital_restant_du(120_000, 3.0, 15, 180) == 0
    assert 0 < capital_restant_du(120_000, 3.0, 15, 60) < 120_000
    assert interets[1] > interets[2]


def test_tableau_annuel_credit_et_taux_zero() -> None:
    echeances = tableau_amortissement(120_000, 0.0, 20)
    annuel = credit_par_annee(echeances)

    assert calcul_mensualite(120_000, 0.0, 20) == 500.0
    assert echeances[0].interets == 0.0
    assert echeances[-1].crd_apres == 0.0
    assert annuel[0]["capital"] == 6_000.0
    assert annuel[0]["interets"] == 0.0


def test_assurance_sur_capital_initial() -> None:
    assert mensualite_assurance(100_000, 0.30) == 25.0
