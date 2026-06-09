"""Application Streamlit locale pour piloter les decisions locatives."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from achat_immo.grids import (
    GrilleParametres,
    compter_scenarios_grille,
    generer_plage_float,
    generer_plage_int,
    grille_to_dataframe,
    simuler_grille_annonce,
)
from achat_immo.comparison import SeuilsDecision
from achat_immo.city_profiles import (
    SECTEUR_A_VERIFIER,
    canonical_city_label,
    loyer_max_hc_mensuel,
    profile_for_city,
    supported_city_labels,
)
from achat_immo.diagnostics import DiagnosticStatus, diagnostiquer_annonce
from achat_immo.models import (
    BienImmobilier,
    EpoqueConstruction,
    Fiscalite,
    HypothesesLocation,
    ModeLocation,
    TypeBien,
)
from achat_immo.robustness import RobustesseGrille, analyser_grille
from achat_immo.storage import (
    AnnonceRecord,
    DEFAULT_DB_PATH,
    HypothesesAchatRecord,
    get_annonce_bundle,
    get_simulation_results,
    list_annonces,
    list_simulation_runs,
    open_database,
    save_annonce,
    save_simulation_run,
    to_domain_models,
    update_decision,
)


STATUTS = [
    "a_analyser",
    "diagnostic_incomplet",
    "a_visiter",
    "a_negocier",
    "favori",
    "rejete",
    "archive",
]


@st.cache_resource
def _database(db_path: str):
    return open_database(Path(db_path))


def _as_float_tuple(values: list[float]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


def _as_int_tuple(values: list[int]) -> tuple[int, ...]:
    return tuple(int(value) for value in values)


def _enum_label(value: Any) -> str:
    return str(getattr(value, "value", value)).replace("_", " ")


def _annonce_label(row: dict[str, Any]) -> str:
    quartier = f" - {row['quartier']}" if row.get("quartier") else ""
    return f"#{row['id']} {row['ville']}{quartier} - {row['surface_m2']:.0f} m2 - {row['prix_affiche']:,.0f} EUR"


def _create_blank_annonce(conn) -> int:
    return save_annonce(
        conn,
        AnnonceRecord(
            ville="Grenoble",
            surface_m2=30.0,
            prix_affiche=80_000.0,
            nb_pieces=2,
            secteur_encadrement=SECTEUR_A_VERIFIER,
            statut="a_analyser",
        ),
        HypothesesAchatRecord(loyer_hc_mensuel=500.0),
    )


def _sidebar(conn) -> tuple[list[dict[str, Any]], int | None]:
    st.sidebar.subheader("Annonces")
    if st.sidebar.button("Nouvelle annonce", type="primary", width="stretch"):
        annonce_id = _create_blank_annonce(conn)
        st.session_state["selected_annonce_id"] = annonce_id
        st.rerun()

    rows = list_annonces(conn)
    if not rows:
        st.sidebar.info("Cree une annonce pour commencer.")
        return rows, None

    ids = [int(row["id"]) for row in rows]
    default_id = st.session_state.get("selected_annonce_id", ids[0])
    index = ids.index(default_id) if default_id in ids else 0
    selected = st.sidebar.selectbox(
        "Annonce active",
        options=ids,
        index=index,
        format_func=lambda annonce_id: _annonce_label(next(row for row in rows if row["id"] == annonce_id)),
    )
    st.session_state["selected_annonce_id"] = selected
    return rows, selected


def _load_bundle(conn, annonce_id: int | None):
    if annonce_id is None:
        return None, None
    return get_annonce_bundle(conn, annonce_id)


def _dashboard(conn, rows: list[dict[str, Any]]) -> None:
    st.subheader("Vue base SQLite")
    st.caption("Cette page sert a voir ce qui est stocke : annonces suivies, decisions et derniers runs.")
    runs = list_simulation_runs(conn)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Annonces", len(rows))
    c2.metric("Runs sauvegardes", len(runs))
    c3.metric("Favorites", sum(1 for row in rows if row["statut"] == "favori"))
    c4.metric("Rejetees", sum(1 for row in rows if row["statut"] == "rejete"))

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(
            df[
                [
                    "id",
                    "statut",
                    "ville",
                    "quartier",
                    "adresse",
                    "type_bien",
                    "nb_pieces",
                    "epoque_construction",
                    "secteur_encadrement",
                    "surface_m2",
                    "prix_affiche",
                    "dpe",
                ]
            ],
            hide_index=True,
            width="stretch",
        )
    if runs:
        st.subheader("Derniers runs")
        st.dataframe(pd.DataFrame(runs).head(10), hide_index=True, width="stretch")


def _annonce_page(conn, annonce: AnnonceRecord | None, hypotheses: HypothesesAchatRecord | None) -> None:
    if annonce is None or hypotheses is None:
        st.info("Cree ou selectionne une annonce dans la barre laterale.")
        return

    st.subheader("Donnees factuelles de l'annonce")
    st.caption("Ici on garde les informations propres au bien. La decision et les parametres iterables restent ailleurs.")

    with st.form("annonce_form"):
        c1, c2 = st.columns(2)
        with c1:
            villes = supported_city_labels()
            ville_actuelle = canonical_city_label(annonce.ville)
            ville = st.selectbox(
                "Ville",
                options=villes,
                index=villes.index(ville_actuelle) if ville_actuelle in villes else 0,
            )
            quartier = st.text_input("Quartier", value=annonce.quartier)
            adresse = st.text_input("Adresse approximative", value=annonce.adresse)
            type_bien = st.selectbox(
                "Type",
                options=list(TypeBien),
                index=list(TypeBien).index(annonce.type_bien),
                format_func=lambda item: item.value,
            )
            nb_pieces = st.number_input(
                "Nombre de pieces",
                min_value=1,
                max_value=10,
                value=int(annonce.nb_pieces or 2),
                step=1,
            )
        with c2:
            surface_m2 = st.number_input("Surface m2", min_value=1.0, value=float(annonce.surface_m2), step=1.0)
            prix_affiche = st.number_input(
                "Prix affiche",
                min_value=1_000.0,
                value=float(annonce.prix_affiche),
                step=1_000.0,
            )
            epoque_construction = st.selectbox(
                "Epoque construction",
                options=list(EpoqueConstruction),
                index=list(EpoqueConstruction).index(annonce.epoque_construction),
                format_func=_enum_label,
            )
            profile = profile_for_city(ville)
            secteurs = profile.secteurs_encadrement if profile else {}
            if secteurs:
                secteur_options = tuple(secteurs)
                secteur_value = (
                    annonce.secteur_encadrement
                    if annonce.secteur_encadrement in secteurs
                    else SECTEUR_A_VERIFIER
                )
                secteur_encadrement = st.selectbox(
                    "Secteur encadrement",
                    options=secteur_options,
                    index=secteur_options.index(secteur_value),
                    format_func=lambda value: secteurs[value],
                )
            else:
                secteur_encadrement = ""
            dpe = st.text_input("DPE", value=annonce.dpe)
            url = st.text_input("URL", value=annonce.url)

        description = st.text_area("Description brute de l'annonce", value=annonce.description, height=150)

        submitted = st.form_submit_button("Sauvegarder l'annonce")
        if submitted:
            save_annonce(
                conn,
                AnnonceRecord(
                    id=annonce.id,
                    date_creation=annonce.date_creation,
                    url=url,
                    ville=ville,
                    quartier=quartier.strip(),
                    adresse=adresse.strip(),
                    type_bien=type_bien,
                    nb_pieces=int(nb_pieces),
                    epoque_construction=epoque_construction,
                    secteur_encadrement=secteur_encadrement,
                    surface_m2=surface_m2,
                    prix_affiche=prix_affiche,
                    prix_negocie=None,
                    dpe=dpe.strip().upper(),
                    description=description,
                    statut=annonce.statut,
                    notes=annonce.notes,
                ),
                hypotheses,
            )
            st.success("Annonce sauvegardee.")
            st.rerun()


def _hypotheses_page(conn, annonce: AnnonceRecord | None, hypotheses: HypothesesAchatRecord | None) -> None:
    if annonce is None or hypotheses is None:
        st.info("Cree ou selectionne une annonce dans la barre laterale.")
        return

    st.subheader("Hypotheses du modele")
    st.caption("Ces valeurs ne viennent pas toutes de l'annonce. Elles cadrent le cout total et l'exploitation.")

    with st.form("hypotheses_form"):
        achat, exploitation, frais = st.columns(3)
        with achat:
            st.markdown("**Acquisition**")
            frais_notaire = st.number_input(
                "Frais notaire estimes",
                min_value=0.0,
                value=float(hypotheses.frais_notaire_estimes),
                step=500.0,
            )
            frais_agence_achat = st.number_input(
                "Frais agence achat",
                min_value=0.0,
                value=float(hypotheses.frais_agence_achat),
                step=500.0,
            )
            travaux = st.number_input("Travaux", min_value=0.0, value=float(hypotheses.travaux_estimes), step=500.0)
            meubles = st.number_input("Meubles", min_value=0.0, value=float(hypotheses.meubles_estimes), step=500.0)
            frais_bancaires = st.number_input(
                "Frais bancaires",
                min_value=0.0,
                value=float(hypotheses.frais_bancaires),
                step=100.0,
            )
            garantie = st.number_input("Garantie", min_value=0.0, value=float(hypotheses.garantie), step=100.0)

        with exploitation:
            st.markdown("**Exploitation**")
            mode_location = st.selectbox(
                "Mode location",
                options=list(ModeLocation),
                index=list(ModeLocation).index(hypotheses.mode_location),
                format_func=_enum_label,
            )
            loyer_reference = st.number_input(
                "Loyer HC de reference",
                min_value=1.0,
                value=float(hypotheses.loyer_hc_mensuel),
                step=10.0,
                help="Utilise seulement pour pre-remplir la grille de simulation.",
            )
            taxe_fonciere = st.number_input(
                "Taxe fonciere",
                min_value=0.0,
                value=float(hypotheses.taxe_fonciere),
                step=50.0,
            )
            charges_copro = st.number_input(
                "Charges copro annuelles",
                min_value=0.0,
                value=float(hypotheses.charges_copro_annuelles),
                step=50.0,
            )
            charges_recup = st.number_input(
                "Charges recuperables annuelles",
                min_value=0.0,
                value=float(hypotheses.charges_recuperables_annuelles),
                step=50.0,
            )

        with frais:
            st.markdown("**Frais recurrents**")
            assurance_pno = st.number_input("Assurance PNO", min_value=0.0, value=float(hypotheses.assurance_pno), step=20.0)
            assurance_gli = st.number_input("Assurance GLI", min_value=0.0, value=float(hypotheses.assurance_gli), step=20.0)
            comptable_lmnp = st.number_input(
                "Comptable LMNP",
                min_value=0.0,
                value=float(hypotheses.comptable_lmnp),
                step=50.0,
            )
            entretien_annuel = st.number_input(
                "Entretien annuel",
                min_value=0.0,
                value=float(hypotheses.entretien_annuel),
                step=50.0,
            )
            gestion_agence_possible = st.checkbox(
                "Gestion agence possible",
                value=bool(hypotheses.gestion_agence_possible),
            )

        if st.form_submit_button("Sauvegarder les hypotheses"):
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
                    comptable_lmnp=comptable_lmnp,
                    entretien_annuel=entretien_annuel,
                    gestion_agence_possible=gestion_agence_possible,
                ),
            )
            st.success("Hypotheses sauvegardees.")
            st.rerun()


def _simulation_inputs(
    bien: BienImmobilier,
    location: HypothesesLocation,
    hypotheses: HypothesesAchatRecord,
) -> tuple[BienImmobilier, HypothesesLocation, GrilleParametres, str, int, str]:
    st.subheader("Parametres de simulation")
    revenus, credit, gestion = st.columns(3)
    with revenus:
        with st.container(border=True):
            st.markdown("**Revenus locatifs**")
            plafond_loyer = loyer_max_hc_mensuel(bien, location)
            loyer_reference = float(hypotheses.loyer_hc_mensuel)
            if plafond_loyer is not None:
                loyer_reference = min(loyer_reference, plafond_loyer)
                st.caption(f"Plafond local calcule : {plafond_loyer:,.0f} EUR HC/mois.")
            elif (profile := profile_for_city(bien.ville)) and profile.requires_rent_sector:
                st.caption("Plafond local non calcule : complete le secteur et l'epoque de construction.")
            loyer_min_default = max(1.0, loyer_reference - 50.0)
            loyer_max_default = loyer_reference + 50.0
            input_bounds: dict[str, float] = {}
            if plafond_loyer is not None:
                loyer_min_default = min(loyer_min_default, plafond_loyer)
                loyer_max_default = min(loyer_max_default, plafond_loyer)
                input_bounds["max_value"] = float(plafond_loyer)
            loyer_min = st.number_input(
                "Loyer HC min",
                min_value=1.0,
                value=float(loyer_min_default),
                step=10.0,
                **input_bounds,
            )
            loyer_max = st.number_input(
                "Loyer HC max",
                min_value=1.0,
                value=float(max(loyer_max_default, loyer_min_default)),
                step=10.0,
                **input_bounds,
            )
            loyer_pas = st.number_input("Pas loyer", min_value=1.0, value=25.0, step=5.0)
            vacances = st.multiselect(
                "Vacance mois/an",
                [0.0, 1.0, 2.0, 3.0],
                default=[0.0, 1.0, 2.0],
                help="0 mois represente le cas optimiste. Les scenarios prudents restent au moins a 1 mois/an.",
            )

    with credit:
        with st.container(border=True):
            st.markdown("**Credit**")
            prix_reference = float(bien.prix_achat)
            prix_min = st.number_input(
                "Prix achat min",
                min_value=1_000.0,
                value=max(1_000.0, prix_reference - 10_000.0),
                step=1_000.0,
            )
            prix_max = st.number_input(
                "Prix achat max",
                min_value=1_000.0,
                value=prix_reference,
                step=1_000.0,
            )
            prix_pas = st.number_input("Pas prix", min_value=1_000.0, value=5_000.0, step=1_000.0)
            taux_min = st.number_input("Taux credit min %", min_value=0.0, value=3.30, step=0.10, format="%.2f")
            taux_max = st.number_input("Taux credit max %", min_value=0.0, value=4.00, step=0.10, format="%.2f")
            taux_pas = st.number_input("Pas taux %", min_value=0.01, value=0.10, step=0.01, format="%.2f")
            duree_min = st.number_input("Duree credit min annees", min_value=1, max_value=30, value=15, step=1)
            duree_max = st.number_input("Duree credit max annees", min_value=1, max_value=30, value=25, step=1)
            duree_pas = st.number_input("Pas duree annees", min_value=1, max_value=10, value=1, step=1)
            assurance_emprunteur = st.number_input(
                "Assurance emprunteur %/an",
                min_value=0.0,
                value=float(hypotheses.assurance_emprunteur_pct),
                step=0.05,
                format="%.2f",
            )
            apports = st.multiselect(
                "Apports",
                [10_000.0, 15_000.0, 20_000.0, 25_000.0],
                default=[10_000.0, 15_000.0, 20_000.0],
                format_func=lambda value: f"{value:,.0f} EUR",
            )

    with gestion:
        with st.container(border=True):
            st.markdown("**Gestion**")
            modes_gestion = st.multiselect("Mode de gestion", ["directe", "agence"], default=["directe", "agence"])
            frais_gestion = st.multiselect("Frais gestion agence %", [5.0, 7.0, 8.0], default=[7.0])
            commentaire = st.text_input("Libelle de sauvegarde", value="simulation de travail")

    try:
        prix_achats = generer_plage_float(prix_min, prix_max, prix_pas, decimales=0)
        loyers = generer_plage_float(loyer_min, loyer_max, loyer_pas, decimales=0)
        taux = generer_plage_float(taux_min, taux_max, taux_pas)
        durees = generer_plage_int(int(duree_min), int(duree_max), int(duree_pas))
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
        horizon_annees=10,
        assurance_emprunteur_annuelle_pct=assurance_emprunteur,
    )
    scenario_count = compter_scenarios_grille(
        bien_simule,
        location_simulee,
        params,
        gestion_agence_possible=bool(hypotheses.gestion_agence_possible),
    )
    signature = repr((bien_simule, location_simulee, params, bool(hypotheses.gestion_agence_possible)))
    return bien_simule, location_simulee, params, commentaire, scenario_count, signature


def _simulation_state_key(annonce_id: int | None, suffix: str) -> str:
    return f"simulation_{annonce_id or 'none'}_{suffix}"


def _format_eur(value: float) -> str:
    return f"{value:,.0f} EUR"


def _format_eur_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.0f} EUR"


def _gestion_label(value: object) -> str:
    return "agence" if bool(value) else "directe"


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

    st.subheader("Simulation")
    st.caption("Les parametres peuvent bouger librement. Le moteur ne calcule qu'au clic.")
    bien_simule, location_simulee, params, commentaire, scenario_count, signature = _simulation_inputs(
        bien,
        location,
        hypotheses,
    )
    _simulation_summary(bien_simule, params, scenario_count)

    df_key = _simulation_state_key(annonce.id, "df")
    signature_key = _simulation_state_key(annonce.id, "signature")
    comment_key = _simulation_state_key(annonce.id, "comment")

    disabled = scenario_count == 0
    if st.button("Lancer la simulation", type="primary", disabled=disabled):
        resultats = simuler_grille_annonce(
            bien=bien_simule,
            location=location_simulee,
            fiscalite=Fiscalite(),
            parametres=params,
            gestion_agence_possible=bool(hypotheses.gestion_agence_possible),
        )
        st.session_state[df_key] = grille_to_dataframe(resultats)
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
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Meilleur score", int(best["score"]))
    c2.metric("Cash-flow annee 1", f"{best['cashflow_mensuel_apres_impot']:,.0f} EUR/mois")
    c3.metric("Pret du meilleur scenario", _format_eur(float(best["montant_emprunte"])))
    c4.metric("Mensualite credit", f"{best['mensualite_totale']:,.0f} EUR/mois")
    st.caption(f"{len(df):,} scenarios calcules. Le cash-flow affiche est la moyenne mensuelle de l'annee 1.")

    cols = [
        "score",
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
        "alertes",
        "diagnostics",
    ]
    st.dataframe(df[cols].head(40), width="stretch", hide_index=True)
    _visualisations(df)
    _decision_map(df, annonce, bien_simule, location_simulee)

    if st.button("Sauvegarder ce snapshot", type="secondary"):
        run_id = save_simulation_run(
            conn,
            annonce_id=annonce.id or 0,
            resultats=df.to_dict("records"),
            commentaire=st.session_state.get(comment_key, commentaire),
        )
        st.success(f"Snapshot #{run_id} sauvegarde.")


def _decision_robuste_status(decision: str) -> str:
    return {
        "interessant": "OK",
        "a_creuser": "Attention",
        "a_negocier": "Attention",
        "diagnostic_incomplet": "A verifier",
        "a_rejeter": "Bloquant",
    }.get(decision, "Neutre")


def _robustesse_summary(robustesse: RobustesseGrille) -> None:
    st.subheader("Decision robuste")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _decision_factor(
            "Decision",
            robustesse.decision.replace("_", " "),
            _decision_robuste_status(robustesse.decision),
            "Decision basee sur l'ensemble de la grille, pas seulement le meilleur scenario.",
        )
    c2.metric("Scenarios viables", f"{robustesse.nb_viables:,} / {robustesse.nb_scenarios:,}", f"{robustesse.pct_viables:.1f} %")
    c3.metric("Cash-flow median", _format_eur_optional(robustesse.cashflow_median))
    c4.metric("Cash-flow P10", _format_eur_optional(robustesse.cashflow_p10))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Scenarios positifs", f"{robustesse.nb_positifs:,}", f"{robustesse.pct_positifs:.1f} %")
    c6.metric("Prix max viable", _format_eur_optional(robustesse.prix_max_viable))
    c7.metric("Meilleur prudent", _format_eur_optional(robustesse.meilleur_cashflow_prudent))
    c8.metric("Meilleur agence", _format_eur_optional(robustesse.meilleur_cashflow_agence))

    st.markdown("**Raisons**")
    for raison in robustesse.raisons:
        st.caption(raison)

    st.markdown("**Conditions de validite observees**")
    st.dataframe(
        pd.DataFrame({"condition": list(robustesse.conditions_validite)}),
        hide_index=True,
        width="stretch",
    )


def _visualisations(df: pd.DataFrame) -> None:
    st.subheader("Cash-flow mensuel annee 1")
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        prix_achat = st.selectbox("Prix achat", sorted(df["prix_achat"].unique()), format_func=lambda v: f"{v:,.0f} EUR")
    with f2:
        loyer = st.selectbox("Loyer HC", sorted(df["loyer_hc_mensuel"].unique()), format_func=lambda v: f"{v:,.0f} EUR")
    with f3:
        apport = st.selectbox("Apport", sorted(df["apport"].unique()), format_func=lambda v: f"{v:,.0f} EUR")
    with f4:
        gestion = st.selectbox(
            "Gestion",
            sorted(df["gestion_agence"].unique()),
            format_func=lambda v: "agence" if v else "directe",
        )
    with f5:
        frais_gestion_options = sorted(df[df["gestion_agence"] == gestion]["frais_gestion_pct"].unique())
        frais_gestion = st.selectbox("Frais gestion", frais_gestion_options, format_func=lambda v: f"{v:g} %")

    filtered = df[
        (df["prix_achat"] == prix_achat)
        & (df["loyer_hc_mensuel"] == loyer)
        & (df["apport"] == apport)
        & (df["gestion_agence"] == gestion)
        & (df["frais_gestion_pct"] == frais_gestion)
    ]
    if filtered.empty:
        st.info("Aucune combinaison pour ces filtres.")
        return

    vacances = sorted(filtered["vacance_mois"].unique())
    tabs = st.tabs([f"Vacance {vacance:g} mois/an" for vacance in vacances])
    for tab, vacance in zip(tabs, vacances, strict=True):
        vacancy_df = filtered[filtered["vacance_mois"] == vacance]
        with tab:
            _plot_heatmap(vacancy_df, "cashflow_mensuel_apres_impot", "Cash-flow")

    direct_mask = ~df["gestion_agence"].astype(bool)
    chart_df = df[
        (df["prix_achat"] == prix_achat)
        & (df["apport"] == apport)
        & (direct_mask | (df["frais_gestion_pct"] == frais_gestion))
    ].copy()
    chart_df["gestion"] = chart_df["gestion_agence"].map(_gestion_label)
    chart_df["duree_credit"] = chart_df["duree_annees"].map(lambda duree: f"{int(duree)} ans")
    chart_df["vacance"] = chart_df["vacance_mois"].map(lambda mois: f"{mois:g} mois")
    fig = px.line(
        chart_df.sort_values("taux_credit"),
        x="taux_credit",
        y="cashflow_mensuel_apres_impot",
        color="duree_credit",
        line_dash="vacance",
        facet_col="gestion",
        markers=True,
        labels={
            "taux_credit": "Taux",
            "cashflow_mensuel_apres_impot": "Cash-flow mensuel",
            "duree_credit": "Duree",
            "vacance": "Vacance",
            "gestion": "Gestion",
        },
    )
    st.plotly_chart(fig, width="stretch")

    distribution = df.copy()
    distribution["gestion"] = distribution["gestion_agence"].map(_gestion_label)
    hist = px.histogram(
        distribution,
        x="cashflow_mensuel_apres_impot",
        color="gestion",
        nbins=40,
        labels={
            "cashflow_mensuel_apres_impot": "Cash-flow mensuel annee 1",
            "gestion": "Gestion",
        },
    )
    st.plotly_chart(hist, width="stretch")


def _plot_heatmap(df: pd.DataFrame, value: str, label: str) -> None:
    pivot = df.pivot_table(
        index="taux_credit",
        columns="duree_annees",
        values=value,
        aggfunc="mean",
    )
    fig = px.imshow(
        pivot,
        text_auto=".0f",
        aspect="auto",
        color_continuous_scale="RdYlGn",
        labels={"x": "Duree", "y": "Taux", "color": label},
    )
    st.plotly_chart(fig, width="stretch")


def _cashflow_status(value: float, seuils: SeuilsDecision) -> str:
    if value >= seuils.cashflow_mensuel_cible:
        return "OK"
    if value >= seuils.cashflow_mensuel_min:
        return "Attention"
    return "Bloquant"


def _threshold_status(value: float, minimum: float) -> str:
    return "OK" if value >= minimum else "Bloquant"


def _status_style(status: str) -> str:
    return {
        "OK": "background:#dcfce7;color:#166534;border:1px solid #86efac;",
        "Attention": "background:#fef3c7;color:#92400e;border:1px solid #fcd34d;",
        "Bloquant": "background:#fee2e2;color:#991b1b;border:1px solid #fecaca;",
        "Neutre": "background:#e2e8f0;color:#475569;border:1px solid #cbd5e1;",
        "A verifier": "background:#e0f2fe;color:#075985;border:1px solid #7dd3fc;",
    }.get(status, "background:#e2e8f0;color:#475569;border:1px solid #cbd5e1;")


def _decision_factor(title: str, value: str, status: str, detail: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.markdown(
            f"<span style='display:inline-block;padding:2px 8px;border-radius:999px;{_status_style(status)}'>{status}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(value)
        st.caption(detail)


def _diagnostic_status_label(status: DiagnosticStatus) -> str:
    return {
        DiagnosticStatus.OK: "OK",
        DiagnosticStatus.WARNING: "Attention",
        DiagnosticStatus.BLOCKING: "Bloquant",
        DiagnosticStatus.MISSING: "A verifier",
    }[status]


def _decision_map(
    df: pd.DataFrame,
    annonce: AnnonceRecord,
    bien: BienImmobilier,
    location: HypothesesLocation,
) -> None:
    st.subheader("Carte de decision")
    seuils = SeuilsDecision()
    best = df.iloc[0]
    cashflow = float(best["cashflow_mensuel_apres_impot"])
    viables = df[df["cashflow_mensuel_apres_impot"] >= seuils.cashflow_mensuel_min]
    pct_viable = len(viables) / len(df) * 100 if len(df) else 0.0

    agence_df = df[df["gestion_agence"].astype(bool)]
    if agence_df.empty:
        agence_value = "Non simulee"
        agence_status = "Neutre"
        agence_detail = "Active la gestion agence si elle doit rester viable."
    else:
        agence_cashflow = float(agence_df["cashflow_mensuel_apres_impot"].max())
        agence_value = f"{agence_cashflow:,.0f} EUR/mois"
        agence_status = _cashflow_status(agence_cashflow, seuils)
        agence_detail = "Meilleur cash-flow avec agence."

    prudent_df = df[df["vacance_mois"] >= 1.0]
    prudent_cashflow = float(prudent_df["cashflow_mensuel_apres_impot"].max()) if not prudent_df.empty else cashflow
    dpe = (annonce.dpe or "").strip().upper()[:1]
    if not dpe:
        dpe_status = "Attention"
        dpe_value = "A verifier"
    elif dpe in seuils.dpe_a_eviter:
        dpe_status = "Bloquant"
        dpe_value = dpe
    else:
        dpe_status = "OK"
        dpe_value = dpe

    c1, c2, c3 = st.columns(3)
    with c1:
        _decision_factor(
            "Cash-flow",
            f"{cashflow:,.0f} EUR/mois",
            _cashflow_status(cashflow, seuils),
            "Meilleur scenario calcule, moyenne mensuelle annee 1.",
        )
    with c2:
        _decision_factor(
            "Scenarios viables",
            f"{len(viables):,} / {len(df):,}",
            "OK" if pct_viable >= 50 else "Attention" if pct_viable > 0 else "Bloquant",
            f"{pct_viable:.0f} % des scenarios restent au-dessus de {seuils.cashflow_mensuel_min:,.0f} EUR/mois.",
        )
    with c3:
        _decision_factor(
            "Gestion agence",
            agence_value,
            agence_status,
            agence_detail,
        )

    c4, c5, c6 = st.columns(3)
    with c4:
        _decision_factor(
            "Vacance prudente",
            f"{prudent_cashflow:,.0f} EUR/mois",
            _cashflow_status(prudent_cashflow, seuils),
            "Meilleur scenario avec au moins 1 mois de vacance par an.",
        )
    with c5:
        rendement_net = float(best["rendement_net_avant_impot_pct"])
        _decision_factor(
            "Rendement net",
            f"{rendement_net:.2f} %",
            _threshold_status(rendement_net, seuils.rendement_net_min_pct),
            f"Seuil indicatif : {seuils.rendement_net_min_pct:.1f} % avant impot.",
        )
    with c6:
        _decision_factor(
            "DPE",
            dpe_value,
            dpe_status,
            "F/G a traiter comme risque bloquant sans decote et travaux maitrises.",
        )

    st.subheader("Diagnostic reglementaire")
    location_best = replace(location, loyer_hc_mensuel=float(best["loyer_hc_mensuel"]))
    diagnostics = diagnostiquer_annonce(bien, location_best)
    if not diagnostics:
        st.info("Aucun diagnostic local disponible pour cette annonce.")
        return
    for item in diagnostics:
        status = _diagnostic_status_label(item.status)
        detail = item.message
        if item.seuil is not None:
            detail = f"{detail} Seuil : {item.seuil}."
        _decision_factor(
            item.code.replace("_", " "),
            str(item.valeur) if item.valeur is not None else "-",
            status,
            detail,
        )


def _comparison_page(conn, rows: list[dict[str, Any]], annonce: AnnonceRecord | None) -> None:
    st.subheader("Comparaison et decision")
    runs = list_simulation_runs(conn)
    if runs:
        latest_by_annonce: dict[int, dict[str, Any]] = {}
        for run in runs:
            latest_by_annonce.setdefault(int(run["annonce_id"]), run)
        best_rows = []
        for run in latest_by_annonce.values():
            results = get_simulation_results(conn, int(run["id"]))
            if results:
                best = results[0]
                robustesse = analyser_grille(results)
                best["ville"] = run["ville"]
                best["quartier"] = run["quartier"]
                best["run_id"] = run["id"]
                best["decision_robuste"] = robustesse.decision
                best["cashflow_median"] = robustesse.cashflow_median
                best["pct_scenarios_viables"] = robustesse.pct_viables
                best["nb_scenarios_viables"] = robustesse.nb_viables
                best_rows.append(best)
        if best_rows:
            df = pd.DataFrame(best_rows)
            st.dataframe(
                df[
                    [
                        "ville",
                        "quartier",
                        "decision_robuste",
                        "cashflow_median",
                        "pct_scenarios_viables",
                        "nb_scenarios_viables",
                        "score",
                        "prix_achat",
                        "loyer_hc_mensuel",
                        "cashflow_mensuel_apres_impot",
                        "effort_epargne_mensuel",
                        "montant_emprunte",
                        "mensualite_totale",
                        "rendement_net_net_pct",
                        "taux_credit",
                        "duree_annees",
                        "apport",
                        "vacance_mois",
                        "gestion_agence",
                        "frais_gestion_pct",
                        "run_id",
                    ]
                ].sort_values(["score", "cashflow_mensuel_apres_impot"], ascending=False),
                hide_index=True,
                width="stretch",
            )
    else:
        st.info("Aucun snapshot sauvegarde. Tu peux deja analyser en direct dans l'onglet Simulations.")

    if annonce is None:
        return
    st.divider()
    st.subheader("Decision sur l'annonce active")
    with st.form("decision_form"):
        statut = st.selectbox(
            "Statut",
            options=STATUTS,
            index=STATUTS.index(annonce.statut) if annonce.statut in STATUTS else 0,
        )
        notes = st.text_area("Notes de decision", value=annonce.notes, height=130)
        if st.form_submit_button("Sauvegarder la decision"):
            update_decision(conn, annonce.id or 0, statut=statut, notes=notes)
            st.success("Decision sauvegardee.")
            st.rerun()


def _history_page(conn, annonce_id: int | None) -> None:
    runs = list_simulation_runs(conn, annonce_id)
    if not runs:
        st.info("Pas encore d'historique.")
        return
    st.dataframe(pd.DataFrame(runs), hide_index=True, width="stretch")
    run_id = st.selectbox("Inspecter un snapshot", [int(run["id"]) for run in runs])
    st.dataframe(pd.DataFrame(get_simulation_results(conn, run_id)).head(100), hide_index=True, width="stretch")


def main() -> None:
    st.set_page_config(page_title="Simulateur d'Achat immobilier locatif", layout="wide")
    st.title("Simulateur d'Achat immobilier locatif")

    db_path = st.sidebar.text_input("Base SQLite", value=str(DEFAULT_DB_PATH))
    conn = _database(db_path)
    rows, selected_id = _sidebar(conn)
    annonce, hypotheses = _load_bundle(conn, selected_id)

    tab_dashboard, tab_annonce, tab_hypotheses, tab_simulation, tab_comparison, tab_history = st.tabs(
        ["Tableau de bord", "Annonce", "Hypotheses", "Simulations", "Comparaison", "Historique"]
    )

    with tab_dashboard:
        _dashboard(conn, rows)
    with tab_annonce:
        _annonce_page(conn, annonce, hypotheses)
    with tab_hypotheses:
        _hypotheses_page(conn, annonce, hypotheses)
    with tab_simulation:
        _simulation_page(conn, annonce, hypotheses)
    with tab_comparison:
        _comparison_page(conn, rows, annonce)
    with tab_history:
        _history_page(conn, selected_id)


if __name__ == "__main__":
    main()
