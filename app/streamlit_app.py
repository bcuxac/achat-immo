"""Application Streamlit pour piloter les decisions locatives."""

from __future__ import annotations

from dataclasses import asdict, replace
from inspect import signature
import os
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
SRC_PATH_STR = str(SRC_PATH)
if SRC_PATH_STR in sys.path:
    sys.path.remove(SRC_PATH_STR)
sys.path.insert(0, SRC_PATH_STR)

from achat_immo.auth import verify_password
from achat_immo.grids import (
    GrilleResultat,
    GrilleParametres,
    compter_scenarios_grille,
    generer_plage_float,
    generer_plage_int,
    grille_to_dataframe,
    simuler_grille_annonce,
)
from achat_immo.loan import tableau_amortissement
from achat_immo.comparison import SeuilsDecision
from achat_immo.city_profiles import (
    SECTEUR_A_VERIFIER,
    canonical_city_label,
    loyer_max_hc_mensuel,
    profile_for_city,
    supported_city_labels,
)
from achat_immo.diagnostics import DiagnosticStatus, diagnostiquer_annonce
from achat_immo.hypothesis_inference import (
    appliquer_suggestions,
    inferer_hypotheses_depuis_annonce,
    prelevements_sociaux_par_regime,
    regime_fiscal_recommande,
    regimes_compatibles,
)
from achat_immo.models import (
    BienImmobilier,
    EpoqueConstruction,
    Fiscalite,
    HypothesesLocation,
    ModeLocation,
    RegimeFiscal,
    ResultatSimulation,
    Scenario,
    TypeBien,
)
from achat_immo.robustness import RobustesseGrille, analyser_grille
from achat_immo.storage import (
    AnnonceRecord,
    DEFAULT_DB_PATH,
    fiscalite_from_hypotheses,
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

SIMULATION_SECTION_LABELS = ("Exploitation", "Strategies testees", "Analyse")
PORTFOLIO_DECISION_LABEL = "Decision portefeuille"


HYPOTHESES_HELP = {
    "frais_notaire_estimes": (
        "Impact fort sur le cout total et le pret. Estimation automatique : environ 8 % dans l'ancien, "
        "2,5 % si l'annonce mentionne neuf ou VEFA. A remplacer par le decompte notarial."
    ),
    "frais_agence_achat": (
        "Impact fort si les honoraires sont a charge acquereur. Laisser a 0 si le prix est FAI ou si les "
        "honoraires sont a charge vendeur."
    ),
    "travaux_estimes": (
        "Impact tres fort : augmente le cout total mais peut aussi reduire le resultat fiscal au reel. "
        "Inclure travaux immediats, energetiques, remise en location et marge d'imprevu."
    ),
    "meubles_estimes": (
        "Budget mobilier du scenario meuble. Il reste saisi meme si le regime de reference est nu : "
        "le moteur le neutralise automatiquement pour les strategies en location nue."
    ),
    "frais_bancaires": (
        "Frais de dossier, courtage eventuel et petits frais de mise en place du pret. Impact modere mais finance."
    ),
    "garantie": (
        "Cautionnement, credit logement ou garantie bancaire. Impacte le cout total finance ; a remplacer par "
        "l'offre bancaire des qu'elle existe."
    ),
    "mode_location": (
        "Determine le cadre fiscal et parfois le plafond de loyer. Meuble : revenus BIC/LMNP, CFE possible. "
        "Nue : revenus fonciers."
    ),
    "loyer_hc_mensuel": (
        "Loyer hors charges de reference. Il sert a pre-remplir la grille ; a Grenoble il doit rester sous le "
        "loyer de reference majore calcule. Source Grenoble : "
        "https://www.grenoblealpesmetropole.fr/940-me-renseigner-sur-l-encadrement-des-loyers.htm"
    ),
    "taxe_fonciere": (
        "Charge proprietaire recurrente, non incluse dans les charges locatives. Impact direct sur cash-flow "
        "et rendement net."
    ),
    "charges_copro_annuelles": (
        "Charges annuelles totales de copropriete payees par le proprietaire. Le modele retranche ensuite la "
        "part recuperable pour calculer la charge bailleur nette."
    ),
    "charges_recuperables_annuelles": (
        "Part des charges de copro refacturable au locataire. Ne doit pas depasser les charges copro annuelles."
    ),
    "assurance_pno": (
        "Assurance proprietaire non occupant. Charge recurrente deductible au reel, impact modere mais quasi "
        "systematique."
    ),
    "assurance_gli": (
        "Garantie loyers impayes. Si elle est activee, saisir le cout annuel ; ordre de grandeur courant : "
        "2,5 a 4 % des loyers charges comprises."
    ),
    "cfe_annuelle": (
        "Cotisation fonciere des entreprises. Les locations meublees peuvent y etre soumises, meme en LMNP ; "
        "exoneration generale si recettes <= 5 000 EUR. Source : "
        "https://www.impots.gouv.fr/particulier/questions/je-fais-de-la-location-meublee-dois-je-payer-de-la-cfe-cotisation-fonciere-des"
    ),
    "comptable_lmnp": (
        "Honoraires annuels d'expert-comptable ou plateforme comptable. Pertinent surtout en LMNP reel, car le "
        "regime reel suppose une comptabilite et une declaration de resultat. Source : "
        "https://www.impots.gouv.fr/particulier/les-regimes-dimposition"
    ),
    "entretien_annuel": (
        "Reserve annuelle pour petit entretien, remplacement et menus travaux non planifies. Impact direct sur "
        "cash-flow prudent."
    ),
    "gestion_agence_possible": (
        "Autorise la grille a tester les scenarios avec agence. Si decoche, les scenarios agence sont exclus."
    ),
    "regime_fiscal": (
        "Regime fiscal de reference pour l'annonce. La simulation peut ensuite tester automatiquement les "
        "regimes compatibles. Source : https://www.impots.gouv.fr/particulier/les-regimes-dimposition"
    ),
    "tmi_pct": (
        "Tranche marginale d'imposition du foyer. Le modele applique TMI + prelevements sociaux au resultat "
        "taxable positif ; c'est une approximation prudente."
    ),
    "prelevements_sociaux_pct": (
        "Taux 2026 sur revenu net locatif : 17,2 % en location nue, 18,6 % en location meublee. Source : "
        "https://www.impots.gouv.fr/particulier/questions/je-donne-un-bien-en-location-dois-je-payer-des-prelevements-sociaux"
    ),
    "part_terrain_pct": (
        "Part du prix correspondant au terrain, non amortissable en LMNP reel. Valeur indicative a confirmer "
        "avec le comptable."
    ),
    "duree_amortissement_bien_annees": (
        "Duree d'amortissement indicative du bati en LMNP reel. L'amortissement ne peut pas creer de deficit "
        "fiscal LMNP. Source : https://www.impots.gouv.fr/particulier/les-regimes-dimposition"
    ),
    "duree_amortissement_travaux_annees": (
        "Duree indicative d'amortissement des travaux immobilises au LMNP reel. A ajuster selon la nature des "
        "travaux et le comptable."
    ),
    "duree_amortissement_meubles_annees": (
        "Duree indicative d'amortissement du mobilier au LMNP reel. A ajuster selon le plan comptable retenu."
    ),
    "abattement_micro_bic_pct": (
        "Abattement forfaitaire micro-BIC pour location meublee longue duree : 50 % dans le cas usuel modelise. "
        "Les charges reelles ne sont alors pas deduites. Source : https://www.impots.gouv.fr/particulier/les-regimes-dimposition"
    ),
    "abattement_micro_foncier_pct": (
        "Abattement forfaitaire micro-foncier : 30 % si revenus fonciers bruts du foyer <= 15 000 EUR et pas "
        "d'exclusion. Source : https://bofip.impots.gouv.fr/bofip/3973-PGP.html"
    ),
}

FIELD_HELP = HYPOTHESES_HELP

SIMULATION_HELP = {
    "prix_decotes": (
        "Teste le prix affiche et les decotes de negociation. A modifier si la marge de negociation est "
        "manifestement plus faible ou plus forte."
    ),
    "loyer_variations": (
        "Teste un loyer prudent, central et optimiste autour du loyer de reference. Le plafond local reste applique."
    ),
    "taux_credit": "Taux annuels a comparer. Garde une fourchette courte pour lire rapidement l'effet bancaire.",
    "durees": "Durees de credit proposees. Elles pilotent fortement le cash-flow et le patrimoine net.",
    "apports": "Fonds propres investis au depart. Sert au TRI fonds propres et au cash-on-cash.",
    "assurance_emprunteur": "Taux annuel d'assurance emprunteur applique au capital initial.",
    "vacances": "Vacance locative annuelle testee. Un mois par an correspond a environ 8,33 % de vacance.",
    "modes_gestion": "Compare gestion directe et agence si l'annonce peut rester viable avec delegation.",
    "frais_gestion": "Honoraires annuels d'agence en pourcentage des loyers encaisses.",
    "comparer_regimes": "Teste automatiquement les regimes fiscaux compatibles avec le mode de location retenu.",
    "comparer_modes": "Ajoute la comparaison meublee / nue. Utile si la strategie n'est pas encore tranchee.",
    "regimes_fiscaux": "Permet d'exclure un regime que tu ne souhaites pas utiliser malgre sa compatibilite.",
    "horizon": "Duree de detention analysee. Elle change le TRI, la plus-value et le capital restant du.",
    "taux_actualisation": "Cout du capital utilise pour la VAN. 4 % est une valeur prudente par defaut.",
    "commentaire": "Libelle du snapshot sauvegarde pour retrouver l'hypothese de travail.",
    "grille_avancee": "Active les min/max/pas historiques si tu veux une grille plus large que le mode compact.",
}

FIELD_ORIGIN = {
    "frais_notaire_estimes": "Saisi",
    "frais_agence_achat": "Saisi",
    "travaux_estimes": "Saisi",
    "meubles_estimes": "Saisi",
    "frais_bancaires": "Saisi",
    "garantie": "Saisi",
    "mode_location": "Saisi",
    "loyer_hc_mensuel": "Saisi",
    "taxe_fonciere": "Saisi",
    "charges_copro_annuelles": "Saisi",
    "charges_recuperables_annuelles": "Saisi",
    "assurance_pno": "Saisi",
    "assurance_gli": "Saisi",
    "cfe_annuelle": "Saisi",
    "comptable_lmnp": "Saisi",
    "entretien_annuel": "Saisi",
    "gestion_agence_possible": "Saisi",
    "regime_fiscal": "Saisi",
    "tmi_pct": "Saisi",
    "prelevements_sociaux_pct": "Deduit",
    "abattement_micro_bic_pct": "Deduit",
    "abattement_micro_foncier_pct": "Deduit",
    "seuil_micro_bic": "Deduit",
    "seuil_micro_foncier": "Deduit",
    "taux_impot_plus_value_pct": "Deduit",
    "taux_prelevements_sociaux_plus_value_pct": "Deduit",
    "reintegrer_amortissements_lmnp_plus_value": "Deduit",
    "cfe_neutralisee": "Deduit",
    "comptable_lmnp_neutralise": "Deduit",
    "part_terrain_pct": "Avance",
    "duree_amortissement_bien_annees": "Avance",
    "duree_amortissement_travaux_annees": "Avance",
    "duree_amortissement_meubles_annees": "Avance",
}


def field_origin(field_name: str) -> str:
    return FIELD_ORIGIN.get(field_name, "Saisi")


def is_deduced_field(field_name: str) -> bool:
    return field_origin(field_name) == "Deduit"


def is_advanced_field(field_name: str) -> bool:
    return field_origin(field_name) == "Avance"


def is_cfe_applicable(mode_location: ModeLocation) -> bool:
    return mode_location == ModeLocation.MEUBLEE


def is_comptable_lmnp_applicable(regime_fiscal: RegimeFiscal) -> bool:
    return regime_fiscal == RegimeFiscal.LMNP_REEL


def effective_cfe_value(mode_location: ModeLocation, value: float) -> float:
    return float(value) if is_cfe_applicable(mode_location) else 0.0


def effective_comptable_lmnp_value(regime_fiscal: RegimeFiscal, value: float) -> float:
    return float(value) if is_comptable_lmnp_applicable(regime_fiscal) else 0.0


def derived_fiscalite_values(regime_fiscal: RegimeFiscal) -> dict[str, float | bool]:
    defaults = Fiscalite()
    return {
        "prelevements_sociaux_pct": prelevements_sociaux_par_regime(regime_fiscal),
        "abattement_micro_bic_pct": defaults.abattement_micro_bic_pct,
        "abattement_micro_foncier_pct": defaults.abattement_micro_foncier_pct,
        "taux_impot_plus_value_pct": defaults.taux_impot_plus_value_pct,
        "taux_prelevements_sociaux_plus_value_pct": defaults.taux_prelevements_sociaux_plus_value_pct,
        "reintegrer_amortissements_lmnp_plus_value": defaults.reintegrer_amortissements_lmnp_plus_value,
    }


def _badge_caption(field_name: str) -> None:
    st.caption(f"Champ {field_origin(field_name)}")


def _readonly_field(label: str, value: str, field_name: str, help_text: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{label}**")
        st.write(value)
        st.caption(f"Champ {field_origin(field_name)} - {help_text}")


@st.cache_resource
def _database(target: str):
    return open_database(target)


def _secret_value(key: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(key, default)
    except FileNotFoundError:
        return default


def _secret_section(key: str) -> dict[str, Any]:
    value = _secret_value(key, {})
    if value is None:
        return {}
    return dict(value)


def _configured_database_url() -> str:
    database = _secret_section("database")
    value = (
        database.get("url")
        or _secret_value("DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    )
    return str(value).strip()


def _auth_users() -> dict[str, str]:
    auth = _secret_section("auth")
    users = dict(auth.get("users", {}) or {})
    if users:
        return {str(user): str(password_hash) for user, password_hash in users.items()}

    password_hash = auth.get("password_hash") or auth.get("password")
    if password_hash:
        return {"": str(password_hash)}
    return {}


def _auth_enabled() -> bool:
    auth = _secret_section("auth")
    if "enabled" in auth:
        return bool(auth["enabled"])
    return bool(_auth_users())


def _require_authentication() -> None:
    if not _auth_enabled():
        return

    users = _auth_users()
    if not users:
        st.error("Authentification active mais aucun utilisateur n'est configure.")
        st.stop()

    if st.session_state.get("authenticated"):
        auth_user = st.session_state.get("auth_user", "")
        if auth_user:
            st.sidebar.caption(f"Connecte : {auth_user}")
        if st.sidebar.button("Deconnexion"):
            st.session_state.pop("authenticated", None)
            st.session_state.pop("auth_user", None)
            st.rerun()
        return

    st.title("Connexion")
    with st.form("login-form"):
        username = ""
        if "" not in users:
            username = st.text_input("Utilisateur")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter")

    if submitted:
        expected = users.get(username)
        if expected and verify_password(password, expected):
            st.session_state["authenticated"] = True
            st.session_state["auth_user"] = username
            st.rerun()
        st.error("Identifiants invalides.")

    st.stop()


def _as_float_tuple(values: list[float]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


def _as_int_tuple(values: list[int]) -> tuple[int, ...]:
    return tuple(int(value) for value in values)


def _runtime_api_errors() -> list[str]:
    errors: list[str] = []
    grille_params = signature(GrilleParametres).parameters
    scenario_params = signature(Scenario).parameters
    count_params = signature(compter_scenarios_grille).parameters
    simulate_params = signature(simuler_grille_annonce).parameters

    for field_name in ("modes_location", "regimes_fiscaux", "comparer_regimes", "appliquer_plafond_loyer"):
        if field_name not in grille_params:
            errors.append(f"GrilleParametres ne contient pas {field_name}.")
    if "taux_actualisation_pct" not in scenario_params:
        errors.append("Scenario ne contient pas taux_actualisation_pct.")
    for parameter_name in ("fiscalite", "gestion_agence_possible"):
        if parameter_name not in count_params:
            errors.append(f"compter_scenarios_grille ne supporte pas {parameter_name}.")
    for parameter_name in ("fiscalite", "scenario_base", "gestion_agence_possible"):
        if parameter_name not in simulate_params:
            errors.append(f"simuler_grille_annonce ne supporte pas {parameter_name}.")
    return errors


def _require_current_runtime_api() -> None:
    errors = _runtime_api_errors()
    if not errors:
        return
    st.error("Le code Python charge par l'application n'est pas synchronise avec l'interface Streamlit.")
    st.caption("Redeploie l'application avec le dernier commit et vide le cache de dependances si necessaire.")
    st.code("\n".join(errors))
    st.stop()


def _enum_label(value: Any) -> str:
    return str(getattr(value, "value", value)).replace("_", " ")


def _display_hypothesis_value(value: Any) -> str:
    if hasattr(value, "value"):
        return _enum_label(value)
    if isinstance(value, bool):
        return "oui" if value else "non"
    if isinstance(value, float):
        return f"{value:,.1f}" if value % 1 else f"{value:,.0f}"
    return str(value)


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


def _strategie_summary(df: pd.DataFrame) -> None:
    st.subheader("Meilleures strategies")
    rows = []
    if "tri_annuel_pct" in df.columns:
        tri_df = df.dropna(subset=["tri_annuel_pct"])
        if not tri_df.empty:
            row = tri_df.sort_values("tri_annuel_pct", ascending=False).iloc[0]
            rows.append(("Meilleur TRI", row))
    if "patrimoine_net_sortie" in df.columns:
        row = df.sort_values("patrimoine_net_sortie", ascending=False).iloc[0]
        rows.append(("Meilleur patrimoine net", row))
    prudent_df = df[df["vacance_mois"] >= 1.0] if "vacance_mois" in df.columns else pd.DataFrame()
    if not prudent_df.empty:
        row = prudent_df.sort_values("cashflow_mensuel_apres_impot", ascending=False).iloc[0]
        rows.append(("Cash-flow prudent", row))
    rows.append(("Meilleur compromis", df.sort_values("score", ascending=False).iloc[0]))

    synthese = []
    for objectif, row in rows:
        synthese.append(
            {
                "objectif": objectif,
                "mode_location": row.get("mode_location", ""),
                "regime_fiscal": row.get("regime_fiscal", ""),
                "score": row.get("score"),
                "tri_annuel_pct": row.get("tri_annuel_pct"),
                "cashflow_mensuel_apres_impot": row.get("cashflow_mensuel_apres_impot"),
                "patrimoine_net_sortie": row.get("patrimoine_net_sortie"),
                "van": row.get("van"),
                "break_even_year": row.get("break_even_year"),
                "nb_annees_cashflow_negatif": row.get("nb_annees_cashflow_negatif"),
                "impot_plus_value": row.get("impot_plus_value"),
            }
        )
    st.dataframe(pd.DataFrame(synthese), hide_index=True, width="stretch")

    group_cols = [col for col in ("mode_location", "regime_fiscal") if col in df.columns]
    if group_cols and {"tri_annuel_pct", "patrimoine_net_sortie", "cashflow_mensuel_apres_impot"}.issubset(df.columns):
        strategy_rows = []
        for key, group in df.groupby(group_cols, dropna=False):
            if not isinstance(key, tuple):
                key = (key,)
            prudent_group = group[group["vacance_mois"] >= 1.0] if "vacance_mois" in group.columns else group
            cashflow_prudent = (
                float(prudent_group["cashflow_mensuel_apres_impot"].max())
                if not prudent_group.empty
                else float(group["cashflow_mensuel_apres_impot"].max())
            )
            strategy_rows.append(
                {
                    **dict(zip(group_cols, key, strict=True)),
                    "tri_annuel_pct": group["tri_annuel_pct"].max(),
                    "patrimoine_net_sortie": group["patrimoine_net_sortie"].max(),
                    "cashflow_prudent": cashflow_prudent,
                    "score": group["score"].max() if "score" in group.columns else None,
                }
            )
        strategy_df = pd.DataFrame(strategy_rows).dropna(subset=["tri_annuel_pct", "patrimoine_net_sortie"])
        if not strategy_df.empty:
            strategy_df["strategie"] = strategy_df[group_cols].astype(str).agg(" / ".join, axis=1)
            fig = px.scatter(
                strategy_df,
                x="tri_annuel_pct",
                y="patrimoine_net_sortie",
                color="cashflow_prudent",
                hover_name="strategie",
                hover_data=["score"],
                labels={
                    "tri_annuel_pct": "TRI fonds propres (%)",
                    "patrimoine_net_sortie": "Patrimoine net sortie",
                    "cashflow_prudent": "Cash-flow prudent",
                },
            )
            st.plotly_chart(fig, width="stretch")


def _scenario_option_label(item: GrilleResultat) -> str:
    resultat = item.resultat
    regime = resultat.regime_fiscal.value if resultat.regime_fiscal else item.regime_fiscal.value
    mode = resultat.mode_location.value if resultat.mode_location else item.mode_location.value
    tri = "n/a" if resultat.tri_annuel_pct is None else f"{resultat.tri_annuel_pct:.2f} %"
    return (
        f"{mode} / {regime} | score {item.score} | "
        f"CF {resultat.cashflow_mensuel_apres_impot:,.0f} EUR/mois | TRI {tri}"
    )


def _tableau_mensuel_credit(item: GrilleResultat) -> pd.DataFrame:
    echeances = tableau_amortissement(
        montant=item.resultat.montant_emprunte,
        taux_annuel_pct=item.taux_credit,
        duree_annees=item.duree_annees,
        assurance_annuelle_pct=item.assurance_emprunteur_annuelle_pct,
    )
    return pd.DataFrame([asdict(echeance) for echeance in echeances])


def _scenario_details(resultats: list[GrilleResultat]) -> None:
    with st.expander("Inspection detaillee du scenario selectionne", expanded=False):
        limit = min(len(resultats), 200)
        item = st.selectbox(
            "Scenario inspecte",
            resultats[:limit],
            format_func=_scenario_option_label,
        )
        resultat: ResultatSimulation = item.resultat

        with st.expander("Amortissement du credit", expanded=True):
            credit_df = pd.DataFrame(resultat.credit_annuel)
            if not credit_df.empty:
                fig = px.bar(
                    credit_df,
                    x="annee",
                    y=["capital", "interets"],
                    labels={"value": "EUR", "annee": "Annee", "variable": "Flux"},
                )
                st.plotly_chart(fig, width="stretch")
                crd_fig = px.line(credit_df, x="annee", y="crd_fin", markers=True, labels={"crd_fin": "CRD fin"})
                st.plotly_chart(crd_fig, width="stretch")
                st.dataframe(credit_df, hide_index=True, width="stretch")

            credit_mensuel_df = _tableau_mensuel_credit(item)
            st.download_button(
                "Telecharger le tableau mensuel du credit",
                credit_mensuel_df.to_csv(index=False).encode("utf-8"),
                file_name=f"credit_{resultat.scenario.nom}.csv",
                mime="text/csv",
            )

        with st.expander("Fiscalite annuelle", expanded=False):
            fiscal_df = pd.DataFrame(resultat.fiscalite_annuelle)
            if fiscal_df.empty:
                st.info("Aucune fiscalite annuelle disponible pour ce scenario.")
            else:
                st.dataframe(fiscal_df, hide_index=True, width="stretch")

        with st.expander("Amortissements fiscaux", expanded=False):
            amort_df = pd.DataFrame(resultat.amortissements_fiscaux)
            if resultat.regime_fiscal != RegimeFiscal.LMNP_REEL:
                st.info("Amortissements fiscaux non applicable pour ce regime.")
            elif amort_df.empty:
                st.info("Aucun tableau d'amortissement fiscal disponible.")
            else:
                fig_amort = px.bar(
                    amort_df,
                    x="annee",
                    y=["bati", "travaux", "meubles", "frais_acquisition"],
                    labels={"value": "Dotation", "annee": "Annee", "variable": "Composant"},
                )
                st.plotly_chart(fig_amort, width="stretch")
                line_df = amort_df[["annee", "amortissement_reporte", "resultat_imposable"]]
                line_fig = px.line(
                    line_df,
                    x="annee",
                    y=["amortissement_reporte", "resultat_imposable"],
                    markers=True,
                    labels={"value": "EUR", "variable": "Indicateur"},
                )
                st.plotly_chart(line_fig, width="stretch")
                st.dataframe(amort_df, hide_index=True, width="stretch")


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
    c4.metric("Cash-flow P10 grille", _format_eur_optional(robustesse.cashflow_p10))

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
    st.subheader("Sensibilite principale du cash-flow")
    f1, f2, f3, f4, f5, f6, f7 = st.columns(7)
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
    with f6:
        mode_location = st.selectbox("Mode", sorted(df["mode_location"].unique()) if "mode_location" in df.columns else [""])
    with f7:
        regime_fiscal = st.selectbox("Regime", sorted(df["regime_fiscal"].unique()) if "regime_fiscal" in df.columns else [""])

    filtered = df[
        (df["prix_achat"] == prix_achat)
        & (df["loyer_hc_mensuel"] == loyer)
        & (df["apport"] == apport)
        & (df["gestion_agence"] == gestion)
        & (df["frais_gestion_pct"] == frais_gestion)
    ]
    if "mode_location" in filtered.columns:
        filtered = filtered[filtered["mode_location"] == mode_location]
    if "regime_fiscal" in filtered.columns:
        filtered = filtered[filtered["regime_fiscal"] == regime_fiscal]
    if filtered.empty:
        st.info("Aucune combinaison pour ces filtres.")
        return

    vacances = sorted(filtered["vacance_mois"].unique())
    tabs = st.tabs([f"Vacance {vacance:g} mois/an" for vacance in vacances])
    for tab, vacance in zip(tabs, vacances, strict=True):
        vacancy_df = filtered[filtered["vacance_mois"] == vacance]
        with tab:
            _plot_heatmap(vacancy_df, "cashflow_mensuel_apres_impot", "Cash-flow")

    with st.expander("Graphes avances", expanded=False):
        direct_mask = ~df["gestion_agence"].astype(bool)
        chart_df = df[
            (df["prix_achat"] == prix_achat)
            & (df["apport"] == apport)
            & (direct_mask | (df["frais_gestion_pct"] == frais_gestion))
        ].copy()
        if "mode_location" in chart_df.columns:
            chart_df = chart_df[chart_df["mode_location"] == mode_location]
        if "regime_fiscal" in chart_df.columns:
            chart_df = chart_df[chart_df["regime_fiscal"] == regime_fiscal]
        if not chart_df.empty:
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
    st.subheader(PORTFOLIO_DECISION_LABEL)
    st.caption("Compare uniquement les annonces pour lesquelles un snapshot de simulation a ete sauvegarde.")
    runs = list_simulation_runs(conn)
    status_by_annonce = {
        int(row["id"]): str(row.get("statut") or "")
        for row in rows
        if row.get("id") is not None
    }
    if runs:
        latest_by_annonce: dict[int, dict[str, Any]] = {}
        for run in runs:
            latest_by_annonce.setdefault(int(run["annonce_id"]), run)
        best_rows = []
        for run in latest_by_annonce.values():
            results = get_simulation_results(conn, int(run["id"]))
            if results:
                best = dict(results[0])
                robustesse = analyser_grille(results)
                annonce_id = int(run["annonce_id"])
                best["ville"] = run["ville"]
                best["quartier"] = run["quartier"]
                best["run_id"] = run["id"]
                best["statut"] = status_by_annonce.get(annonce_id, "")
                best["decision_robuste"] = robustesse.decision
                best["meilleure_strategie"] = " / ".join(
                    value for value in (str(best.get("mode_location") or ""), str(best.get("regime_fiscal") or "")) if value
                )
                best["cashflow_prudent"] = robustesse.meilleur_cashflow_prudent
                best["cashflow_median"] = robustesse.cashflow_median
                best["pct_scenarios_viables"] = robustesse.pct_viables
                best_rows.append(best)
        if best_rows:
            df = pd.DataFrame(best_rows)
            decision_cols = [
                "ville",
                "quartier",
                "statut",
                "decision_robuste",
                "meilleure_strategie",
                "tri_annuel_pct",
                "patrimoine_net_sortie",
                "cashflow_prudent",
                "cashflow_median",
                "pct_scenarios_viables",
                "score",
                "run_id",
            ]
            visible_cols = [col for col in decision_cols if col in df.columns]
            sort_cols = [col for col in ("score", "patrimoine_net_sortie", "cashflow_prudent") if col in df.columns]
            st.dataframe(
                df[visible_cols].sort_values(sort_cols, ascending=False) if sort_cols else df[visible_cols],
                hide_index=True,
                width="stretch",
            )
        else:
            st.info("Sauvegarde un snapshot depuis Simulations pour comparer les annonces.")
    else:
        st.info("Sauvegarde un snapshot depuis Simulations pour comparer les annonces.")

    if annonce is None:
        return
    st.divider()
    st.subheader("Statut de l'annonce active")
    st.caption(
        "Ce statut sert au suivi de ton pipeline personnel : a analyser, a visiter, a negocier, favori, "
        "rejete ou archive."
    )
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
    _require_authentication()
    st.title("Simulateur d'Achat immobilier locatif")
    _require_current_runtime_api()

    database_url = _configured_database_url()
    if database_url:
        st.sidebar.caption("Base : PostgreSQL cloud")
        database_target = database_url
    else:
        database_target = st.sidebar.text_input("Base SQLite", value=str(DEFAULT_DB_PATH))
    conn = _database(database_target)
    rows, selected_id = _sidebar(conn)
    annonce, hypotheses = _load_bundle(conn, selected_id)

    tab_dashboard, tab_annonce, tab_hypotheses, tab_simulation, tab_comparison, tab_history = st.tabs(
        ["Tableau de bord", "Annonce", "Hypotheses", "Simulation", PORTFOLIO_DECISION_LABEL, "Historique"]
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
