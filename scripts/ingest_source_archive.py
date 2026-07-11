#!/usr/bin/env python3
"""Importe des alertes et URLs Jinka depuis un export local."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from achat_immo.sourcing_discovery import read_jinka_alert_archive, read_source_archive
from achat_immo.storage import enqueue_jinka_alert, enqueue_sourcing_url, open_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Importer une archive d'alertes Jinka.")
    parser.add_argument("archive", type=Path, help="Fichier CSV/TXT/EML/MBOX ou repertoire a importer.")
    parser.add_argument("--source", default="jinka_archive", help="Nom enregistre dans la queue.")
    parser.add_argument("--priority", type=int, default=0, help="Priorite des nouvelles URLs.")
    parser.add_argument(
        "--mode",
        choices=("alerts", "ads", "both"),
        default="both",
        help="Nature des elements importes depuis l'archive.",
    )
    parser.add_argument(
        "--resolve-tracked-links",
        action="store_true",
        help="Suivre les liens du bouton Jinka pour retrouver alert_id dans les emails exportes.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    load_dotenv()
    urls = read_source_archive(args.archive) if args.mode in {"ads", "both"} else []
    alert_ids = (
        read_jinka_alert_archive(args.archive, resolve_tracked_links=args.resolve_tracked_links)
        if args.mode in {"alerts", "both"}
        else []
    )
    conn = open_database()
    try:
        alert_rows = {
            enqueue_jinka_alert(
                conn,
                alert_id,
                source_url=_jinka_alert_url(alert_id),
                source=args.source,
                priority=args.priority,
            )
            for alert_id in alert_ids
        }
        queue_rows = {enqueue_sourcing_url(conn, url, source=args.source, priority=args.priority) for url in urls}
    finally:
        conn.close()
    print(
        f"{len(alert_ids)} alerte(s) importee(s), {len(alert_rows)} ligne(s) d'alerte concernee(s), "
        f"{len(urls)} URL(s) canonique(s) importee(s), {len(queue_rows)} element(s) de queue concernes."
    )


def _jinka_alert_url(alert_id: str) -> str:
    return f"https://www.jinka.fr/alerts?alert_id={alert_id}"


if __name__ == "__main__":
    main()
