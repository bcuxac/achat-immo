from achat_immo.qualification import ProfitabilityTargets, evaluate_monte_carlo_summary


def _summary() -> dict[str, float]:
    return {
        "tri_median": 7.0,
        "tri_p10": 3.5,
        "coc_median": 1.0,
        "cashflow_mensuel_minimal_median": 25.0,
        "probabilite_cashflow_cumule_positif": 0.65,
    }


def test_qualification_exige_toutes_les_metriques_canoniques() -> None:
    targets = ProfitabilityTargets()

    accepted = evaluate_monte_carlo_summary(_summary(), targets)
    weak_p10 = evaluate_monte_carlo_summary({**_summary(), "tri_p10": 2.9}, targets)
    weak_probability = evaluate_monte_carlo_summary(
        {**_summary(), "probabilite_cashflow_cumule_positif": 0.49},
        targets,
    )

    assert accepted.meets_targets is True
    assert weak_p10.reasons == ("tri_p10_insuffisant",)
    assert weak_probability.reasons == ("probabilite_cashflow_insuffisante",)


def test_qualification_explique_les_metriques_absentes() -> None:
    evaluation = evaluate_monte_carlo_summary({}, ProfitabilityTargets())

    assert evaluation.meets_targets is False
    assert "metrique_absente:tri_median" in evaluation.reasons
    assert "metrique_absente:probabilite_cashflow_cumule_positif" in evaluation.reasons
