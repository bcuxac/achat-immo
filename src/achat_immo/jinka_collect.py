"""Collecte authentifiee des annonces rattachees a une alerte Jinka."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from achat_immo.sourcing_discovery import extract_jinka_ad_urls
from achat_immo.storage import normalize_jinka_alert_id

DEFAULT_JINKA_STORAGE_STATE = Path("data/jinka_storage_state.json")
JINKA_BASE_URL = "https://www.jinka.fr"


@dataclass(frozen=True, slots=True)
class JinkaAlertCollectionResult:
    """Resultat d'une collecte d'alerte Jinka."""

    alert_id: str
    alert_url: str
    final_url: str
    ad_urls: tuple[str, ...] = ()
    requires_login: bool = False
    error_message: str = ""
    inspected_response_count: int = 0
    diagnostics: tuple[str, ...] = field(default_factory=tuple)


def jinka_alert_url(alert_id: str) -> str:
    """Construit l'URL web d'une alerte Jinka."""

    return f"{JINKA_BASE_URL}/alerts?alert_id={normalize_jinka_alert_id(alert_id)}"


def extract_jinka_ad_urls_from_payload(payload: Any) -> list[str]:
    """Extrait des fiches Jinka depuis du texte, JSON ou structures imbriquees."""

    urls: list[str] = []
    if isinstance(payload, str):
        urls.extend(extract_jinka_ad_urls(payload))
        stripped = payload.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                urls.extend(extract_jinka_ad_urls_from_payload(json.loads(stripped)))
            except json.JSONDecodeError:
                pass
    elif isinstance(payload, dict):
        for value in payload.values():
            urls.extend(extract_jinka_ad_urls_from_payload(value))
    elif isinstance(payload, list | tuple):
        for value in payload:
            urls.extend(extract_jinka_ad_urls_from_payload(value))
    return list(dict.fromkeys(urls))


def collect_jinka_alert_ads(
    alert_id: str,
    *,
    storage_state_path: Path = DEFAULT_JINKA_STORAGE_STATE,
    headless: bool = True,
    timeout_ms: int = 30_000,
    settle_ms: int = 3_000,
    scroll_steps: int = 4,
) -> JinkaAlertCollectionResult:
    """Ouvre une alerte Jinka authentifiee et retourne les URLs d'annonces visibles."""

    normalized_alert_id = normalize_jinka_alert_id(alert_id)
    alert_url = jinka_alert_url(normalized_alert_id)
    if not storage_state_path.exists():
        return JinkaAlertCollectionResult(
            alert_id=normalized_alert_id,
            alert_url=alert_url,
            final_url="",
            requires_login=True,
            error_message=(
                f"Session Jinka absente: {storage_state_path}. "
                "Executer scripts/setup_jinka_session.py avant la collecte."
            ),
        )

    response_payloads: list[str] = []
    diagnostics: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(storage_state_path))
        page = context.new_page()

        def capture_response(response) -> None:  # noqa: ANN001
            if not _should_inspect_response(response.url, response.headers):
                return
            try:
                text = response.text()
            except Exception:
                return
            if text:
                response_payloads.append(text[:2_000_000])

        page.on("response", capture_response)
        try:
            try:
                page.goto(alert_url, wait_until="domcontentloaded", timeout=timeout_ms)
            except PlaywrightTimeoutError:
                diagnostics.append("Timeout au chargement initial, lecture du DOM partiel.")
            page.wait_for_timeout(settle_ms)
            for _ in range(max(scroll_steps, 0)):
                page.mouse.wheel(0, 2400)
                page.wait_for_timeout(600)

            final_url = page.url
            anchors = page.eval_on_selector_all("a[href]", "(nodes) => nodes.map((node) => node.href)")
            html = page.content()
            ad_urls = _deduplicate(
                [
                    *extract_jinka_ad_urls("\n".join(str(anchor) for anchor in anchors)),
                    *extract_jinka_ad_urls(html),
                    *extract_jinka_ad_urls_from_payload(response_payloads),
                ]
            )
            requires_login = _requires_login(final_url, html)
            error_message = "Session Jinka non connectee ou expiree." if requires_login else ""
            return JinkaAlertCollectionResult(
                alert_id=normalized_alert_id,
                alert_url=alert_url,
                final_url=final_url,
                ad_urls=tuple(ad_urls),
                requires_login=requires_login,
                error_message=error_message,
                inspected_response_count=len(response_payloads),
                diagnostics=tuple(diagnostics),
            )
        finally:
            context.close()
            browser.close()


def _should_inspect_response(url: str, headers: dict[str, str]) -> bool:
    if "jinka.fr" not in url:
        return False
    content_type = headers.get("content-type", "").lower()
    return any(
        marker in content_type
        for marker in (
            "application/json",
            "text/",
            "x-component",
        )
    )


def _requires_login(final_url: str, html: str) -> bool:
    lower_url = final_url.lower()
    if "/sign/in" in lower_url or "/auth/signin" in lower_url:
        return True
    lower_html = html.lower()
    login_markers = (
        "connectez-vous",
        "connexion",
        "se connecter",
        "sign in",
    )
    return "/alerts" not in lower_url and any(marker in lower_html for marker in login_markers)


def _deduplicate(urls: list[str]) -> list[str]:
    return list(dict.fromkeys(urls))
