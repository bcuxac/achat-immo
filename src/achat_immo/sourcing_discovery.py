"""Decouverte d'URLs d'annonces depuis des exports et alertes Jinka."""

from __future__ import annotations

import csv
from email import policy
from email.message import Message
from email.parser import BytesParser
from html import unescape
import mailbox
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlsplit

from achat_immo.storage import normalize_source_url

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_JINKA_HOSTS = {"jinka.fr", "www.jinka.fr"}
_SUPPORTED_ARCHIVE_SUFFIXES = {".csv", ".eml", ".html", ".htm", ".mbox", ".txt"}


def is_jinka_ad_url(url: str) -> bool:
    """Indique si l'URL cible une fiche annonce Jinka."""

    parsed = urlsplit(url)
    return (parsed.hostname or "").lower() in _JINKA_HOSTS and bool(
        re.fullmatch(r"/ad/[^/]+/?", parsed.path)
    )


def extract_jinka_ad_urls(text: str) -> list[str]:
    """Extrait et canonise les URLs d'annonces Jinka presentes dans un texte."""

    urls: list[str] = []
    seen: set[str] = set()
    decoded_text = unescape(text)
    for raw_url in _URL_PATTERN.findall(decoded_text):
        candidate = raw_url.rstrip("),.;]}")
        candidates = [candidate]
        parsed = urlsplit(candidate)
        for values in parse_qs(parsed.query).values():
            candidates.extend(unquote(value) for value in values)

        for value in candidates:
            if not is_jinka_ad_url(value):
                continue
            normalized = normalize_source_url(value)
            if normalized not in seen:
                seen.add(normalized)
                urls.append(normalized)
    return urls


def message_text(message: Message) -> str:
    """Retourne les parties texte et HTML utiles d'un message RFC 822."""

    chunks: list[str] = []
    parts = message.walk() if message.is_multipart() else (message,)
    for part in parts:
        if part.get_content_maintype() != "text":
            continue
        if part.get_content_disposition() == "attachment":
            continue
        try:
            content = part.get_content()
        except (AttributeError, LookupError, UnicodeDecodeError):
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if isinstance(content, str):
            chunks.append(content)
    return "\n".join(chunks)


def extract_jinka_urls_from_message(message: Message) -> list[str]:
    """Extrait les fiches Jinka d'un e-mail decode."""

    return extract_jinka_ad_urls(message_text(message))


def read_source_archive(path: Path) -> list[str]:
    """Lit un export CSV, texte, EML, MBOX ou un repertoire d'exports."""

    if not path.exists():
        raise FileNotFoundError(path)

    if path.is_dir():
        apple_mail_payload = path / "mbox"
        if path.suffix.lower() == ".mbox" and apple_mail_payload.is_file():
            return _deduplicate(_read_mbox(apple_mail_payload))
        urls: list[str] = []
        for child in sorted(path.rglob("*")):
            if child.is_file() and child.suffix.lower() in _SUPPORTED_ARCHIVE_SUFFIXES:
                urls.extend(read_source_archive(child))
        return _deduplicate(urls)

    suffix = path.suffix.lower()
    if suffix == ".eml":
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        return extract_jinka_urls_from_message(message)
    if suffix == ".mbox" or path.name == "mbox":
        return _deduplicate(_read_mbox(path))
    if suffix == ".csv":
        return _read_csv(path)
    if suffix in {".txt", ".html", ".htm"}:
        return extract_jinka_ad_urls(path.read_text(encoding="utf-8", errors="replace"))
    raise ValueError(f"Format d'archive non supporte: {path.suffix or path.name}")


def _read_mbox(path: Path) -> list[str]:
    urls: list[str] = []
    archive = mailbox.mbox(
        path,
        factory=lambda handle: BytesParser(policy=policy.default).parse(handle),
        create=False,
    )
    for message in archive:
        urls.extend(extract_jinka_urls_from_message(message))
    return urls


def _read_csv(path: Path) -> list[str]:
    urls: list[str] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        for row in csv.reader(handle, dialect):
            for cell in row:
                urls.extend(extract_jinka_ad_urls(cell))
    return _deduplicate(urls)


def _deduplicate(urls: list[str]) -> list[str]:
    return list(dict.fromkeys(urls))
