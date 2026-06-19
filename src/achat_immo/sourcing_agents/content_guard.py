"""Detection de contenus non exploitables apres chargement navigateur."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContentAccessDecision:
    accepted: bool
    status: str
    reason: str
    matches: tuple[str, ...] = field(default_factory=tuple)


class SourcingAccessBlockedError(RuntimeError):
    """Erreur metier pour les pages chargees mais bloquees par la source."""

    def __init__(self, decision: ContentAccessDecision):
        self.decision = decision
        super().__init__(decision.reason)


ANTI_BOT_PATTERNS: tuple[str, ...] = (
    "access denied",
    "attention required",
    "captcha",
    "cf-turnstile",
    "checking if the site connection is secure",
    "checking your browser",
    "cloudflare",
    "hcaptcha",
    "just a moment",
    "pardon the interruption",
    "recaptcha",
    "turnstile",
    "verify you are human",
    "verification required",
)

CONSENT_PATTERNS: tuple[str, ...] = (
    "accepter les cookies",
    "choix de confidentialite",
    "consentement",
    "cookie consent",
    "cookies et autres traceurs",
    "gestion des cookies",
    "parametrer mes choix",
    "privacy choices",
)


def classify_content_access(text: str) -> ContentAccessDecision:
    """Classe le texte extrait avant envoi au LLM."""

    normalized = " ".join(text.lower().split())
    if not normalized:
        return ContentAccessDecision(False, "empty_content", "Contenu vide apres chargement navigateur.")

    anti_bot_matches = _find_matches(normalized, ANTI_BOT_PATTERNS)
    if anti_bot_matches:
        return ContentAccessDecision(
            False,
            "blocked_antibot",
            "Blocage anti-bot detecte: " + ", ".join(anti_bot_matches) + ".",
            anti_bot_matches,
        )

    consent_matches = _find_matches(normalized, CONSENT_PATTERNS)
    if len(consent_matches) >= 1 and _looks_like_consent_wall(normalized):
        return ContentAccessDecision(
            False,
            "blocked_consent",
            "Mur de consentement detecte: " + ", ".join(consent_matches) + ".",
            consent_matches,
        )

    return ContentAccessDecision(True, "content_ok", "Contenu exploitable.")


def ensure_content_accessible(text: str) -> None:
    decision = classify_content_access(text)
    if not decision.accepted:
        raise SourcingAccessBlockedError(decision)


def _find_matches(text: str, patterns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(pattern for pattern in patterns if pattern in text)


def _looks_like_consent_wall(text: str) -> bool:
    cookie_markers = ("cookie", "cookies", "traceurs", "consentement", "privacy")
    action_markers = ("accepter", "refuser", "parametrer", "choix", "continuer")
    has_cookie_marker = any(marker in text for marker in cookie_markers)
    has_action_marker = any(marker in text for marker in action_markers)
    return has_cookie_marker and has_action_marker
