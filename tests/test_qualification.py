from achat_immo.qualification import (
    ProfitabilityTargets,
    classify_monte_carlo_summary,
    evaluate_monte_carlo_summary,
)


def _summary() -> dict[str, float]:
    return {
        "tri_median": 7.0,
        "tri_p10": 3.5,
        "coc_median": 1.0,
        "cashflow_premiere_annee_mensuel_p10": 25.0,
        "probabilite_cashflow_premiere_annee_positif": 0.65,
        "cashflow_mensuel_minimal_median": 10.0,
        "probabilite_toutes_annees_cashflow_positif": 0.60,
    }


def test_qualification_exige_toutes_les_metriques_canoniques() -> None:
    targets = ProfitabilityTargets()

    accepted = evaluate_monte_carlo_summary(_summary(), targets)
    weak_p10 = evaluate_monte_carlo_summary({**_summary(), "tri_p10": 2.9}, targets)
    weak_probability = evaluate_monte_carlo_summary(
        {**_summary(), "probabilite_cashflow_premiere_annee_positif": 0.49},
        targets,
    )

    assert accepted.meets_targets is True
    assert weak_p10.reasons == ("tri_p10_insuffisant",)
    assert weak_probability.reasons == ("probabilite_cashflow_premiere_annee_insuffisante",)


def test_qualification_explique_les_metriques_absentes() -> None:
    evaluation = evaluate_monte_carlo_summary({}, ProfitabilityTargets())

    assert evaluation.meets_targets is False
    assert "metrique_absente:tri_median" in evaluation.reasons
    assert "metrique_absente:probabilite_cashflow_premiere_annee_positif" in evaluation.reasons


def test_qualification_distingue_rentabilite_et_autofinancement() -> None:
    profitable_with_effort = classify_monte_carlo_summary(
        {**_summary(), "cashflow_premiere_annee_mensuel_p10": -50.0},
        ProfitabilityTargets(),
    )
    self_financed = classify_monte_carlo_summary(_summary(), ProfitabilityTargets())

    assert profitable_with_effort.qualification == "rentable_avec_effort_epargne"
    assert self_financed.qualification == "rentable_et_autofinance"
