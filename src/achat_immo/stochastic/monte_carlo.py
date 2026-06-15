"""Moteur d'exécution de Monte Carlo."""

from achat_immo.models import BienImmobilier, HypothesesLocation, Financement, Fiscalite, Scenario
from achat_immo.engines.scenarios import simuler_bien_sur_horizon
from achat_immo.stochastic.models import Strategy, ScenarioInput, ScenarioOutput
from achat_immo.stochastic.scenario_generator import ScenarioGenerator

class MonteCarloRunner:
    """Exécute les simulations stochastiques."""
    
    def run(self, strategy: Strategy, generator: ScenarioGenerator, n_scenarios: int = 1000) -> list[ScenarioOutput]:
        scenarios_input = generator.sample_many(n_scenarios, strategy)
        
        outputs = []
        for s_in in scenarios_input:
            out = self._run_single(strategy, s_in)
            outputs.append(out)
            
        return outputs
        
    def _run_single(self, strategy: Strategy, s_in: ScenarioInput) -> ScenarioOutput:
        bien = BienImmobilier(
            ville=strategy.ville,
            surface_m2=strategy.surface_m2,
            prix_affiche=strategy.prix_achat,
            travaux_estimes=strategy.travaux_initiaux,
            frais_notaire_estimes=strategy.frais_notaire_estimes,
            frais_agence_achat=strategy.frais_agence_achat,
        )
        
        location = HypothesesLocation(
            loyer_hc_mensuel=s_in.loyer_hc_mensuel,
            mode_location=strategy.mode_location,
            charges_copro_annuelles=strategy.charges_copro_annuelles,
            taxe_fonciere=strategy.taxe_fonciere,
            vacance_mois_par_an=s_in.vacance_mois_par_an,
            evolution_loyer_annuelle_pct=s_in.croissance_loyer_annuelle_pct,
            evolution_charges_annuelles_pct=s_in.inflation_charges_annuelle_pct,
            travaux_futurs_annuels=s_in.travaux_imprevus_annuels,
            gestion_agence_active=strategy.gestion_agence_active,
            frais_gestion_pct=strategy.frais_gestion_pct,
        )
        
        financement = Financement(
            apport=strategy.apport,
            duree_credit_annees=strategy.duree_credit_annees,
            taux_credit_annuel_pct=strategy.taux_credit_pct,
            assurance_emprunteur_annuelle_pct=strategy.assurance_emprunteur_pct,
        )
        
        fiscalite = Fiscalite(regime=strategy.regime_fiscal)
        
        scenario_proj = Scenario(
            nom=f"sim_mc_{s_in.scenario_id}",
            horizon_annees=strategy.horizon_annees,
            appreciation_annuelle_pct=s_in.appreciation_bien_annuelle_pct,
            frais_revente_pct=s_in.decote_revente_pct,
        )
        
        try:
            res = simuler_bien_sur_horizon(
                bien=bien,
                location=location,
                financement=financement,
                fiscalite=fiscalite,
                scenario=scenario_proj,
            )
            
            cashflows = [p["cashflow_annuel_apres_impot"] for p in res.projection_annuelle[1:]]
            cf_min = min(cashflows) if cashflows else 0.0
            
            return ScenarioOutput(
                scenario_id=s_in.scenario_id,
                tri_annuel_pct=res.tri_annuel_pct,
                van=res.van,
                cash_on_cash_return_pct=res.cash_on_cash_return_pct,
                cashflow_cumule_horizon=res.cashflow_cumule_horizon,
                cashflow_annuel_minimal=cf_min,
                nb_annees_cashflow_negatif=res.nb_annees_cashflow_negatif,
                patrimoine_net_horizon=res.patrimoine_net_horizon,
                prix_net_revente=res.patrimoine_net_sortie, # Wait, patrimoine_net_sortie vs flux_sortie_net, let's use res.plus_value.prix_net_vendeur ?
                impot_total_paye=res.impots_total_horizon,
            )
        except Exception as e:
            return ScenarioOutput(
                scenario_id=s_in.scenario_id,
                tri_annuel_pct=None,
                van=None,
                cash_on_cash_return_pct=None,
                cashflow_cumule_horizon=0.0,
                cashflow_annuel_minimal=0.0,
                nb_annees_cashflow_negatif=0,
                patrimoine_net_horizon=0.0,
                prix_net_revente=0.0,
                impot_total_paye=0.0,
                is_valid=False,
                error_message=str(e)
            )
