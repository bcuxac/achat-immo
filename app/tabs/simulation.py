"""Page de simulation des scenarios d'investissement."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd
import streamlit as st

from achat_immo.city_profiles import loyer_max_hc_mensuel, profile_for_city
from achat_immo.engines.fiscal_rules import regimes_compatibles
from achat_immo.grids import (
    GrilleParametres,
    compter_scenarios_grille,
    generer_plage_float,
    generer_plage_int,
    grille_to_dataframe,
    simuler_grille_annonce,
)
from achat_immo.models import (
    BienImmobilier,
    HypothesesLocation,
    ModeLocation,
    RegimeFiscal,
    Scenario,
)
from achat_immo.robustness import analyser_grille
from achat_immo.storage import (
    AnnonceRecord,
    DatabaseConnection,
    fiscalite_from_hypotheses,
    HypothesesAchatRecord,
    save_simulation_run,
    to_domain_models,
)
from app.help_texts import SIMULATION_HELP
from app.simulation_views import (
    decision_map as _decision_map,
    robustesse_summary as _robustesse_summary,
    scenario_details as _scenario_details,
    strategie_summary as _strategie_summary,
    visualisations as _visualisations,
)
from app.ui_helpers import (
    SIMULATION_SECTION_LABELS,
    enum_label as _enum_label,
    format_eur as _format_eur,
    format_eur_optional as _format_eur_optional,
)


def simulation_page(
    conn: DatabaseConnection,
    annonce: AnnonceRecord | None,
    hypotheses: HypothesesAchatRecord | None,
) -> None:
    if annonce is None or hypotheses is None:
        st.info("Selectionne une annonce.")
        return
        
    if annonce.surface_m2 <= 0.0 or annonce.prix_affiche <= 0.0:
        st.warning("Impossible d'afficher la simulation : veuillez d'abord renseigner la surface et le prix de l'annonce.")
        return
        
    bien, location, _ = to_domain_models(annonce, hypotheses)
    fiscalite = fiscalite_from_hypotheses(hypotheses)

    st.subheader("Simulation")
    st.caption("Les parametres peuvent bouger librement. Le moteur ne calcule qu'au clic.")
    bien_simule, location_simulee, params, scenario_base, commentaire, scenario_count, signature = _simulation_inputs(
        bien,
        location,
        hypotheses,
        fiscalite,
    )
    signature = repr((signature, fiscalite))
    _simulation_summary(bien_simule, params, scenario_count)

    df_key = _simulation_state_key(annonce.id, "df")
    results_key = _simulation_state_key(annonce.id, "objects")
    signature_key = _simulation_state_key(annonce.id, "signature")
    comment_key = _simulation_state_key(annonce.id, "comment")

    disabled = scenario_count == 0
    if st.button("Lancer la simulation", type="primary", disabled=disabled):
        resultats = simuler_grille_annonce(
            bien=bien_simule,
            location=location_simulee,
            fiscalite=fiscalite,
            parametres=params,
            scenario_base=scenario_base,
            gestion_agence_possible=bool(hypotheses.gestion_agence_possible),
        )
        st.session_state[df_key] = grille_to_dataframe(resultats)
        st.session_state[results_key] = resultats
        st.session_state[signature_key] = signature
        st.session_state[comment_key] = commentaire

    if disabled:
        st.warning("Aucune simulation possible avec ces parametres.")
        return

    df = st.session_state.get(df_key)
    stored_signature = st.session_state.get(signature_key)
    if df is None:
        st.info("Lance la simulation pour afficher les resultats.")
        return
    if stored_signature != signature:
        st.warning("Les parametres ont change depuis la derniere simulation. Relance le calcul pour actualiser les resultats.")
        return
    if df.empty:
        st.warning("Aucun scenario valide avec ces parametres.")
        return

    robustesse = analyser_grille(df.to_dict("records"))
    _robustesse_summary(robustesse)

    best = df.iloc[0]
    tri = best.get("tri_annuel_pct")
    tri_label = "n/a" if pd.isna(tri) else f"{float(tri):.2f} %"
    break_even = best.get("break_even_year")
    break_even_label = "n/a" if pd.isna(break_even) else f"annee {int(break_even)}"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("TRI fonds propres", tri_label)
    c2.metric("Patrimoine net sortie", _format_eur(float(best["patrimoine_net_sortie"])))
    c3.metric("Cash-flow annee 1", f"{best['cashflow_mensuel_apres_impot']:,.0f} EUR/mois")
    c4.metric("Annees cash-flow negatif", int(best.get("nb_annees_cashflow_negatif", 0)))
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("VAN", _format_eur(float(best.get("van", 0.0))))
    c6.metric("Cash-flow median grille", _format_eur_optional(robustesse.cashflow_median))
    c7.metric("Cash-flow P10 grille", _format_eur_optional(robustesse.cashflow_p10))
    c8.metric("Break-even", break_even_label)
    st.caption(
        f"{len(df):,} scenarios calcules. Le cash-flow affiche est la moyenne mensuelle de l'annee 1 ; "
        "les percentiles sont des percentiles de grille, pas des probabilites."
    )
    _strategie_summary(df)

    cols = [
        "score",
        "mode_location",
        "regime_fiscal",
        "prix_achat",
        "cout_total_projet",
        "loyer_hc_mensuel",
        "taux_credit",
        "duree_annees",
        "apport",
        "montant_emprunte",
        "mensualite_totale",
        "vacance_mois",
        "gestion_agence",
        "frais_gestion_pct",
        "cashflow_mensuel_apres_impot",
        "effort_epargne_mensuel",
        "rendement_net_avant_impot_pct",
        "rendement_net_net_pct",
        "tri_annuel_pct",
        "van",
        "cash_on_cash_return_pct",
        "impot_plus_value",
        "patrimoine_net_sortie",
        "break_even_year",
        "alertes",
        "diagnostics",
    ]
    with st.expander("Tableau complet de grille", expanded=False):
        st.dataframe(df[[col for col in cols if col in df.columns]].head(80), width="stretch", hide_index=True)
    _visualisations(df)
    _decision_map(df, annonce, bien_simule, location_simulee)
    resultats_objets = st.session_state.get(results_key, [])
    if resultats_objets:
        _scenario_details(resultats_objets)

    if st.button("Sauvegarder ce snapshot", type="secondary"):
        run_id = save_simulation_run(
            conn,
            annonce_id=annonce.id or 0,
            resultats=df.to_dict("records"),
            commentaire=st.session_state.get(comment_key, commentaire),
        )
        st.success(f"Snapshot #{run_id} sauvegarde.")


def _simulation_inputs(
    bien: BienImmobilier,
    location: HypothesesLocation,
    hypotheses: HypothesesAchatRecord,
    fiscalite: Any,
) -> tuple[BienImmobilier, HypothesesLocation, GrilleParametres, Scenario, str, int, str]:
    st.subheader("Parametres de simulation")
    st.caption(
        "La grille compacte teste les leviers qui changent vraiment la decision. Les min/max/pas restent "
        "disponibles dans Grille avancee."
    )

    plafond_loyer = loyer_max_hc_mensuel(bien, location)
    loyer_reference = float(hypotheses.loyer_hc_mensuel)
    if plafond_loyer is not None:
        loyer_reference = min(loyer_reference, plafond_loyer)
        st.caption(f"Plafond local calcule : {plafond_loyer:,.0f} EUR HC/mois.")
    elif (profile := profile_for_city(bien.ville)) and profile.requires_rent_sector:
        st.caption("Plafond local non calcule : complete le secteur et l'epoque de construction.")

    with st.container(border=True):
        st.markdown("**Grille compacte**")
        c1, c2, c3, c4, c5 = st.columns(5)
        prix_reference = float(bien.prix_achat)
        with c1:
            prix_decotes = st.multiselect(
                "Decotes prix",
                [0.0, 5_000.0, 10_000.0, 15_000.0, 20_000.0],
                default=[0.0, 5_000.0, 10_000.0],
                format_func=lambda value: f"-{value:,.0f} EUR" if value else "prix affiche",
                help=SIMULATION_HELP["prix_decotes"],
            )
        with c2:
            loyer_variations = st.multiselect(
                "Variations loyer",
                [-50.0, -25.0, 0.0, 25.0, 50.0],
                default=[-50.0, 0.0, 50.0],
                format_func=lambda value: f"{value:+,.0f} EUR",
                help=SIMULATION_HELP["loyer_variations"],
            )
        with c3:
            taux_proposes = st.multiselect(
                "Taux credit testes",
                [3.3, 3.6, 4.0],
                default=[3.3, 3.6, 4.0],
                format_func=lambda value: f"{value:.2f} %",
                help=SIMULATION_HELP["taux_credit"],
            )
        with c4:
            durees_proposees = st.multiselect(
                "Durees credit",
                [15, 20, 25],
                default=[20, 25],
                format_func=lambda value: f"{value} ans",
                help=SIMULATION_HELP["durees"],
            )
        with c5:
            apports = st.multiselect(
                "Apports",
                [10_000.0, 15_000.0, 20_000.0, 25_000.0],
                default=[10_000.0, 15_000.0, 20_000.0],
                format_func=lambda value: f"{value:,.0f} EUR",
                help=SIMULATION_HELP["apports"],
            )
        assurance_emprunteur = st.number_input(
            "Assurance emprunteur %/an",
            min_value=0.0,
            value=float(hypotheses.assurance_emprunteur_pct),
            step=0.05,
            format="%.2f",
            help=SIMULATION_HELP["assurance_emprunteur"],
        )

    loyer_min_default = max(1.0, loyer_reference - 50.0)
    loyer_max_default = loyer_reference + 50.0
    input_bounds: dict[str, float] = {}
    if plafond_loyer is not None:
        loyer_min_default = min(loyer_min_default, plafond_loyer)
        loyer_max_default = min(loyer_max_default, plafond_loyer)
        input_bounds["max_value"] = float(plafond_loyer)

    with st.expander("Grille avancee", expanded=False):
        use_advanced_grid = st.checkbox(
            "Utiliser les min/max/pas ci-dessous",
            value=False,
            help=SIMULATION_HELP["grille_avancee"],
        )
        g1, g2, g3, g4 = st.columns(4)
        with g1:
            prix_min = st.number_input(
                "Prix achat min",
                min_value=1_000.0,
                value=max(1_000.0, prix_reference - 10_000.0),
                step=1_000.0,
            )
            prix_max = st.number_input("Prix achat max", min_value=1_000.0, value=prix_reference, step=1_000.0)
            prix_pas = st.number_input("Pas prix", min_value=1_000.0, value=5_000.0, step=1_000.0)
        with g2:
            loyer_min = st.number_input("Loyer HC min", min_value=1.0, value=float(loyer_min_default), step=10.0, **input_bounds)
            loyer_max = st.number_input(
                "Loyer HC max",
                min_value=1.0,
                value=float(max(loyer_max_default, loyer_min_default)),
                step=10.0,
                **input_bounds,
            )
            loyer_pas = st.number_input("Pas loyer", min_value=1.0, value=25.0, step=5.0)
        with g3:
            taux_min = st.number_input("Taux credit min %", min_value=0.0, value=3.30, step=0.10, format="%.2f")
            taux_max = st.number_input("Taux credit max %", min_value=0.0, value=4.00, step=0.10, format="%.2f")
            taux_pas = st.number_input("Pas taux %", min_value=0.01, value=0.10, step=0.01, format="%.2f")
        with g4:
            duree_min = st.number_input("Duree credit min annees", min_value=1, max_value=30, value=15, step=1)
            duree_max = st.number_input("Duree credit max annees", min_value=1, max_value=30, value=25, step=1)
            duree_pas = st.number_input("Pas duree annees", min_value=1, max_value=10, value=1, step=1)

    exploitation, strategies, analyse = st.columns(3)
    with exploitation:
        with st.container(border=True):
            st.markdown(f"**{SIMULATION_SECTION_LABELS[0]}**")
            vacances = st.multiselect(
                "Vacance mois/an",
                [0.0, 1.0, 2.0, 3.0],
                default=[0.0, 1.0, 2.0],
                help=SIMULATION_HELP["vacances"],
            )
            default_modes = ["directe", "agence"] if hypotheses.gestion_agence_possible else ["directe"]
            modes_gestion = st.multiselect(
                "Mode de gestion",
                ["directe", "agence"],
                default=default_modes,
                help=SIMULATION_HELP["modes_gestion"],
            )
            frais_gestion = st.multiselect(
                "Frais gestion agence %",
                [5.0, 7.0, 8.0],
                default=[7.0],
                help=SIMULATION_HELP["frais_gestion"],
            )

    with strategies:
        with st.container(border=True):
            st.markdown(f"**{SIMULATION_SECTION_LABELS[1]}**")
            comparer_regimes = st.checkbox(
                "Comparer regimes fiscaux compatibles",
                value=True,
                help=SIMULATION_HELP["comparer_regimes"],
            )
            comparer_modes = st.checkbox(
                "Comparer meuble et nue",
                value=False,
                help=SIMULATION_HELP["comparer_modes"],
            )
            modes_location = (ModeLocation.MEUBLEE, ModeLocation.NUE) if comparer_modes else (location.mode_location,)
            default_regimes = tuple(
                dict.fromkeys(regime for mode in modes_location for regime in regimes_compatibles(mode))
            )
            regimes_fiscaux = st.multiselect(
                "Regimes fiscaux testes",
                list(RegimeFiscal),
                default=list(default_regimes),
                format_func=_enum_label,
                disabled=not comparer_regimes,
                help=SIMULATION_HELP["regimes_fiscaux"],
            )

    with analyse:
        with st.container(border=True):
            st.markdown(f"**{SIMULATION_SECTION_LABELS[2]}**")
            horizon = st.number_input(
                "Horizon analyse annees",
                min_value=1,
                max_value=30,
                value=10,
                step=1,
                help=SIMULATION_HELP["horizon"],
            )
            taux_actualisation = st.number_input(
                "Taux actualisation %",
                min_value=0.0,
                value=4.0,
                step=0.25,
                format="%.2f",
                help=SIMULATION_HELP["taux_actualisation"],
            )
            commentaire = st.text_input(
                "Libelle de snapshot",
                value="simulation de travail",
                help=SIMULATION_HELP["commentaire"],
            )

    try:
        if use_advanced_grid:
            prix_achats = generer_plage_float(prix_min, prix_max, prix_pas, decimales=0)
            loyers = generer_plage_float(loyer_min, loyer_max, loyer_pas, decimales=0)
            taux = generer_plage_float(taux_min, taux_max, taux_pas)
            durees = generer_plage_int(int(duree_min), int(duree_max), int(duree_pas))
        else:
            prix_achats = tuple(sorted({round(max(1_000.0, prix_reference - decote), 0) for decote in prix_decotes}))
            loyers = tuple(
                sorted(
                    {
                        round(min(max(1.0, loyer_reference + variation), plafond_loyer or float("inf")), 0)
                        for variation in loyer_variations
                    }
                )
            )
            taux = tuple(float(value) for value in taux_proposes)
            durees = tuple(int(value) for value in durees_proposees)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    bien_simule = bien
    location_simulee = replace(
        location,
        loyer_hc_mensuel=float(loyers[0]) if loyers else location.loyer_hc_mensuel,
        frais_gestion_pct=float(frais_gestion[0]) if frais_gestion else 7.0,
    )
    params = GrilleParametres(
        prix_achats=_as_float_tuple(list(prix_achats)),
        loyers_hc_mensuels=_as_float_tuple(list(loyers)),
        taux_credit=_as_float_tuple(taux),
        durees_annees=_as_int_tuple(durees),
        apports=_as_float_tuple(apports),
        vacances_mois=_as_float_tuple(vacances),
        gestions_agence=tuple(mode == "agence" for mode in modes_gestion),
        frais_gestion_pct=_as_float_tuple(frais_gestion),
        horizon_annees=int(horizon),
        assurance_emprunteur_annuelle_pct=assurance_emprunteur,
        modes_location=tuple(modes_location),
        regimes_fiscaux=tuple(regimes_fiscaux) if comparer_regimes else (),
        comparer_regimes=bool(comparer_regimes),
    )
    scenario_base = Scenario(
        horizon_annees=int(horizon),
        taux_actualisation_pct=float(taux_actualisation),
    )
    scenario_count = compter_scenarios_grille(
        bien_simule,
        location_simulee,
        params,
        fiscalite=fiscalite,
        gestion_agence_possible=bool(hypotheses.gestion_agence_possible),
    )
    signature = repr((bien_simule, location_simulee, params, scenario_base, bool(hypotheses.gestion_agence_possible)))
    return bien_simule, location_simulee, params, scenario_base, commentaire, scenario_count, signature


def _simulation_state_key(annonce_id: int | None, suffix: str) -> str:
    return f"simulation_{annonce_id or 'none'}_{suffix}"


def _pret_range(bien: BienImmobilier, params: GrilleParametres) -> tuple[float, float] | None:
    prix_achats = params.prix_achats or (bien.prix_achat,)
    montants = []
    for prix_achat in prix_achats:
        bien_scenario = replace(bien, prix_negocie=prix_achat)
        montants.extend(
            bien_scenario.cout_total_projet - apport
            for apport in params.apports
            if apport <= bien_scenario.cout_total_projet
        )
    if not montants:
        return None
    return min(montants), max(montants)


def _simulation_summary(bien: BienImmobilier, params: GrilleParametres, scenario_count: int) -> None:
    pret = _pret_range(bien, params)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Cout total projet", _format_eur(bien.cout_total_projet))
    if pret is None:
        c2.metric("Pret necessaire", "Aucun apport valide")
    else:
        min_pret, max_pret = pret
        c2.metric("Pret necessaire", f"{_format_eur(min_pret)} - {_format_eur(max_pret)}")
    c3.metric("Prix testes", len(params.prix_achats))
    c4.metric("Loyers testes", len(params.loyers_hc_mensuels))
    c5.metric("Simulations prevues", f"{scenario_count:,}")


def _as_float_tuple(values: list[float]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


def _as_int_tuple(values: list[int]) -> tuple[int, ...]:
    return tuple(int(value) for value in values)
