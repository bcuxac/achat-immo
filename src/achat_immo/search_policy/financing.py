"""Politique de financement pour les recherches de prix cible."""

from __future__ import annotations

from dataclasses import dataclass, replace

from achat_immo.stochastic.models import Strategy


def project_cost(strategy: Strategy) -> float:
    """Cout projet connu par le modele stochastique."""

    return (
        strategy.prix_achat
        + strategy.frais_notaire_estimes
        + strategy.frais_agence_achat
        + strategy.travaux_initiaux
    )


@dataclass(frozen=True, slots=True)
class FinancingPolicy:
    """Recalcule l'apport quand le prix cible change.

    La politique conserve au minimum le ratio d'apport observe sur la strategie
    de reference, tout en appliquant un plancher prudent de fonds propres. Ainsi,
    un prix cible fortement negocie n'herite pas artificiellement du meme apport
    absolu que le prix affiche.
    """

    min_equity_ratio_pct: float = 10.0
    min_cash_apport: float = 5_000.0
    reference_project_cost: float = 0.0
    reference_apport: float = 0.0

    @classmethod
    def from_strategy(
        cls,
        strategy: Strategy,
        *,
        min_equity_ratio_pct: float = 10.0,
        min_cash_apport: float = 5_000.0,
    ) -> FinancingPolicy:
        return cls(
            min_equity_ratio_pct=min_equity_ratio_pct,
            min_cash_apport=min_cash_apport,
            reference_project_cost=project_cost(strategy),
            reference_apport=strategy.apport,
        )

    @property
    def effective_equity_ratio_pct(self) -> float:
        if self.reference_project_cost <= 0 or self.reference_apport <= 0:
            return self.min_equity_ratio_pct
        reference_ratio = self.reference_apport / self.reference_project_cost * 100
        return max(self.min_equity_ratio_pct, reference_ratio)

    def apport_for_project_cost(self, cost: float) -> float:
        if cost <= 0:
            return 0.0
        apport = max(self.min_cash_apport, cost * self.effective_equity_ratio_pct / 100)
        return min(round(apport, 2), cost)

    def apply(self, strategy: Strategy) -> Strategy:
        cost = project_cost(strategy)
        return replace(strategy, apport=self.apport_for_project_cost(cost))

    def describe(self) -> str:
        return (
            f"ratio_apport={self.effective_equity_ratio_pct:.2f}%, "
            f"apport_min={self.min_cash_apport:.0f} EUR"
        )
