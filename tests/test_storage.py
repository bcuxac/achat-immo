from pathlib import Path

import psycopg

from achat_immo.grids import GrilleParametres, simuler_grille_annonce
from achat_immo.storage import (
    AnnonceRecord,
    connect,
    DatabaseConnection,
    HypothesesAchatRecord,
    fiscalite_from_hypotheses,
    get_annonce_bundle,
    is_postgres_target,
    get_simulation_results,
    list_annonces,
    list_simulation_runs,
    open_database,
    save_annonce,
    save_simulation_run,
    to_domain_models,
)
from achat_immo.models import EpoqueConstruction, ModeLocation, RegimeFiscal


def test_detecte_les_urls_postgresql() -> None:
    assert is_postgres_target("postgresql://user:password@example.test/db")
    assert is_postgres_target("postgres://user:password@example.test/db")
    assert not is_postgres_target(Path("data/achat.sqlite"))


def test_facade_postgresql_convertit_les_placeholders_executemany() -> None:
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def executemany(self, sql, params):
            calls.append((sql, list(params)))

    class FakeRaw:
        def cursor(self):
            return FakeCursor()

    conn = DatabaseConnection(FakeRaw(), "postgres")

    conn.executemany("INSERT INTO table_test (a, b) VALUES (?, ?)", [(1, 2)])

    assert calls == [("INSERT INTO table_test (a, b) VALUES (%s, %s)", [(1, 2)])]


def test_facade_postgresql_reconnecte_apres_erreur_operationnelle() -> None:
    calls = []

    class DeadRaw:
        def execute(self, sql, params):
            calls.append(("dead", sql, params))
            raise psycopg.OperationalError("connexion fermee")

        def close(self):
            calls.append(("closed",))

    class HealthyRaw:
        def execute(self, sql, params):
            calls.append(("healthy", sql, params))
            return "ok"

    conn = DatabaseConnection(DeadRaw(), "postgres", dsn="postgresql://example")

    def reconnect():
        conn.raw = HealthyRaw()

    conn._reconnect = reconnect

    result = conn.execute("SELECT * FROM annonces WHERE id = ?", (1,))

    assert result == "ok"
    assert calls == [
        ("dead", "SELECT * FROM annonces WHERE id = %s", (1,)),
        ("healthy", "SELECT * FROM annonces WHERE id = %s", (1,)),
    ]


def test_connexion_postgresql_desactive_les_prepared_statements(monkeypatch) -> None:
    calls = []

    class FakeRaw:
        def close(self):
            calls.append(("closed",))

    def fake_connect(dsn, **kwargs):
        calls.append(("connect", dsn, kwargs))
        return FakeRaw()

    monkeypatch.setattr(psycopg, "connect", fake_connect)

    conn = connect("postgresql://example.test/db")
    conn._reconnect()

    connect_calls = [call for call in calls if call[0] == "connect"]
    assert len(connect_calls) == 2
    for _, dsn, kwargs in connect_calls:
        assert dsn == "postgresql://example.test/db"
        assert kwargs["autocommit"] is True
        assert kwargs["prepare_threshold"] is None
        assert kwargs["row_factory"] is not None


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
            cfe_annuelle=320,
            regime_fiscal=RegimeFiscal.LOCATION_NUE_REEL,
            tmi_pct=41,
            prelevements_sociaux_pct=17.2,
            part_terrain_pct=12,
            duree_amortissement_bien_annees=35,
            taxe_fonciere=900,
            charges_copro_annuelles=1_200,
            charges_recuperables_annuelles=500,
        ),
    )

    annonces = list_annonces(conn)
    annonce, hypotheses = get_annonce_bundle(conn, annonce_id)
    bien, location, financement = to_domain_models(annonce, hypotheses)
    fiscalite = fiscalite_from_hypotheses(hypotheses)

    assert annonces[0]["ville"] == "Grenoble"
    assert bien.adresse_approx == "Rue test"
    assert bien.nb_pieces == 2
    assert bien.epoque_construction == EpoqueConstruction.APRES_1990
    assert bien.secteur_encadrement == "zone_1"
    assert bien.cout_total_projet == 127_800
    assert location.loyer_hc_mensuel == 700
    assert location.mode_location == ModeLocation.NUE
    assert location.cfe_annuelle == 320
    assert financement.apport == 15_000
    assert fiscalite.regime == RegimeFiscal.LOCATION_NUE_REEL
    assert fiscalite.tmi_pct == 41
    assert fiscalite.part_terrain_pct == 12
    assert fiscalite.duree_amortissement_bien_annees == 35


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

    assert runs[0]["nb_resultats"] == 2
    assert runs[0]["commentaire"] == "scenario initial"
    assert rows[0]["prix_achat"] == 90_000
    assert rows[0]["cout_total_projet"] == 90_000
    assert rows[0]["loyer_hc_mensuel"] == 620
    assert rows[0]["montant_emprunte"] > 0
    assert rows[0]["frais_gestion_pct"] == 0.0
    assert rows[0]["mode_location"] == "meublee"
    assert rows[0]["regime_fiscal"] in {"lmnp_reel", "micro_bic"}
    assert "patrimoine_net_sortie" in rows[0]
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
