"""Rendus Streamlit des resultats de simulation."""

from __future__ import annotations

from dataclasses import asdict, replace

import pandas as pd
import plotly.express as px
import streamlit as st

from achat_immo.comparison import SeuilsDecision
from achat_immo.diagnostics import diagnostiquer_annonce
from achat_immo.grids import GrilleResultat
from achat_immo.engines.loan import tableau_amortissement
from achat_immo.models import (
    BienImmobilier,
    HypothesesLocation,
    RegimeFiscal,
    ResultatSimulation,
)
from achat_immo.robustness import RobustesseGrille
from achat_immo.storage import AnnonceRecord
from app.components import (
    decision_factor as _decision_factor,
    decision_robuste_status as _decision_robuste_status,
    diagnostic_status_label as _diagnostic_status_label,
)
from app.ui_helpers import (
    format_eur_optional as _format_eur_optional,
    gestion_label as _gestion_label,
)


def strategie_summary(df: pd.DataFrame) -> None:
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


def scenario_details(resultats: list[GrilleResultat]) -> None:
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


def robustesse_summary(robustesse: RobustesseGrille) -> None:
    st.subheader("Decision robuste")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _decision_factor(
            "Decision",
            robustesse.decision.replace("_", " "),
            _decision_robuste_status(robustesse.decision),
            "Decision basee sur l'ensemble de la grille, pas seulement le meilleur scenario.",
        )
    c2.metric(
        "Scenarios viables",
        f"{robustesse.nb_viables:,} / {robustesse.nb_scenarios:,}",
        f"{robustesse.pct_viables:.1f} %",
    )
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


def visualisations(df: pd.DataFrame) -> None:
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


def decision_map(
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
