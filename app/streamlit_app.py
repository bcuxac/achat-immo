"""Application Streamlit pour piloter les decisions locatives."""

from __future__ import annotations

from dataclasses import replace
import importlib
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
SRC_PATH_STR = str(SRC_PATH)
if SRC_PATH_STR in sys.path:
    sys.path.remove(SRC_PATH_STR)
sys.path.insert(0, SRC_PATH_STR)


def _force_fresh_repo_source_package(package_name: str) -> None:
    """Supprime les modules locaux deja charges pour forcer une lecture du source courant."""

    importlib.invalidate_caches()
    for module_name in list(sys.modules):
        if module_name != package_name and not module_name.startswith(f"{package_name}."):
            continue
        del sys.modules[module_name]


_force_fresh_repo_source_package("achat_immo")

from achat_immo import grids as grids_module
from achat_immo import models as models_module
from achat_immo.grids import (
    GrilleParametres,
    compter_scenarios_grille,
    generer_plage_float,
    generer_plage_int,
    grille_to_dataframe,
    simuler_grille_annonce,
)
from achat_immo.city_profiles import loyer_max_hc_mensuel, profile_for_city
from achat_immo.fiscal_rules import (
    regime_fiscal_recommande,
    regimes_compatibles,
)
from achat_immo.hypothesis_inference import (
    appliquer_suggestions,
    inferer_hypotheses_depuis_annonce,
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
    DEFAULT_DB_PATH,
    fiscalite_from_hypotheses,
    HypothesesAchatRecord,
    open_database,
    save_annonce,
    save_simulation_run,
    to_domain_models,
)
from app.components import (
    badge_caption as _badge_caption,
    readonly_field as _readonly_field,
)
from app.help_texts import FIELD_HELP, SIMULATION_HELP
from app.pages.annonce import annonce_page
from app.pages.comparison import comparison_page
from app.pages.dashboard import dashboard_page
from app.pages.history import history_page
from app.runtime_config import (
    configured_database_url as _configured_database_url,
    require_authentication as _require_authentication,
)
from app.runtime_checks import (
    RuntimeApiContext,
    require_current_runtime_api as _require_current_runtime_api,
    runtime_api_errors as _runtime_api_errors_for_context,
)
from app.sidebar import load_bundle as _load_bundle, sidebar as _sidebar
from app.simulation_views import (
    decision_map as _decision_map,
    robustesse_summary as _robustesse_summary,
    scenario_details as _scenario_details,
    strategie_summary as _strategie_summary,
    visualisations as _visualisations,
)
from app.ui_helpers import (
    PORTFOLIO_DECISION_LABEL,
    SIMULATION_SECTION_LABELS,
    derived_fiscalite_values,
    display_hypothesis_value as _display_hypothesis_value,
    effective_cfe_value,
    effective_comptable_lmnp_value,
    enum_label as _enum_label,
    field_origin as field_origin,
    format_eur as _format_eur,
    format_eur_optional as _format_eur_optional,
    is_advanced_field as is_advanced_field,
    is_cfe_applicable,
    is_comptable_lmnp_applicable,
    is_deduced_field as is_deduced_field,
)


EXPECTED_GRID_API_VERSION = "multi_regime_grid_v1"
EXPECTED_MODEL_API_VERSION = "multi_regime_models_v1"
DB_CONNECTION_CACHE_VERSION = "postgres_no_prepared_statements_v1"
RUNTIME_API_CONTEXT = RuntimeApiContext(
    expected_grid_api_version=EXPECTED_GRID_API_VERSION,
    expected_model_api_version=EXPECTED_MODEL_API_VERSION,
    src_path=SRC_PATH,
    app_file=__file__,
    grids_module=grids_module,
    models_module=models_module,
    grille_parametres=GrilleParametres,
    scenario=Scenario,
    compter_scenarios_grille=compter_scenarios_grille,
    simuler_grille_annonce=simuler_grille_annonce,
)

@st.cache_resource
def _database(target: str, cache_version: str):
    return open_database(target)


def _as_float_tuple(values: list[float]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


def _as_int_tuple(values: list[int]) -> tuple[int, ...]:
    return tuple(int(value) for value in values)


def _runtime_api_errors() -> list[str]:
    return _runtime_api_errors_for_context(RUNTIME_API_CONTEXT)


def _suggestions_dataframe(
    hypotheses: HypothesesAchatRecord,
    suggestions: dict[str, Any],
) -> pd.DataFrame:
    rows = []
    for field, suggestion in suggestions.items():
        current = getattr(hypotheses, field)
        if current == suggestion.value:
            continue
        rows.append(
            {
                "champ": field,
                "actuel": _display_hypothesis_value(current),
                "suggere": _display_hypothesis_value(suggestion.value),
                "confiance": suggestion.confidence,
                "source": suggestion.source,
                "raison": suggestion.reason,
            }
        )
    return pd.DataFrame(rows)


def _hypotheses_inference_panel(
    conn,
    annonce: AnnonceRecord,
    hypotheses: HypothesesAchatRecord,
) -> None:
    suggestions = inferer_hypotheses_depuis_annonce(annonce, hypotheses)
    suggestions_df = _suggestions_dataframe(hypotheses, suggestions)
    with st.expander("Suggestions automatiques depuis l'annonce", expanded=not suggestions_df.empty):
        st.caption(
            "Ces valeurs sont des propositions auditables. Elles accelerent la saisie, mais les champs "
            "faible confiance doivent rester a verifier avant decision."
        )
        if suggestions_df.empty:
            st.success("Les hypotheses sauvegardees sont deja alignees avec les suggestions automatiques.")
        else:
            st.dataframe(
                suggestions_df,
                hide_index=True,
                width="stretch",
            )
            c1, c2 = st.columns(2)
            if c1.button("Appliquer aux champs vides", width="stretch"):
                save_annonce(
                    conn,
                    annonce,
                    appliquer_suggestions(hypotheses, suggestions, only_empty=True),
                )
                st.success("Suggestions appliquees aux champs non renseignes.")
                st.rerun()
            if c2.button("Remplacer par les suggestions", width="stretch"):
                save_annonce(
                    conn,
                    annonce,
                    appliquer_suggestions(hypotheses, suggestions),
                )
                st.success("Hypotheses remplacees par les suggestions automatiques.")
                st.rerun()


def _hypotheses_page(conn, annonce: AnnonceRecord | None, hypotheses: HypothesesAchatRecord | None) -> None:
    if annonce is None or hypotheses is None:
        st.info("Cree ou selectionne une annonce dans la barre laterale.")
        return

    st.subheader("Hypotheses d'investissement")
    st.caption(
        "Parcours guide : les champs Saisi sont tes donnees d'entree, les champs Deduit sont calcules "
        "depuis le regime, et les champs Avance restent replis."
    )
    _hypotheses_inference_panel(conn, annonce, hypotheses)

    with st.form("hypotheses_form"):
        achat, exploitation, frais, fiscalite_col = st.columns(4)
        with exploitation:
            st.markdown("**Exploitation**")
            st.caption("Donnees brutes du bien et du bail vise.")
            mode_location = st.selectbox(
                "Mode location",
                options=list(ModeLocation),
                index=list(ModeLocation).index(hypotheses.mode_location),
                format_func=_enum_label,
                help=FIELD_HELP["mode_location"],
            )
            _badge_caption("mode_location")
            loyer_reference = st.number_input(
                "Loyer HC de reference",
                min_value=1.0,
                value=float(hypotheses.loyer_hc_mensuel),
                step=10.0,
                help=FIELD_HELP["loyer_hc_mensuel"],
            )
            taxe_fonciere = st.number_input(
                "Taxe fonciere",
                min_value=0.0,
                value=float(hypotheses.taxe_fonciere),
                step=50.0,
                help=FIELD_HELP["taxe_fonciere"],
            )
            charges_copro = st.number_input(
                "Charges copro annuelles",
                min_value=0.0,
                value=float(hypotheses.charges_copro_annuelles),
                step=50.0,
                help=FIELD_HELP["charges_copro_annuelles"],
            )
            charges_recup = st.number_input(
                "Charges recuperables annuelles",
                min_value=0.0,
                value=float(hypotheses.charges_recuperables_annuelles),
                step=50.0,
                help=FIELD_HELP["charges_recuperables_annuelles"],
            )

        with fiscalite_col:
            st.markdown("**Fiscalite**")
            st.caption("Choix de reference et constantes fiscales deduites.")
            regime_options = regimes_compatibles(mode_location)
            current_regime = (
                hypotheses.regime_fiscal
                if hypotheses.regime_fiscal in regime_options
                else regime_fiscal_recommande(mode_location, float(loyer_reference) * 12)
            )
            regime_fiscal = st.selectbox(
                "Regime de reference",
                options=list(regime_options),
                index=list(regime_options).index(current_regime),
                format_func=_enum_label,
                help=FIELD_HELP["regime_fiscal"],
            )
            _badge_caption("regime_fiscal")
            tmi_pct = st.number_input(
                "TMI %",
                min_value=0.0,
                max_value=100.0,
                value=float(hypotheses.tmi_pct),
                step=1.0,
                format="%.1f",
                help=FIELD_HELP["tmi_pct"],
            )
            derived_values = derived_fiscalite_values(regime_fiscal)
            prelevements_sociaux_pct = float(derived_values["prelevements_sociaux_pct"])
            abattement_micro_bic = float(derived_values["abattement_micro_bic_pct"])
            abattement_micro_foncier = float(derived_values["abattement_micro_foncier_pct"])
            _readonly_field(
                "Prelevements sociaux",
                f"{prelevements_sociaux_pct:.1f} %",
                "prelevements_sociaux_pct",
                FIELD_HELP["prelevements_sociaux_pct"],
            )
            if regime_fiscal == RegimeFiscal.MICRO_BIC:
                _readonly_field(
                    "Abattement micro-BIC",
                    f"{abattement_micro_bic:.1f} %",
                    "abattement_micro_bic_pct",
                    FIELD_HELP["abattement_micro_bic_pct"],
                )
            elif regime_fiscal == RegimeFiscal.MICRO_FONCIER:
                _readonly_field(
                    "Abattement micro-foncier",
                    f"{abattement_micro_foncier:.1f} %",
                    "abattement_micro_foncier_pct",
                    FIELD_HELP["abattement_micro_foncier_pct"],
                )
            _readonly_field(
                "Plus-value immobiliere",
                (
                    f"IR {derived_values['taux_impot_plus_value_pct']:.1f} %, "
                    f"PS {derived_values['taux_prelevements_sociaux_plus_value_pct']:.1f} %"
                ),
                "taux_impot_plus_value_pct",
                "Taux et abattements de duree appliques par le moteur selon le regime de sortie.",
            )

            part_terrain_pct = float(hypotheses.part_terrain_pct)
            duree_amortissement_bien = int(hypotheses.duree_amortissement_bien_annees)
            duree_amortissement_travaux = int(hypotheses.duree_amortissement_travaux_annees)
            duree_amortissement_meubles = int(hypotheses.duree_amortissement_meubles_annees)
            with st.expander("Fiscalite avancee", expanded=False):
                st.caption("A modifier seulement si ton comptable retient un plan different.")
                part_terrain_pct = st.number_input(
                    "Part terrain non amortissable %",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(hypotheses.part_terrain_pct),
                    step=1.0,
                    format="%.1f",
                    help=FIELD_HELP["part_terrain_pct"],
                )
                duree_amortissement_bien = st.number_input(
                    "Amortissement bien annees",
                    min_value=1,
                    max_value=80,
                    value=int(hypotheses.duree_amortissement_bien_annees),
                    step=1,
                    help=FIELD_HELP["duree_amortissement_bien_annees"],
                )
                duree_amortissement_travaux = st.number_input(
                    "Amortissement travaux annees",
                    min_value=1,
                    max_value=50,
                    value=int(hypotheses.duree_amortissement_travaux_annees),
                    step=1,
                    help=FIELD_HELP["duree_amortissement_travaux_annees"],
                )
                duree_amortissement_meubles = st.number_input(
                    "Amortissement meubles annees",
                    min_value=1,
                    max_value=20,
                    value=int(hypotheses.duree_amortissement_meubles_annees),
                    step=1,
                    help=FIELD_HELP["duree_amortissement_meubles_annees"],
                )
                _readonly_field(
                    "Options frais",
                    "Acquisition amortie sur 5 ans, frais d'emprunt deduits annee 1",
                    "reintegrer_amortissements_lmnp_plus_value",
                    "Options par defaut du moteur fiscal v1.",
                )

        with achat:
            st.markdown("**Acquisition**")
            st.caption("Couts bruts du projet, avant strategie fiscale.")
            frais_notaire = st.number_input(
                "Frais notaire estimes",
                min_value=0.0,
                value=float(hypotheses.frais_notaire_estimes),
                step=500.0,
                help=FIELD_HELP["frais_notaire_estimes"],
            )
            frais_agence_achat = st.number_input(
                "Frais agence achat",
                min_value=0.0,
                value=float(hypotheses.frais_agence_achat),
                step=500.0,
                help=FIELD_HELP["frais_agence_achat"],
            )
            travaux = st.number_input(
                "Travaux",
                min_value=0.0,
                value=float(hypotheses.travaux_estimes),
                step=500.0,
                help=FIELD_HELP["travaux_estimes"],
            )
            meubles = st.number_input(
                "Meubles (budget si meuble)",
                min_value=0.0,
                value=float(hypotheses.meubles_estimes),
                step=500.0,
                help=FIELD_HELP["meubles_estimes"],
            )
            frais_bancaires = st.number_input(
                "Frais bancaires",
                min_value=0.0,
                value=float(hypotheses.frais_bancaires),
                step=100.0,
                help=FIELD_HELP["frais_bancaires"],
            )
            garantie = st.number_input(
                "Garantie",
                min_value=0.0,
                value=float(hypotheses.garantie),
                step=100.0,
                help=FIELD_HELP["garantie"],
            )

        with frais:
            st.markdown("**Frais recurrents**")
            st.caption("Charges d'exploitation payees par le proprietaire.")
            assurance_pno = st.number_input(
                "Assurance PNO",
                min_value=0.0,
                value=float(hypotheses.assurance_pno),
                step=20.0,
                help=FIELD_HELP["assurance_pno"],
            )
            assurance_gli = st.number_input(
                "Assurance GLI",
                min_value=0.0,
                value=float(hypotheses.assurance_gli),
                step=20.0,
                help=FIELD_HELP["assurance_gli"],
            )
            if is_cfe_applicable(mode_location):
                cfe_annuelle = st.number_input(
                    "CFE annuelle",
                    min_value=0.0,
                    value=float(hypotheses.cfe_annuelle),
                    step=50.0,
                    help=FIELD_HELP["cfe_annuelle"],
                )
            else:
                cfe_annuelle = 0.0
                _readonly_field(
                    "CFE annuelle",
                    "0 EUR",
                    "cfe_neutralisee",
                    "Non applicable en location nue dans le parcours standard.",
                )
            if is_comptable_lmnp_applicable(regime_fiscal):
                comptable_lmnp = st.number_input(
                    "Comptable LMNP",
                    min_value=0.0,
                    value=float(hypotheses.comptable_lmnp),
                    step=50.0,
                    help=FIELD_HELP["comptable_lmnp"],
                )
            else:
                comptable_lmnp = 0.0
                _readonly_field(
                    "Comptable LMNP",
                    "0 EUR",
                    "comptable_lmnp_neutralise",
                    "Neutralise hors LMNP reel.",
                )
            entretien_annuel = st.number_input(
                "Entretien annuel",
                min_value=0.0,
                value=float(hypotheses.entretien_annuel),
                step=50.0,
                help=FIELD_HELP["entretien_annuel"],
            )
            gestion_agence_possible = st.checkbox(
                "Gestion agence possible",
                value=bool(hypotheses.gestion_agence_possible),
                help=FIELD_HELP["gestion_agence_possible"],
            )

        if st.form_submit_button("Sauvegarder les hypotheses"):
            if charges_recup > charges_copro:
                st.error("Les charges recuperables ne peuvent pas depasser les charges de copro annuelles.")
                st.stop()
            regime_sauvegarde = regime_fiscal
            if regime_sauvegarde not in regimes_compatibles(mode_location):
                regime_sauvegarde = regime_fiscal_recommande(mode_location, float(loyer_reference) * 12)
            derived_values = derived_fiscalite_values(regime_sauvegarde)
            prelevements_sociaux_pct = float(derived_values["prelevements_sociaux_pct"])
            abattement_micro_bic = float(derived_values["abattement_micro_bic_pct"])
            abattement_micro_foncier = float(derived_values["abattement_micro_foncier_pct"])
            save_annonce(
                conn,
                annonce,
                replace(
                    hypotheses,
                    frais_agence_achat=frais_agence_achat,
                    frais_notaire_estimes=frais_notaire,
                    travaux_estimes=travaux,
                    meubles_estimes=meubles,
                    frais_bancaires=frais_bancaires,
                    garantie=garantie,
                    loyer_hc_mensuel=loyer_reference,
                    mode_location=mode_location,
                    taxe_fonciere=taxe_fonciere,
                    charges_copro_annuelles=charges_copro,
                    charges_recuperables_annuelles=charges_recup,
                    assurance_pno=assurance_pno,
                    assurance_gli=assurance_gli,
                    cfe_annuelle=effective_cfe_value(mode_location, cfe_annuelle),
                    comptable_lmnp=effective_comptable_lmnp_value(regime_sauvegarde, comptable_lmnp),
                    entretien_annuel=entretien_annuel,
                    regime_fiscal=regime_sauvegarde,
                    tmi_pct=tmi_pct,
                    prelevements_sociaux_pct=prelevements_sociaux_pct,
                    part_terrain_pct=part_terrain_pct,
                    duree_amortissement_bien_annees=int(duree_amortissement_bien),
                    duree_amortissement_travaux_annees=int(duree_amortissement_travaux),
                    duree_amortissement_meubles_annees=int(duree_amortissement_meubles),
                    abattement_micro_bic_pct=abattement_micro_bic,
                    abattement_micro_foncier_pct=abattement_micro_foncier,
                    gestion_agence_possible=gestion_agence_possible,
                ),
            )
            st.success("Hypotheses sauvegardees.")
            st.rerun()


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


def _simulation_page(conn, annonce: AnnonceRecord | None, hypotheses: HypothesesAchatRecord | None) -> None:
    if annonce is None or hypotheses is None:
        st.info("Selectionne une annonce.")
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


def main() -> None:
    st.set_page_config(page_title="Simulateur d'Achat immobilier locatif", layout="wide")
    _require_authentication()
    st.title("Simulateur d'Achat immobilier locatif")
    _require_current_runtime_api(RUNTIME_API_CONTEXT)

    database_url = _configured_database_url()
    if database_url:
        st.sidebar.caption("Base : PostgreSQL cloud")
        database_target = database_url
    else:
        database_target = st.sidebar.text_input("Base SQLite", value=str(DEFAULT_DB_PATH))
    conn = _database(database_target, DB_CONNECTION_CACHE_VERSION)
    rows, selected_id = _sidebar(conn)
    annonce, hypotheses = _load_bundle(conn, selected_id)

    tab_dashboard, tab_annonce, tab_hypotheses, tab_simulation, tab_comparison, tab_history = st.tabs(
        ["Tableau de bord", "Annonce", "Hypotheses", "Simulation", PORTFOLIO_DECISION_LABEL, "Historique"]
    )

    with tab_dashboard:
        dashboard_page(conn, rows)
    with tab_annonce:
        annonce_page(conn, annonce, hypotheses)
    with tab_hypotheses:
        _hypotheses_page(conn, annonce, hypotheses)
    with tab_simulation:
        _simulation_page(conn, annonce, hypotheses)
    with tab_comparison:
        comparison_page(conn, rows, annonce)
    with tab_history:
        history_page(conn, selected_id)


if __name__ == "__main__":
    main()
