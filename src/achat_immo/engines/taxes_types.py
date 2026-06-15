"""Types de donnees pour la fiscalite locative."""

from __future__ import annotations

from dataclasses import dataclass, field

from achat_immo.models import RegimeFiscal


AMORTISSEMENT_COMPONENTS = ("bati", "travaux", "frais_acquisition", "meubles")


@dataclass(slots=True)
class ReportFiscal:
    annee_origine: int
    montant: float


@dataclass(slots=True)
class EtatFiscal:
    """Etat fiscal reporte d'une annee a l'autre pour une simulation."""

    amortissement_reports: dict[str, float] = field(default_factory=dict)
    deficit_lmnp: list[ReportFiscal] = field(default_factory=list)
    deficit_foncier: list[ReportFiscal] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ResultatFiscal:
    regime: RegimeFiscal
    revenus: float
    charges_deductibles: float
    interets: float
    amortissement: float
    resultat_avant_amortissement: float
    resultat_fiscal: float
    impot: float
    amortissement_non_utilise: float = 0.0
    amortissement_utilise: float = 0.0
    amortissement_report_debut: float = 0.0
    amortissement_report_fin: float = 0.0
    amortissement_deduit: float = 0.0
    amortissement_deduit_plus_value: float = 0.0
    deficit_report_debut: float = 0.0
    deficit_report_fin: float = 0.0
    deficit_utilise: float = 0.0
    deficit_genere: float = 0.0
    frais_deductibles_exceptionnels: float = 0.0
    amortissement_bati: float = 0.0
    amortissement_travaux: float = 0.0
    amortissement_meubles: float = 0.0
    amortissement_frais_acquisition: float = 0.0
    amortissement_bati_deduit: float = 0.0
    amortissement_travaux_deduit: float = 0.0
    amortissement_meubles_deduit: float = 0.0
    amortissement_frais_acquisition_deduit: float = 0.0
    eligible: bool = True
    avertissements: tuple[str, ...] = ()
