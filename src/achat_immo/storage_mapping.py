"""Conversions entre lignes persistantes et modeles metier."""

from __future__ import annotations

from achat_immo.models import (
    BienImmobilier,
    Financement,
    Fiscalite,
    HypothesesLocation,
)
from achat_immo.storage_records import AnnonceRecord, HypothesesAchatRecord


def to_domain_models(
    annonce: AnnonceRecord,
    hypotheses: HypothesesAchatRecord,
) -> tuple[BienImmobilier, HypothesesLocation, Financement]:
    bien = BienImmobilier(
        ville=annonce.ville,
        quartier=annonce.quartier,
        adresse_approx=annonce.adresse,
        lien=annonce.url,
        surface_m2=annonce.surface_m2,
        prix_affiche=annonce.prix_affiche,
        prix_negocie=annonce.prix_negocie,
        nb_pieces=annonce.nb_pieces,
        type_bien=annonce.type_bien,
        dpe=annonce.dpe or None,
        epoque_construction=annonce.epoque_construction,
        secteur_encadrement=annonce.secteur_encadrement,
        frais_agence_achat=hypotheses.frais_agence_achat,
        frais_notaire_estimes=hypotheses.frais_notaire_estimes,
        travaux_estimes=hypotheses.travaux_estimes,
        meubles_estimes=hypotheses.meubles_estimes,
        frais_bancaires=hypotheses.frais_bancaires,
        garantie=hypotheses.garantie,
    )
    location = HypothesesLocation(
        loyer_hc_mensuel=hypotheses.loyer_hc_mensuel,
        mode_location=hypotheses.mode_location,
        charges_copro_annuelles=hypotheses.charges_copro_annuelles,
        charges_recuperables_annuelles=hypotheses.charges_recuperables_annuelles,
        taxe_fonciere=hypotheses.taxe_fonciere,
        assurance_pno=hypotheses.assurance_pno,
        assurance_gli=hypotheses.assurance_gli,
        frais_gestion_pct=hypotheses.frais_gestion_pct,
        cfe_annuelle=hypotheses.cfe_annuelle,
        comptable_lmnp=hypotheses.comptable_lmnp,
        entretien_annuel=hypotheses.entretien_annuel,
    )
    financement = Financement(
        apport=hypotheses.apport_reference,
        taux_credit_annuel_pct=hypotheses.taux_credit_reference,
        duree_credit_annees=hypotheses.duree_credit_reference,
        assurance_emprunteur_annuelle_pct=hypotheses.assurance_emprunteur_pct,
    )
    return bien, location, financement


def fiscalite_from_hypotheses(hypotheses: HypothesesAchatRecord) -> Fiscalite:
    """Construit les hypotheses fiscales associees a une annonce."""

    return Fiscalite(
        regime=hypotheses.regime_fiscal,
        tmi_pct=hypotheses.tmi_pct,
        prelevements_sociaux_pct=hypotheses.prelevements_sociaux_pct,
        part_terrain_pct=hypotheses.part_terrain_pct,
        duree_amortissement_bien_annees=hypotheses.duree_amortissement_bien_annees,
        duree_amortissement_travaux_annees=hypotheses.duree_amortissement_travaux_annees,
        duree_amortissement_meubles_annees=hypotheses.duree_amortissement_meubles_annees,
        abattement_micro_bic_pct=hypotheses.abattement_micro_bic_pct,
        abattement_micro_foncier_pct=hypotheses.abattement_micro_foncier_pct,
    )
