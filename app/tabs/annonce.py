"""Page de saisie des donnees factuelles d'une annonce."""

from __future__ import annotations

import os

import streamlit as st

from achat_immo.analysis.manual_analysis import AnalysisTargets, rerun_financial_analysis
from achat_immo.city_profiles import (
    SECTEUR_A_VERIFIER,
    canonical_city_label,
    profile_for_city,
    supported_city_labels,
)
from achat_immo.models import EpoqueConstruction, TypeBien
from achat_immo.storage import (
    AnnonceRecord,
    DatabaseConnection,
    HypothesesAchatRecord,
    save_annonce,
)
from achat_immo.sourcing_agents.llm_agent import LLMSourcingAgent
from achat_immo.sourcing_agents.orchestrator import SourcingOrchestrator
from app.ui_helpers import enum_label as _enum_label


def annonce_page(
    conn: DatabaseConnection,
    annonce: AnnonceRecord | None,
    hypotheses: HypothesesAchatRecord | None,
) -> None:
    if annonce is None or hypotheses is None:
        st.info("Cree ou selectionne une annonce dans la barre laterale.")
        return

    st.subheader("Données factuelles de l'annonce")
    st.caption("Ici on garde les informations propres au bien. La decision et les parametres iterables restent ailleurs.")

    # --- AFFICHAGE DES KPIs ORCHESTRATEUR ---
    if annonce.tri_p50 is not None:
        st.info("Cette annonce a été analysée par l'Orchestrateur en tâche de fond.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("TRI Médian", f"{annonce.tri_p50:.1f}%")
        c2.metric("Cash-on-Cash", f"{annonce.coc_p50:.1f}%" if annonce.coc_p50 else "N/A")
        c3.metric("Cashflow Mensuel", f"{annonce.cashflow_p50:.0f} €" if annonce.cashflow_p50 else "N/A")
        if annonce.prix_cible_recommande:
            diff_pct = (annonce.prix_cible_recommande - annonce.prix_affiche) / annonce.prix_affiche * 100
            c4.metric("Offre Recommandée", f"{annonce.prix_cible_recommande:,.0f} €", f"{diff_pct:.1f}%")
        else:
            c4.metric("Offre Recommandée", "Impossible")
            
        st.divider()

    with st.expander("Relance d'analyse"):
        c1, c2, c3, c4 = st.columns(4)
        target_tri = c1.number_input("TRI median cible (%)", value=6.0, step=0.5, key=f"target_tri_{annonce.id}")
        target_tri_p10 = c2.number_input("TRI P10 cible (%)", value=3.0, step=0.5, key=f"target_tri_p10_{annonce.id}")
        target_coc = c3.number_input("CoC cible (%)", value=0.0, step=0.5, key=f"target_coc_{annonce.id}")
        target_cf = c4.number_input("Cashflow cible", value=0.0, step=25.0, key=f"target_cf_{annonce.id}")
        targets = AnalysisTargets(
            target_tri_median=float(target_tri),
            target_tri_p10=float(target_tri_p10),
            target_coc=float(target_coc),
            target_cashflow=float(target_cf),
        )
        action_cols = st.columns(2)
        if action_cols[0].button(
            "Relancer l'analyse financiere",
            type="primary",
            width="stretch",
            key=f"rerun_financial_analysis_{annonce.id}",
        ):
            with st.spinner("Analyse Monte Carlo et solveur en cours..."):
                try:
                    result = rerun_financial_analysis(
                        conn,
                        annonce,
                        hypotheses,
                        targets=targets,
                        run_source="streamlit_manual",
                    )
                except Exception as exc:
                    st.error(f"Analyse impossible : {exc}")
                else:
                    st.success(f"Analyse sauvegardee. Run #{result.analysis_run_id}, statut {result.status}.")
                    st.rerun()
        if action_cols[1].button(
            "Relancer sourcing complet depuis l'URL",
            width="stretch",
            key=f"rerun_full_sourcing_{annonce.id}",
        ):
            if not annonce.url:
                st.error("Aucune URL n'est associee a cette annonce.")
            elif not os.environ.get("GEMINI_API_KEY"):
                st.error("GEMINI_API_KEY est requis dans l'environnement ou Streamlit secrets.")
            else:
                with st.spinner("Extraction IA, Monte Carlo et solveur en cours..."):
                    try:
                        orchestrator = SourcingOrchestrator(
                            target_tri=float(target_tri),
                            target_tri_p10=float(target_tri_p10),
                            target_coc=float(target_coc),
                            target_cf=float(target_cf),
                        )
                        annonce_id = orchestrator.process_url(conn, annonce.url)
                    except Exception as exc:
                        st.error(f"Sourcing impossible : {exc}")
                    else:
                        st.success(f"Sourcing complet sauvegarde. Annonce #{annonce_id}.")
                        st.rerun()

    # --- IA SOURCING ---
    with st.expander("Remplissage automatique par IA"):
        st.write("Collez l'URL de l'annonce ou son texte pour que Gemini et Playwright extraient toutes les données factuelles.")
        
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            st.warning("Clé GEMINI_API_KEY non trouvée dans l'environnement. Renseignez-la ci-dessous pour ce test.")
            api_key = st.text_input("Clé API Gemini", type="password")
            
        url_input = st.text_input("URL de l'annonce (Jinka, BienIci, LeBonCoin, etc.)")
        
        if st.button("Lancer l'extraction IA", type="primary"):
            if not api_key:
                st.error("Une clé API est requise.")
            elif not url_input:
                st.error("Veuillez saisir une URL.")
            else:
                with st.spinner("Initialisation de l'Agent IA..."):
                    try:
                        agent = LLMSourcingAgent(api_key=api_key)
                        
                        # Phase 1: Radar (si Jinka)
                        target_url = url_input
                        if "jinka.fr" in url_input.lower():
                            st.info("URL Jinka détectée : recherche du lien original en cours...")
                            html_radar = agent.fetch_url(url_input)
                            original_url = agent.extract_original_link(html_radar)
                            if original_url:
                                st.success(f"Lien original trouvé : {original_url}")
                                target_url = original_url
                            else:
                                st.warning("Impossible de trouver le lien source dans Jinka. On essaie quand même.")
                        
                        # Phase 2: Extraction profonde
                        st.info(f"Aspiration et analyse du site avec Playwright... ({target_url})")
                        html_content = agent.fetch_url(target_url)
                        prop = agent.extract_from_text(html_content, source_url=target_url)
                        
                        # Mise a jour des variables en memoire
                        # On ecrase uniquement si la valeur n'est pas None (pour respecter l'existant)
                        if prop.prix is not None:
                            annonce.prix_affiche = prop.prix
                        if prop.surface is not None:
                            annonce.surface_m2 = prop.surface
                        if prop.dpe is not None and prop.dpe.upper() != "INCONNU":
                            annonce.dpe = prop.dpe.upper()
                        if prop.ville is not None and prop.ville.upper() != "INCONNU":
                            annonce.ville = prop.ville.upper()
                        if prop.quartier is not None and prop.quartier.upper() != "INCONNU":
                            annonce.quartier = prop.quartier
                        annonce.url = target_url
                        
                        # Ajout des red flags dans les notes
                        notes_additionnelles = ""
                        if prop.red_flags:
                            notes_additionnelles += f"\\n\\n[IA Red Flags]: {', '.join(prop.red_flags)}"
                        if prop.donnees_manquantes:
                            notes_additionnelles += f"\\n\\n[IA Manque]: {', '.join(prop.donnees_manquantes)}"
                        if notes_additionnelles:
                            annonce.notes = (annonce.notes or "") + notes_additionnelles
                            
                        # Hypotheses financieres
                        if prop.loyer_estime is not None:
                            hypotheses.loyer_hc_mensuel = prop.loyer_estime
                        if prop.charges_mensuelles is not None:
                            hypotheses.charges_copro_annuelles = prop.charges_mensuelles * 12
                        if prop.taxe_fonciere is not None:
                            hypotheses.taxe_fonciere = prop.taxe_fonciere
                        if prop.travaux_visibles is not None and prop.travaux_visibles > 0:
                            hypotheses.travaux_estimes = prop.travaux_visibles

                        save_annonce(conn, annonce, hypotheses)
                        st.success("Extraction réussie et sauvegardée ! Rechargement...")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Erreur lors de l'extraction : {e}")

    # --- FIN IA SOURCING ---

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
            surface_m2 = st.number_input("Surface m2", min_value=0.0, value=float(annonce.surface_m2), step=1.0)
            prix_affiche = st.number_input(
                "Prix affiche",
                min_value=0.0,
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
                    tri_p50=annonce.tri_p50,
                    tri_p10=annonce.tri_p10,
                    probabilite_cashflow_positif=annonce.probabilite_cashflow_positif,
                    prix_cible_recommande=annonce.prix_cible_recommande,
                    cashflow_p50=annonce.cashflow_p50,
                    coc_p50=annonce.coc_p50,
                ),
                hypotheses,
            )
            st.success("Annonce sauvegardee.")
            st.rerun()
