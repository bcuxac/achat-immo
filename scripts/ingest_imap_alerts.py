#!/usr/bin/env python3
"""Importe sans les marquer comme lus les alertes Jinka d'une boite IMAP."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
import imaplib
import os

from dotenv import load_dotenv

from achat_immo.sourcing_discovery import (
    extract_jinka_alert_ids_from_message,
    extract_jinka_notification_count_from_message,
    extract_jinka_urls_from_message,
)
from achat_immo.storage import enqueue_jinka_alert, enqueue_sourcing_url, open_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Importer les alertes Jinka depuis IMAP.")
    parser.add_argument("--lookback-days", type=int, default=2, help="Fenetre de recherche des messages.")
    parser.add_argument("--source", default="jinka_email", help="Nom enregistre dans la queue.")
    parser.add_argument("--priority", type=int, default=0, help="Priorite des nouvelles URLs.")
    parser.add_argument(
        "--mode",
        choices=("alerts", "ads", "both"),
        default="both",
        help="Nature des elements importes depuis les messages.",
    )
    parser.add_argument(
        "--no-resolve-tracked-links",
        action="store_true",
        help="Ne pas suivre le lien 'Voir dans l'application Jinka' pour retrouver alert_id.",
    )
    return parser


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Variable requise absente: {name}")
    return value


def fetch_messages(*, lookback_days: int) -> list[bytes]:
    """Charge les messages de la fenetre configuree sans modifier la boite."""

    host = _required_env("SOURCING_IMAP_HOST")
    username = _required_env("SOURCING_IMAP_USERNAME")
    password = _required_env("SOURCING_IMAP_PASSWORD")
    port = int(os.environ.get("SOURCING_IMAP_PORT", "993"))
    mailbox_name = os.environ.get("SOURCING_IMAP_MAILBOX", "INBOX")
    sender = os.environ.get("SOURCING_IMAP_SENDER", "").strip()
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%d-%b-%Y")

    client = imaplib.IMAP4_SSL(host, port)
    try:
        client.login(username, password)
        status, _ = client.select(mailbox_name, readonly=True)
        if status != "OK":
            raise RuntimeError(f"Impossible d'ouvrir la boite IMAP: {mailbox_name}")
        criteria: list[str] = ["SINCE", since]
        if sender:
            criteria.extend(["FROM", f'"{sender}"'])
        status, data = client.uid("search", None, *criteria)
        if status != "OK":
            raise RuntimeError("La recherche IMAP a echoue.")

        messages: list[bytes] = []
        for uid in data[0].split():
            status, payload = client.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                continue
            for item in payload:
                if isinstance(item, tuple) and isinstance(item[1], bytes):
                    messages.append(item[1])
                    break
        return messages
    finally:
        try:
            client.logout()
        except imaplib.IMAP4.error:
            pass


def main() -> None:
    args = build_parser().parse_args()
    if args.lookback_days < 1:
        raise SystemExit("--lookback-days doit etre superieur ou egal a 1.")
    load_dotenv()
    raw_messages = fetch_messages(lookback_days=args.lookback_days)

    urls: list[str] = []
    alert_rows: list[tuple[str, str, int | None]] = []
    for raw_message in raw_messages:
        message = BytesParser(policy=policy.default).parsebytes(raw_message)
        if args.mode in {"ads", "both"}:
            urls.extend(extract_jinka_urls_from_message(message))
        if args.mode in {"alerts", "both"}:
            observed_at = _message_observed_at(message)
            notification_count = extract_jinka_notification_count_from_message(message)
            for alert_id in extract_jinka_alert_ids_from_message(
                message,
                resolve_tracked_links=not args.no_resolve_tracked_links,
            ):
                alert_rows.append((alert_id, observed_at, notification_count))
    urls = list(dict.fromkeys(urls))
    alert_rows = list(dict.fromkeys(alert_rows))

    conn = open_database()
    try:
        for alert_id, observed_at, notification_count in alert_rows:
            enqueue_jinka_alert(
                conn,
                alert_id,
                source_url=_jinka_alert_url(alert_id),
                source=args.source,
                priority=args.priority,
                observed_at=observed_at,
                notification_count=notification_count,
            )
        for url in urls:
            enqueue_sourcing_url(conn, url, source=args.source, priority=args.priority)
    finally:
        conn.close()
    print(
        f"{len(raw_messages)} message(s) examines, "
        f"{len(alert_rows)} alerte(s) Jinka importee(s), "
        f"{len(urls)} annonce(s) Jinka mise(s) en queue."
    )


def _message_observed_at(message) -> str:  # noqa: ANN001
    date_header = message.get("Date", "")
    if not date_header:
        return ""
    try:
        parsed = parsedate_to_datetime(date_header)
    except (TypeError, ValueError, IndexError):
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _jinka_alert_url(alert_id: str) -> str:
    return f"https://www.jinka.fr/alerts?alert_id={alert_id}"


if __name__ == "__main__":
    main()
