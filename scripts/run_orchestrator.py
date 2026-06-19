#!/usr/bin/env python3
"""Script CLI pour executer l'orchestrateur de sourcing."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

from achat_immo.sourcing_agents.orchestrator import SourcingOrchestrator
from achat_immo.sourcing_agents.prefilter import UrlPrefilterPolicy
from achat_immo.sourcing_queue_actions import process_sourcing_queue_item
from achat_immo.storage import (
    DatabaseConnection,
    SourcingRunRecord,
    complete_sourcing_run,
    count_sourcing_queue,
    create_sourcing_run,
    enqueue_sourcing_url,
    list_pending_sourcing_urls,
    open_database,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def read_url_file(path: Path) -> list[str]:
    """Lit un fichier d'URLs, en ignorant lignes vides et commentaires."""

    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            urls.append(value)
    return urls


def process_pending_queue(
    conn: DatabaseConnection,
    orchestrator: SourcingOrchestrator,
    *,
    limit: int,
    prefilter_policy: UrlPrefilterPolicy | None = None,
    skip_prefilter: bool = False,
    max_per_source: int | None = None,
) -> tuple[int, int, int, int]:
    """Traite les URLs en attente. Retourne (succes, echecs, ignores, bloques)."""

    successes = 0
    failures = 0
    skipped = 0
    blocked = 0
    policy = prefilter_policy or UrlPrefilterPolicy()
    pending_items = list_pending_sourcing_urls(conn, limit=limit)
    run_id = create_sourcing_run(
        conn,
        SourcingRunRecord(
            url_limit=limit,
            source_limit=max_per_source,
            allowed_domains=", ".join(policy.normalized_allowed_domains()),
            skip_prefilter=skip_prefilter,
            pending_at_start=len(pending_items),
        ),
    )
    logger.info("Run de sourcing #%s demarre (%s URLs examinees au maximum).", run_id, len(pending_items))

    try:
        processed_by_source: dict[str, int] = {}
        for item in pending_items:
            queue_id = int(item["id"])
            url = str(item["source_url"])
            source = str(item["source"])
            logger.info("Traitement queue #%s : %s", queue_id, url)

            if max_per_source is not None and processed_by_source.get(source, 0) >= max_per_source:
                logger.info("Quota source atteint pour %s ; URL conservee en attente: %s", source, url)
                continue

            result = process_sourcing_queue_item(
                conn,
                item,
                orchestrator,
                prefilter_policy=policy,
                skip_prefilter=skip_prefilter,
            )
            if result.attempted_processing:
                processed_by_source[source] = processed_by_source.get(source, 0) + 1
            if result.status == "skipped":
                skipped += 1
                logger.info("URL ignoree par prefiltre #%s : %s", queue_id, result.message)
            elif result.status == "blocked":
                blocked += 1
                logger.warning("Source bloquee pour %s : %s", url, result.message)
            elif result.status == "failed":
                failures += 1
                logger.error("Echec du traitement de %s : %s", url, result.message)
            elif result.status == "done":
                successes += 1
                logger.info("Annonce sauvegardee avec succes. ID: %s", result.annonce_id)
    except Exception as exc:
        complete_sourcing_run(
            conn,
            run_id,
            status="failed",
            examined_count=len(pending_items),
            processed_count=successes + failures + blocked,
            successes=successes,
            failures=failures,
            skipped=skipped,
            blocked=blocked,
            pending_after=count_sourcing_queue(conn, status="pending"),
            error_message=str(exc),
        )
        raise

    complete_sourcing_run(
        conn,
        run_id,
        status=_queue_run_status(failures=failures, skipped=skipped, blocked=blocked),
        examined_count=len(pending_items),
        processed_count=successes + failures + blocked,
        successes=successes,
        failures=failures,
        skipped=skipped,
        blocked=blocked,
        pending_after=count_sourcing_queue(conn, status="pending"),
    )
    logger.info("Run de sourcing #%s finalise.", run_id)
    return successes, failures, skipped, blocked


def _queue_run_status(*, failures: int, skipped: int, blocked: int) -> str:
    if failures:
        return "completed_with_errors"
    if skipped or blocked:
        return "completed_with_warnings"
    return "completed"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Orchestrateur de Sourcing Immobilier")
    parser.add_argument("url", nargs="?", help="URL d'annonce a analyser immediatement.")
    parser.add_argument("--url-file", type=Path, help="Fichier contenant une URL par ligne a ajouter a la file.")
    parser.add_argument("--process-queue", action="store_true", help="Traiter les URLs en attente dans la file.")
    parser.add_argument("--queue-only", action="store_true", help="Ajouter les URLs sans les traiter immediatement.")
    parser.add_argument("--limit", type=int, default=20, help="Nombre maximal d'URLs de la file a examiner.")
    parser.add_argument(
        "--source-limit",
        type=int,
        help="Nombre maximal d'URLs a charger par source pendant ce run.",
    )
    parser.add_argument("--source", default="manual", help="Nom de la source pour les URLs ajoutees.")
    parser.add_argument("--priority", type=int, default=0, help="Priorite des URLs ajoutees.")
    parser.add_argument(
        "--allowed-domain",
        action="append",
        default=[],
        help="Domaine autorise par le prefiltre. Peut etre repete. Par defaut, aucun filtrage domaine.",
    )
    parser.add_argument("--skip-prefilter", action="store_true", help="Desactive le prefiltre URL deterministe.")
    parser.add_argument("--tri", type=float, default=6.0, help="TRI median cible minimum (%%).")
    parser.add_argument("--tri-p10", type=float, default=3.0, help="TRI P10 cible minimum (%%).")
    parser.add_argument("--coc", type=float, default=0.0, help="Cash-on-Cash cible minimum (%%).")
    parser.add_argument("--cf", type=float, default=0.0, help="Cashflow mensuel cible minimum (EUR).")
    return parser


def build_orchestrator(args: argparse.Namespace) -> SourcingOrchestrator:
    logger.info(
        "Demarrage de l'orchestrateur. Cibles: TRI=%s%%, TRI_P10=%s%%, CoC=%s%%, CF=%s EUR",
        args.tri,
        args.tri_p10,
        args.coc,
        args.cf,
    )
    return SourcingOrchestrator(
        target_tri=args.tri,
        target_tri_p10=args.tri_p10,
        target_coc=args.coc,
        target_cf=args.cf,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.url and not args.url_file and not args.process_queue:
        parser.error("Fournis une URL, --url-file, ou --process-queue.")
    if args.source_limit is not None and args.source_limit < 1:
        parser.error("--source-limit doit etre superieur ou egal a 1.")

    load_dotenv()

    conn = open_database()
    try:
        if args.url and not args.url_file and not args.process_queue and not args.queue_only:
            orchestrator = build_orchestrator(args)
            annonce_id = orchestrator.process_url(conn, args.url)
            logger.info("Annonce sauvegardee avec succes. ID: %s", annonce_id)
            return

        urls = []
        if args.url:
            urls.append(args.url)
        if args.url_file:
            urls.extend(read_url_file(args.url_file))

        for url in urls:
            queue_id = enqueue_sourcing_url(conn, url, source=args.source, priority=args.priority)
            logger.info("URL en file #%s : %s", queue_id, url)

        if args.queue_only:
            return

        if urls or args.process_queue:
            prefilter_policy = UrlPrefilterPolicy(allowed_domains=tuple(args.allowed_domain))
            orchestrator = build_orchestrator(args)
            successes, failures, skipped, blocked = process_pending_queue(
                conn,
                orchestrator,
                limit=args.limit,
                prefilter_policy=prefilter_policy,
                skip_prefilter=args.skip_prefilter,
                max_per_source=args.source_limit,
            )
            logger.info(
                "Queue terminee : %s succes, %s echecs, %s ignorees, %s bloquees",
                successes,
                failures,
                skipped,
                blocked,
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
