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
from achat_immo.models import RegimeFiscal, ModeLocation, TypeBien
from achat_immo.search_policy.financing import FinancingPolicy
from achat_immo.stochastic.models import Strategy
from achat_immo.stochastic.distributions import Distribution, TriangularDist, TruncatedNormalDist
from achat_immo.stochastic.scenario_generator import ScenarioGenerator
from achat_immo.stochastic.monte_carlo import MonteCarloRunner
from achat_immo.search_policy.inverse_solver import InverseSolver
from achat_immo.analysis.metrics import summarize_monte_carlo_outputs
from achat_immo.sourcing_agents.content_guard import SourcingAccessBlockedError, ensure_content_accessible
from achat_immo.sourcing_agents.llm_agent import LLMSourcingAgent
from achat_immo.deal_scoring.candidate_property import CandidateProperty
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
) -> dict[str, Distribution]:
    """Construit les distributions d'incertitude utilisées par l'aspirateur.

    Les bornes restent volontairement prudentes : le scoring automatique doit
    plutôt rater une bonne annonce que promouvoir une annonce sur des données
    insuffisantes.
    """

    confidence = (candidate.confiance_loyer or "basse").lower()
    rent = strategy.loyer_hc_mensuel
    if confidence == "haute":
        rent_distribution = TriangularDist(rent * 0.95, rent, rent * 1.03)
    elif confidence == "moyenne":
        rent_distribution = TriangularDist(rent * 0.90, rent, rent * 1.07)
    else:
        rent_distribution = TriangularDist(rent * 0.80, rent, rent * 1.10)

    dpe = (candidate.dpe or "").upper()
    red_flags = " ".join(candidate.red_flags or []).lower()
    has_energy_risk = dpe in {"F", "G"} or "passoire" in red_flags or "dpe" in red_flags
    if has_energy_risk:
        future_works_high = max(2_000.0, strategy.surface_m2 * 120.0)
        future_works_mode = max(500.0, strategy.surface_m2 * 35.0)
    elif strategy.travaux_initiaux > 0:
        future_works_high = max(1_500.0, strategy.travaux_initiaux * 0.12)
        future_works_mode = max(250.0, strategy.travaux_initiaux * 0.03)
    else:
        future_works_high = max(900.0, strategy.surface_m2 * 25.0)
        future_works_mode = max(150.0, strategy.surface_m2 * 8.0)

    return {
        "loyer_hc_mensuel": rent_distribution,
        "vacance_mois_par_an": TruncatedNormalDist(mean=1.2, std=0.8, low=0.0, high=6.0),
        "croissance_loyer_annuelle_pct": TruncatedNormalDist(mean=1.0, std=0.6, low=0.0, high=3.0),
        "inflation_charges_annuelle_pct": TruncatedNormalDist(mean=2.5, std=1.0, low=0.0, high=6.0),
        "travaux_imprevus_annuels": TriangularDist(0.0, future_works_mode, future_works_high),
        "appreciation_bien_annuelle_pct": TruncatedNormalDist(mean=0.5, std=1.4, low=-3.0, high=4.0),
        "decote_revente_pct": TruncatedNormalDist(mean=7.0, std=1.0, low=5.0, high=10.0),
    }


class SourcingOrchestrator:
    def __init__(
        self,
        target_tri: float = 6.0,
        target_coc: float = 0.0,
        target_cf: float = 0.0,
        target_tri_p10: float = 3.0,
    ):
        self.llm_agent = LLMSourcingAgent()
        self.generator = ScenarioGenerator(config={}, seed=42)
        self.runner = MonteCarloRunner()
        self.solver = InverseSolver(self.runner, self.generator)
        
        self.target_tri = target_tri
        self.target_coc = target_coc
        self.target_cf = target_cf
        self.target_tri_p10 = target_tri_p10
        
    def _map_candidate_to_strategy(self, cand: CandidateProperty) -> Strategy:
        # Valeurs par defaut arbitraires si Gemini n'a rien trouvé
        loyer = cand.loyer_estime or (cand.surface * 15.0)  
        charges = (cand.charges_mensuelles * 12) if cand.charges_mensuelles else (cand.surface * 30.0)
        taxe = cand.taxe_fonciere or (cand.surface * 20.0)
        travaux = cand.travaux_visibles or 0.0
        frais_notaire = cand.prix * 0.08
        
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
            apport=15000.0,
            duree_credit_annees=20,
            taux_credit_pct=3.5,
            regime_fiscal=RegimeFiscal.LMNP_REEL,
            mode_location=ModeLocation.MEUBLEE
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
            build_sourcing_stochastic_config(candidate, strategy),
            seed=scenario_seed,
        )
        
        # 1. Simulation Monte Carlo
        logger.info("Exécution du Monte Carlo (1000 scénarios)...")
        outputs = self.runner.run(strategy, generator, n_scenarios=1000)
        summary = summarize_monte_carlo_outputs(outputs)
        
        tri_p50 = summary.get("tri_median")
        tri_p10 = summary.get("tri_p10")
        prob_cf = summary.get("probabilite_cashflow_cumule_positif")
        coc_p50 = summary.get("coc_median")
        cf_p50 = summary.get("cashflow_mensuel_minimal_median")
        
        # 2. Evaluation
        meets_criteria = False
        if tri_p50 is not None and coc_p50 is not None and cf_p50 is not None:
            if (tri_p50 >= self.target_tri and 
                coc_p50 >= self.target_coc and 
                cf_p50 >= self.target_cf):
                meets_criteria = True
                
        statut = "a_analyser" if meets_criteria else "hors_criteres"
        
        # 3. Inverse Solver
        logger.info(f"Exécution du Solveur Inversé (Cibles: TRI>={self.target_tri}%, CoC>={self.target_coc}%, CF>={self.target_cf}€)...")
        solver = InverseSolver(self.runner, generator)
        criteria = solver.find_criteria(
            strategy,
            target_tri_median=self.target_tri,
            target_tri_p10=self.target_tri_p10,
            min_coc_median=self.target_coc,
            min_monthly_cashflow_median=self.target_cf,
            min_prob_positive_cashflow=0.5,
            n_scenarios_per_eval=300,
            financing_policy=financing_policy,
        )
        prix_recommande = criteria.max_price if criteria else None
        
        # 4. Preparation des Records
        notes_str = f"Red Flags: {', '.join(candidate.red_flags) if candidate.red_flags else 'Aucun'}\n"
        notes_str += f"Donnees manquantes: {', '.join(candidate.donnees_manquantes) if candidate.donnees_manquantes else 'Aucune'}"
        notes_str += f"\nSeed scenarios: {scenario_seed}"
        notes_str += f"\nFinancement: {financing_policy.describe()}"
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
                target_tri_median=self.target_tri,
                target_tri_p10=self.target_tri_p10,
                target_coc=self.target_coc,
                target_cashflow=self.target_cf,
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
                    " | ".join(criteria.diagnostics)
                    if criteria
                    else " | ".join(solver.last_diagnostics) or "Aucun prix cible viable."
                ),
            ),
        )
        return annonce_id
