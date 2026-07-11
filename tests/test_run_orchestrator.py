from pathlib import Path

from achat_immo.investment_profile import InvestmentProfile
from achat_immo.sourcing_agents.models import CandidateProperty
from achat_immo.sourcing_agents.orchestrator import SourcingOrchestrator
from achat_immo.sourcing_agents.content_guard import ContentAccessDecision, SourcingAccessBlockedError
from achat_immo.sourcing_agents.rate_limit import SourcingRateLimitedError
from achat_immo.storage import (
    AnnonceRecord,
    HypothesesAchatRecord,
    enqueue_sourcing_url,
    list_sourcing_queue,
    list_sourcing_runs,
    list_analysis_runs,
    list_qualification_runs,
    open_database,
    save_annonce,
)
from achat_immo.viability.query import FastQualification
from scripts.run_orchestrator import process_pending_queue, read_url_file


def test_read_url_file_ignore_vides_et_commentaires(tmp_path: Path) -> None:
    path = tmp_path / "urls.txt"
    path.write_text(
        "\n# commentaire\nhttps://example.test/a\n  https://example.test/b  \n",
        encoding="utf-8",
    )

    assert read_url_file(path) == ["https://example.test/a", "https://example.test/b"]


def test_prefiltre_sauvegarde_sans_lancer_analyse_approfondie(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    orchestrator = SourcingOrchestrator.__new__(SourcingOrchestrator)
    orchestrator.profile = InvestmentProfile()
    candidate = CandidateProperty(
        source="test",
        url="https://example.test/bien",
        ville="Grenoble",
        quartier="Centre",
        prix=100_000,
        surface=35,
        charges_mensuelles=None,
        taxe_fonciere=None,
        dpe="D",
        etage=None,
        ascenseur=None,
        loyer_estime=None,
        confiance_loyer="basse",
        travaux_visibles=None,
        red_flags=[],
        donnees_manquantes=["loyer", "charges", "taxe fonciere"],
    )
    qualification = FastQualification(
        qualification="a_enrichir",
        viable_neighbor_ratio=0.4,
        distance_to_viable=0.1,
        estimated_max_price=95_000,
        missing_fields=("loyer", "charges"),
        reasons=("donnees_manquantes",),
    )

    annonce_id = orchestrator._save_prefiltered_candidate(
        conn=conn,
        candidate=candidate,
        existing_annonce_id=None,
        source_url=candidate.url,
        final_url=candidate.url,
        text="annonce test",
        extraction_warning="",
        map_id=None,
        fast_qualification=qualification,
    )

    assert list_analysis_runs(conn, annonce_id) == []
    runs = list_qualification_runs(conn, annonce_id)
    assert runs[0]["qualification"] == "a_enrichir"
    assert runs[0]["estimated_max_price"] == 95_000


def test_process_pending_queue_met_a_jour_les_statuts(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(ville="Grenoble", surface_m2=42, prix_affiche=110_000),
        HypothesesAchatRecord(loyer_hc_mensuel=700),
    )
    enqueue_sourcing_url(conn, "https://example.test/ok")
    enqueue_sourcing_url(conn, "https://example.test/fail")

    class FakeOrchestrator:
        def process_url(self, conn, url: str) -> int:
            if url.endswith("/fail"):
                raise RuntimeError("boom")
            return annonce_id

    successes, failures, skipped, blocked = process_pending_queue(conn, FakeOrchestrator(), limit=10)
    rows = list_sourcing_queue(conn)
    by_url = {row["source_url"]: row for row in rows}

    assert (successes, failures, skipped, blocked) == (1, 1, 0, 0)
    assert by_url["https://example.test/ok"]["status"] == "done"
    assert by_url["https://example.test/ok"]["annonce_id"] == annonce_id
    assert by_url["https://example.test/fail"]["status"] == "failed"
    assert by_url["https://example.test/fail"]["last_error"] == "boom"
    run = list_sourcing_runs(conn)[0]
    assert run["status"] == "completed_with_errors"
    assert run["examined_count"] == 2
    assert run["processed_count"] == 2
    assert run["successes"] == 1
    assert run["failures"] == 1


def test_process_pending_queue_ignore_les_urls_rejetees_par_prefiltre(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    enqueue_sourcing_url(conn, "https://example.test/login")

    class FakeOrchestrator:
        calls: list[str] = []

        def process_url(self, conn, url: str) -> int:
            self.calls.append(url)
            return 1

    orchestrator = FakeOrchestrator()
    successes, failures, skipped, blocked = process_pending_queue(conn, orchestrator, limit=10)
    rows = list_sourcing_queue(conn)

    assert (successes, failures, skipped, blocked) == (0, 0, 1, 0)
    assert orchestrator.calls == []
    assert rows[0]["status"] == "skipped"
    assert "login" in rows[0]["last_error"]
    run = list_sourcing_runs(conn)[0]
    assert run["status"] == "completed_with_warnings"
    assert run["examined_count"] == 1
    assert run["processed_count"] == 0
    assert run["skipped"] == 1


def test_process_pending_queue_marque_les_blocages_source(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    enqueue_sourcing_url(conn, "https://example.test/annonce")

    class FakeOrchestrator:
        def process_url(self, conn, url: str) -> int:
            raise SourcingAccessBlockedError(
                ContentAccessDecision(
                    accepted=False,
                    status="blocked_antibot",
                    reason="Blocage anti-bot detecte: cloudflare.",
                    matches=("cloudflare",),
                )
            )

    successes, failures, skipped, blocked = process_pending_queue(conn, FakeOrchestrator(), limit=10)
    rows = list_sourcing_queue(conn)

    assert (successes, failures, skipped, blocked) == (0, 0, 0, 1)
    assert rows[0]["status"] == "blocked"
    assert rows[0]["last_error"] == "Blocage anti-bot detecte: cloudflare."
    run = list_sourcing_runs(conn)[0]
    assert run["status"] == "completed_with_warnings"
    assert run["blocked"] == 1


def test_process_pending_queue_respecte_un_quota_par_source(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(ville="Grenoble", surface_m2=42, prix_affiche=110_000),
        HypothesesAchatRecord(loyer_hc_mensuel=700),
    )
    enqueue_sourcing_url(conn, "https://example.test/a", source="jinka")
    enqueue_sourcing_url(conn, "https://example.test/b", source="jinka")

    class FakeOrchestrator:
        calls: list[str] = []

        def process_url(self, conn, url: str) -> int:
            self.calls.append(url)
            return annonce_id

    orchestrator = FakeOrchestrator()
    result = process_pending_queue(conn, orchestrator, limit=10, max_per_source=1)
    rows = list_sourcing_queue(conn)

    assert result == (1, 0, 0, 0)
    assert orchestrator.calls == ["https://example.test/a"]
    assert [row["status"] for row in rows] == ["done", "pending"]
    run = list_sourcing_runs(conn)[0]
    assert run["status"] == "completed"
    assert run["examined_count"] == 2
    assert run["processed_count"] == 1
    assert run["pending_after"] == 1


def test_process_pending_queue_s_arrete_sur_quota_temporaire(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    enqueue_sourcing_url(conn, "https://example.test/quota")
    enqueue_sourcing_url(conn, "https://example.test/apres")

    class FakeOrchestrator:
        calls: list[str] = []

        def process_url(self, conn, url: str) -> int:
            self.calls.append(url)
            raise SourcingRateLimitedError("Quota Gemini temporairement atteint.", retry_after_seconds=60)

    orchestrator = FakeOrchestrator()
    result = process_pending_queue(conn, orchestrator, limit=10)
    rows = list_sourcing_queue(conn)
    run = list_sourcing_runs(conn)[0]

    assert result == (0, 0, 0, 0)
    assert orchestrator.calls == ["https://example.test/quota"]
    assert [row["status"] for row in rows] == ["pending", "pending"]
    assert "Quota Gemini" in rows[0]["last_error"]
    assert rows[1]["last_error"] == ""
    assert run["status"] == "rate_limited"
    assert run["processed_count"] == 1
    assert run["pending_after"] == 2
