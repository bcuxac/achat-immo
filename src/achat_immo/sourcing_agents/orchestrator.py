"""Orchestrateur pour lier le Sourcing IA, le Monte Carlo, le Solveur et la Base de Données."""

import hashlib
import json
import logging
from achat_immo.storage_records import (
    AnalysisRunRecord,
    AnnonceRecord,
    ExtractionRunRecord,
    HypothesesAchatRecord,
)
from achat_immo.models import ModeLocation, TypeBien
from achat_immo.investment_profile import InvestmentProfile
from achat_immo.search_policy.financing import FinancingPolicy
from achat_immo.qualification import ProfitabilityTargets, evaluate_monte_carlo_summary
from achat_immo.stochastic.models import Strategy
from achat_immo.stochastic.distributions import Distribution, TriangularDist, TruncatedNormalDist
from achat_immo.stochastic.assumptions import StochasticAssumptions
from achat_immo.stochastic.scenario_generator import ScenarioGenerator
from achat_immo.stochastic.monte_carlo import MonteCarloRunner
from achat_immo.search_policy.inverse_solver import InverseSolver
from achat_immo.analysis.metrics import summarize_monte_carlo_outputs
from achat_immo.sourcing_agents.content_guard import SourcingAccessBlockedError, ensure_content_accessible
from achat_immo.sourcing_agents.llm_agent import LLMSourcingAgent
from achat_immo.sourcing_agents.models import CandidateProperty
from achat_immo.storage import (
    DatabaseConnection,
    find_annonce_id_by_url,
    normalize_source_url,
    save_analysis_run,
    save_annonce,
    save_extraction_run,
)

logger = logging.getLogger(__name__)


def stable_seed(value: str, fallback: int = 42) -> int:
    """Construit une seed reproductible depuis une URL ou une clé métier."""

    if not value:
        return fallback
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big")


def build_sourcing_stochastic_config(
    candidate: CandidateProperty,
    strategy: Strategy,
    assumptions: StochasticAssumptions | None = None,
) -> dict[str, Distribution]:
    """Construit les distributions d'incertitude utilisées par l'aspirateur.

    Les bornes restent prudentes et explicites. Les donnees insuffisantes sont
    signalees separement afin de ne pas transformer une valeur de repli en fait.
    """

    assumptions = assumptions or StochasticAssumptions()
    confidence = (candidate.confiance_loyer or "basse").lower()
    rent = strategy.loyer_hc_mensuel
    if confidence == "haute":
        rent_distribution = TriangularDist(
            rent
            * (
                assumptions.rent_multiplier_mode
                - (assumptions.rent_multiplier_mode - assumptions.rent_multiplier_low) * 0.5
            ),
            rent * assumptions.rent_multiplier_mode,
            rent
            * (
                assumptions.rent_multiplier_mode
                + (assumptions.rent_multiplier_high - assumptions.rent_multiplier_mode) * 0.5
            ),
        )
    elif confidence == "moyenne":
        rent_distribution = TriangularDist(
            rent * assumptions.rent_multiplier_low,
            rent * assumptions.rent_multiplier_mode,
            rent * assumptions.rent_multiplier_high,
        )
    else:
        rent_distribution = TriangularDist(
            rent
            * max(
                0.0,
                assumptions.rent_multiplier_mode
                - (assumptions.rent_multiplier_mode - assumptions.rent_multiplier_low) * 2,
            ),
            rent * assumptions.rent_multiplier_mode,
            rent
            * (
                assumptions.rent_multiplier_mode
                + (assumptions.rent_multiplier_high - assumptions.rent_multiplier_mode) * 2
            ),
        )

    dpe = (candidate.dpe or "").upper()
    red_flags = " ".join(candidate.red_flags or []).lower()
    has_energy_risk = dpe in {"F", "G"} or "passoire" in red_flags or "dpe" in red_flags
    if has_energy_risk:
        future_works_high = max(2_000.0, strategy.surface_m2 * assumptions.unexpected_works_max_per_m2)
        future_works_mode = max(500.0, strategy.surface_m2 * assumptions.unexpected_works_mode_per_m2)
    elif strategy.travaux_initiaux > 0:
        future_works_high = max(
            strategy.surface_m2 * assumptions.unexpected_works_max_per_m2,
            strategy.travaux_initiaux * 0.12,
        )
        future_works_mode = max(
            strategy.surface_m2 * assumptions.unexpected_works_mode_per_m2,
            strategy.travaux_initiaux * 0.03,
        )
    else:
        future_works_high = strategy.surface_m2 * assumptions.unexpected_works_max_per_m2
        future_works_mode = strategy.surface_m2 * assumptions.unexpected_works_mode_per_m2

    return {
        "loyer_hc_mensuel": rent_distribution,
        "vacance_mois_par_an": TruncatedNormalDist(
            mean=assumptions.vacancy_mean_months,
            std=assumptions.vacancy_std_months,
            low=0.0,
            high=assumptions.vacancy_max_months,
        ),
        "croissance_loyer_annuelle_pct": TruncatedNormalDist(
            mean=assumptions.annual_rent_growth_mean_pct,
            std=assumptions.annual_rent_growth_std_pct,
            low=assumptions.annual_rent_growth_min_pct,
            high=assumptions.annual_rent_growth_max_pct,
        ),
        "inflation_charges_annuelle_pct": TruncatedNormalDist(
            mean=assumptions.annual_charge_inflation_mean_pct,
            std=assumptions.annual_charge_inflation_std_pct,
            low=assumptions.annual_charge_inflation_min_pct,
            high=assumptions.annual_charge_inflation_max_pct,
        ),
        "travaux_imprevus_annuels": TriangularDist(0.0, future_works_mode, future_works_high),
        "appreciation_bien_annuelle_pct": TruncatedNormalDist(
            mean=assumptions.annual_appreciation_mean_pct,
            std=assumptions.annual_appreciation_std_pct,
            low=assumptions.annual_appreciation_min_pct,
            high=assumptions.annual_appreciation_max_pct,
        ),
        "decote_revente_pct": TruncatedNormalDist(
            mean=assumptions.resale_cost_mean_pct,
            std=assumptions.resale_cost_std_pct,
            low=assumptions.resale_cost_min_pct,
            high=assumptions.resale_cost_max_pct,
        ),
    }


class SourcingOrchestrator:
    def __init__(
        self,
        profile: InvestmentProfile | None = None,
        target_tri: float | None = None,
        target_coc: float | None = None,
        target_cf: float | None = None,
        target_tri_p10: float | None = None,
    ):
        self.profile = profile or InvestmentProfile()
        self.llm_agent = LLMSourcingAgent()
        self.runner = MonteCarloRunner()
        self.targets = ProfitabilityTargets(
            target_tri_median=self.profile.target_tri_median if target_tri is None else target_tri,
            target_tri_p10=self.profile.target_tri_p10 if target_tri_p10 is None else target_tri_p10,
            target_coc=self.profile.target_cash_on_cash if target_coc is None else target_coc,
            target_cashflow=self.profile.target_monthly_cashflow if target_cf is None else target_cf,
            min_prob_positive_cashflow=self.profile.min_positive_cashflow_probability,
        )
        
    def _map_candidate_to_strategy(self, cand: CandidateProperty) -> Strategy:
        # Valeurs par defaut arbitraires si Gemini n'a rien trouvé
        loyer = cand.loyer_estime or (cand.surface * 15.0)  
        charges = (cand.charges_mensuelles * 12) if cand.charges_mensuelles else (cand.surface * 30.0)
        taxe = cand.taxe_fonciere or (cand.surface * 20.0)
        travaux = cand.travaux_visibles or 0.0
        frais_notaire = cand.prix * self.profile.notary_cost_pct / 100
        
        return Strategy(
            ville=cand.ville,
            surface_m2=cand.surface,
            prix_achat=cand.prix,
            loyer_hc_mensuel=loyer,
            charges_copro_annuelles=charges,
            taxe_fonciere=taxe,
            travaux_initiaux=travaux,
            frais_notaire_estimes=frais_notaire,
            # Hypotheses conservatrices standard
            apport=self.profile.equity_max,
            duree_credit_annees=self.profile.credit_duration_years,
            taux_credit_pct=self.profile.credit_rate_pct,
            assurance_emprunteur_pct=self.profile.borrower_insurance_pct,
            tmi_pct=self.profile.marginal_tax_rate_pct,
            regime_fiscal=self.profile.reference_tax_regime,
            mode_location=ModeLocation.MEUBLEE,
            horizon_annees=self.profile.holding_horizon_years,
            gestion_agence_active=self.profile.management_enabled,
            frais_gestion_pct=self.profile.management_fee_pct,
        )

    def process_url(self, conn: DatabaseConnection, url: str) -> int:
        """Télécharge, extrait, simule, résout et sauvegarde. Retourne l'ID."""
        logger.info(f"Début du traitement pour l'URL: {url}")
        
        text = self.llm_agent.fetch_url(url)
        ensure_content_accessible(text)
        original_url = self.llm_agent.extract_original_link(text)
        final_url = original_url if original_url else url
        final_url = normalize_source_url(final_url)
        extraction_warning = ""
        if original_url:
            try:
                original_text = self.llm_agent.fetch_url(final_url)
                ensure_content_accessible(original_text)
                text = original_text
            except (RuntimeError, SourcingAccessBlockedError) as exc:
                extraction_warning = (
                    "Lien original detecte mais inaccessible ; extraction realisee depuis le texte agregateur. "
                    f"Erreur: {exc}"
                )
                logger.warning(extraction_warning)
        
        candidate = self.llm_agent.extract_from_text(text, source_url=final_url)
        existing_annonce_id = find_annonce_id_by_url(conn, final_url)
        raw_strategy = self._map_candidate_to_strategy(candidate)
        financing_policy = FinancingPolicy.from_strategy(raw_strategy)
        strategy = financing_policy.apply(raw_strategy)
        scenario_seed = stable_seed(final_url)
        generator = ScenarioGenerator(
            build_sourcing_stochastic_config(candidate, strategy, self.profile.stochastic_assumptions),
            seed=scenario_seed,
        )
        
        # 1. Simulation Monte Carlo
        logger.info(
            "Exécution du Monte Carlo (%s scénarios)...",
            self.profile.detailed_scenario_count,
        )
        outputs = self.runner.run(strategy, generator, n_scenarios=self.profile.detailed_scenario_count)
        summary = summarize_monte_carlo_outputs(outputs)
        
        tri_p50 = summary.get("tri_median")
        tri_p10 = summary.get("tri_p10")
        prob_cf = summary.get("probabilite_cashflow_cumule_positif")
        coc_p50 = summary.get("coc_median")
        cf_p50 = summary.get("cashflow_mensuel_minimal_median")
        
        # 2. Evaluation
        evaluation = evaluate_monte_carlo_summary(summary, self.targets)
        statut = "a_verifier" if evaluation.meets_targets else "hors_criteres"
        
        # 3. Inverse Solver
        logger.info(
            "Exécution du Solveur Inversé (Cibles: TRI>=%s%%, TRI P10>=%s%%, CoC>=%s%%, CF>=%s EUR)...",
            self.targets.target_tri_median,
            self.targets.target_tri_p10,
            self.targets.target_coc,
            self.targets.target_cashflow,
        )
        solver = InverseSolver(self.runner, generator)
        criteria = solver.find_criteria(
            strategy,
            target_tri_median=self.targets.target_tri_median,
            target_tri_p10=self.targets.target_tri_p10,
            min_coc_median=self.targets.target_coc,
            min_monthly_cashflow_median=self.targets.target_cashflow,
            min_prob_positive_cashflow=self.targets.min_prob_positive_cashflow,
            n_scenarios_per_eval=self.profile.solver_scenario_count,
            financing_policy=financing_policy,
        )
        prix_recommande = criteria.max_price if criteria else None
        
        # 4. Preparation des Records
        notes_str = f"Red Flags: {', '.join(candidate.red_flags) if candidate.red_flags else 'Aucun'}\n"
        notes_str += f"Donnees manquantes: {', '.join(candidate.donnees_manquantes) if candidate.donnees_manquantes else 'Aucune'}"
        notes_str += f"\nSeed scenarios: {scenario_seed}"
        notes_str += f"\nFinancement: {financing_policy.describe()}"
        notes_str += f"\nProfil: {self.profile.fingerprint[:12]}"
        notes_str += f"\nQualification: {' | '.join(evaluation.reasons) or 'seuils_atteints'}"
        if criteria:
            notes_str += f"\nSolveur: {criteria.status}, iterations={criteria.iterations}, scenarios={criteria.n_scenarios}"
            notes_str += f"\nDiagnostics solveur: {' | '.join(criteria.diagnostics)}"
        else:
            notes_str += f"\nDiagnostics solveur: {' | '.join(solver.last_diagnostics) or 'Aucun prix cible viable.'}"
        if extraction_warning:
            notes_str += f"\nAvertissement extraction: {extraction_warning}"
        notes_str += "\nDetails techniques: voir extraction_runs et analysis_runs."
        
        annonce = AnnonceRecord(
            id=existing_annonce_id,
            url=candidate.url,
            ville=candidate.ville,
            quartier=candidate.quartier,
            surface_m2=candidate.surface,
            prix_affiche=candidate.prix,
            dpe=candidate.dpe,
            statut=statut,
            notes=notes_str,
            tri_p50=tri_p50,
            tri_p10=tri_p10,
            probabilite_cashflow_positif=prob_cf,
            prix_cible_recommande=prix_recommande,
            cashflow_p50=cf_p50,
            coc_p50=coc_p50,
            # Arbitrary fallback if missing
            type_bien=TypeBien.T2
        )
        
        hypotheses = HypothesesAchatRecord(
            frais_notaire_estimes=strategy.frais_notaire_estimes,
            travaux_estimes=strategy.travaux_initiaux,
            loyer_hc_mensuel=strategy.loyer_hc_mensuel,
            charges_copro_annuelles=strategy.charges_copro_annuelles,
            taxe_fonciere=strategy.taxe_fonciere,
            mode_location=strategy.mode_location,
        )
        
        # 5. Sauvegarde
        logger.info(f"Sauvegarde en base de données. Statut: {statut}")
        annonce_id = save_annonce(conn, annonce, hypotheses)
        save_extraction_run(
            conn,
            ExtractionRunRecord(
                annonce_id=annonce_id,
                source_url=url,
                final_url=final_url,
                status="success_with_warning" if extraction_warning else "success",
                model="gemini-2.5-flash",
                input_chars=len(text),
                raw_content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                extracted_source=candidate.source,
                red_flags=", ".join(candidate.red_flags),
                missing_fields=", ".join(candidate.donnees_manquantes),
                error_message=extraction_warning,
            ),
        )
        save_analysis_run(
            conn,
            AnalysisRunRecord(
                annonce_id=annonce_id,
                status=statut,
                scenario_seed=scenario_seed,
                nb_scenarios=int(summary.get("nb_scenarios_total", 0)),
                solver_status=criteria.status if criteria else "no_solution",
                solver_iterations=criteria.iterations if criteria else 0,
                price_floor=criteria.price_floor if criteria else None,
                price_ceiling=criteria.price_ceiling if criteria else None,
                target_tri_median=self.targets.target_tri_median,
                target_tri_p10=self.targets.target_tri_p10,
                target_coc=self.targets.target_coc,
                target_cashflow=self.targets.target_cashflow,
                tri_p50=tri_p50,
                tri_p10=tri_p10,
                probabilite_cashflow_positif=prob_cf,
                coc_p50=coc_p50,
                cashflow_p50=cf_p50,
                recommended_price=prix_recommande,
                recommended_project_cost=criteria.project_cost if criteria else None,
                recommended_apport=criteria.apport if criteria else None,
                recommended_loan_amount=criteria.loan_amount if criteria else None,
                summary_json=json.dumps(summary, sort_keys=True),
                diagnostics=(
                    f"profil={self.profile.fingerprint[:12]} | " + " | ".join(criteria.diagnostics)
                    if criteria
                    else f"profil={self.profile.fingerprint[:12]} | "
                    + (" | ".join(solver.last_diagnostics) or "Aucun prix cible viable.")
                ),
            ),
        )
        return annonce_id
