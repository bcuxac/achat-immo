"""Persistance SQL pour les annonces, hypotheses et decisions.

SQLite reste le backend local par defaut. PostgreSQL est supporte pour un
deploiement cloud avec stockage persistant.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Any

from achat_immo.models import (
    BienImmobilier,
    EpoqueConstruction,
    Financement,
    Fiscalite,
    HypothesesLocation,
    ModeLocation,
    RegimeFiscal,
    TypeBien,
)


DEFAULT_DB_PATH = Path("data/achat_immo.sqlite")
POSTGRES_URL_PREFIXES = ("postgresql://", "postgres://")


class DatabaseConnection:
    """Petite facade DB-API pour garder le code metier independant du backend."""

    def __init__(self, raw: Any, kind: str) -> None:
        self.raw = raw
        self.kind = kind

    @property
    def is_postgres(self) -> bool:
        return self.kind == "postgres"

    def execute(self, sql: str, params: Iterable[Any] | Mapping[str, Any] = ()) -> Any:
        return self.raw.execute(self._sql(sql), params)

    def executemany(self, sql: str, params: Iterable[Iterable[Any] | Mapping[str, Any]]) -> Any:
        if self.is_postgres:
            with self.raw.cursor() as cursor:
                return cursor.executemany(self._sql(sql), params)
        return self.raw.executemany(self._sql(sql), params)

    def executescript(self, script: str) -> Any:
        if not self.is_postgres:
            return self.raw.executescript(script)
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)
        return None

    def commit(self) -> None:
        self.raw.commit()

    def close(self) -> None:
        self.raw.close()

    def _sql(self, sql: str) -> str:
        if self.is_postgres:
            return sql.replace("?", "%s")
        return sql


def is_postgres_target(target: str | Path) -> bool:
    """Indique si une cible de base est une URL PostgreSQL."""

    return str(target).startswith(POSTGRES_URL_PREFIXES)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AnnonceRecord:
    """Annonce suivie dans l'application."""

    ville: str
    surface_m2: float
    prix_affiche: float
    id: int | None = None
    date_creation: str = ""
    url: str = ""
    quartier: str = ""
    adresse: str = ""
    type_bien: TypeBien = TypeBien.T2
    nb_pieces: int | None = None
    epoque_construction: EpoqueConstruction = EpoqueConstruction.INCONNUE
    secteur_encadrement: str = ""
    prix_negocie: float | None = None
    dpe: str = ""
    description: str = ""
    statut: str = "a_analyser"
    notes: str = ""


@dataclass(slots=True)
class HypothesesAchatRecord:
    """Hypotheses propres a l'annonce, hors grille automatique."""

    annonce_id: int | None = None
    frais_agence_achat: float = 0.0
    frais_notaire_estimes: float = 0.0
    travaux_estimes: float = 0.0
    meubles_estimes: float = 0.0
    frais_bancaires: float = 0.0
    garantie: float = 0.0
    loyer_hc_mensuel: float = 650.0
    mode_location: ModeLocation = ModeLocation.MEUBLEE
    charges_copro_annuelles: float = 0.0
    charges_recuperables_annuelles: float = 0.0
    taxe_fonciere: float = 0.0
    assurance_pno: float = 180.0
    assurance_gli: float = 0.0
    frais_gestion_pct: float = 7.0
    cfe_annuelle: float = 0.0
    comptable_lmnp: float = 500.0
    entretien_annuel: float = 500.0
    regime_fiscal: RegimeFiscal = RegimeFiscal.LMNP_REEL
    tmi_pct: float = 30.0
    prelevements_sociaux_pct: float = 18.6
    part_terrain_pct: float = 15.0
    duree_amortissement_bien_annees: int = 30
    duree_amortissement_travaux_annees: int = 15
    duree_amortissement_meubles_annees: int = 7
    abattement_micro_bic_pct: float = 50.0
    abattement_micro_foncier_pct: float = 30.0
    gestion_agence_possible: bool = True
    apport_reference: float = 15_000.0
    taux_credit_reference: float = 3.6
    duree_credit_reference: int = 20
    assurance_emprunteur_pct: float = 0.30


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> DatabaseConnection:
    """Ouvre une connexion SQL locale ou cloud selon la cible fournie."""

    if is_postgres_target(db_path):
        return _connect_postgres(str(db_path))

    return _connect_sqlite(db_path)


def _connect_sqlite(db_path: str | Path = DEFAULT_DB_PATH) -> DatabaseConnection:
    """Ouvre une connexion SQLite locale et cree le dossier si besoin."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return DatabaseConnection(conn, "sqlite")


def _connect_postgres(database_url: str) -> DatabaseConnection:
    """Ouvre une connexion PostgreSQL depuis une URL de connexion."""

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - dependance absente seulement hors env projet
        raise RuntimeError(
            "La dependance psycopg est requise pour utiliser PostgreSQL. "
            "Installe les dependances avec `uv sync`."
        ) from exc

    conn = psycopg.connect(database_url, row_factory=dict_row)
    return DatabaseConnection(conn, "postgres")


def init_db(conn: DatabaseConnection) -> None:
    """Cree le schema minimal de l'application."""

    if conn.is_postgres:
        conn.executescript(_POSTGRES_SCHEMA)
    else:
        conn.executescript(_SQLITE_SCHEMA)
    _migrate_annonces(conn)
    _migrate_hypotheses_achat(conn)
    _migrate_simulation_results(conn)
    conn.commit()


_SQLITE_SCHEMA = """
        CREATE TABLE IF NOT EXISTS annonces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_creation TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            ville TEXT NOT NULL,
            quartier TEXT NOT NULL DEFAULT '',
            adresse TEXT NOT NULL DEFAULT '',
            type_bien TEXT NOT NULL,
            nb_pieces INTEGER,
            epoque_construction TEXT NOT NULL DEFAULT 'inconnue',
            secteur_encadrement TEXT NOT NULL DEFAULT '',
            surface_m2 REAL NOT NULL,
            prix_affiche REAL NOT NULL,
            prix_negocie REAL,
            dpe TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            statut TEXT NOT NULL DEFAULT 'a_analyser',
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS hypotheses_achat (
            annonce_id INTEGER PRIMARY KEY,
            frais_agence_achat REAL NOT NULL DEFAULT 0,
            frais_notaire_estimes REAL NOT NULL DEFAULT 0,
            travaux_estimes REAL NOT NULL DEFAULT 0,
            meubles_estimes REAL NOT NULL DEFAULT 0,
            frais_bancaires REAL NOT NULL DEFAULT 0,
            garantie REAL NOT NULL DEFAULT 0,
            loyer_hc_mensuel REAL NOT NULL DEFAULT 650,
            mode_location TEXT NOT NULL DEFAULT 'meublee',
            charges_copro_annuelles REAL NOT NULL DEFAULT 0,
            charges_recuperables_annuelles REAL NOT NULL DEFAULT 0,
            taxe_fonciere REAL NOT NULL DEFAULT 0,
            assurance_pno REAL NOT NULL DEFAULT 180,
            assurance_gli REAL NOT NULL DEFAULT 0,
            frais_gestion_pct REAL NOT NULL DEFAULT 7,
            cfe_annuelle REAL NOT NULL DEFAULT 0,
            comptable_lmnp REAL NOT NULL DEFAULT 500,
            entretien_annuel REAL NOT NULL DEFAULT 500,
            regime_fiscal TEXT NOT NULL DEFAULT 'lmnp_reel',
            tmi_pct REAL NOT NULL DEFAULT 30,
            prelevements_sociaux_pct REAL NOT NULL DEFAULT 18.6,
            part_terrain_pct REAL NOT NULL DEFAULT 15,
            duree_amortissement_bien_annees INTEGER NOT NULL DEFAULT 30,
            duree_amortissement_travaux_annees INTEGER NOT NULL DEFAULT 15,
            duree_amortissement_meubles_annees INTEGER NOT NULL DEFAULT 7,
            abattement_micro_bic_pct REAL NOT NULL DEFAULT 50,
            abattement_micro_foncier_pct REAL NOT NULL DEFAULT 30,
            gestion_agence_possible INTEGER NOT NULL DEFAULT 1,
            apport_reference REAL NOT NULL DEFAULT 15000,
            taux_credit_reference REAL NOT NULL DEFAULT 3.6,
            duree_credit_reference INTEGER NOT NULL DEFAULT 20,
            assurance_emprunteur_pct REAL NOT NULL DEFAULT 0.30,
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS simulation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annonce_id INTEGER NOT NULL,
            date_run TEXT NOT NULL,
            commentaire TEXT NOT NULL DEFAULT '',
            nb_resultats INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS simulation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            annonce_id INTEGER NOT NULL,
            scenario TEXT NOT NULL,
            prix_achat REAL NOT NULL DEFAULT 0,
            cout_total_projet REAL NOT NULL DEFAULT 0,
            loyer_hc_mensuel REAL NOT NULL,
            taux_credit REAL NOT NULL,
            duree_annees INTEGER NOT NULL,
            apport REAL NOT NULL,
            vacance_mois REAL NOT NULL,
            gestion_agence INTEGER NOT NULL,
            frais_gestion_pct REAL NOT NULL DEFAULT 0,
            montant_emprunte REAL NOT NULL,
            mensualite_totale REAL NOT NULL,
            cashflow_mensuel_avant_impot REAL NOT NULL,
            cashflow_mensuel_apres_impot REAL NOT NULL,
            effort_epargne_mensuel REAL NOT NULL,
            rendement_net_avant_impot_pct REAL NOT NULL,
            rendement_net_net_pct REAL NOT NULL,
            patrimoine_net_horizon REAL NOT NULL,
            score INTEGER NOT NULL,
            decision TEXT NOT NULL,
            alertes TEXT NOT NULL DEFAULT '',
            diagnostics TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (run_id) REFERENCES simulation_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );
        """


_POSTGRES_SCHEMA = """
        CREATE TABLE IF NOT EXISTS annonces (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            date_creation TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            ville TEXT NOT NULL,
            quartier TEXT NOT NULL DEFAULT '',
            adresse TEXT NOT NULL DEFAULT '',
            type_bien TEXT NOT NULL,
            nb_pieces INTEGER,
            epoque_construction TEXT NOT NULL DEFAULT 'inconnue',
            secteur_encadrement TEXT NOT NULL DEFAULT '',
            surface_m2 DOUBLE PRECISION NOT NULL,
            prix_affiche DOUBLE PRECISION NOT NULL,
            prix_negocie DOUBLE PRECISION,
            dpe TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            statut TEXT NOT NULL DEFAULT 'a_analyser',
            notes TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS hypotheses_achat (
            annonce_id INTEGER PRIMARY KEY,
            frais_agence_achat DOUBLE PRECISION NOT NULL DEFAULT 0,
            frais_notaire_estimes DOUBLE PRECISION NOT NULL DEFAULT 0,
            travaux_estimes DOUBLE PRECISION NOT NULL DEFAULT 0,
            meubles_estimes DOUBLE PRECISION NOT NULL DEFAULT 0,
            frais_bancaires DOUBLE PRECISION NOT NULL DEFAULT 0,
            garantie DOUBLE PRECISION NOT NULL DEFAULT 0,
            loyer_hc_mensuel DOUBLE PRECISION NOT NULL DEFAULT 650,
            mode_location TEXT NOT NULL DEFAULT 'meublee',
            charges_copro_annuelles DOUBLE PRECISION NOT NULL DEFAULT 0,
            charges_recuperables_annuelles DOUBLE PRECISION NOT NULL DEFAULT 0,
            taxe_fonciere DOUBLE PRECISION NOT NULL DEFAULT 0,
            assurance_pno DOUBLE PRECISION NOT NULL DEFAULT 180,
            assurance_gli DOUBLE PRECISION NOT NULL DEFAULT 0,
            frais_gestion_pct DOUBLE PRECISION NOT NULL DEFAULT 7,
            cfe_annuelle DOUBLE PRECISION NOT NULL DEFAULT 0,
            comptable_lmnp DOUBLE PRECISION NOT NULL DEFAULT 500,
            entretien_annuel DOUBLE PRECISION NOT NULL DEFAULT 500,
            regime_fiscal TEXT NOT NULL DEFAULT 'lmnp_reel',
            tmi_pct DOUBLE PRECISION NOT NULL DEFAULT 30,
            prelevements_sociaux_pct DOUBLE PRECISION NOT NULL DEFAULT 18.6,
            part_terrain_pct DOUBLE PRECISION NOT NULL DEFAULT 15,
            duree_amortissement_bien_annees INTEGER NOT NULL DEFAULT 30,
            duree_amortissement_travaux_annees INTEGER NOT NULL DEFAULT 15,
            duree_amortissement_meubles_annees INTEGER NOT NULL DEFAULT 7,
            abattement_micro_bic_pct DOUBLE PRECISION NOT NULL DEFAULT 50,
            abattement_micro_foncier_pct DOUBLE PRECISION NOT NULL DEFAULT 30,
            gestion_agence_possible INTEGER NOT NULL DEFAULT 1,
            apport_reference DOUBLE PRECISION NOT NULL DEFAULT 15000,
            taux_credit_reference DOUBLE PRECISION NOT NULL DEFAULT 3.6,
            duree_credit_reference INTEGER NOT NULL DEFAULT 20,
            assurance_emprunteur_pct DOUBLE PRECISION NOT NULL DEFAULT 0.30,
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS simulation_runs (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            annonce_id INTEGER NOT NULL,
            date_run TEXT NOT NULL,
            commentaire TEXT NOT NULL DEFAULT '',
            nb_resultats INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS simulation_results (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            run_id INTEGER NOT NULL,
            annonce_id INTEGER NOT NULL,
            scenario TEXT NOT NULL,
            prix_achat DOUBLE PRECISION NOT NULL DEFAULT 0,
            cout_total_projet DOUBLE PRECISION NOT NULL DEFAULT 0,
            loyer_hc_mensuel DOUBLE PRECISION NOT NULL,
            taux_credit DOUBLE PRECISION NOT NULL,
            duree_annees INTEGER NOT NULL,
            apport DOUBLE PRECISION NOT NULL,
            vacance_mois DOUBLE PRECISION NOT NULL,
            gestion_agence INTEGER NOT NULL,
            frais_gestion_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
            montant_emprunte DOUBLE PRECISION NOT NULL,
            mensualite_totale DOUBLE PRECISION NOT NULL,
            cashflow_mensuel_avant_impot DOUBLE PRECISION NOT NULL,
            cashflow_mensuel_apres_impot DOUBLE PRECISION NOT NULL,
            effort_epargne_mensuel DOUBLE PRECISION NOT NULL,
            rendement_net_avant_impot_pct DOUBLE PRECISION NOT NULL,
            rendement_net_net_pct DOUBLE PRECISION NOT NULL,
            patrimoine_net_horizon DOUBLE PRECISION NOT NULL,
            score INTEGER NOT NULL,
            decision TEXT NOT NULL,
            alertes TEXT NOT NULL DEFAULT '',
            diagnostics TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (run_id) REFERENCES simulation_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );
        """


def _table_columns(conn: DatabaseConnection, table: str) -> set[str]:
    if conn.is_postgres:
        rows = conn.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = ?
            """,
            (table,),
        ).fetchall()
        return {str(row["name"]) for row in rows}

    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _migrate_annonces(conn: DatabaseConnection) -> None:
    """Ajoute les colonnes locales aux bases deja creees."""

    columns = _table_columns(conn, "annonces")
    migrations = {
        "nb_pieces": "ALTER TABLE annonces ADD COLUMN nb_pieces INTEGER",
        "epoque_construction": "ALTER TABLE annonces ADD COLUMN epoque_construction TEXT NOT NULL DEFAULT 'inconnue'",
        "secteur_encadrement": "ALTER TABLE annonces ADD COLUMN secteur_encadrement TEXT NOT NULL DEFAULT ''",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)


def _migrate_hypotheses_achat(conn: DatabaseConnection) -> None:
    """Ajoute les hypotheses de location aux bases deja creees."""

    columns = _table_columns(conn, "hypotheses_achat")
    migrations = {
        "mode_location": "ALTER TABLE hypotheses_achat ADD COLUMN mode_location TEXT NOT NULL DEFAULT 'meublee'",
        "cfe_annuelle": "ALTER TABLE hypotheses_achat ADD COLUMN cfe_annuelle REAL NOT NULL DEFAULT 0",
        "regime_fiscal": "ALTER TABLE hypotheses_achat ADD COLUMN regime_fiscal TEXT NOT NULL DEFAULT 'lmnp_reel'",
        "tmi_pct": "ALTER TABLE hypotheses_achat ADD COLUMN tmi_pct REAL NOT NULL DEFAULT 30",
        "prelevements_sociaux_pct": "ALTER TABLE hypotheses_achat ADD COLUMN prelevements_sociaux_pct REAL NOT NULL DEFAULT 18.6",
        "part_terrain_pct": "ALTER TABLE hypotheses_achat ADD COLUMN part_terrain_pct REAL NOT NULL DEFAULT 15",
        "duree_amortissement_bien_annees": "ALTER TABLE hypotheses_achat ADD COLUMN duree_amortissement_bien_annees INTEGER NOT NULL DEFAULT 30",
        "duree_amortissement_travaux_annees": "ALTER TABLE hypotheses_achat ADD COLUMN duree_amortissement_travaux_annees INTEGER NOT NULL DEFAULT 15",
        "duree_amortissement_meubles_annees": "ALTER TABLE hypotheses_achat ADD COLUMN duree_amortissement_meubles_annees INTEGER NOT NULL DEFAULT 7",
        "abattement_micro_bic_pct": "ALTER TABLE hypotheses_achat ADD COLUMN abattement_micro_bic_pct REAL NOT NULL DEFAULT 50",
        "abattement_micro_foncier_pct": "ALTER TABLE hypotheses_achat ADD COLUMN abattement_micro_foncier_pct REAL NOT NULL DEFAULT 30",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)


def _migrate_simulation_results(conn: DatabaseConnection) -> None:
    """Ajoute les colonnes recentes aux bases locales deja creees."""

    columns = _table_columns(conn, "simulation_results")
    migrations = {
        "loyer_hc_mensuel": "ALTER TABLE simulation_results ADD COLUMN loyer_hc_mensuel REAL NOT NULL DEFAULT 0",
        "montant_emprunte": "ALTER TABLE simulation_results ADD COLUMN montant_emprunte REAL NOT NULL DEFAULT 0",
        "diagnostics": "ALTER TABLE simulation_results ADD COLUMN diagnostics TEXT NOT NULL DEFAULT ''",
        "prix_achat": "ALTER TABLE simulation_results ADD COLUMN prix_achat REAL NOT NULL DEFAULT 0",
        "cout_total_projet": "ALTER TABLE simulation_results ADD COLUMN cout_total_projet REAL NOT NULL DEFAULT 0",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)


def open_database(db_path: str | Path | None = DEFAULT_DB_PATH) -> DatabaseConnection:
    target = db_path
    if target is None:
        target = os.environ.get("DATABASE_URL") or DEFAULT_DB_PATH
    conn = connect(target)
    init_db(conn)
    return conn


def _type_bien(value: str) -> TypeBien:
    try:
        return TypeBien(value)
    except ValueError:
        return TypeBien.AUTRE


def _epoque_construction(value: str) -> EpoqueConstruction:
    try:
        return EpoqueConstruction(value)
    except ValueError:
        return EpoqueConstruction.INCONNUE


def _mode_location(value: str) -> ModeLocation:
    try:
        return ModeLocation(value)
    except ValueError:
        return ModeLocation.MEUBLEE


def _regime_fiscal(value: str) -> RegimeFiscal:
    try:
        return RegimeFiscal(value)
    except ValueError:
        return RegimeFiscal.LMNP_REEL


def _annonce_from_row(row: Mapping[str, Any]) -> AnnonceRecord:
    return AnnonceRecord(
        id=int(row["id"]),
        date_creation=str(row["date_creation"]),
        url=str(row["url"]),
        ville=str(row["ville"]),
        quartier=str(row["quartier"]),
        adresse=str(row["adresse"]),
        type_bien=_type_bien(str(row["type_bien"])),
        nb_pieces=int(row["nb_pieces"]) if row["nb_pieces"] is not None else None,
        epoque_construction=_epoque_construction(str(row["epoque_construction"])),
        secteur_encadrement=str(row["secteur_encadrement"]),
        surface_m2=float(row["surface_m2"]),
        prix_affiche=float(row["prix_affiche"]),
        prix_negocie=float(row["prix_negocie"]) if row["prix_negocie"] is not None else None,
        dpe=str(row["dpe"]),
        description=str(row["description"]),
        statut=str(row["statut"]),
        notes=str(row["notes"]),
    )


def _hypotheses_from_row(row: Mapping[str, Any]) -> HypothesesAchatRecord:
    return HypothesesAchatRecord(
        annonce_id=int(row["annonce_id"]),
        frais_agence_achat=float(row["frais_agence_achat"]),
        frais_notaire_estimes=float(row["frais_notaire_estimes"]),
        travaux_estimes=float(row["travaux_estimes"]),
        meubles_estimes=float(row["meubles_estimes"]),
        frais_bancaires=float(row["frais_bancaires"]),
        garantie=float(row["garantie"]),
        loyer_hc_mensuel=float(row["loyer_hc_mensuel"]),
        mode_location=_mode_location(str(row["mode_location"])),
        charges_copro_annuelles=float(row["charges_copro_annuelles"]),
        charges_recuperables_annuelles=float(row["charges_recuperables_annuelles"]),
        taxe_fonciere=float(row["taxe_fonciere"]),
        assurance_pno=float(row["assurance_pno"]),
        assurance_gli=float(row["assurance_gli"]),
        frais_gestion_pct=float(row["frais_gestion_pct"]),
        cfe_annuelle=float(row["cfe_annuelle"]),
        comptable_lmnp=float(row["comptable_lmnp"]),
        entretien_annuel=float(row["entretien_annuel"]),
        regime_fiscal=_regime_fiscal(str(row["regime_fiscal"])),
        tmi_pct=float(row["tmi_pct"]),
        prelevements_sociaux_pct=float(row["prelevements_sociaux_pct"]),
        part_terrain_pct=float(row["part_terrain_pct"]),
        duree_amortissement_bien_annees=int(row["duree_amortissement_bien_annees"]),
        duree_amortissement_travaux_annees=int(row["duree_amortissement_travaux_annees"]),
        duree_amortissement_meubles_annees=int(row["duree_amortissement_meubles_annees"]),
        abattement_micro_bic_pct=float(row["abattement_micro_bic_pct"]),
        abattement_micro_foncier_pct=float(row["abattement_micro_foncier_pct"]),
        gestion_agence_possible=bool(row["gestion_agence_possible"]),
        apport_reference=float(row["apport_reference"]),
        taux_credit_reference=float(row["taux_credit_reference"]),
        duree_credit_reference=int(row["duree_credit_reference"]),
        assurance_emprunteur_pct=float(row["assurance_emprunteur_pct"]),
    )


def save_annonce(
    conn: DatabaseConnection,
    annonce: AnnonceRecord,
    hypotheses: HypothesesAchatRecord,
) -> int:
    """Cree ou met a jour une annonce et ses hypotheses."""

    if annonce.id is None:
        insert_sql = """
            INSERT INTO annonces (
                date_creation, url, ville, quartier, adresse, type_bien, nb_pieces,
                epoque_construction, secteur_encadrement, surface_m2,
                prix_affiche, prix_negocie, dpe, description, statut, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        if conn.is_postgres:
            insert_sql += " RETURNING id"
        cursor = conn.execute(
            insert_sql,
            (
                annonce.date_creation or _now_iso(),
                annonce.url,
                annonce.ville,
                annonce.quartier,
                annonce.adresse,
                annonce.type_bien.value,
                annonce.nb_pieces,
                annonce.epoque_construction.value,
                annonce.secteur_encadrement,
                annonce.surface_m2,
                annonce.prix_affiche,
                annonce.prix_negocie,
                annonce.dpe,
                annonce.description,
                annonce.statut,
                annonce.notes,
            ),
        )
        if conn.is_postgres:
            row = cursor.fetchone()
            annonce_id = int(row["id"])
        else:
            annonce_id = int(cursor.lastrowid)
    else:
        annonce_id = annonce.id
        conn.execute(
            """
            UPDATE annonces
            SET url = ?, ville = ?, quartier = ?, adresse = ?, type_bien = ?,
                nb_pieces = ?, epoque_construction = ?, secteur_encadrement = ?, surface_m2 = ?,
                prix_affiche = ?, prix_negocie = ?, dpe = ?, description = ?,
                statut = ?, notes = ?
            WHERE id = ?
            """,
            (
                annonce.url,
                annonce.ville,
                annonce.quartier,
                annonce.adresse,
                annonce.type_bien.value,
                annonce.nb_pieces,
                annonce.epoque_construction.value,
                annonce.secteur_encadrement,
                annonce.surface_m2,
                annonce.prix_affiche,
                annonce.prix_negocie,
                annonce.dpe,
                annonce.description,
                annonce.statut,
                annonce.notes,
                annonce_id,
            ),
        )

    conn.execute(
        """
        INSERT INTO hypotheses_achat (
            annonce_id, frais_agence_achat, frais_notaire_estimes, travaux_estimes,
            meubles_estimes, frais_bancaires, garantie, loyer_hc_mensuel,
            mode_location, charges_copro_annuelles, charges_recuperables_annuelles, taxe_fonciere,
            assurance_pno, assurance_gli, frais_gestion_pct, cfe_annuelle, comptable_lmnp,
            entretien_annuel, regime_fiscal, tmi_pct, prelevements_sociaux_pct,
            part_terrain_pct, duree_amortissement_bien_annees,
            duree_amortissement_travaux_annees, duree_amortissement_meubles_annees,
            abattement_micro_bic_pct, abattement_micro_foncier_pct,
            gestion_agence_possible, apport_reference,
            taux_credit_reference, duree_credit_reference, assurance_emprunteur_pct
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(annonce_id) DO UPDATE SET
            frais_agence_achat = excluded.frais_agence_achat,
            frais_notaire_estimes = excluded.frais_notaire_estimes,
            travaux_estimes = excluded.travaux_estimes,
            meubles_estimes = excluded.meubles_estimes,
            frais_bancaires = excluded.frais_bancaires,
            garantie = excluded.garantie,
            loyer_hc_mensuel = excluded.loyer_hc_mensuel,
            mode_location = excluded.mode_location,
            charges_copro_annuelles = excluded.charges_copro_annuelles,
            charges_recuperables_annuelles = excluded.charges_recuperables_annuelles,
            taxe_fonciere = excluded.taxe_fonciere,
            assurance_pno = excluded.assurance_pno,
            assurance_gli = excluded.assurance_gli,
            frais_gestion_pct = excluded.frais_gestion_pct,
            cfe_annuelle = excluded.cfe_annuelle,
            comptable_lmnp = excluded.comptable_lmnp,
            entretien_annuel = excluded.entretien_annuel,
            regime_fiscal = excluded.regime_fiscal,
            tmi_pct = excluded.tmi_pct,
            prelevements_sociaux_pct = excluded.prelevements_sociaux_pct,
            part_terrain_pct = excluded.part_terrain_pct,
            duree_amortissement_bien_annees = excluded.duree_amortissement_bien_annees,
            duree_amortissement_travaux_annees = excluded.duree_amortissement_travaux_annees,
            duree_amortissement_meubles_annees = excluded.duree_amortissement_meubles_annees,
            abattement_micro_bic_pct = excluded.abattement_micro_bic_pct,
            abattement_micro_foncier_pct = excluded.abattement_micro_foncier_pct,
            gestion_agence_possible = excluded.gestion_agence_possible,
            apport_reference = excluded.apport_reference,
            taux_credit_reference = excluded.taux_credit_reference,
            duree_credit_reference = excluded.duree_credit_reference,
            assurance_emprunteur_pct = excluded.assurance_emprunteur_pct
        """,
        (
            annonce_id,
            hypotheses.frais_agence_achat,
            hypotheses.frais_notaire_estimes,
            hypotheses.travaux_estimes,
            hypotheses.meubles_estimes,
            hypotheses.frais_bancaires,
            hypotheses.garantie,
            hypotheses.loyer_hc_mensuel,
            hypotheses.mode_location.value,
            hypotheses.charges_copro_annuelles,
            hypotheses.charges_recuperables_annuelles,
            hypotheses.taxe_fonciere,
            hypotheses.assurance_pno,
            hypotheses.assurance_gli,
            hypotheses.frais_gestion_pct,
            hypotheses.cfe_annuelle,
            hypotheses.comptable_lmnp,
            hypotheses.entretien_annuel,
            hypotheses.regime_fiscal.value,
            hypotheses.tmi_pct,
            hypotheses.prelevements_sociaux_pct,
            hypotheses.part_terrain_pct,
            hypotheses.duree_amortissement_bien_annees,
            hypotheses.duree_amortissement_travaux_annees,
            hypotheses.duree_amortissement_meubles_annees,
            hypotheses.abattement_micro_bic_pct,
            hypotheses.abattement_micro_foncier_pct,
            int(hypotheses.gestion_agence_possible),
            hypotheses.apport_reference,
            hypotheses.taux_credit_reference,
            hypotheses.duree_credit_reference,
            hypotheses.assurance_emprunteur_pct,
        ),
    )
    conn.commit()
    return annonce_id


def list_annonces(conn: DatabaseConnection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT a.*, h.loyer_hc_mensuel, h.taxe_fonciere, h.gestion_agence_possible
        FROM annonces a
        LEFT JOIN hypotheses_achat h ON h.annonce_id = a.id
        ORDER BY a.id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def update_decision(
    conn: DatabaseConnection,
    annonce_id: int,
    statut: str,
    notes: str,
) -> None:
    """Met a jour la decision humaine associee a une annonce."""

    conn.execute(
        """
        UPDATE annonces
        SET statut = ?, notes = ?
        WHERE id = ?
        """,
        (statut, notes, annonce_id),
    )
    conn.commit()


def get_annonce_bundle(
    conn: DatabaseConnection,
    annonce_id: int,
) -> tuple[AnnonceRecord, HypothesesAchatRecord]:
    annonce_row = conn.execute("SELECT * FROM annonces WHERE id = ?", (annonce_id,)).fetchone()
    if annonce_row is None:
        raise KeyError(f"Annonce introuvable : {annonce_id}")
    hypotheses_row = conn.execute(
        "SELECT * FROM hypotheses_achat WHERE annonce_id = ?",
        (annonce_id,),
    ).fetchone()
    if hypotheses_row is None:
        raise KeyError(f"Hypotheses introuvables pour l'annonce : {annonce_id}")
    return _annonce_from_row(annonce_row), _hypotheses_from_row(hypotheses_row)


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


def save_simulation_run(
    conn: DatabaseConnection,
    annonce_id: int,
    resultats: Iterable[Mapping[str, Any]],
    commentaire: str = "",
) -> int:
    rows = [dict(resultat) for resultat in resultats]
    insert_sql = """
        INSERT INTO simulation_runs (annonce_id, date_run, commentaire, nb_resultats)
        VALUES (?, ?, ?, ?)
        """
    if conn.is_postgres:
        insert_sql += " RETURNING id"
    cursor = conn.execute(
        insert_sql,
        (annonce_id, _now_iso(), commentaire, len(rows)),
    )
    if conn.is_postgres:
        row = cursor.fetchone()
        run_id = int(row["id"])
    else:
        run_id = int(cursor.lastrowid)
    conn.executemany(
        """
        INSERT INTO simulation_results (
            run_id, annonce_id, scenario, prix_achat, cout_total_projet,
            loyer_hc_mensuel, taux_credit, duree_annees, apport,
            vacance_mois, gestion_agence, frais_gestion_pct, mensualite_totale,
            montant_emprunte, cashflow_mensuel_avant_impot, cashflow_mensuel_apres_impot,
            effort_epargne_mensuel, rendement_net_avant_impot_pct,
            rendement_net_net_pct, patrimoine_net_horizon,
            score, decision, alertes, diagnostics
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                annonce_id,
                row.get("scenario", ""),
                row.get("prix_achat", 0.0),
                row.get("cout_total_projet", 0.0),
                row["loyer_hc_mensuel"],
                row["taux_credit"],
                row["duree_annees"],
                row["apport"],
                row["vacance_mois"],
                int(bool(row["gestion_agence"])),
                row.get("frais_gestion_pct", 0.0),
                row["mensualite_totale"],
                row["montant_emprunte"],
                row["cashflow_mensuel_avant_impot"],
                row["cashflow_mensuel_apres_impot"],
                row["effort_epargne_mensuel"],
                row["rendement_net_avant_impot_pct"],
                row["rendement_net_net_pct"],
                row["patrimoine_net_horizon"],
                row["score"],
                row["decision"],
                row.get("alertes", ""),
                row.get("diagnostics", ""),
            )
            for row in rows
        ],
    )
    conn.commit()
    return run_id


def list_simulation_runs(conn: DatabaseConnection, annonce_id: int | None = None) -> list[dict[str, Any]]:
    if annonce_id is None:
        rows = conn.execute(
            """
            SELECT r.*, a.ville, a.quartier
            FROM simulation_runs r
            JOIN annonces a ON a.id = r.annonce_id
            ORDER BY r.id DESC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT r.*, a.ville, a.quartier
            FROM simulation_runs r
            JOIN annonces a ON a.id = r.annonce_id
            WHERE r.annonce_id = ?
            ORDER BY r.id DESC
            """,
            (annonce_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_simulation_results(conn: DatabaseConnection, run_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM simulation_results
        WHERE run_id = ?
        ORDER BY score DESC, cashflow_mensuel_apres_impot DESC
        """,
        (run_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def reset_identity_sequences(conn: DatabaseConnection) -> None:
    """Aligne les sequences PostgreSQL apres une importation avec ids explicites."""

    if not conn.is_postgres:
        return

    for table in ("annonces", "simulation_runs", "simulation_results"):
        row = conn.execute(f"SELECT COALESCE(MAX(id), 0) AS max_id FROM {table}").fetchone()
        max_id = int(row["max_id"])
        if max_id > 0:
            conn.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), ?, true)",
                (max_id,),
            )
    conn.commit()
