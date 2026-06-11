"""Page de saisie des donnees factuelles d'une annonce."""

from __future__ import annotations

import streamlit as st

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
from app.ui_helpers import enum_label as _enum_label


def annonce_page(
    conn: DatabaseConnection,
    annonce: AnnonceRecord | None,
    hypotheses: HypothesesAchatRecord | None,
) -> None:
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
