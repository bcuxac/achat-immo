"""Migre la base SQLite locale vers une base PostgreSQL vide ou existante."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from achat_immo.storage import (
    DEFAULT_DB_PATH,
    DatabaseConnection,
    is_postgres_target,
    open_database,
    reset_identity_sequences,
)


TABLES = (
    "annonces",
    "hypotheses_achat",
    "simulation_runs",
    "simulation_results",
    "extraction_runs",
    "analysis_runs",
    "sourcing_queue",
    "sourcing_runs",
    "jinka_alerts",
    "investment_profile_versions",
    "viability_maps",
    "viability_points",
    "qualification_runs",
)


def _fetch_rows(conn: DatabaseConnection, table: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
    return [dict(row) for row in rows]


def _delete_existing_rows(conn: DatabaseConnection) -> None:
    for table in reversed(TABLES):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()


def _insert_rows(conn: DatabaseConnection, table: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    columns = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(columns)
    sql = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"
    conn.executemany(sql, [tuple(row[column] for column in columns) for row in rows])
    return len(rows)


def migrate(source_path: Path, target_url: str, *, replace: bool) -> dict[str, int]:
    if not source_path.exists():
        raise FileNotFoundError(f"Base SQLite source introuvable : {source_path}")

    source = open_database(source_path)
    target = open_database(target_url)
    if not target.is_postgres:
        raise ValueError("La cible doit etre une URL PostgreSQL.")

    if replace:
        _delete_existing_rows(target)

    copied: dict[str, int] = {}
    try:
        for table in TABLES:
            rows = _fetch_rows(source, table)
            copied[table] = _insert_rows(target, table, rows)
        target.commit()
        reset_identity_sequences(target)
        return copied
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Chemin de la base SQLite source.",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("DATABASE_URL", ""),
        help="URL PostgreSQL cible. Defaut: variable DATABASE_URL.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Vide les tables PostgreSQL avant import.",
    )
    args = parser.parse_args()

    if not args.target:
        raise SystemExit("Fournis --target ou la variable DATABASE_URL.")
    if not is_postgres_target(args.target):
        raise SystemExit("La cible doit commencer par postgresql:// ou postgres://.")
    if not args.source.exists():
        raise SystemExit(f"Base SQLite source introuvable : {args.source}")

    copied = migrate(args.source, args.target, replace=args.replace)
    for table, count in copied.items():
        print(f"{table}: {count} ligne(s) copiee(s)")


if __name__ == "__main__":
    main()
