"""Persistance SQL pour les annonces, hypotheses et decisions.

SQLite reste le backend local par defaut. PostgreSQL est supporte pour un
deploiement cloud avec stockage persistant.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from achat_immo.schemas import (
    AnnonceRecordSchema,
    HypothesesAchatRecordSchema,
    SimulationResultRowSchema,
)
from achat_immo.storage_connection import (
    DEFAULT_DB_PATH,
    DatabaseConnection,
    connect,
    is_postgres_target as is_postgres_target,
)
from achat_immo.storage_mapping import (
    fiscalite_from_hypotheses as fiscalite_from_hypotheses,
    to_domain_models as to_domain_models,
)
from achat_immo.storage_records import AnnonceRecord, HypothesesAchatRecord
from achat_immo.storage_schema import init_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def open_database(db_path: str | Path | None = DEFAULT_DB_PATH) -> DatabaseConnection:
    target = db_path
    if target is None:
        target = os.environ.get("DATABASE_URL") or DEFAULT_DB_PATH
    conn = connect(target)
    init_db(conn)
    return conn


def _annonce_from_row(row: Mapping[str, Any]) -> AnnonceRecord:
    data = AnnonceRecordSchema.model_validate(dict(row)).model_dump()
    return AnnonceRecord(**data)


def _hypotheses_from_row(row: Mapping[str, Any]) -> HypothesesAchatRecord:
    data = HypothesesAchatRecordSchema.model_validate(dict(row)).model_dump()
    return HypothesesAchatRecord(**data)


def save_annonce(
    conn: DatabaseConnection,
    annonce: AnnonceRecord,
    hypotheses: HypothesesAchatRecord,
) -> int:
    """Cree ou met a jour une annonce et ses hypotheses."""

    AnnonceRecordSchema.model_validate(annonce)
    HypothesesAchatRecordSchema.model_validate(hypotheses)

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


def save_simulation_run(
    conn: DatabaseConnection,
    annonce_id: int,
    resultats: Iterable[Mapping[str, Any]],
    commentaire: str = "",
) -> int:
    rows = [
        SimulationResultRowSchema.model_validate(dict(resultat)).model_dump()
        for resultat in resultats
    ]
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
            run_id, annonce_id, scenario, mode_location, regime_fiscal, prix_achat, cout_total_projet,
            loyer_hc_mensuel, taux_credit, duree_annees, apport,
            vacance_mois, gestion_agence, frais_gestion_pct, mensualite_totale,
            montant_emprunte, cashflow_mensuel_avant_impot, cashflow_mensuel_apres_impot,
            effort_epargne_mensuel, rendement_net_avant_impot_pct,
            rendement_net_net_pct, tri_annuel_pct, van, cash_on_cash_return_pct,
            impots_total_horizon, impot_plus_value, patrimoine_net_horizon,
            patrimoine_net_sortie, break_even_year, nb_annees_cashflow_negatif,
            score, decision, alertes, diagnostics
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                run_id,
                annonce_id,
                row.get("scenario", ""),
                row.get("mode_location", ""),
                row.get("regime_fiscal", ""),
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
                row.get("tri_annuel_pct", row.get("tri")),
                row.get("van"),
                row.get("cash_on_cash_return_pct", row.get("cash_on_cash")),
                row.get("impots_total_horizon", 0.0),
                row.get("impot_plus_value", 0.0),
                row["patrimoine_net_horizon"],
                row.get("patrimoine_net_sortie", row["patrimoine_net_horizon"]),
                row.get("break_even_year"),
                row.get("nb_annees_cashflow_negatif", 0),
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
