"""Connexion SQL SQLite/PostgreSQL pour la persistance."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
import sqlite3
from typing import Any


DEFAULT_DB_PATH = Path("data/achat_immo.sqlite")
POSTGRES_URL_PREFIXES = ("postgresql://", "postgres://")


class DatabaseConnection:
    """Petite facade DB-API pour garder le code metier independant du backend."""

    def __init__(self, raw: Any, kind: str, dsn: str = "") -> None:
        self.raw = raw
        self.kind = kind
        self.dsn = dsn

    @property
    def is_postgres(self) -> bool:
        return self.kind == "postgres"

    def execute(self, sql: str, params: Iterable[Any] | Mapping[str, Any] = ()) -> Any:
        prepared_sql = self._sql(sql)
        try:
            return self.raw.execute(prepared_sql, params)
        except Exception as exc:
            if not self._should_reconnect(exc):
                raise
            self._reconnect()
            return self.raw.execute(prepared_sql, params)

    def executemany(self, sql: str, params: Iterable[Iterable[Any] | Mapping[str, Any]]) -> Any:
        prepared_sql = self._sql(sql)
        if self.is_postgres:
            try:
                with self.raw.cursor() as cursor:
                    return cursor.executemany(prepared_sql, params)
            except Exception as exc:
                if not self._should_reconnect(exc):
                    raise
                self._reconnect()
                with self.raw.cursor() as cursor:
                    return cursor.executemany(prepared_sql, params)
        return self.raw.executemany(prepared_sql, params)

    def executescript(self, script: str) -> Any:
        if not self.is_postgres:
            return self.raw.executescript(script)
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)
        return None

    def commit(self) -> None:
        if self.is_postgres and getattr(self.raw, "autocommit", False):
            return
        self.raw.commit()

    def rollback(self) -> None:
        if self.is_postgres and getattr(self.raw, "autocommit", False):
            return
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()

    def _sql(self, sql: str) -> str:
        if self.is_postgres:
            return sql.replace("?", "%s")
        return sql

    def _should_reconnect(self, exc: Exception) -> bool:
        if not self.is_postgres or not self.dsn:
            return False
        try:
            import psycopg
        except ImportError:  # pragma: no cover - psycopg est deja requis ici
            return False
        return isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))

    def _reconnect(self) -> None:
        try:
            self.raw.close()
        except Exception:
            pass
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - dependance absente seulement hors env projet
            raise RuntimeError(
                "La dependance psycopg est requise pour reconnecter PostgreSQL. "
                "Installe les dependances avec `uv sync`."
            ) from exc
        self.raw = psycopg.connect(self.dsn, row_factory=dict_row, autocommit=True, prepare_threshold=None)


def is_postgres_target(target: str | Path) -> bool:
    """Indique si une cible de base est une URL PostgreSQL."""

    return str(target).startswith(POSTGRES_URL_PREFIXES)


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

    conn = psycopg.connect(database_url, row_factory=dict_row, autocommit=True, prepare_threshold=None)
    return DatabaseConnection(conn, "postgres", dsn=database_url)
