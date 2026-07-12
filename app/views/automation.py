"""Vue Parametres / Automatisation."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from achat_immo.city_profiles import profile_for_city, supported_city_labels
from achat_immo.models import RegimeFiscal
from achat_immo.storage import (
    DatabaseConnection,
    get_active_simulation_map,
    get_investment_profile,
    list_annonces,
    list_investment_profile_versions,
    list_sourcing_queue,
    list_sourcing_runs,
    list_simulation_maps,
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
    _render_simulation_maps(conn)
    _render_runtime_status(database_target)
    _render_github_actions_status(conn)
    _render_sourcing_policy()


def _render_simulation_maps(conn: DatabaseConnection) -> None:
    st.subheader("Carte mathematique des simulations")
    profile = get_investment_profile(conn)
    active = get_active_simulation_map(
        conn,
        profile.target_city,
        profile.simulation_fingerprint,
    )
    rows = list_simulation_maps(conn, limit=10)
    if active is None:
        st.warning(
            "Aucune carte active. Le sourcing continuera en analyse approfondie sans prefiltrage. "
            "Lance le workflow GitHub 'Cartographie de viabilite' ou le script local."
        )
        return
    map_id, simulation_map = active
    points = _simulation_points_dataframe(simulation_map)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ville", simulation_map.config.market.city)
    c2.metric("Simulations structurelles", len(points))
    c3.metric("TRI median central", f"{points['tri_median'].median():.2f} %")
    c4.metric("Carte active", f"#{map_id}")
    st.caption(
        "Cette carte ne qualifie et ne rejette aucun point. Les couleurs sont des sorties "
        "numeriques conditionnelles aux entrees affichees dans le profil."
    )
    _render_simulation_scatter(conn, points, simulation_map.config.market.city)
    with st.expander("Historique des cartes", expanded=False):
        history = pd.DataFrame(rows)
        history = history.rename(columns={"profile_hash": "simulation_hash"})
        st.dataframe(history, hide_index=True, width="stretch")


def _simulation_points_dataframe(simulation_map) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "sample_id": point.property.sample_id,
                "sample_kind": point.property.sample_kind,
                "sector": point.property.rent_sector or "sans secteur",
                "room_count": point.property.room_count,
                "surface_m2": point.property.surface_m2,
                "price_per_m2": point.property.price_per_m2,
                "rent_per_m2": point.property.rent_per_m2,
                "project_cost": point.property.total_project_cost,
                "tri_median": point.tri_median,
                "tri_p10": point.tri_p10,
                "cashflow_year1_p10": point.first_year_monthly_cashflow_p10,
                "cashflow_worst_median": point.prudent_monthly_cashflow,
                "coc_median": point.cash_on_cash_median,
            }
            for point in simulation_map.points
        ]
    )


def _render_simulation_scatter(
    conn: DatabaseConnection,
    points: pd.DataFrame,
    city: str,
) -> None:
    metric_labels = {
        "tri_median": "TRI median (%)",
        "tri_p10": "TRI P10 (%)",
        "cashflow_year1_p10": "Cash-flow annee 1 P10 (EUR/mois)",
        "cashflow_worst_median": "Pire cash-flow median (EUR/mois)",
        "coc_median": "Cash-on-cash median (%)",
    }
    c1, c2, c3 = st.columns(3)
    color_metric = c1.selectbox(
        "Couleur",
        options=list(metric_labels),
        format_func=metric_labels.get,
        key="simulation_map_color",
    )
    sample_kinds = sorted(points["sample_kind"].dropna().unique())
    selected_kinds = c2.multiselect(
        "Plan d'experiences",
        options=sample_kinds,
        default=sample_kinds,
        key="simulation_map_sample_kind",
    )
    room_options = sorted(int(value) for value in points["room_count"].dropna().unique())
    selected_rooms = c3.multiselect(
        "Nombre de pieces",
        options=room_options,
        default=room_options,
        key="simulation_map_rooms",
    )
    filtered = points[
        points["sample_kind"].isin(selected_kinds)
        & (points["room_count"].isna() | points["room_count"].isin(selected_rooms))
    ]
    simulation_chart = (
        alt.Chart(filtered)
        .mark_circle(opacity=0.68)
        .encode(
            x=alt.X("price_per_m2:Q", title="Prix d'achat (EUR/m2)"),
            y=alt.Y("rent_per_m2:Q", title="Loyer HC (EUR/m2/mois)"),
            color=alt.Color(f"{color_metric}:Q", title=metric_labels[color_metric]),
            size=alt.Size("project_cost:Q", title="Cout total", scale=alt.Scale(range=[25, 180])),
            tooltip=[
                "sample_id:Q",
                "sample_kind:N",
                "sector:N",
                "room_count:Q",
                alt.Tooltip("surface_m2:Q", format=".1f"),
                alt.Tooltip("price_per_m2:Q", format=".0f"),
                alt.Tooltip("rent_per_m2:Q", format=".2f"),
                alt.Tooltip("tri_median:Q", format=".2f"),
                alt.Tooltip("tri_p10:Q", format=".2f"),
                alt.Tooltip("cashflow_year1_p10:Q", format=".0f"),
            ],
        )
    )
    annonces = pd.DataFrame(
        [
            {
                "id": row["id"],
                "price_per_m2": float(row["prix_affiche"]) / float(row["surface_m2"]),
                "rent_per_m2": float(row["loyer_hc_mensuel"]) / float(row["surface_m2"]),
                "quartier": row.get("quartier") or "",
            }
            for row in list_annonces(conn)
            if str(row.get("ville") or "").casefold() == city.casefold()
            and row.get("surface_m2")
            and row.get("loyer_hc_mensuel")
        ]
    )
    if not annonces.empty:
        real_chart = (
            alt.Chart(annonces)
            .mark_point(shape="diamond", filled=True, color="black", size=180)
            .encode(
                x="price_per_m2:Q",
                y="rent_per_m2:Q",
                tooltip=["id:Q", "quartier:N", "price_per_m2:Q", "rent_per_m2:Q"],
            )
        )
        simulation_chart = simulation_chart + real_chart
    st.altair_chart(simulation_chart.properties(height=520), width="stretch")

    pareto = (
        alt.Chart(filtered)
        .mark_circle(opacity=0.7)
        .encode(
            x=alt.X("tri_p10:Q", title="TRI P10 (%)"),
            y=alt.Y("cashflow_year1_p10:Q", title="Cash-flow annee 1 P10 (EUR/mois)"),
            color=alt.Color("tri_median:Q", title="TRI median (%)"),
            tooltip=["sample_id:Q", "sample_kind:N", "tri_median:Q", "tri_p10:Q", "cashflow_year1_p10:Q"],
        )
    )
    st.altair_chart(pareto.properties(height=420), width="stretch")


def _render_investment_profile(conn: DatabaseConnection) -> None:
    profile = get_investment_profile(conn)
    st.subheader("Profil d'investissement")
    st.caption(
        "Les entrees economiques pilotent la carte ; les objectifs personnels ne servent qu'aux "
        "analyses detaillees et n'invalident plus la carte. "
        f"Simulation : {profile.simulation_fingerprint[:12]} · Profil complet : {profile.fingerprint[:12]}."
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
        if selected_city_profile := profile_for_city(str(city)):
            st.caption(selected_city_profile.note)

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
        st.caption(
            "Les couts suivants sont des hypotheses explicites du profil, jamais des donnees "
            "deduites d'une annonce ou de la ville."
        )
        c1, c2, c3, c4 = st.columns(4)
        annual_pno = c1.number_input(
            "PNO annuelle", min_value=0.0, value=profile.annual_pno_cost, step=25.0
        )
        annual_accounting = c2.number_input(
            "Comptable annuel", min_value=0.0, value=profile.annual_accounting_cost, step=50.0
        )
        annual_maintenance = c3.number_input(
            "Reserve entretien annuelle",
            min_value=0.0,
            value=profile.annual_maintenance_reserve,
            step=50.0,
        )
        annual_cfe = c4.number_input(
            "CFE annuelle", min_value=0.0, value=profile.annual_cfe_cost, step=50.0
        )

        st.markdown("**Preferences de decision — sans effet sur la carte**")
        c1, c2, c3, c4, c5 = st.columns(5)
        target_tri = c1.number_input("TRI median min (%)", value=profile.target_tri_median, step=0.5)
        target_tri_p10 = c2.number_input("TRI P10 min (%)", value=profile.target_tri_p10, step=0.5)
        target_coc = c3.number_input("Cash-on-cash min (%)", value=profile.target_cash_on_cash, step=0.5)
        target_cf = c4.number_input(
            "Cash-flow annee 1 P10 min", value=profile.target_monthly_cashflow, step=25.0
        )
        target_probability_pct = c5.number_input(
            "Probabilite CF+ annee 1 min (%)",
            min_value=0.0,
            max_value=100.0,
            value=profile.min_positive_cashflow_probability * 100,
            step=5.0,
        )

        with st.expander("Budgets de calcul", expanded=False):
            c1, c2, c3, c4, c5, c6 = st.columns(6)
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
            map_frontier_share_pct = c6.number_input(
                "Frontiere favorable (%)",
                min_value=0.0,
                max_value=100.0,
                value=profile.map_frontier_share * 100,
                step=5.0,
            )

        with st.expander("Hypotheses economiques avancees", expanded=False):
            st.caption(
                "Bornes d'exploration theorique saisies par l'utilisateur : elles ne sont pas "
                "presentees comme des statistiques de marche. Les charges correspondent uniquement "
                "a la part non recuperable supportee par le bailleur."
            )
            c1, c2, c3, c4 = st.columns(4)
            map_surface_min = c1.number_input(
                "Surface min m2", min_value=1.0, value=profile.map_surface_min_m2, step=1.0
            )
            map_surface_max = c2.number_input(
                "Surface max m2", min_value=1.0, value=profile.map_surface_max_m2, step=1.0
            )
            map_price_m2_min = c3.number_input(
                "Prix/m2 min", min_value=1.0, value=profile.map_price_per_m2_min, step=100.0
            )
            map_price_m2_max = c4.number_input(
                "Prix/m2 max", min_value=1.0, value=profile.map_price_per_m2_max, step=100.0
            )
            c1, c2, c3, c4 = st.columns(4)
            map_rent_m2_min = c1.number_input(
                "Loyer HC/m2 min", min_value=0.1, value=profile.map_rent_per_m2_min, step=0.5
            )
            map_rent_m2_max = c2.number_input(
                "Loyer HC/m2 max", min_value=0.1, value=profile.map_rent_per_m2_max, step=0.5
            )
            map_charges_m2_min = c3.number_input(
                "Charges non recuperables/m2/an min",
                min_value=0.0,
                value=profile.map_nonrecoverable_charges_per_m2_min,
                step=1.0,
            )
            map_charges_m2_max = c4.number_input(
                "Charges non recuperables/m2/an max",
                min_value=0.0,
                value=profile.map_nonrecoverable_charges_per_m2_max,
                step=1.0,
            )
            c1, c2, c3, c4 = st.columns(4)
            map_tax_m2_min = c1.number_input(
                "Taxe fonciere/m2/an min",
                min_value=0.0,
                value=profile.map_property_tax_per_m2_min,
                step=1.0,
            )
            map_tax_m2_max = c2.number_input(
                "Taxe fonciere/m2/an max",
                min_value=0.0,
                value=profile.map_property_tax_per_m2_max,
                step=1.0,
            )
            map_works_m2_min = c3.number_input(
                "Travaux initiaux/m2 min",
                min_value=0.0,
                value=profile.map_initial_works_per_m2_min,
                step=25.0,
            )
            map_works_m2_max = c4.number_input(
                "Travaux initiaux/m2 max",
                min_value=0.0,
                value=profile.map_initial_works_per_m2_max,
                step=25.0,
            )
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
                annual_pno_cost=float(annual_pno),
                annual_accounting_cost=float(annual_accounting),
                annual_maintenance_reserve=float(annual_maintenance),
                annual_cfe_cost=float(annual_cfe),
                map_surface_min_m2=float(map_surface_min),
                map_surface_max_m2=float(map_surface_max),
                map_price_per_m2_min=float(map_price_m2_min),
                map_price_per_m2_max=float(map_price_m2_max),
                map_rent_per_m2_min=float(map_rent_m2_min),
                map_rent_per_m2_max=float(map_rent_m2_max),
                map_nonrecoverable_charges_per_m2_min=float(map_charges_m2_min),
                map_nonrecoverable_charges_per_m2_max=float(map_charges_m2_max),
                map_property_tax_per_m2_min=float(map_tax_m2_min),
                map_property_tax_per_m2_max=float(map_tax_m2_max),
                map_initial_works_per_m2_min=float(map_works_m2_min),
                map_initial_works_per_m2_max=float(map_works_m2_max),
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
                map_frontier_share=float(map_frontier_share_pct) / 100,
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
