from achat_immo.hypothesis_inference import (
    appliquer_suggestions,
    inferer_hypotheses_depuis_annonce,
    prelevements_sociaux_par_regime,
    regimes_compatibles,
)
from achat_immo.models import EpoqueConstruction, ModeLocation, RegimeFiscal, TypeBien
from achat_immo.storage import AnnonceRecord, HypothesesAchatRecord


def test_inference_grenoble_borne_loyer_et_fiscalite_meublee() -> None:
    annonce = AnnonceRecord(
        ville="Grenoble",
        quartier="Championnet",
        surface_m2=30,
        prix_affiche=100_000,
        type_bien=TypeBien.T2,
        nb_pieces=2,
        epoque_construction=EpoqueConstruction.APRES_1990,
        secteur_encadrement="zone_1",
        dpe="D",
        description="Appartement meuble en bon etat. Taxe fonciere 720 EUR. Charges copro 75 EUR par mois.",
    )
    hypotheses = HypothesesAchatRecord(loyer_hc_mensuel=650)

    suggestions = inferer_hypotheses_depuis_annonce(annonce, hypotheses)

    assert suggestions["mode_location"].value == ModeLocation.MEUBLEE
    assert suggestions["loyer_hc_mensuel"].value == 520
    assert suggestions["prelevements_sociaux_pct"].value == 18.6
    assert suggestions["cfe_annuelle"].value == 300
    assert suggestions["taxe_fonciere"].value == 700
    assert suggestions["charges_copro_annuelles"].value == 900


def test_application_suggestions_peut_preserver_les_champs_deja_renseignes() -> None:
    annonce = AnnonceRecord(ville="Nimes", surface_m2=40, prix_affiche=90_000)
    hypotheses = HypothesesAchatRecord(
        loyer_hc_mensuel=620,
        frais_notaire_estimes=7_000,
        taxe_fonciere=0,
    )

    suggestions = inferer_hypotheses_depuis_annonce(annonce, hypotheses)
    updated = appliquer_suggestions(hypotheses, suggestions, only_empty=True)

    assert updated.frais_notaire_estimes == 7_000
    assert updated.loyer_hc_mensuel == 620
    assert updated.taxe_fonciere > 0


def test_regimes_et_prelevements_sociaux_dependant_du_mode() -> None:
    assert regimes_compatibles(ModeLocation.MEUBLEE) == (
        RegimeFiscal.LMNP_REEL,
        RegimeFiscal.MICRO_BIC,
    )
    assert regimes_compatibles(ModeLocation.NUE) == (
        RegimeFiscal.LOCATION_NUE_REEL,
        RegimeFiscal.MICRO_FONCIER,
    )
    assert prelevements_sociaux_par_regime(RegimeFiscal.LMNP_REEL) == 18.6
    assert prelevements_sociaux_par_regime(RegimeFiscal.MICRO_BIC) == 18.6
    assert prelevements_sociaux_par_regime(RegimeFiscal.LOCATION_NUE_REEL) == 17.2
