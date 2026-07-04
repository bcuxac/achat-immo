"""Vue Parametres / Automatisation."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from achat_immo.city_profiles import supported_city_labels
from achat_immo.models import RegimeFiscal
from achat_immo.storage import (
    DatabaseConnection,
    get_investment_profile,
    list_investment_profile_versions,
    list_sourcing_queue,
    list_sourcing_runs,
    list_viability_maps,
    save_investment_profile,
)
from app.runtime_config import configured_database_url, configured_gemini_api_key


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCING_WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "sourcing.yml"
GITHUB_ACTIONS_URL = "https://github.com/bcuxac/achat-immo/actions/workflows/sourcing.yml"
DEFAULT_ALLOWED_DOMAINS = "jinka.fr,leboncoin.fr,seloger.com,bienici.com,pap.fr"


def automation_page(conn: DatabaseConnection, *, database_target: str) -> None:
    st.header("Parametres / Automatisation")
    _render_investment_profile(conn)
    _render_viability_maps(conn)
    _render_runtime_status(database_target)
    _render_github_actions_status(conn)
    _render_sourcing_policy()


def _render_viability_maps(conn: DatabaseConnection) -> None:
    st.subheader("Cartes de viabilite")
    rows = list_viability_maps(conn, limit=10)
    if not rows:
        st.warning(
            "Aucune carte active. Le sourcing continuera en analyse approfondie sans prefiltrage. "
            "Lance le workflow GitHub 'Cartographie de viabilite' ou le script local."
        )
        return
    latest = rows[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ville", str(latest["city"]))
    c2.metric("Points", int(latest["point_count"]))
    c3.metric("Points viables", int(latest["viable_count"]))
    c4.metric("Active", "oui" if latest["active"] else "non")
    if int(latest["viable_count"]) == 0:
        st.warning("Cette carte ne contient aucun point viable : elle est non conclusive et ne rejettera aucune annonce.")
    with st.expander("Historique des cartes", expanded=False):
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _render_investment_profile(conn: DatabaseConnection) -> None:
    profile = get_investment_profile(conn)
    st.subheader("Profil d'investissement")
    st.caption(
        "Ces valeurs pilotent la future cartographie et les analyses approfondies. "
        f"Configuration active : {profile.fingerprint[:12]}."
    )
    if not profile.credit_rate_updated_on or not profile.credit_rate_source:
        st.warning("Le taux de credit actif n'est pas encore date et source.")
    city_options = list(supported_city_labels())
    if profile.target_city not in city_options:
        city_options.append(profile.target_city)
    regime_options = list(RegimeFiscal)

    with st.form("investment_profile_form"):
        st.markdown("**Budget et financement**")
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Nom du profil", value=profile.name)
        city = c2.selectbox(
            "Ville cible",
            options=city_options,
            index=city_options.index(profile.target_city),
        )
        tax_regime = c3.selectbox(
            "Regime fiscal de reference",
            options=regime_options,
            index=regime_options.index(profile.reference_tax_regime),
            format_func=lambda value: value.value,
        )

        c1, c2, c3, c4 = st.columns(4)
        budget_min = c1.number_input("Budget total min", min_value=1_000.0, value=profile.total_budget_min, step=5_000.0)
        budget_max = c2.number_input("Budget total max", min_value=1_000.0, value=profile.total_budget_max, step=5_000.0)
        equity_min = c3.number_input("Apport min", min_value=0.0, value=profile.equity_min, step=1_000.0)
        equity_max = c4.number_input("Apport max", min_value=0.0, value=profile.equity_max, step=1_000.0)

        c1, c2, c3, c4 = st.columns(4)
        credit_duration = c1.number_input(
            "Duree du credit (ans)", min_value=1, max_value=30, value=profile.credit_duration_years, step=1
        )
        credit_rate = c2.number_input(
            "Taux du credit (%)", min_value=0.0, max_value=20.0, value=profile.credit_rate_pct, step=0.05
        )
        insurance_rate = c3.number_input(
            "Assurance emprunteur (%)",
            min_value=0.0,
            max_value=10.0,
            value=profile.borrower_insurance_pct,
            step=0.05,
        )
        holding_horizon = c4.number_input(
            "Horizon de detention (ans)", min_value=1, max_value=50, value=profile.holding_horizon_years, step=1
        )
        c1, c2 = st.columns(2)
        rate_updated_on = c1.text_input(
            "Date de reference du taux",
            value=profile.credit_rate_updated_on,
            placeholder="AAAA-MM-JJ",
        )
        rate_source = c2.text_input("Source du taux", value=profile.credit_rate_source)

        c1, c2, c3, c4 = st.columns(4)
        tmi = c1.number_input("TMI (%)", min_value=0.0, max_value=100.0, value=profile.marginal_tax_rate_pct, step=1.0)
        notary_cost = c2.number_input(
            "Frais de notaire (%)", min_value=0.0, max_value=20.0, value=profile.notary_cost_pct, step=0.5
        )
        management_enabled = c3.checkbox("Gestion agence", value=profile.management_enabled)
        management_fee = c4.number_input(
            "Frais de gestion (%)", min_value=0.0, max_value=30.0, value=profile.management_fee_pct, step=0.5
        )

        st.markdown("**Objectifs de viabilite**")
        c1, c2, c3, c4, c5 = st.columns(5)
        target_tri = c1.number_input("TRI median min (%)", value=profile.target_tri_median, step=0.5)
        target_tri_p10 = c2.number_input("TRI P10 min (%)", value=profile.target_tri_p10, step=0.5)
        target_coc = c3.number_input("Cash-on-cash min (%)", value=profile.target_cash_on_cash, step=0.5)
        target_cf = c4.number_input("Cash-flow prudent min", value=profile.target_monthly_cashflow, step=25.0)
        target_probability_pct = c5.number_input(
            "Probabilite CF+ min (%)",
            min_value=0.0,
            max_value=100.0,
            value=profile.min_positive_cashflow_probability * 100,
            step=5.0,
        )

        with st.expander("Budgets de calcul", expanded=False):
            c1, c2, c3, c4, c5 = st.columns(5)
            detailed_scenarios = c1.number_input(
                "Scenarios analyse", min_value=1, value=profile.detailed_scenario_count, step=100
            )
            solver_scenarios = c2.number_input(
                "Scenarios solveur", min_value=1, value=profile.solver_scenario_count, step=50
            )
            map_properties = c3.number_input(
                "Biens hypothetiques", min_value=1, value=profile.map_property_count, step=16
            )
            map_scenarios = c4.number_input(
                "Scenarios par bien", min_value=1, value=profile.map_scenarios_per_property, step=10
            )
            map_workers = c5.number_input(
                "Workers carte", min_value=1, max_value=32, value=profile.map_worker_count, step=1
            )

        with st.expander("Hypotheses economiques avancees", expanded=False):
            c1, c2, c3 = st.columns(3)
            rent_low = c1.number_input("Loyer multiplicateur bas", value=profile.rent_multiplier_low, step=0.01)
            rent_mode = c2.number_input("Loyer multiplicateur central", value=profile.rent_multiplier_mode, step=0.01)
            rent_high = c3.number_input("Loyer multiplicateur haut", value=profile.rent_multiplier_high, step=0.01)

            c1, c2, c3 = st.columns(3)
            vacancy_mean = c1.number_input("Vacance moyenne (mois)", value=profile.vacancy_mean_months, step=0.1)
            vacancy_std = c2.number_input("Ecart-type vacance", min_value=0.0, value=profile.vacancy_std_months, step=0.1)
            vacancy_max = c3.number_input("Vacance maximale", value=profile.vacancy_max_months, step=0.5)

            c1, c2, c3, c4, c5, c6 = st.columns(6)
            rent_growth_mean = c1.number_input(
                "Croissance loyer moyenne (%)", value=profile.annual_rent_growth_mean_pct, step=0.1
            )
            rent_growth_std = c2.number_input(
                "Ecart-type croissance loyer", min_value=0.0, value=profile.annual_rent_growth_std_pct, step=0.1
            )
            rent_growth_min = c3.number_input(
                "Croissance loyer min (%)", value=profile.annual_rent_growth_min_pct, step=0.1
            )
            rent_growth_max = c4.number_input(
                "Croissance loyer max (%)", value=profile.annual_rent_growth_max_pct, step=0.1
            )
            charge_inflation_mean = c5.number_input(
                "Inflation charges moyenne (%)", value=profile.annual_charge_inflation_mean_pct, step=0.1
            )
            charge_inflation_std = c6.number_input(
                "Ecart-type inflation charges",
                min_value=0.0,
                value=profile.annual_charge_inflation_std_pct,
                step=0.1,
            )
            c1, c2 = st.columns(2)
            charge_inflation_min = c1.number_input(
                "Inflation charges min (%)", value=profile.annual_charge_inflation_min_pct, step=0.1
            )
            charge_inflation_max = c2.number_input(
                "Inflation charges max (%)", value=profile.annual_charge_inflation_max_pct, step=0.1
            )

            c1, c2, c3, c4 = st.columns(4)
            appreciation_mean = c1.number_input(
                "Appreciation moyenne (%)", value=profile.annual_appreciation_mean_pct, step=0.1
            )
            appreciation_std = c2.number_input(
                "Ecart-type appreciation", min_value=0.0, value=profile.annual_appreciation_std_pct, step=0.1
            )
            appreciation_min = c3.number_input(
                "Appreciation minimale (%)", value=profile.annual_appreciation_min_pct, step=0.5
            )
            appreciation_max = c4.number_input(
                "Appreciation maximale (%)", value=profile.annual_appreciation_max_pct, step=0.5
            )

            c1, c2, c3, c4 = st.columns(4)
            resale_mean = c1.number_input("Frais revente moyens (%)", value=profile.resale_cost_mean_pct, step=0.5)
            resale_std = c2.number_input(
                "Ecart-type frais revente", min_value=0.0, value=profile.resale_cost_std_pct, step=0.1
            )
            resale_min = c3.number_input("Frais revente min (%)", value=profile.resale_cost_min_pct, step=0.5)
            resale_max = c4.number_input("Frais revente max (%)", value=profile.resale_cost_max_pct, step=0.5)

            c1, c2 = st.columns(2)
            works_mode = c1.number_input(
                "Travaux imprevus centraux EUR/m2/an",
                min_value=0.0,
                value=profile.unexpected_works_mode_per_m2,
                step=1.0,
            )
            works_max = c2.number_input(
                "Travaux imprevus max EUR/m2/an",
                min_value=0.0,
                value=profile.unexpected_works_max_per_m2,
                step=5.0,
            )

        submitted = st.form_submit_button("Enregistrer une nouvelle version", type="primary")

    if submitted:
        try:
            updated = replace(
                profile,
                name=name,
                target_city=city,
                total_budget_min=float(budget_min),
                total_budget_max=float(budget_max),
                equity_min=float(equity_min),
                equity_max=float(equity_max),
                credit_duration_years=int(credit_duration),
                credit_rate_pct=float(credit_rate),
                credit_rate_updated_on=rate_updated_on,
                credit_rate_source=rate_source,
                borrower_insurance_pct=float(insurance_rate),
                holding_horizon_years=int(holding_horizon),
                marginal_tax_rate_pct=float(tmi),
                reference_tax_regime=tax_regime,
                management_enabled=bool(management_enabled),
                management_fee_pct=float(management_fee),
                notary_cost_pct=float(notary_cost),
                target_tri_median=float(target_tri),
                target_tri_p10=float(target_tri_p10),
                target_cash_on_cash=float(target_coc),
                target_monthly_cashflow=float(target_cf),
                min_positive_cashflow_probability=float(target_probability_pct) / 100,
                detailed_scenario_count=int(detailed_scenarios),
                solver_scenario_count=int(solver_scenarios),
                map_property_count=int(map_properties),
                map_scenarios_per_property=int(map_scenarios),
                map_worker_count=int(map_workers),
                rent_multiplier_low=float(rent_low),
                rent_multiplier_mode=float(rent_mode),
                rent_multiplier_high=float(rent_high),
                vacancy_mean_months=float(vacancy_mean),
                vacancy_std_months=float(vacancy_std),
                vacancy_max_months=float(vacancy_max),
                annual_rent_growth_mean_pct=float(rent_growth_mean),
                annual_rent_growth_std_pct=float(rent_growth_std),
                annual_rent_growth_min_pct=float(rent_growth_min),
                annual_rent_growth_max_pct=float(rent_growth_max),
                annual_charge_inflation_mean_pct=float(charge_inflation_mean),
                annual_charge_inflation_std_pct=float(charge_inflation_std),
                annual_charge_inflation_min_pct=float(charge_inflation_min),
                annual_charge_inflation_max_pct=float(charge_inflation_max),
                annual_appreciation_mean_pct=float(appreciation_mean),
                annual_appreciation_std_pct=float(appreciation_std),
                annual_appreciation_min_pct=float(appreciation_min),
                annual_appreciation_max_pct=float(appreciation_max),
                resale_cost_mean_pct=float(resale_mean),
                resale_cost_std_pct=float(resale_std),
                resale_cost_min_pct=float(resale_min),
                resale_cost_max_pct=float(resale_max),
                unexpected_works_mode_per_m2=float(works_mode),
                unexpected_works_max_per_m2=float(works_max),
            )
            version_id = save_investment_profile(conn, updated)
        except ValueError as exc:
            st.error(f"Profil invalide : {exc}")
        else:
            st.success(f"Profil sauvegarde dans la version #{version_id}.")
            st.rerun()

    versions = list_investment_profile_versions(conn, limit=10)
    if versions:
        with st.expander("Historique du profil", expanded=False):
            history = pd.DataFrame(versions)
            history["config_hash"] = history["config_hash"].str.slice(0, 12)
            st.dataframe(history, hide_index=True, width="stretch")


def _render_runtime_status(database_target: str) -> None:
    st.subheader("Configuration runtime")
    rows = [
        {
            "element": "DATABASE_URL",
            "statut": _configured_label(bool(configured_database_url())),
            "usage": "Base partagee entre Streamlit, CLI et GitHub Actions",
        },
        {
            "element": "GEMINI_API_KEY",
            "statut": _configured_label(bool(configured_gemini_api_key())),
            "usage": "Extraction LLM et traitement de la queue",
        },
        {
            "element": "Base active",
            "statut": "PostgreSQL" if configured_database_url() else "SQLite",
            "usage": _database_target_label(database_target),
        },
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _render_github_actions_status(conn: DatabaseConnection) -> None:
    st.subheader("Automatisation sourcing")
    queue_rows = list_sourcing_queue(conn)
    run_rows = list_sourcing_runs(conn, limit=10)
    pending_count = sum(1 for row in queue_rows if row.get("status") == "pending")
    blocked_count = sum(1 for row in queue_rows if row.get("status") == "blocked")
    failed_count = sum(1 for row in queue_rows if row.get("status") == "failed")
    latest_run = run_rows[0] if run_rows else {}

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Workflow present dans le code", "oui" if SOURCING_WORKFLOW_PATH.exists() else "non")
    c2.metric("URLs a analyser", pending_count)
    c3.metric("A corriger", failed_count + blocked_count)
    c4.metric("Dernier traitement", str(latest_run.get("status") or "absent"))
    st.caption("Execution planifiee : tous les jours vers 07:17 heure de Paris, plus declenchement manuel GitHub.")
    st.link_button("Ouvrir GitHub Actions", GITHUB_ACTIONS_URL)

    if run_rows:
        with st.expander("Voir les derniers traitements", expanded=False):
            st.dataframe(pd.DataFrame(run_rows).head(10), hide_index=True, width="stretch")
    else:
        st.info("Aucun traitement automatique trace.")


def _render_sourcing_policy() -> None:
    st.subheader("Politique de sourcing")
    allowed_domains = os.environ.get("SOURCING_ALLOWED_DOMAINS", DEFAULT_ALLOWED_DOMAINS)
    rows: list[dict[str, Any]] = [
        {
            "parametre": "Domaines autorises",
            "valeur": allowed_domains,
        },
        {
            "parametre": "Limite URLs par run",
            "valeur": os.environ.get("SOURCING_LIMIT", "20"),
        },
        {
            "parametre": "Limite par source",
            "valeur": os.environ.get("SOURCING_SOURCE_LIMIT", "3"),
        },
        {
            "parametre": "Prefiltre URL",
            "valeur": "actif",
        },
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _configured_label(is_configured: bool) -> str:
    return "configure" if is_configured else "absent"


def _database_target_label(database_target: str) -> str:
    if configured_database_url():
        return "URL configuree"
    return database_target
