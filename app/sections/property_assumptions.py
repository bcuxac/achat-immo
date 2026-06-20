"""Section de saisie des hypotheses d'investissement d'une fiche annonce."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd
import streamlit as st

from achat_immo.engines.fiscal_rules import (
    regime_fiscal_recommande,
    regimes_compatibles,
)
from achat_immo.hypothesis_inference import (
    appliquer_suggestions,
    inferer_hypotheses_depuis_annonce,
)
from achat_immo.models import ModeLocation, RegimeFiscal
from achat_immo.storage import (
    AnnonceRecord,
    DatabaseConnection,
    HypothesesAchatRecord,
    save_annonce,
)
from app.components import (
    badge_caption as _badge_caption,
    readonly_field as _readonly_field,
)
from app.help_texts import FIELD_HELP
from app.ui_helpers import (
    derived_fiscalite_values,
    display_hypothesis_value as _display_hypothesis_value,
    effective_cfe_value,
    effective_comptable_lmnp_value,
    enum_label as _enum_label,
    is_cfe_applicable,
    is_comptable_lmnp_applicable,
)


def property_assumptions_section(
    conn: DatabaseConnection,
    annonce: AnnonceRecord | None,
    hypotheses: HypothesesAchatRecord | None,
) -> None:
    if annonce is None or hypotheses is None:
        st.info("Selectionne une annonce dans la fiche.")
        return

    st.subheader("Hypotheses")
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
                min_value=0.0,
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


def _hypotheses_inference_panel(
    conn: DatabaseConnection,
    annonce: AnnonceRecord,
    hypotheses: HypothesesAchatRecord,
) -> None:
    if annonce.surface_m2 <= 0.0 or annonce.prix_affiche <= 0.0:
        st.info("💡 Renseignez une surface et un prix dans l'onglet 'Annonce' pour obtenir des suggestions automatiques.")
        return

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
