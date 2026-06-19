from pathlib import Path

from achat_immo.sourcing_agents.content_guard import ContentAccessDecision, SourcingAccessBlockedError
from achat_immo.sourcing_queue_actions import process_sourcing_queue_item
from achat_immo.storage import (
    AnnonceRecord,
    HypothesesAchatRecord,
    enqueue_sourcing_url,
    get_sourcing_queue_item,
    open_database,
    save_annonce,
)


def test_process_sourcing_queue_item_sauvegarde_un_succes(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(ville="Grenoble", surface_m2=42, prix_affiche=110_000),
        HypothesesAchatRecord(loyer_hc_mensuel=700),
    )
    queue_id = enqueue_sourcing_url(conn, "https://example.test/ok")
    item = get_sourcing_queue_item(conn, queue_id)
    assert item is not None

    class FakeOrchestrator:
        def process_url(self, conn, url: str) -> int:
            return annonce_id

    result = process_sourcing_queue_item(conn, item, FakeOrchestrator())
    updated = get_sourcing_queue_item(conn, queue_id)

    assert result.status == "done"
    assert result.annonce_id == annonce_id
    assert result.attempted_processing
    assert updated is not None
    assert updated["status"] == "done"
    assert updated["annonce_id"] == annonce_id


def test_process_sourcing_queue_item_ignore_par_prefiltre(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    queue_id = enqueue_sourcing_url(conn, "https://example.test/login")
    item = get_sourcing_queue_item(conn, queue_id)
    assert item is not None

    class FakeOrchestrator:
        def process_url(self, conn, url: str) -> int:
            raise AssertionError("ne doit pas etre appele")

    result = process_sourcing_queue_item(conn, item, FakeOrchestrator())
    updated = get_sourcing_queue_item(conn, queue_id)

    assert result.status == "skipped"
    assert not result.attempted_processing
    assert updated is not None
    assert updated["status"] == "skipped"
    assert "login" in updated["last_error"]


def test_process_sourcing_queue_item_marque_un_blocage_source(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    queue_id = enqueue_sourcing_url(conn, "https://example.test/annonce")
    item = get_sourcing_queue_item(conn, queue_id)
    assert item is not None

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

    result = process_sourcing_queue_item(conn, item, FakeOrchestrator())
    updated = get_sourcing_queue_item(conn, queue_id)

    assert result.status == "blocked"
    assert result.attempted_processing
    assert updated is not None
    assert updated["status"] == "blocked"
    assert updated["last_error"] == "Blocage anti-bot detecte: cloudflare."
