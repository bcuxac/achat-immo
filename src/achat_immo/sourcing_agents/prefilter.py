"""Prefiltrage deterministe des URLs avant scraping et extraction LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from achat_immo.storage import normalize_source_url


@dataclass(frozen=True)
class UrlPrefilterPolicy:
    """Regles conservatrices appliquees avant tout appel couteux ou fragile."""

    allowed_domains: tuple[str, ...] = ()
    max_url_length: int = 2000
    static_suffixes: tuple[str, ...] = (
        ".avif",
        ".css",
        ".gif",
        ".ico",
        ".jpeg",
        ".jpg",
        ".js",
        ".json",
        ".mp4",
        ".pdf",
        ".png",
        ".svg",
        ".webp",
        ".woff",
        ".woff2",
        ".zip",
    )
    blocked_path_segments: tuple[str, ...] = (
        "account",
        "auth",
        "connexion",
        "favoris",
        "login",
        "messages",
        "mon-compte",
    )
    blocked_exact_paths: tuple[str, ...] = (
        "/favicon.ico",
        "/robots.txt",
        "/sitemap.xml",
    )

    def normalized_allowed_domains(self) -> tuple[str, ...]:
        return tuple(domain.lower().strip() for domain in self.allowed_domains if domain.strip())


@dataclass(frozen=True)
class UrlPrefilterDecision:
    accepted: bool
    normalized_url: str
    reason: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


def prefilter_url(url: str, policy: UrlPrefilterPolicy | None = None) -> UrlPrefilterDecision:
    """Accepte ou rejette une URL avant Playwright/LLM.

    Le filtre reste volontairement conservateur : il rejette les cas
    structurellement inutiles, mais n'essaie pas de deviner la qualite business
    d'une annonce.
    """

    policy = policy or UrlPrefilterPolicy()
    try:
        normalized_url = normalize_source_url(url)
    except ValueError as exc:
        return UrlPrefilterDecision(False, "", str(exc), ("invalid",))

    if len(normalized_url) > policy.max_url_length:
        return UrlPrefilterDecision(
            False,
            normalized_url,
            f"URL trop longue ({len(normalized_url)} caracteres).",
            ("invalid",),
        )

    parsed = urlsplit(normalized_url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return UrlPrefilterDecision(
            False,
            normalized_url,
            f"Schema non supporte: {parsed.scheme or 'absent'}.",
            ("invalid",),
        )
    if not parsed.netloc or not parsed.hostname:
        return UrlPrefilterDecision(False, normalized_url, "Domaine absent.", ("invalid",))

    hostname = parsed.hostname.lower()
    allowed_domains = policy.normalized_allowed_domains()
    if allowed_domains and not _matches_allowed_domain(hostname, allowed_domains):
        return UrlPrefilterDecision(
            False,
            normalized_url,
            f"Domaine hors perimetre: {hostname}.",
            ("unsupported_domain",),
        )

    path = parsed.path.lower() or "/"
    if path in policy.blocked_exact_paths:
        return UrlPrefilterDecision(
            False,
            normalized_url,
            f"Chemin technique ignore: {path}.",
            ("technical_path",),
        )
    if path.endswith(policy.static_suffixes):
        return UrlPrefilterDecision(
            False,
            normalized_url,
            f"Ressource statique ignoree: {path}.",
            ("static_asset",),
        )

    path_segments = {segment for segment in path.split("/") if segment}
    blocked_segments = set(policy.blocked_path_segments)
    matched_segments = sorted(path_segments & blocked_segments)
    if matched_segments:
        return UrlPrefilterDecision(
            False,
            normalized_url,
            f"Chemin utilisateur ignore: {', '.join(matched_segments)}.",
            ("account_path",),
        )

    return UrlPrefilterDecision(True, normalized_url, "URL acceptee.", ("accepted",))


def _matches_allowed_domain(hostname: str, allowed_domains: tuple[str, ...]) -> bool:
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains)
