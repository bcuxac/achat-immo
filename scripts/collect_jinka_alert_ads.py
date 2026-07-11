#!/usr/bin/env python3
"""Developpe les alertes Jinka en URLs d'annonces dans la queue de sourcing."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from achat_immo.jinka_collect import DEFAULT_JINKA_STORAGE_STATE, collect_jinka_alert_ads, jinka_alert_url
from achat_immo.storage import (
    enqueue_jinka_alert,
    enqueue_sourcing_url,
    list_pending_jinka_alerts,
    mark_jinka_alert_blocked,
    mark_jinka_alert_failure,
    mark_jinka_alert_processing,
    mark_jinka_alert_success,
    open_database,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collecter les annonces visibles dans les alertes Jinka.")
    parser.add_argument("--alert-id", action="append", default=[], help="Alerte Jinka specifique a collecter.")
    parser.add_argument("--limit", type=int, default=10, help="Nombre maximal d'alertes pending a collecter.")
    parser.add_argument(
        "--storage-state",
        type=Path,
        default=DEFAULT_JINKA_STORAGE_STATE,
        help="Fichier Playwright storage_state Jinka.",
    )
    parser.add_argument("--headed", action="store_true", help="Afficher Chromium pendant la collecte.")
    parser.add_argument("--timeout-ms", type=int, default=30_000, help="Timeout de chargement Playwright.")
    parser.add_argument("--settle-ms", type=int, default=3_000, help="Temps d'attente apres chargement.")
    parser.add_argument("--scroll-steps", type=int, default=4, help="Nombre de scrolls pour charger la liste.")
    parser.add_argument("--source", default="jinka_alert", help="Source enregistree dans la queue d'annonces.")
    parser.add_argument("--priority", type=int, default=0, help="Priorite des URLs d'annonces ajoutees.")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Marquer l'alerte comme traitee meme si aucune annonce n'est detectee.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.limit < 1 and not args.alert_id:
        raise SystemExit("--limit doit etre positif sauf si --alert-id est fourni.")
    load_dotenv()

    conn = open_database()
    try:
        alerts = _alerts_to_collect(conn, args.alert_id, args.limit, args.priority)
        total_urls = 0
        for alert in alerts:
            alert_row_id = int(alert["id"])
            alert_id = str(alert["alert_id"])
            mark_jinka_alert_processing(conn, alert_row_id)
            result = collect_jinka_alert_ads(
                alert_id,
                storage_state_path=args.storage_state,
                headless=not args.headed,
                timeout_ms=args.timeout_ms,
                settle_ms=args.settle_ms,
                scroll_steps=args.scroll_steps,
            )
            if result.requires_login:
                mark_jinka_alert_blocked(conn, alert_row_id, result.error_message)
                print(f"Alerte {alert_id}: bloquee - {result.error_message}")
                continue
            if not result.ad_urls and not args.allow_empty:
                message = (
                    "Aucune annonce Jinka detectee dans l'alerte "
                    f"(final_url={result.final_url}, responses={result.inspected_response_count})."
                )
                mark_jinka_alert_failure(conn, alert_row_id, message)
                print(f"Alerte {alert_id}: echec - {message}")
                continue
            for url in result.ad_urls:
                enqueue_sourcing_url(conn, url, source=args.source, priority=args.priority)
            total_urls += len(result.ad_urls)
            mark_jinka_alert_success(conn, alert_row_id, len(result.ad_urls))
            print(f"Alerte {alert_id}: {len(result.ad_urls)} annonce(s) ajoutee(s) a la queue.")
        print(f"{len(alerts)} alerte(s) examinee(s), {total_urls} URL(s) d'annonce detectee(s).")
    finally:
        conn.close()


def _alerts_to_collect(conn, alert_ids: list[str], limit: int, priority: int) -> list[dict]:  # noqa: ANN001
    if alert_ids:
        alerts: list[dict] = []
        for alert_id in dict.fromkeys(alert_ids):
            row_id = enqueue_jinka_alert(
                conn,
                alert_id,
                source_url=jinka_alert_url(alert_id),
                source="manual_jinka_alert",
                priority=priority,
            )
            row = conn.execute("SELECT * FROM jinka_alerts WHERE id = ?", (row_id,)).fetchone()
            if row is not None:
                alerts.append(dict(row))
        return alerts
    return list_pending_jinka_alerts(conn, limit=limit)


if __name__ == "__main__":
    main()
