import pytest

from achat_immo.sourcing_agents.content_guard import (
    SourcingAccessBlockedError,
    classify_content_access,
    ensure_content_accessible,
)


def test_content_guard_accepte_un_texte_annonce_exploitable() -> None:
    decision = classify_content_access(
        "Appartement T2 de 42 m2 a Grenoble. Prix 120000 euros. Charges 80 euros par mois."
    )

    assert decision.accepted
    assert decision.status == "content_ok"


def test_content_guard_detecte_un_blocage_antibot() -> None:
    decision = classify_content_access("Just a moment. Cloudflare checks if the site connection is secure.")

    assert not decision.accepted
    assert decision.status == "blocked_antibot"
    assert "cloudflare" in decision.matches


def test_content_guard_detecte_un_mur_de_consentement() -> None:
    decision = classify_content_access("Gestion des cookies. Accepter les cookies ou parametrer mes choix.")

    assert not decision.accepted
    assert decision.status == "blocked_consent"
    assert "gestion des cookies" in decision.matches


def test_ensure_content_accessible_leve_une_erreur_metier() -> None:
    with pytest.raises(SourcingAccessBlockedError) as exc_info:
        ensure_content_accessible("Captcha verification required.")

    assert exc_info.value.decision.status == "blocked_antibot"
