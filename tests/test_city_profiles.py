from achat_immo.city_profiles import (
    loyer_max_hc_mensuel,
    loyer_reference_majore_m2,
)
from achat_immo.diagnostics import DiagnosticStatus, diagnostiquer_annonce
from achat_immo.grids import GrilleParametres, simuler_grille_annonce
from achat_immo.models import (
    BienImmobilier,
    EpoqueConstruction,
    HypothesesLocation,
    ModeLocation,
    TypeBien,
)


def _bien_grenoble_encadre() -> BienImmobilier:
    return BienImmobilier(
        ville="Grenoble",
        surface_m2=28,
        prix_affiche=89_000,
        type_bien=TypeBien.T1,
        nb_pieces=1,
        dpe="D",
        epoque_construction=EpoqueConstruction.AVANT_1946,
        secteur_encadrement="zone_2",
    )


def test_plafond_grenoble_depend_du_mode_de_location() -> None:
    bien = _bien_grenoble_encadre()

    meuble = HypothesesLocation(loyer_hc_mensuel=500, mode_location=ModeLocation.MEUBLEE)
    nue = HypothesesLocation(loyer_hc_mensuel=500, mode_location=ModeLocation.NUE)

    assert loyer_reference_majore_m2(bien, meuble) == 19.0
    assert loyer_max_hc_mensuel(bien, meuble) == 532.0
    assert loyer_reference_majore_m2(bien, nue) == 17.8
    assert loyer_max_hc_mensuel(bien, nue) == 498.4


def test_grille_filtre_les_loyers_superieurs_au_plafond_local() -> None:
    bien = _bien_grenoble_encadre()
    location = HypothesesLocation(loyer_hc_mensuel=500, mode_location=ModeLocation.MEUBLEE)

    resultats = simuler_grille_annonce(
        bien,
        location,
        parametres=GrilleParametres(
            loyers_hc_mensuels=(500, 525, 550),
            taux_credit=(3.6,),
            durees_annees=(20,),
            apports=(15_000,),
            vacances_mois=(1.0,),
            gestions_agence=(False,),
            frais_gestion_pct=(7.0,),
            horizon_annees=5,
        ),
    )

    assert {resultat.loyer_hc_mensuel for resultat in resultats} == {500, 525}
    assert all("loyer_superieur_plafond_local" not in resultat.alertes for resultat in resultats)


def test_diagnostic_bloque_un_loyer_superieur_au_plafond_local() -> None:
    diagnostics = diagnostiquer_annonce(
        _bien_grenoble_encadre(),
        HypothesesLocation(loyer_hc_mensuel=550, mode_location=ModeLocation.MEUBLEE),
    )

    blocking = [item for item in diagnostics if item.status == DiagnosticStatus.BLOCKING]

    assert {item.code for item in blocking} == {"loyer_superieur_plafond_local"}
