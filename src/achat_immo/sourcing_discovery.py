"""Decouverte d'URLs d'annonces depuis des exports et alertes Jinka."""

from __future__ import annotations

from collections.abc import Callable
import csv
from email import policy
from email.message import Message
from email.parser import BytesParser
from html import unescape
import mailbox
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from bs4 import BeautifulSoup

from achat_immo.storage import normalize_jinka_alert_id, normalize_source_url

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_MARKDOWN_ACTION_LINK_PATTERN = re.compile(
    r"\[[^\]]*application\s+Jinka[^\]]*\]\((https?://[^)]+)\)",
    re.IGNORECASE,
)
_JINKA_ALERT_ID_PATTERN = re.compile(r"(?:alert_id|alertId)=([A-Za-z0-9_-]{8,128})")
_JINKA_NOTIFICATION_COUNT_PATTERN = re.compile(r"(\d+)\s+nouvelles?\s+annonces?", re.IGNORECASE)
_JINKA_HOSTS = {"jinka.fr", "www.jinka.fr"}
_TRACKING_HOST_SUFFIXES = ("sendgrid.net",)
_SUPPORTED_ARCHIVE_SUFFIXES = {".csv", ".eml", ".html", ".htm", ".mbox", ".txt"}


class _NoRedirectHandler(HTTPRedirectHandler):
    def http_error_301(self, req, fp, code, msg, headers):  # noqa: ANN001
        raise HTTPError(req.full_url, code, msg, headers, fp)

    http_error_302 = http_error_301
    http_error_303 = http_error_301
    http_error_307 = http_error_301
    http_error_308 = http_error_301


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
    for value in _expanded_url_candidates(text):
        if not is_jinka_ad_url(value):
            continue
        normalized = normalize_source_url(value)
        if normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)
    return urls


def extract_jinka_alert_ids(text: str) -> list[str]:
    """Extrait les identifiants d'alertes Jinka visibles dans un texte."""

    alert_ids: list[str] = []
    seen: set[str] = set()
    for value in _expanded_url_candidates(text):
        for match in _JINKA_ALERT_ID_PATTERN.finditer(unquote(unescape(value))):
            try:
                alert_id = normalize_jinka_alert_id(match.group(1))
            except ValueError:
                continue
            if alert_id not in seen:
                seen.add(alert_id)
                alert_ids.append(alert_id)
    return alert_ids


def extract_jinka_notification_count(text: str) -> int | None:
    """Retourne le nombre de nouvelles annonces annonce par un email Jinka."""

    match = _JINKA_NOTIFICATION_COUNT_PATTERN.search(unescape(text))
    return int(match.group(1)) if match else None


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


def extract_jinka_alert_ids_from_message(
    message: Message,
    *,
    resolve_tracked_links: bool = False,
    resolver: Callable[[str], str] | None = None,
) -> list[str]:
    """Extrait les alertes Jinka d'un e-mail decode.

    Les emails Jinka ne contiennent souvent qu'un lien SendGrid vers la page
    d'alerte. Quand ``resolve_tracked_links`` est actif, les liens de tracking
    sont suivis uniquement pour recuperer la redirection finale.
    """

    text = message_text(message)
    alert_ids = extract_jinka_alert_ids(text)
    if not resolve_tracked_links:
        return alert_ids

    seen = set(alert_ids)
    resolve = resolver or resolve_redirect_target
    for url in _jinka_alert_action_urls_from_message(message):
        if not _is_allowed_alert_resolution_url(url):
            continue
        try:
            resolved_url = resolve(url)
        except (OSError, ValueError, URLError, HTTPError):
            continue
        for alert_id in extract_jinka_alert_ids(resolved_url):
            if alert_id not in seen:
                seen.add(alert_id)
                alert_ids.append(alert_id)
    return alert_ids


def extract_jinka_notification_count_from_message(message: Message) -> int | None:
    """Retourne le nombre de nouvelles annonces indique par un e-mail Jinka."""

    return extract_jinka_notification_count(message_text(message))


def _jinka_alert_action_urls_from_message(message: Message) -> list[str]:
    """Retourne uniquement les liens d'ouverture d'alerte, pas les liens d'action destructive."""

    urls: list[str] = []
    seen: set[str] = set()
    parts = message.walk() if message.is_multipart() else (message,)
    for part in parts:
        if part.get_content_maintype() != "text" or part.get_content_disposition() == "attachment":
            continue
        try:
            content = part.get_content()
        except (AttributeError, LookupError, UnicodeDecodeError):
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            content = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if not isinstance(content, str):
            continue
        if part.get_content_subtype() == "html":
            soup = BeautifulSoup(content, "html.parser")
            for anchor in soup.find_all("a", href=True):
                label = " ".join(anchor.get_text(" ", strip=True).split()).lower()
                if "application jinka" not in label:
                    continue
                href = str(anchor["href"])
                if href not in seen:
                    seen.add(href)
                    urls.append(href)
            continue
        for match in _MARKDOWN_ACTION_LINK_PATTERN.finditer(content):
            href = unescape(match.group(1).strip())
            if href not in seen:
                seen.add(href)
                urls.append(href)
    return urls


def resolve_redirect_target(url: str, *, timeout: float = 10.0, max_redirects: int = 6) -> str:
    """Suit prudemment les redirections HTTP et retourne l'URL finale."""

    opener = build_opener(_NoRedirectHandler)
    current = url
    for _ in range(max_redirects):
        request = Request(current, method="HEAD", headers={"User-Agent": "achat-immo-sourcing/1.0"})
        try:
            response = opener.open(request, timeout=timeout)
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                location = exc.headers.get("Location")
                if not location:
                    return current
                current = urljoin(current, location)
                continue
            if exc.code == 405:
                request = Request(current, method="GET", headers={"User-Agent": "achat-immo-sourcing/1.0"})
                response = opener.open(request, timeout=timeout)
            else:
                raise
        with response:
            return response.geturl()
    return current


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


def read_jinka_alert_archive(path: Path, *, resolve_tracked_links: bool = False) -> list[str]:
    """Lit les identifiants d'alertes Jinka depuis un export local."""

    if not path.exists():
        raise FileNotFoundError(path)

    if path.is_dir():
        apple_mail_payload = path / "mbox"
        if path.suffix.lower() == ".mbox" and apple_mail_payload.is_file():
            return _deduplicate(_read_mbox_alerts(apple_mail_payload, resolve_tracked_links=resolve_tracked_links))
        alert_ids: list[str] = []
        for child in sorted(path.rglob("*")):
            if child.is_file() and child.suffix.lower() in _SUPPORTED_ARCHIVE_SUFFIXES:
                alert_ids.extend(read_jinka_alert_archive(child, resolve_tracked_links=resolve_tracked_links))
        return _deduplicate(alert_ids)

    suffix = path.suffix.lower()
    if suffix == ".eml":
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        return extract_jinka_alert_ids_from_message(message, resolve_tracked_links=resolve_tracked_links)
    if suffix == ".mbox" or path.name == "mbox":
        return _deduplicate(_read_mbox_alerts(path, resolve_tracked_links=resolve_tracked_links))
    if suffix == ".csv":
        return _read_csv_alerts(path)
    if suffix in {".txt", ".html", ".htm"}:
        return extract_jinka_alert_ids(path.read_text(encoding="utf-8", errors="replace"))
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


def _read_mbox_alerts(path: Path, *, resolve_tracked_links: bool) -> list[str]:
    alert_ids: list[str] = []
    archive = mailbox.mbox(
        path,
        factory=lambda handle: BytesParser(policy=policy.default).parse(handle),
        create=False,
    )
    for message in archive:
        alert_ids.extend(
            extract_jinka_alert_ids_from_message(message, resolve_tracked_links=resolve_tracked_links)
        )
    return alert_ids


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


def _read_csv_alerts(path: Path) -> list[str]:
    alert_ids: list[str] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        for row in csv.reader(handle, dialect):
            for cell in row:
                alert_ids.extend(extract_jinka_alert_ids(cell))
    return _deduplicate(alert_ids)


def _urls_from_text(text: str) -> list[str]:
    decoded_text = unescape(text)
    return [raw_url.rstrip("),.;]}") for raw_url in _URL_PATTERN.findall(decoded_text)]


def _expanded_url_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    pending = _urls_from_text(text)
    while pending:
        candidate = pending.pop(0)
        if candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)
        parsed = urlsplit(candidate)
        for values in parse_qs(parsed.query).values():
            for value in values:
                decoded = unquote(unescape(value))
                if decoded and decoded not in seen:
                    pending.append(decoded)
    return candidates


def _is_allowed_alert_resolution_url(url: str) -> bool:
    hostname = (urlsplit(url).hostname or "").lower()
    return hostname in _JINKA_HOSTS or any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in _TRACKING_HOST_SUFFIXES)


def _deduplicate(urls: list[str]) -> list[str]:
    return list(dict.fromkeys(urls))
