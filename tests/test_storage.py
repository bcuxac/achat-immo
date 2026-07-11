from pathlib import Path

import psycopg

from achat_immo.grids import GrilleParametres, simuler_grille_annonce
from achat_immo.storage import (
    AnalysisRunRecord,
    AnnonceRecord,
    connect,
    DatabaseConnection,
    ExtractionRunRecord,
    HypothesesAchatRecord,
    SourcingRunRecord,
    complete_sourcing_run,
    count_sourcing_queue,
    create_sourcing_run,
    enqueue_jinka_alert,
    enqueue_sourcing_url,
    fiscalite_from_hypotheses,
    find_annonce_id_by_url,
    get_jinka_alert,
    get_sourcing_queue_item,
    get_annonce_bundle,
    is_postgres_target,
    list_analysis_runs,
    get_simulation_results,
    list_extraction_runs,
    list_annonces,
    list_pending_sourcing_urls,
    list_simulation_runs,
    list_sourcing_queue,
    list_sourcing_runs,
    list_jinka_alerts,
    list_pending_jinka_alerts,
    mark_jinka_alert_blocked,
    mark_jinka_alert_failure,
    mark_jinka_alert_processing,
    mark_jinka_alert_success,
    mark_sourcing_url_blocked,
    mark_sourcing_url_failure,
    mark_sourcing_url_pending,
    mark_sourcing_url_processing,
    mark_sourcing_url_skipped,
    mark_sourcing_url_success,
    normalize_source_url,
    open_database,
    save_analysis_run,
    save_annonce,
    save_extraction_run,
    save_simulation_run,
    to_domain_models,
    update_sourcing_queue_item,
)
from achat_immo.models import EpoqueConstruction, ModeLocation, RegimeFiscal


def test_detecte_les_urls_postgresql() -> None:
    assert is_postgres_target("postgresql://user:password@example.test/db")
    assert is_postgres_target("postgres://user:password@example.test/db")
    assert not is_postgres_target(Path("data/achat.sqlite"))


def test_facade_postgresql_convertit_les_placeholders_executemany() -> None:
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def executemany(self, sql, params):
            calls.append((sql, list(params)))

    class FakeRaw:
        def cursor(self):
            return FakeCursor()

    conn = DatabaseConnection(FakeRaw(), "postgres")

    conn.executemany("INSERT INTO table_test (a, b) VALUES (?, ?)", [(1, 2)])

    assert calls == [("INSERT INTO table_test (a, b) VALUES (%s, %s)", [(1, 2)])]


def test_facade_postgresql_reconnecte_apres_erreur_operationnelle() -> None:
    calls = []

    class DeadRaw:
        def execute(self, sql, params):
            calls.append(("dead", sql, params))
            raise psycopg.OperationalError("connexion fermee")

        def close(self):
            calls.append(("closed",))

    class HealthyRaw:
        def execute(self, sql, params):
            calls.append(("healthy", sql, params))
            return "ok"

    conn = DatabaseConnection(DeadRaw(), "postgres", dsn="postgresql://example")

    def reconnect():
        conn.raw = HealthyRaw()

    conn._reconnect = reconnect

    result = conn.execute("SELECT * FROM annonces WHERE id = ?", (1,))

    assert result == "ok"
    assert calls == [
        ("dead", "SELECT * FROM annonces WHERE id = %s", (1,)),
        ("healthy", "SELECT * FROM annonces WHERE id = %s", (1,)),
    ]


def test_connexion_postgresql_desactive_les_prepared_statements(monkeypatch) -> None:
    calls = []

    class FakeRaw:
        def close(self):
            calls.append(("closed",))

    def fake_connect(dsn, **kwargs):
        calls.append(("connect", dsn, kwargs))
        return FakeRaw()

    monkeypatch.setattr(psycopg, "connect", fake_connect)

    conn = connect("postgresql://example.test/db")
    conn._reconnect()

    connect_calls = [call for call in calls if call[0] == "connect"]
    assert len(connect_calls) == 2
    for _, dsn, kwargs in connect_calls:
        assert dsn == "postgresql://example.test/db"
        assert kwargs["autocommit"] is True
        assert kwargs["prepare_threshold"] is None
        assert kwargs["row_factory"] is not None


def test_sqlite_annonce_hypotheses_et_conversion(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(
            ville="Grenoble",
            quartier="Championnet",
            adresse="Rue test",
            surface_m2=42,
            prix_affiche=110_000,
            nb_pieces=2,
            epoque_construction=EpoqueConstruction.APRES_1990,
            secteur_encadrement="zone_1",
            dpe="D",
            url="https://example.test/annonce",
        ),
        HypothesesAchatRecord(
            frais_notaire_estimes=8_800,
            travaux_estimes=5_000,
            meubles_estimes=4_000,
            loyer_hc_mensuel=700,
            mode_location=ModeLocation.NUE,
            cfe_annuelle=320,
            regime_fiscal=RegimeFiscal.LOCATION_NUE_REEL,
            tmi_pct=41,
            prelevements_sociaux_pct=17.2,
            part_terrain_pct=12,
            duree_amortissement_bien_annees=35,
            taxe_fonciere=900,
            charges_copro_annuelles=1_200,
            charges_recuperables_annuelles=500,
        ),
    )

    annonces = list_annonces(conn)
    annonce, hypotheses = get_annonce_bundle(conn, annonce_id)
    bien, location, financement = to_domain_models(annonce, hypotheses)
    fiscalite = fiscalite_from_hypotheses(hypotheses)

    assert annonces[0]["ville"] == "Grenoble"
    assert bien.adresse_approx == "Rue test"
    assert bien.nb_pieces == 2
    assert bien.epoque_construction == EpoqueConstruction.APRES_1990
    assert bien.secteur_encadrement == "zone_1"
    assert bien.cout_total_projet == 127_800
    assert location.loyer_hc_mensuel == 700
    assert location.mode_location == ModeLocation.NUE
    assert location.cfe_annuelle == 320
    assert financement.apport == 15_000
    assert fiscalite.regime == RegimeFiscal.LOCATION_NUE_REEL
    assert fiscalite.tmi_pct == 41
    assert fiscalite.part_terrain_pct == 12
    assert fiscalite.duree_amortissement_bien_annees == 35


def test_sqlite_sauvegarde_run_de_simulation(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(ville="Nimes", surface_m2=40, prix_affiche=90_000),
        HypothesesAchatRecord(loyer_hc_mensuel=620, taxe_fonciere=850),
    )
    annonce, hypotheses = get_annonce_bundle(conn, annonce_id)
    bien, location, _ = to_domain_models(annonce, hypotheses)
    resultats = simuler_grille_annonce(
        bien,
        location,
        parametres=GrilleParametres(
            taux_credit=(3.6,),
            durees_annees=(20,),
            apports=(15_000,),
            vacances_mois=(1.0,),
            gestions_agence=(False,),
            frais_gestion_pct=(7.0,),
            horizon_annees=5,
        ),
    )

    run_id = save_simulation_run(
        conn,
        annonce_id=annonce_id,
        resultats=[resultat.to_dict() for resultat in resultats],
        commentaire="scenario initial",
    )

    runs = list_simulation_runs(conn, annonce_id)
    rows = get_simulation_results(conn, run_id)

    assert runs[0]["nb_resultats"] == 2
    assert runs[0]["commentaire"] == "scenario initial"
    assert rows[0]["prix_achat"] == 90_000
    assert rows[0]["cout_total_projet"] == 90_000
    assert rows[0]["loyer_hc_mensuel"] == 620
    assert rows[0]["montant_emprunte"] > 0
    assert rows[0]["frais_gestion_pct"] == 0.0
    assert rows[0]["mode_location"] == "meublee"
    assert rows[0]["regime_fiscal"] in {"lmnp_reel", "micro_bic"}
    assert "patrimoine_net_sortie" in rows[0]
    assert rows[0]["decision"] in {"interessant", "a_creuser", "a_rejeter"}
    assert "ecart_vs_alternative" not in rows[0]


def test_sqlite_stocke_plusieurs_annonces_distinctes(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    first_id = save_annonce(
        conn,
        AnnonceRecord(ville="Grenoble", surface_m2=42, prix_affiche=110_000),
        HypothesesAchatRecord(loyer_hc_mensuel=700),
    )
    second_id = save_annonce(
        conn,
        AnnonceRecord(ville="Nimes", surface_m2=38, prix_affiche=90_000),
        HypothesesAchatRecord(loyer_hc_mensuel=620),
    )

    annonces = list_annonces(conn)

    assert {first_id, second_id} == {row["id"] for row in annonces}
    assert [row["ville"] for row in annonces] == ["Nimes", "Grenoble"]


def test_sqlite_sauvegarde_runs_extraction_et_analyse(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(ville="Grenoble", surface_m2=42, prix_affiche=110_000),
        HypothesesAchatRecord(loyer_hc_mensuel=700),
    )

    extraction_id = save_extraction_run(
        conn,
        ExtractionRunRecord(
            annonce_id=annonce_id,
            source_url="https://jinka.example/annonce",
            final_url="https://agency.example/annonce",
            status="success",
            model="gemini-2.5-flash",
            input_chars=12_345,
            raw_content_hash="abc123",
            extracted_source="Agence",
            red_flags="DPE F",
            missing_fields="Taxe fonciere",
        ),
    )
    analysis_id = save_analysis_run(
        conn,
        AnalysisRunRecord(
            annonce_id=annonce_id,
            status="hors_criteres",
            scenario_seed=123,
            nb_scenarios=1000,
            solver_status="solved",
            solver_iterations=8,
            price_floor=44_000,
            price_ceiling=110_000,
            target_tri_median=6.0,
            target_tri_p10=3.0,
            target_coc=0.0,
            target_cashflow=0.0,
            tri_p50=5.2,
            tri_p10=2.1,
            probabilite_cashflow_positif=0.42,
            coc_p50=-1.4,
            cashflow_p50=-80.0,
            recommended_price=88_000,
            recommended_project_cost=100_000,
            recommended_apport=10_000,
            recommended_loan_amount=90_000,
            summary_json='{"tri_median": 5.2}',
            diagnostics="Prix cible obtenu par dichotomie.",
        ),
    )

    extraction_runs = list_extraction_runs(conn, annonce_id)
    analysis_runs = list_analysis_runs(conn, annonce_id)

    assert extraction_runs[0]["id"] == extraction_id
    assert extraction_runs[0]["final_url"] == "https://agency.example/annonce"
    assert extraction_runs[0]["input_chars"] == 12_345
    assert analysis_runs[0]["id"] == analysis_id
    assert analysis_runs[0]["solver_status"] == "solved"
    assert analysis_runs[0]["recommended_price"] == 88_000
    assert analysis_runs[0]["recommended_apport"] == 10_000
    assert analysis_runs[0]["recommended_loan_amount"] == 90_000


def test_sourcing_queue_dedoublonne_et_transitionne(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(ville="Grenoble", surface_m2=42, prix_affiche=110_000, url="https://example.test/a"),
        HypothesesAchatRecord(loyer_hc_mensuel=700),
    )

    first_id = enqueue_sourcing_url(conn, " HTTPS://Example.test/a/#tracking ", source="jinka", priority=1)
    second_id = enqueue_sourcing_url(conn, "https://example.test/a", source="manual", priority=5)
    pending = list_pending_sourcing_urls(conn)

    assert first_id == second_id
    assert normalize_source_url("HTTPS://Example.test/a/#tracking") == "https://example.test/a"
    assert (
        normalize_source_url(
            "https://jinka.fr/ad/53fb9eba?alert_id=secret&utm_source=jinka_app#from-share"
        )
        == "https://www.jinka.fr/ad/53fb9eba"
    )
    assert pending[0]["source_url"] == "https://example.test/a"
    assert pending[0]["priority"] == 5
    assert find_annonce_id_by_url(conn, "https://example.test/a/") == annonce_id

    mark_sourcing_url_processing(conn, first_id)
    processing = list_sourcing_queue(conn, status="processing")
    assert processing[0]["attempts"] == 1

    mark_sourcing_url_success(conn, first_id, annonce_id)
    done = list_sourcing_queue(conn, status="done")
    assert done[0]["annonce_id"] == annonce_id
    assert not list_pending_sourcing_urls(conn)

    failed_id = enqueue_sourcing_url(conn, "https://example.test/fail")
    mark_sourcing_url_processing(conn, failed_id)
    mark_sourcing_url_failure(conn, failed_id, "timeout")
    failed = list_sourcing_queue(conn, status="failed")
    assert failed[0]["last_error"] == "timeout"

    requeued_id = enqueue_sourcing_url(conn, "https://example.test/fail")
    assert requeued_id == failed_id
    assert list_sourcing_queue(conn, status="pending")[0]["last_error"] == ""

    skipped_id = enqueue_sourcing_url(conn, "https://example.test/login")
    mark_sourcing_url_skipped(conn, skipped_id, "Chemin utilisateur ignore: login.")
    skipped = list_sourcing_queue(conn, status="skipped")
    assert skipped[0]["last_error"] == "Chemin utilisateur ignore: login."

    requeued_skipped_id = enqueue_sourcing_url(conn, "https://example.test/login")
    assert requeued_skipped_id == skipped_id
    requeued_skipped = list_sourcing_queue(conn, status="pending")
    assert any(row["source_url"] == "https://example.test/login" for row in requeued_skipped)

    blocked_id = enqueue_sourcing_url(conn, "https://example.test/blocked")
    mark_sourcing_url_blocked(conn, blocked_id, "Blocage anti-bot detecte: cloudflare.")
    blocked = list_sourcing_queue(conn, status="blocked")
    assert blocked[0]["last_error"] == "Blocage anti-bot detecte: cloudflare."

    requeued_blocked_id = enqueue_sourcing_url(conn, "https://example.test/blocked")
    assert requeued_blocked_id == blocked_id
    requeued_blocked = list_sourcing_queue(conn, status="pending")
    assert any(row["source_url"] == "https://example.test/blocked" for row in requeued_blocked)

    update_sourcing_queue_item(conn, blocked_id, source="alerte_mail", priority=9)
    updated = get_sourcing_queue_item(conn, blocked_id)
    assert updated is not None
    assert updated["source"] == "alerte_mail"
    assert updated["priority"] == 9

    mark_sourcing_url_failure(conn, blocked_id, "erreur temporaire")
    mark_sourcing_url_pending(conn, blocked_id)
    pending_item = get_sourcing_queue_item(conn, blocked_id)
    assert pending_item is not None
    assert pending_item["status"] == "pending"
    assert pending_item["last_error"] == ""


def test_jinka_alerts_dedoublonnent_et_repassent_pending_sur_notification_recente(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    alert_id = "9aa8e8eab78a4e21034e334d90719be0"

    first_id = enqueue_jinka_alert(
        conn,
        alert_id,
        source_url=f"https://www.jinka.fr/alerts?alert_id={alert_id}",
        observed_at="2026-07-10T03:13:11+00:00",
        notification_count=4,
    )
    second_id = enqueue_jinka_alert(
        conn,
        alert_id,
        observed_at="2026-07-10T03:13:11+00:00",
        notification_count=4,
    )

    assert first_id == second_id
    assert list_pending_jinka_alerts(conn)[0]["alert_id"] == alert_id

    mark_jinka_alert_processing(conn, first_id)
    processing = list_jinka_alerts(conn, status="processing")
    assert processing[0]["attempts"] == 1

    mark_jinka_alert_success(conn, first_id, discovered_ads_count=4)
    assert not list_pending_jinka_alerts(conn)

    enqueue_jinka_alert(
        conn,
        alert_id,
        observed_at="2026-07-10T03:13:11+00:00",
        notification_count=4,
    )
    assert get_jinka_alert(conn, first_id)["status"] == "done"

    enqueue_jinka_alert(
        conn,
        alert_id,
        observed_at="2026-07-11T03:13:11+00:00",
        notification_count=2,
    )
    refreshed = get_jinka_alert(conn, first_id)
    assert refreshed is not None
    assert refreshed["status"] == "pending"
    assert refreshed["last_notification_count"] == 2

    mark_jinka_alert_failure(conn, first_id, "timeout")
    enqueue_jinka_alert(conn, alert_id, observed_at="2026-07-11T03:13:11+00:00")
    assert get_jinka_alert(conn, first_id)["status"] == "pending"

    mark_jinka_alert_blocked(conn, first_id, "session expiree")
    blocked = list_jinka_alerts(conn, status="blocked")
    assert blocked[0]["last_error"] == "session expiree"


def test_sqlite_sauvegarde_les_runs_de_sourcing(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    enqueue_sourcing_url(conn, "https://example.test/a")
    enqueue_sourcing_url(conn, "https://example.test/b")

    run_id = create_sourcing_run(
        conn,
        SourcingRunRecord(
            url_limit=20,
            source_limit=2,
            allowed_domains="example.test",
            pending_at_start=count_sourcing_queue(conn, status="pending"),
        ),
    )
    complete_sourcing_run(
        conn,
        run_id,
        status="completed_with_warnings",
        examined_count=2,
        processed_count=1,
        successes=1,
        failures=0,
        skipped=1,
        blocked=0,
        pending_after=1,
    )

    runs = list_sourcing_runs(conn)

    assert runs[0]["id"] == run_id
    assert runs[0]["status"] == "completed_with_warnings"
    assert runs[0]["url_limit"] == 20
    assert runs[0]["source_limit"] == 2
    assert runs[0]["allowed_domains"] == "example.test"
    assert runs[0]["pending_at_start"] == 2
    assert runs[0]["processed_count"] == 1
    assert runs[0]["skipped"] == 1
    assert runs[0]["pending_after"] == 1
