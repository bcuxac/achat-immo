"""Authentification legere pour l'application Streamlit."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os


HASH_PREFIX = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 260_000


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Produit un hash PBKDF2-SHA256 stockable dans les secrets Streamlit."""

    if not password:
        raise ValueError("Le mot de passe ne peut pas etre vide.")

    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_b64 = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"{HASH_PREFIX}${iterations}${salt_b64}${digest_b64}"


def verify_password(password: str, expected: str) -> bool:
    """Verifie un mot de passe contre un hash PBKDF2 ou une valeur en clair."""

    if not password or not expected:
        return False

    if not expected.startswith(f"{HASH_PREFIX}$"):
        return hmac.compare_digest(password, expected)

    try:
        _, iterations_raw, salt_b64, digest_b64 = expected.split("$", 3)
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected_digest = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
    except (ValueError, TypeError):
        return False

    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected_digest)
