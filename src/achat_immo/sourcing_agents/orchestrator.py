"""Orchestrateur pour lier le Sourcing IA, le Monte Carlo, le Solveur et la Base de Données."""

import logging
from achat_immo.storage_records import AnnonceRecord, HypothesesAchatRecord
from achat_immo.models import RegimeFiscal, ModeLocation, TypeBien
from achat_immo.stochastic.models import Strategy
from achat_immo.stochastic.scenario_generator import ScenarioGenerator
from achat_immo.stochastic.monte_carlo import MonteCarloRunner
from achat_immo.search_policy.inverse_solver import InverseSolver
from achat_immo.analysis.metrics import summarize_monte_carlo_outputs
from achat_immo.sourcing_agents.llm_agent import LLMSourcingAgent
from achat_immo.deal_scoring.candidate_property import CandidateProperty
from achat_immo.storage import DatabaseConnection, save_annonce

logger = logging.getLogger(__name__)

class SourcingOrchestrator:
    def __init__(self, target_tri: float = 6.0, target_coc: float = 0.0, target_cf: float = 0.0):
        self.llm_agent = LLMSourcingAgent()
        self.generator = ScenarioGenerator(config={})
        self.runner = MonteCarloRunner()
        self.solver = InverseSolver(self.runner, self.generator)
        
        self.target_tri = target_tri
        self.target_coc = target_coc
        self.target_cf = target_cf
        
    def _map_candidate_to_strategy(self, cand: CandidateProperty) -> Strategy:
        # Valeurs par defaut arbitraires si Gemini n'a rien trouvé
        loyer = cand.loyer_estime or (cand.surface * 15.0)  
        charges = (cand.charges_mensuelles * 12) if cand.charges_mensuelles else (cand.surface * 30.0)
        taxe = cand.taxe_fonciere or (cand.surface * 20.0)
        travaux = cand.travaux_visibles or 0.0
        
        return Strategy(
            ville=cand.ville,
            surface_m2=cand.surface,
            prix_achat=cand.prix,
            loyer_hc_mensuel=loyer,
            charges_copro_annuelles=charges,
            taxe_fonciere=taxe,
            travaux_initiaux=travaux,
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
        original_url = self.llm_agent.extract_original_link(text)
        final_url = original_url if original_url else url
        
        candidate = self.llm_agent.extract_from_text(text, source_url=final_url)
        strategy = self._map_candidate_to_strategy(candidate)
        
        # 1. Simulation Monte Carlo
        logger.info("Exécution du Monte Carlo (1000 scénarios)...")
        outputs = self.runner.run(strategy, self.generator, n_scenarios=1000)
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
        criteria = self.solver.find_criteria(
            strategy,
            target_tri_median=self.target_tri,
            min_coc_median=self.target_coc,
            min_monthly_cashflow_median=self.target_cf,
            min_prob_positive_cashflow=0.5,
            n_scenarios_per_eval=100
        )
        prix_recommande = criteria.max_price if criteria else None
        
        # 4. Preparation des Records
        notes_str = f"Red Flags: {', '.join(candidate.red_flags) if candidate.red_flags else 'Aucun'}\n"
        notes_str += f"Donnees manquantes: {', '.join(candidate.donnees_manquantes) if candidate.donnees_manquantes else 'Aucune'}"
        
        annonce = AnnonceRecord(
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
            travaux_estimes=strategy.travaux_initiaux,
            loyer_hc_mensuel=strategy.loyer_hc_mensuel,
            charges_copro_annuelles=strategy.charges_copro_annuelles,
            taxe_fonciere=strategy.taxe_fonciere,
            mode_location=strategy.mode_location,
        )
        
        # 5. Sauvegarde
        logger.info(f"Sauvegarde en base de données. Statut: {statut}")
        annonce_id = save_annonce(conn, annonce, hypotheses)
        return annonce_id
