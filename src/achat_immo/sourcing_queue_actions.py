"""Actions partagees pour piloter la queue de sourcing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Any

from achat_immo.sourcing_agents.content_guard import SourcingAccessBlockedError
from achat_immo.sourcing_agents.prefilter import UrlPrefilterPolicy, prefilter_url
from achat_immo.storage import (
    DatabaseConnection,
    mark_sourcing_url_blocked,
    mark_sourcing_url_failure,
    mark_sourcing_url_processing,
    mark_sourcing_url_skipped,
    mark_sourcing_url_success,
)


class QueueOrchestrator(Protocol):
    def process_url(self, conn: DatabaseConnection, url: str) -> int:
        ...


@dataclass(frozen=True, slots=True)
class QueueProcessResult:
    queue_id: int
    source_url: str
    status: str
    annonce_id: int | None = None
    message: str = ""
    attempted_processing: bool = False


def process_sourcing_queue_item(
    conn: DatabaseConnection,
    item: dict[str, Any],
    orchestrator: QueueOrchestrator,
    *,
    prefilter_policy: UrlPrefilterPolicy | None = None,
    skip_prefilter: bool = False,
) -> QueueProcessResult:
    queue_id = int(item["id"])
    url = str(item["source_url"])
    policy = prefilter_policy or UrlPrefilterPolicy()
    if not skip_prefilter:
        decision = prefilter_url(url, policy)
        if not decision.accepted:
            mark_sourcing_url_skipped(conn, queue_id, decision.reason)
            return QueueProcessResult(queue_id, url, "skipped", message=decision.reason)

    mark_sourcing_url_processing(conn, queue_id)
    try:
        annonce_id = orchestrator.process_url(conn, url)
    except SourcingAccessBlockedError as exc:
        mark_sourcing_url_blocked(conn, queue_id, exc.decision.reason)
        return QueueProcessResult(
            queue_id,
            url,
            "blocked",
            message=exc.decision.reason,
            attempted_processing=True,
        )
    except Exception as exc:
        message = str(exc)
        mark_sourcing_url_failure(conn, queue_id, message)
        return QueueProcessResult(queue_id, url, "failed", message=message, attempted_processing=True)

    mark_sourcing_url_success(conn, queue_id, annonce_id)
    return QueueProcessResult(queue_id, url, "done", annonce_id=annonce_id, attempted_processing=True)
