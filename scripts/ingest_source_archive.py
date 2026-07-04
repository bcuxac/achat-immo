#!/usr/bin/env python3
"""Importe des URLs Jinka depuis un export local dans la queue de sourcing."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from achat_immo.sourcing_discovery import read_source_archive
from achat_immo.storage import enqueue_sourcing_url, open_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Importer une archive d'alertes Jinka.")
    parser.add_argument("archive", type=Path, help="Fichier CSV/TXT/EML/MBOX ou repertoire a importer.")
    parser.add_argument("--source", default="jinka_archive", help="Nom enregistre dans la queue.")
    parser.add_argument("--priority", type=int, default=0, help="Priorite des nouvelles URLs.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    load_dotenv()
    urls = read_source_archive(args.archive)
    conn = open_database()
    try:
        before = {enqueue_sourcing_url(conn, url, source=args.source, priority=args.priority) for url in urls}
    finally:
        conn.close()
    print(f"{len(urls)} URL(s) canonique(s) importee(s), {len(before)} element(s) de queue concernes.")


if __name__ == "__main__":
    main()
