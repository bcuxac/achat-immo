from achat_immo.city_profiles import (
    RentControlKind,
    loyer_max_hc_mensuel,
    loyer_reference_majore_m2,
    profile_for_city,
    rent_reference_records,
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


def test_categories_grenoble_conservent_les_dimensions_reglementaires() -> None:
    records = rent_reference_records("Grenoble", ModeLocation.MEUBLEE)

    assert len(records) == 48
    assert {record.rental_mode for record in records} == {ModeLocation.MEUBLEE}
    assert {record.room_count for record in records} == {1, 2, 3, 4}
    assert {record.sector for record in records} == {"zone_1", "zone_2", "zone_a"}
    assert all(record.source_url.endswith("Arrete-prefectoral-du-6-janvier-2026.pdf") for record in records)


def test_nimes_exige_le_loyer_precedent_sans_grille_locale() -> None:
    profile = profile_for_city("Nimes")

    assert profile is not None
    assert profile.rent_control_kind == RentControlKind.ZONE_TENDUE_RELOCATION
    assert rent_reference_records("Nimes", ModeLocation.MEUBLEE) == ()
    assert "loyer precedent" in profile.note.lower()
