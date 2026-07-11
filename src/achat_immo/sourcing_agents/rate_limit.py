"""Erreurs de quota temporaire pour les fournisseurs externes du sourcing."""

from __future__ import annotations


class SourcingRateLimitedError(RuntimeError):
    """Erreur temporaire indiquant qu'un fournisseur doit etre reessaye plus tard."""

    def __init__(self, reason: str, *, retry_after_seconds: float | None = None):
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds
        super().__init__(reason)
