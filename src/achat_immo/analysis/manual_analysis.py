"""Relance manuelle d'analyse financiere pour une annonce stockee."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json

from achat_immo.analysis.metrics import summarize_monte_carlo_outputs
from achat_immo.search_policy.financing import FinancingPolicy
from achat_immo.search_policy.inverse_solver import InverseSolver, SearchCriteria
from achat_immo.stochastic.distributions import Distribution, TriangularDist, TruncatedNormalDist
from achat_immo.stochastic.monte_carlo import MonteCarloRunner
from achat_immo.stochastic.models import Strategy
from achat_immo.stochastic.scenario_generator import ScenarioGenerator
from achat_immo.storage import DatabaseConnection, save_analysis_run, save_annonce
from achat_immo.storage_records import AnalysisRunRecord, AnnonceRecord, HypothesesAchatRecord


HUMAN_MANAGED_STATUSES = {
    "shortlist",
    "a_visiter",
    "a_negocier",
    "favori",
    "contacte",
    "offre_faite",
    "rejete",
    "archive",
}


@dataclass(frozen=True, slots=True)
class AnalysisTargets:
    target_tri_median: float = 6.0
    target_tri_p10: float = 3.0
    target_coc: float = 0.0
    target_cashflow: float = 0.0
    min_prob_positive_cashflow: float = 0.5
    n_scenarios: int = 1000
    n_solver_scenarios: int = 300


@dataclass(frozen=True, slots=True)
class ManualAnalysisResult:
    annonce_id: int
    analysis_run_id: int
    status: str
    scenario_seed: int
    summary: dict[str, object]
    criteria: SearchCriteria | None


def rerun_financial_analysis(
    conn: DatabaseConnection,
    annonce: AnnonceRecord,
    hypotheses: HypothesesAchatRecord,
    *,
    targets: AnalysisTargets | None = None,
    run_source: str = "streamlit_manual",
) -> ManualAnalysisResult:
    """Relance Monte Carlo + solveur inverse sur les donnees deja stockees."""

    if annonce.id is None:
        raise ValueError("L'annonce doit etre sauvegardee avant analyse.")
    targets = targets or AnalysisTargets()
    raw_strategy = strategy_from_records(annonce, hypotheses)
    financing_policy = FinancingPolicy.from_strategy(raw_strategy)
    strategy = financing_policy.apply(raw_strategy)
    scenario_seed = stable_seed(annonce.url or f"annonce:{annonce.id}:{annonce.prix_affiche}")
    generator = ScenarioGenerator(build_manual_stochastic_config(annonce, strategy), seed=scenario_seed)
    runner = MonteCarloRunner()

    outputs = runner.run(strategy, generator, n_scenarios=targets.n_scenarios)
    summary = summarize_monte_carlo_outputs(outputs)
    tri_p50 = summary.get("tri_median")
    tri_p10 = summary.get("tri_p10")
    prob_cf = summary.get("probabilite_cashflow_cumule_positif")
    coc_p50 = summary.get("coc_median")
    cf_p50 = summary.get("cashflow_mensuel_minimal_median")

    solver = InverseSolver(runner, generator)
    criteria = solver.find_criteria(
        strategy,
        target_tri_median=targets.target_tri_median,
        target_tri_p10=targets.target_tri_p10,
        min_coc_median=targets.target_coc,
        min_monthly_cashflow_median=targets.target_cashflow,
        min_prob_positive_cashflow=targets.min_prob_positive_cashflow,
        n_scenarios_per_eval=targets.n_solver_scenarios,
        financing_policy=financing_policy,
    )
    status = _status_after_analysis(annonce.statut, tri_p50, coc_p50, cf_p50, targets)
    updated_annonce = replace(
        annonce,
        statut=status,
        tri_p50=_optional_float(tri_p50),
        tri_p10=_optional_float(tri_p10),
        probabilite_cashflow_positif=_optional_float(prob_cf),
        prix_cible_recommande=criteria.max_price if criteria else None,
        cashflow_p50=_optional_float(cf_p50),
        coc_p50=_optional_float(coc_p50),
    )
    save_annonce(conn, updated_annonce, hypotheses)

    diagnostics = _analysis_diagnostics(run_source, financing_policy, criteria, solver.last_diagnostics)
    analysis_run_id = save_analysis_run(
        conn,
        AnalysisRunRecord(
            annonce_id=annonce.id,
            status=status,
            scenario_seed=scenario_seed,
            nb_scenarios=int(summary.get("nb_scenarios_total", 0)),
            solver_status=criteria.status if criteria else "no_solution",
            solver_iterations=criteria.iterations if criteria else 0,
            price_floor=criteria.price_floor if criteria else None,
            price_ceiling=criteria.price_ceiling if criteria else None,
            target_tri_median=targets.target_tri_median,
            target_tri_p10=targets.target_tri_p10,
            target_coc=targets.target_coc,
            target_cashflow=targets.target_cashflow,
            tri_p50=_optional_float(tri_p50),
            tri_p10=_optional_float(tri_p10),
            probabilite_cashflow_positif=_optional_float(prob_cf),
            coc_p50=_optional_float(coc_p50),
            cashflow_p50=_optional_float(cf_p50),
            recommended_price=criteria.max_price if criteria else None,
            recommended_project_cost=criteria.project_cost if criteria else None,
            recommended_apport=criteria.apport if criteria else None,
            recommended_loan_amount=criteria.loan_amount if criteria else None,
            summary_json=json.dumps(summary, sort_keys=True),
            diagnostics=diagnostics,
        ),
    )
    return ManualAnalysisResult(
        annonce_id=annonce.id,
        analysis_run_id=analysis_run_id,
        status=status,
        scenario_seed=scenario_seed,
        summary=summary,
        criteria=criteria,
    )


def strategy_from_records(annonce: AnnonceRecord, hypotheses: HypothesesAchatRecord) -> Strategy:
    _validate_analysis_inputs(annonce, hypotheses)
    price = annonce.prix_negocie or annonce.prix_affiche
    frais_notaire = hypotheses.frais_notaire_estimes or price * 0.08
    return Strategy(
        ville=annonce.ville or "Inconnue",
        surface_m2=annonce.surface_m2,
        prix_achat=price,
        apport=hypotheses.apport_reference,
        duree_credit_annees=hypotheses.duree_credit_reference,
        taux_credit_pct=hypotheses.taux_credit_reference,
        assurance_emprunteur_pct=hypotheses.assurance_emprunteur_pct,
        regime_fiscal=hypotheses.regime_fiscal,
        mode_location=hypotheses.mode_location,
        loyer_hc_mensuel=hypotheses.loyer_hc_mensuel,
        charges_copro_annuelles=hypotheses.charges_copro_annuelles,
        taxe_fonciere=hypotheses.taxe_fonciere,
        travaux_initiaux=hypotheses.travaux_estimes,
        frais_notaire_estimes=frais_notaire,
        frais_agence_achat=hypotheses.frais_agence_achat,
        frais_gestion_pct=hypotheses.frais_gestion_pct,
        gestion_agence_active=hypotheses.gestion_agence_possible,
    )


def build_manual_stochastic_config(
    annonce: AnnonceRecord,
    strategy: Strategy,
) -> dict[str, Distribution]:
    rent = strategy.loyer_hc_mensuel
    dpe = (annonce.dpe or "").upper()
    notes = (annonce.notes or "").lower()
    has_energy_risk = dpe in {"F", "G"} or "passoire" in notes
    if has_energy_risk:
        works_mode = max(500.0, strategy.surface_m2 * 35.0)
        works_high = max(2_000.0, strategy.surface_m2 * 120.0)
    elif strategy.travaux_initiaux > 0:
        works_mode = max(250.0, strategy.travaux_initiaux * 0.03)
        works_high = max(1_500.0, strategy.travaux_initiaux * 0.12)
    else:
        works_mode = max(150.0, strategy.surface_m2 * 8.0)
        works_high = max(900.0, strategy.surface_m2 * 25.0)

    return {
        "loyer_hc_mensuel": TriangularDist(rent * 0.90, rent, rent * 1.07),
        "vacance_mois_par_an": TruncatedNormalDist(mean=1.2, std=0.8, low=0.0, high=6.0),
        "croissance_loyer_annuelle_pct": TruncatedNormalDist(mean=1.0, std=0.6, low=0.0, high=3.0),
        "inflation_charges_annuelle_pct": TruncatedNormalDist(mean=2.5, std=1.0, low=0.0, high=6.0),
        "travaux_imprevus_annuels": TriangularDist(0.0, works_mode, works_high),
        "appreciation_bien_annuelle_pct": TruncatedNormalDist(mean=0.5, std=1.4, low=-3.0, high=4.0),
        "decote_revente_pct": TruncatedNormalDist(mean=7.0, std=1.0, low=5.0, high=10.0),
    }


def stable_seed(value: str, fallback: int = 42) -> int:
    if not value:
        return fallback
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big")


def _status_after_analysis(
    current_status: str,
    tri_p50: object,
    coc_p50: object,
    cf_p50: object,
    targets: AnalysisTargets,
) -> str:
    if current_status in HUMAN_MANAGED_STATUSES:
        return current_status
    meets_criteria = (
        tri_p50 is not None
        and coc_p50 is not None
        and cf_p50 is not None
        and float(tri_p50) >= targets.target_tri_median
        and float(coc_p50) >= targets.target_coc
        and float(cf_p50) >= targets.target_cashflow
    )
    return "a_verifier" if meets_criteria else "hors_criteres"


def _analysis_diagnostics(
    run_source: str,
    financing_policy: FinancingPolicy,
    criteria: SearchCriteria | None,
    solver_diagnostics: list[str],
) -> str:
    parts = [f"source={run_source}", f"financement={financing_policy.describe()}"]
    if criteria is not None:
        parts.append(f"solveur={criteria.status}")
        parts.extend(criteria.diagnostics)
    else:
        parts.append("solveur=no_solution")
        parts.extend(solver_diagnostics)
    return " | ".join(part for part in parts if part)


def _validate_analysis_inputs(annonce: AnnonceRecord, hypotheses: HypothesesAchatRecord) -> None:
    if annonce.prix_affiche <= 0 and not annonce.prix_negocie:
        raise ValueError("Prix affiche ou negocie requis pour relancer l'analyse.")
    if annonce.surface_m2 <= 0:
        raise ValueError("Surface positive requise pour relancer l'analyse.")
    if hypotheses.loyer_hc_mensuel <= 0:
        raise ValueError("Loyer mensuel positif requis pour relancer l'analyse.")
    if hypotheses.duree_credit_reference <= 0:
        raise ValueError("Duree de credit positive requise pour relancer l'analyse.")


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
