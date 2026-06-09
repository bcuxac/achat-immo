from pathlib import Path

from achat_immo.grids import GrilleParametres, simuler_grille_annonce
from achat_immo.storage import (
    AnnonceRecord,
    HypothesesAchatRecord,
    get_annonce_bundle,
    get_simulation_results,
    list_annonces,
    list_simulation_runs,
    open_database,
    save_annonce,
    save_simulation_run,
    to_domain_models,
)
from achat_immo.models import EpoqueConstruction, ModeLocation


def test_sqlite_annonce_hypotheses_et_conversion(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(
            ville="Grenoble",
            quartier="Championnet",
            adresse="Rue test",
            surface_m2=42,
            prix_affiche=110_000,
            nb_pieces=2,
            epoque_construction=EpoqueConstruction.APRES_1990,
            secteur_encadrement="zone_1",
            dpe="D",
            url="https://example.test/annonce",
        ),
        HypothesesAchatRecord(
            frais_notaire_estimes=8_800,
            travaux_estimes=5_000,
            meubles_estimes=4_000,
            loyer_hc_mensuel=700,
            mode_location=ModeLocation.NUE,
            taxe_fonciere=900,
            charges_copro_annuelles=1_200,
            charges_recuperables_annuelles=500,
        ),
    )

    annonces = list_annonces(conn)
    annonce, hypotheses = get_annonce_bundle(conn, annonce_id)
    bien, location, financement = to_domain_models(annonce, hypotheses)

    assert annonces[0]["ville"] == "Grenoble"
    assert bien.adresse_approx == "Rue test"
    assert bien.nb_pieces == 2
    assert bien.epoque_construction == EpoqueConstruction.APRES_1990
    assert bien.secteur_encadrement == "zone_1"
    assert bien.cout_total_projet == 127_800
    assert location.loyer_hc_mensuel == 700
    assert location.mode_location == ModeLocation.NUE
    assert financement.apport == 15_000


def test_sqlite_sauvegarde_run_de_simulation(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    annonce_id = save_annonce(
        conn,
        AnnonceRecord(ville="Nimes", surface_m2=40, prix_affiche=90_000),
        HypothesesAchatRecord(loyer_hc_mensuel=620, taxe_fonciere=850),
    )
    annonce, hypotheses = get_annonce_bundle(conn, annonce_id)
    bien, location, _ = to_domain_models(annonce, hypotheses)
    resultats = simuler_grille_annonce(
        bien,
        location,
        parametres=GrilleParametres(
            taux_credit=(3.6,),
            durees_annees=(20,),
            apports=(15_000,),
            vacances_mois=(1.0,),
            gestions_agence=(False,),
            frais_gestion_pct=(7.0,),
            horizon_annees=5,
        ),
    )

    run_id = save_simulation_run(
        conn,
        annonce_id=annonce_id,
        resultats=[resultat.to_dict() for resultat in resultats],
        commentaire="scenario initial",
    )

    runs = list_simulation_runs(conn, annonce_id)
    rows = get_simulation_results(conn, run_id)

    assert runs[0]["nb_resultats"] == 1
    assert runs[0]["commentaire"] == "scenario initial"
    assert rows[0]["prix_achat"] == 90_000
    assert rows[0]["cout_total_projet"] == 90_000
    assert rows[0]["loyer_hc_mensuel"] == 620
    assert rows[0]["montant_emprunte"] > 0
    assert rows[0]["frais_gestion_pct"] == 0.0
    assert rows[0]["decision"] in {"interessant", "a_creuser", "a_rejeter"}
    assert "ecart_vs_alternative" not in rows[0]


def test_sqlite_stocke_plusieurs_annonces_distinctes(tmp_path: Path) -> None:
    conn = open_database(tmp_path / "achat.sqlite")
    first_id = save_annonce(
        conn,
        AnnonceRecord(ville="Grenoble", surface_m2=42, prix_affiche=110_000),
        HypothesesAchatRecord(loyer_hc_mensuel=700),
    )
    second_id = save_annonce(
        conn,
        AnnonceRecord(ville="Nimes", surface_m2=38, prix_affiche=90_000),
        HypothesesAchatRecord(loyer_hc_mensuel=620),
    )

    annonces = list_annonces(conn)

    assert {first_id, second_id} == {row["id"] for row in annonces}
    assert [row["ville"] for row in annonces] == ["Nimes", "Grenoble"]
