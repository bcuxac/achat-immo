from achat_immo.decision_cockpit import build_cockpit_snapshot


def test_cockpit_snapshot_classe_les_annonces_dans_le_funnel() -> None:
    annonces = [
        {
            "id": 1,
            "ville": "Grenoble",
            "quartier": "Championnet",
            "statut": "favori",
            "prix_affiche": 120_000,
            "prix_cible_recommande": 105_000,
            "tri_p50": 7.2,
            "cashflow_p50": 80.0,
            "coc_p50": 4.0,
            "dpe": "D",
            "loyer_hc_mensuel": 720,
            "taxe_fonciere": 850,
        },
        {
            "id": 2,
            "ville": "Lyon",
            "quartier": "",
            "statut": "hors_criteres",
            "prix_affiche": 180_000,
            "tri_p50": 3.0,
            "cashflow_p50": -150.0,
            "coc_p50": -2.0,
            "dpe": "E",
            "loyer_hc_mensuel": 800,
            "taxe_fonciere": 1_100,
        },
        {
            "id": 3,
            "ville": "Nimes",
            "quartier": "",
            "statut": "a_analyser",
            "prix_affiche": 90_000,
            "tri_p50": None,
            "cashflow_p50": None,
            "coc_p50": None,
            "dpe": "",
            "loyer_hc_mensuel": 0,
            "taxe_fonciere": 0,
        },
    ]
    extraction_runs = [
        {"annonce_id": 3, "missing_fields": "Charges copro, Taxe fonciere", "red_flags": "DPE absent"}
    ]
    analysis_runs = [{"annonce_id": 2, "status": "hors_criteres", "solver_status": "no_solution"}]
    sourcing_queue = [
        {"annonce_id": 4, "status": "blocked", "last_error": "Blocage anti-bot detecte: cloudflare."},
        {"annonce_id": None, "status": "pending", "last_error": ""},
    ]
    sourcing_runs = [{"id": 12, "status": "completed_with_warnings"}]

    snapshot = build_cockpit_snapshot(annonces, extraction_runs, analysis_runs, sourcing_queue, sourcing_runs)

    assert snapshot.funnel_counts["shortlist"] == 1
    assert snapshot.funnel_counts["hors_criteres"] == 1
    assert snapshot.funnel_counts["donnees_insuffisantes"] == 1
    assert snapshot.queue_counts == {"blocked": 1, "pending": 1}
    assert snapshot.latest_sourcing_run == {"id": 12, "status": "completed_with_warnings"}
    assert snapshot.priority_items[0]["id"] == 1
    assert snapshot.priority_items[0]["stage"] == "shortlist"
    assert snapshot.priority_items[1]["id"] == 3
    assert snapshot.priority_items[1]["stage"] == "donnees_insuffisantes"
    assert "DPE" in snapshot.priority_items[1]["donnees_manquantes"]


def test_cockpit_snapshot_marque_une_annonce_liee_a_une_queue_bloquee() -> None:
    snapshot = build_cockpit_snapshot(
        annonces=[
            {
                "id": 5,
                "ville": "Grenoble",
                "quartier": "",
                "statut": "a_analyser",
                "prix_affiche": 110_000,
                "dpe": "D",
                "loyer_hc_mensuel": 700,
                "taxe_fonciere": 900,
            }
        ],
        extraction_runs=[],
        analysis_runs=[],
        sourcing_queue=[
            {"annonce_id": 5, "status": "blocked", "last_error": "Mur de consentement detecte."}
        ],
        sourcing_runs=[],
    )

    assert snapshot.funnel_counts["extraction_bloquee"] == 1
    assert snapshot.priority_items[0]["stage"] == "extraction_bloquee"
    assert snapshot.priority_items[0]["signal"] == "Mur de consentement detecte."
