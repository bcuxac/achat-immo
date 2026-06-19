from achat_immo.analysis.run_deltas import compare_latest_analysis_runs


def test_compare_latest_analysis_runs_retourne_none_si_un_seul_run() -> None:
    assert compare_latest_analysis_runs([{"id": 1, "tri_p50": 6.0}]) is None


def test_compare_latest_analysis_runs_calcule_les_deltas_numeriques_et_statuts() -> None:
    snapshot = compare_latest_analysis_runs(
        [
            {
                "id": 2,
                "status": "a_verifier",
                "solver_status": "solved",
                "tri_p50": 7.0,
                "tri_p10": 3.2,
                "probabilite_cashflow_positif": 0.62,
                "coc_p50": 2.0,
                "cashflow_p50": 80.0,
                "recommended_price": 100_000,
            },
            {
                "id": 1,
                "status": "hors_criteres",
                "solver_status": "no_solution",
                "tri_p50": 6.0,
                "tri_p10": 3.5,
                "probabilite_cashflow_positif": 0.50,
                "coc_p50": 2.0,
                "cashflow_p50": 40.0,
                "recommended_price": 95_000,
            },
        ]
    )

    assert snapshot is not None
    assert snapshot["latest_run_id"] == 2
    assert snapshot["previous_run_id"] == 1
    by_label = {row["champ"]: row for row in snapshot["numeric_deltas"]}
    assert by_label["TRI median"]["delta"] == 1.0
    assert by_label["TRI median"]["impact"] == "amelioration"
    assert by_label["TRI P10"]["delta"] == -0.3
    assert by_label["TRI P10"]["impact"] == "degradation"
    assert by_label["Cash-on-Cash median"]["impact"] == "stable"
    assert by_label["Prix recommande"]["impact"] == "info"
    assert snapshot["status_changes"] == [
        {"champ": "Statut analyse", "precedent": "hors_criteres", "nouveau": "a_verifier"},
        {"champ": "Statut solveur", "precedent": "no_solution", "nouveau": "solved"},
    ]
