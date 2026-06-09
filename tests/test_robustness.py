from achat_immo.robustness import analyser_grille


def _row(
    cashflow: float,
    *,
    loyer: float = 600,
    apport: float = 15_000,
    taux: float = 3.6,
    vacance: float = 1.0,
    gestion: bool = False,
    diagnostics: str = "",
    alertes: str = "",
) -> dict[str, object]:
    return {
        "loyer_hc_mensuel": loyer,
        "taux_credit": taux,
        "duree_annees": 20,
        "apport": apport,
        "vacance_mois": vacance,
        "gestion_agence": gestion,
        "cashflow_mensuel_apres_impot": cashflow,
        "diagnostics": diagnostics,
        "alertes": alertes,
    }


def test_analyse_grille_detecte_un_diagnostic_incomplet() -> None:
    robustesse = analyser_grille(
        [
            _row(10, diagnostics="secteur_encadrement_manquant"),
            _row(-50, diagnostics="secteur_encadrement_manquant"),
        ]
    )

    assert robustesse.decision == "diagnostic_incomplet"
    assert robustesse.diagnostic_incomplet is True
    assert robustesse.diagnostics_critiques == ("secteur_encadrement_manquant",)


def test_analyse_grille_rejette_si_aucun_scenario_viable() -> None:
    robustesse = analyser_grille([_row(-250), _row(-300), _row(-500)])

    assert robustesse.decision == "a_rejeter"
    assert robustesse.nb_viables == 0
    assert "Aucun scenario" in robustesse.conditions_validite[0]


def test_analyse_grille_identifie_conditions_de_validite() -> None:
    robustesse = analyser_grille(
        [
            _row(-260, loyer=550, apport=10_000, taux=4.0, vacance=2.0),
            _row(-150, loyer=600, apport=15_000, taux=3.8, vacance=1.0),
            _row(20, loyer=650, apport=20_000, taux=3.4, vacance=0.0, gestion=True),
        ]
    )

    assert robustesse.decision == "a_creuser"
    assert robustesse.nb_viables == 2
    assert robustesse.nb_positifs == 1
    assert "Loyer HC >= 600 EUR" in robustesse.conditions_validite
    assert "Aucun scenario ne produit un cash-flow positif." not in robustesse.conditions_validite
