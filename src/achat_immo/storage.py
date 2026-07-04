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
from urllib.parse import urlsplit, urlunsplit

from achat_immo.schemas import (
    AnalysisRunRecordSchema,
    AnnonceRecordSchema,
    ExtractionRunRecordSchema,
    HypothesesAchatRecordSchema,
    SimulationResultRowSchema,
    SourcingQueueRecordSchema,
    SourcingRunRecordSchema,
)
from achat_immo.investment_profile import (
    DEFAULT_PROFILE_KEY,
    PROFILE_SCHEMA_VERSION,
    InvestmentProfile,
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
from achat_immo.storage_records import (
    AnalysisRunRecord,
    AnnonceRecord,
    ExtractionRunRecord,
    HypothesesAchatRecord,
    SourcingQueueRecord,
    SourcingRunRecord,
)
from achat_immo.storage_schema import init_db
from achat_immo.viability.artifact import deserialize_viability_config, serialize_viability_config
from achat_immo.viability.models import HypotheticalProperty, ViabilityMap, ViabilityPoint


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def normalize_source_url(url: str) -> str:
    """Normalise une URL source pour la deduplication conservative."""

    value = url.strip()
    if not value:
        raise ValueError("L'URL source ne peut pas etre vide.")
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value.rstrip("/")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


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
                prix_affiche, prix_negocie, dpe, description, statut, notes,
                tri_p50, tri_p10, probabilite_cashflow_positif, prix_cible_recommande, cashflow_p50, coc_p50
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                annonce.tri_p50,
                annonce.tri_p10,
                annonce.probabilite_cashflow_positif,
                annonce.prix_cible_recommande,
                annonce.cashflow_p50,
                annonce.coc_p50,
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
                statut = ?, notes = ?, tri_p50 = ?, tri_p10 = ?, probabilite_cashflow_positif = ?,
                prix_cible_recommande = ?, cashflow_p50 = ?, coc_p50 = ?
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
                annonce.tri_p50,
                annonce.tri_p10,
                annonce.probabilite_cashflow_positif,
                annonce.prix_cible_recommande,
                annonce.cashflow_p50,
                annonce.coc_p50,
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


def find_annonce_id_by_url(conn: DatabaseConnection, url: str) -> int | None:
    """Retourne l'annonce connue pour une URL canonique si elle existe."""

    normalized_url = normalize_source_url(url)
    row = conn.execute(
        """
        SELECT id
        FROM annonces
        WHERE url = ?
        ORDER BY id DESC
        """,
        (normalized_url,),
    ).fetchone()
    return int(row["id"]) if row else None


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


def get_investment_profile(
    conn: DatabaseConnection,
    profile_key: str = DEFAULT_PROFILE_KEY,
) -> InvestmentProfile:
    """Charge la derniere version du profil ou retourne les valeurs initiales."""

    row = conn.execute(
        """
        SELECT config_json
        FROM investment_profile_versions
        WHERE profile_key = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (profile_key,),
    ).fetchone()
    return InvestmentProfile.from_json(str(row["config_json"])) if row else InvestmentProfile()


def save_investment_profile(
    conn: DatabaseConnection,
    profile: InvestmentProfile,
    profile_key: str = DEFAULT_PROFILE_KEY,
) -> int:
    """Ajoute une version seulement lorsque la configuration change."""

    if not profile_key.strip():
        raise ValueError("La cle du profil est obligatoire.")
    latest = conn.execute(
        """
        SELECT id, config_hash
        FROM investment_profile_versions
        WHERE profile_key = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (profile_key,),
    ).fetchone()
    if latest and str(latest["config_hash"]) == profile.fingerprint:
        return int(latest["id"])

    insert_sql = """
        INSERT INTO investment_profile_versions (
            profile_key, date_creation, schema_version, config_hash, config_json
        )
        VALUES (?, ?, ?, ?, ?)
        """
    if conn.is_postgres:
        insert_sql += " RETURNING id"
    cursor = conn.execute(
        insert_sql,
        (
            profile_key,
            _now_iso(),
            PROFILE_SCHEMA_VERSION,
            profile.fingerprint,
            profile.to_json(),
        ),
    )
    version_id = int(cursor.fetchone()["id"]) if conn.is_postgres else int(cursor.lastrowid)
    conn.commit()
    return version_id


def list_investment_profile_versions(
    conn: DatabaseConnection,
    profile_key: str = DEFAULT_PROFILE_KEY,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if limit <= 0:
        raise ValueError("La limite doit etre strictement positive.")
    rows = conn.execute(
        """
        SELECT id, profile_key, date_creation, schema_version, config_hash
        FROM investment_profile_versions
        WHERE profile_key = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (profile_key, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def save_viability_map(conn: DatabaseConnection, viability_map: ViabilityMap) -> int:
    """Persiste une carte et l'active pour sa ville et son profil."""

    config = viability_map.config
    conn.execute(
        "UPDATE viability_maps SET active = 0 WHERE city = ? AND profile_hash = ?",
        (config.market.city, config.profile_fingerprint),
    )
    insert_sql = """
        INSERT INTO viability_maps (
            date_creation, city, profile_hash, map_version, config_json,
            point_count, viable_count, active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
    """
    if conn.is_postgres:
        insert_sql += " RETURNING id"
    cursor = conn.execute(
        insert_sql,
        (
            _now_iso(),
            config.market.city,
            config.profile_fingerprint,
            config.version,
            serialize_viability_config(config),
            len(viability_map.points),
            viability_map.viable_count,
        ),
    )
    map_id = int(cursor.fetchone()["id"]) if conn.is_postgres else int(cursor.lastrowid)
    conn.executemany(
        """
        INSERT INTO viability_points (
            map_id, sample_id, surface_m2, price, monthly_rent, annual_charges,
            property_tax, initial_works, equity, total_project_cost,
            legal_rent_cap_per_m2, qualification, reasons, tri_median, tri_p10,
            cash_on_cash_median, prudent_monthly_cashflow,
            positive_cashflow_probability, valid_scenarios
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                map_id,
                point.property.sample_id,
                point.property.surface_m2,
                point.property.price,
                point.property.monthly_rent,
                point.property.annual_charges,
                point.property.property_tax,
                point.property.initial_works,
                point.property.equity,
                point.property.total_project_cost,
                point.property.legal_rent_cap_per_m2,
                point.qualification,
                ",".join(point.reasons),
                point.tri_median,
                point.tri_p10,
                point.cash_on_cash_median,
                point.prudent_monthly_cashflow,
                point.positive_cashflow_probability,
                point.valid_scenarios,
            )
            for point in viability_map.points
        ],
    )
    conn.commit()
    return map_id


def get_active_viability_map(
    conn: DatabaseConnection,
    city: str,
    profile_hash: str,
) -> tuple[int, ViabilityMap] | None:
    row = conn.execute(
        """
        SELECT * FROM viability_maps
        WHERE city = ? AND profile_hash = ? AND active = 1
        ORDER BY id DESC LIMIT 1
        """,
        (city, profile_hash),
    ).fetchone()
    if row is None:
        return None
    map_id = int(row["id"])
    config = deserialize_viability_config(str(row["config_json"]))
    point_rows = conn.execute(
        "SELECT * FROM viability_points WHERE map_id = ? ORDER BY sample_id",
        (map_id,),
    ).fetchall()
    points = tuple(_viability_point_from_row(point_row) for point_row in point_rows)
    return map_id, ViabilityMap(config=config, points=points)


def list_viability_maps(conn: DatabaseConnection, *, limit: int = 20) -> list[dict[str, Any]]:
    if limit <= 0:
        raise ValueError("La limite doit etre strictement positive.")
    rows = conn.execute(
        "SELECT * FROM viability_maps ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _viability_point_from_row(row: Mapping[str, Any]) -> ViabilityPoint:
    return ViabilityPoint(
        property=HypotheticalProperty(
            sample_id=int(row["sample_id"]),
            surface_m2=float(row["surface_m2"]),
            price=float(row["price"]),
            monthly_rent=float(row["monthly_rent"]),
            annual_charges=float(row["annual_charges"]),
            property_tax=float(row["property_tax"]),
            initial_works=float(row["initial_works"]),
            equity=float(row["equity"]),
            total_project_cost=float(row["total_project_cost"]),
            legal_rent_cap_per_m2=(
                float(row["legal_rent_cap_per_m2"]) if row["legal_rent_cap_per_m2"] is not None else None
            ),
        ),
        qualification=str(row["qualification"]),
        reasons=tuple(part for part in str(row["reasons"]).split(",") if part),
        tri_median=_optional_float(row["tri_median"]),
        tri_p10=_optional_float(row["tri_p10"]),
        cash_on_cash_median=_optional_float(row["cash_on_cash_median"]),
        prudent_monthly_cashflow=_optional_float(row["prudent_monthly_cashflow"]),
        positive_cashflow_probability=_optional_float(row["positive_cashflow_probability"]),
        valid_scenarios=int(row["valid_scenarios"]),
    )


def save_qualification_run(
    conn: DatabaseConnection,
    *,
    annonce_id: int,
    map_id: int | None,
    profile_hash: str,
    qualification: str,
    viable_neighbor_ratio: float | None,
    distance_to_viable: float | None,
    estimated_max_price: float | None,
    missing_fields: Iterable[str] = (),
    reasons: Iterable[str] = (),
) -> int:
    insert_sql = """
        INSERT INTO qualification_runs (
            annonce_id, map_id, date_run, profile_hash, qualification,
            viable_neighbor_ratio, distance_to_viable, estimated_max_price,
            missing_fields, reasons
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    if conn.is_postgres:
        insert_sql += " RETURNING id"
    cursor = conn.execute(
        insert_sql,
        (
            annonce_id,
            map_id,
            _now_iso(),
            profile_hash,
            qualification,
            viable_neighbor_ratio,
            distance_to_viable,
            estimated_max_price,
            ",".join(missing_fields),
            ",".join(reasons),
        ),
    )
    run_id = int(cursor.fetchone()["id"]) if conn.is_postgres else int(cursor.lastrowid)
    conn.commit()
    return run_id


def list_qualification_runs(
    conn: DatabaseConnection,
    annonce_id: int | None = None,
) -> list[dict[str, Any]]:
    if annonce_id is None:
        rows = conn.execute("SELECT * FROM qualification_runs ORDER BY id DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM qualification_runs WHERE annonce_id = ? ORDER BY id DESC",
            (annonce_id,),
        ).fetchall()
    return [dict(row) for row in rows]


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
                row.get("tri_annuel_pct"),
                row.get("van"),
                row.get("cash_on_cash_return_pct"),
                row.get("impots_total_horizon", 0.0),
                row.get("impot_plus_value", 0.0),
                row["patrimoine_net_horizon"],
                row["patrimoine_net_sortie"],
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


def save_extraction_run(conn: DatabaseConnection, run: ExtractionRunRecord) -> int:
    """Sauvegarde une trace d'extraction IA/scraping."""

    data = ExtractionRunRecordSchema.model_validate(run).model_dump()
    insert_sql = """
        INSERT INTO extraction_runs (
            annonce_id, date_run, source_url, final_url, status, model,
            input_chars, raw_content_hash, extracted_source, red_flags,
            missing_fields, error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
    if conn.is_postgres:
        insert_sql += " RETURNING id"
    cursor = conn.execute(
        insert_sql,
        (
            data["annonce_id"],
            data["date_run"] or _now_iso(),
            data["source_url"],
            data["final_url"],
            data["status"],
            data["model"],
            data["input_chars"],
            data["raw_content_hash"],
            data["extracted_source"],
            data["red_flags"],
            data["missing_fields"],
            data["error_message"],
        ),
    )
    if conn.is_postgres:
        row = cursor.fetchone()
        run_id = int(row["id"])
    else:
        run_id = int(cursor.lastrowid)
    conn.commit()
    return run_id


def list_extraction_runs(conn: DatabaseConnection, annonce_id: int | None = None) -> list[dict[str, Any]]:
    if annonce_id is None:
        rows = conn.execute(
            """
            SELECT *
            FROM extraction_runs
            ORDER BY id DESC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM extraction_runs
            WHERE annonce_id = ?
            ORDER BY id DESC
            """,
            (annonce_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def save_analysis_run(conn: DatabaseConnection, run: AnalysisRunRecord) -> int:
    """Sauvegarde une trace d'analyse Monte Carlo et solveur inverse."""

    data = AnalysisRunRecordSchema.model_validate(run).model_dump()
    insert_sql = """
        INSERT INTO analysis_runs (
            annonce_id, date_run, status, scenario_seed, nb_scenarios,
            solver_status, solver_iterations, price_floor, price_ceiling,
            target_tri_median, target_tri_p10, target_coc, target_cashflow,
            tri_p50, tri_p10, probabilite_cashflow_positif, coc_p50,
            cashflow_p50, recommended_price, recommended_project_cost,
            recommended_apport, recommended_loan_amount, summary_json, diagnostics
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
    if conn.is_postgres:
        insert_sql += " RETURNING id"
    cursor = conn.execute(
        insert_sql,
        (
            data["annonce_id"],
            data["date_run"] or _now_iso(),
            data["status"],
            data["scenario_seed"],
            data["nb_scenarios"],
            data["solver_status"],
            data["solver_iterations"],
            data["price_floor"],
            data["price_ceiling"],
            data["target_tri_median"],
            data["target_tri_p10"],
            data["target_coc"],
            data["target_cashflow"],
            data["tri_p50"],
            data["tri_p10"],
            data["probabilite_cashflow_positif"],
            data["coc_p50"],
            data["cashflow_p50"],
            data["recommended_price"],
            data["recommended_project_cost"],
            data["recommended_apport"],
            data["recommended_loan_amount"],
            data["summary_json"],
            data["diagnostics"],
        ),
    )
    if conn.is_postgres:
        row = cursor.fetchone()
        run_id = int(row["id"])
    else:
        run_id = int(cursor.lastrowid)
    conn.commit()
    return run_id


def list_analysis_runs(conn: DatabaseConnection, annonce_id: int | None = None) -> list[dict[str, Any]]:
    if annonce_id is None:
        rows = conn.execute(
            """
            SELECT *
            FROM analysis_runs
            ORDER BY id DESC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM analysis_runs
            WHERE annonce_id = ?
            ORDER BY id DESC
            """,
            (annonce_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def enqueue_sourcing_url(
    conn: DatabaseConnection,
    url: str,
    *,
    source: str = "manual",
    priority: int = 0,
) -> int:
    """Ajoute une URL a la file sans creer de doublon."""

    source_url = normalize_source_url(url)
    now = _now_iso()
    existing = conn.execute(
        "SELECT * FROM sourcing_queue WHERE source_url = ?",
        (source_url,),
    ).fetchone()
    if existing is not None:
        row = dict(existing)
        should_requeue = row["status"] in {"blocked", "failed", "skipped"}
        status = "pending" if should_requeue else row["status"]
        last_error = "" if should_requeue else row["last_error"]
        conn.execute(
            """
            UPDATE sourcing_queue
            SET date_update = ?, source = ?, status = ?, priority = ?, last_error = ?
            WHERE id = ?
            """,
            (
                now,
                source,
                status,
                max(int(row["priority"]), priority),
                last_error,
                row["id"],
            ),
        )
        conn.commit()
        return int(row["id"])

    record = SourcingQueueRecordSchema.model_validate(
        SourcingQueueRecord(
            source_url=source_url,
            date_creation=now,
            date_update=now,
            source=source,
            priority=priority,
        )
    ).model_dump()
    insert_sql = """
        INSERT INTO sourcing_queue (
            date_creation, date_update, source_url, source, status, priority,
            attempts, annonce_id, last_error, last_processed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
    if conn.is_postgres:
        insert_sql += " RETURNING id"
    cursor = conn.execute(
        insert_sql,
        (
            record["date_creation"],
            record["date_update"],
            record["source_url"],
            record["source"],
            record["status"],
            record["priority"],
            record["attempts"],
            record["annonce_id"],
            record["last_error"],
            record["last_processed_at"],
        ),
    )
    if conn.is_postgres:
        row = cursor.fetchone()
        queue_id = int(row["id"])
    else:
        queue_id = int(cursor.lastrowid)
    conn.commit()
    return queue_id


def list_sourcing_queue(conn: DatabaseConnection, status: str | None = None) -> list[dict[str, Any]]:
    if status is None:
        rows = conn.execute(
            """
            SELECT *
            FROM sourcing_queue
            ORDER BY priority DESC, id ASC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM sourcing_queue
            WHERE status = ?
            ORDER BY priority DESC, id ASC
            """,
            (status,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_sourcing_queue_item(conn: DatabaseConnection, queue_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM sourcing_queue WHERE id = ?",
        (queue_id,),
    ).fetchone()
    return dict(row) if row else None


def update_sourcing_queue_item(
    conn: DatabaseConnection,
    queue_id: int,
    *,
    source: str,
    priority: int,
) -> None:
    conn.execute(
        """
        UPDATE sourcing_queue
        SET source = ?, priority = ?, date_update = ?
        WHERE id = ?
        """,
        (source, priority, _now_iso(), queue_id),
    )
    conn.commit()


def list_pending_sourcing_urls(conn: DatabaseConnection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM sourcing_queue
        WHERE status = 'pending'
        ORDER BY priority DESC, id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def mark_sourcing_url_pending(conn: DatabaseConnection, queue_id: int, *, clear_error: bool = True) -> None:
    now = _now_iso()
    if clear_error:
        conn.execute(
            """
            UPDATE sourcing_queue
            SET status = 'pending', last_error = '', date_update = ?
            WHERE id = ?
            """,
            (now, queue_id),
        )
    else:
        conn.execute(
            """
            UPDATE sourcing_queue
            SET status = 'pending', date_update = ?
            WHERE id = ?
            """,
            (now, queue_id),
        )
    conn.commit()


def count_sourcing_queue(conn: DatabaseConnection, status: str | None = None) -> int:
    if status is None:
        row = conn.execute("SELECT COUNT(*) AS count FROM sourcing_queue").fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM sourcing_queue WHERE status = ?",
            (status,),
        ).fetchone()
    return int(row["count"])


def create_sourcing_run(conn: DatabaseConnection, run: SourcingRunRecord) -> int:
    """Cree une synthese de run avant traitement de queue."""

    data = SourcingRunRecordSchema.model_validate(run).model_dump()
    insert_sql = """
        INSERT INTO sourcing_runs (
            date_start, date_end, status, url_limit, source_limit,
            allowed_domains, skip_prefilter, pending_at_start,
            examined_count, processed_count, successes, failures,
            skipped, blocked, pending_after, error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
    if conn.is_postgres:
        insert_sql += " RETURNING id"
    cursor = conn.execute(
        insert_sql,
        (
            data["date_start"] or _now_iso(),
            data["date_end"],
            data["status"],
            data["url_limit"],
            data["source_limit"],
            data["allowed_domains"],
            int(data["skip_prefilter"]),
            data["pending_at_start"],
            data["examined_count"],
            data["processed_count"],
            data["successes"],
            data["failures"],
            data["skipped"],
            data["blocked"],
            data["pending_after"],
            data["error_message"],
        ),
    )
    if conn.is_postgres:
        row = cursor.fetchone()
        run_id = int(row["id"])
    else:
        run_id = int(cursor.lastrowid)
    conn.commit()
    return run_id


def complete_sourcing_run(
    conn: DatabaseConnection,
    run_id: int,
    *,
    status: str,
    examined_count: int,
    processed_count: int,
    successes: int,
    failures: int,
    skipped: int,
    blocked: int,
    pending_after: int,
    error_message: str = "",
) -> None:
    """Finalise une synthese de traitement de queue."""

    conn.execute(
        """
        UPDATE sourcing_runs
        SET date_end = ?, status = ?, examined_count = ?, processed_count = ?,
            successes = ?, failures = ?, skipped = ?, blocked = ?,
            pending_after = ?, error_message = ?
        WHERE id = ?
        """,
        (
            _now_iso(),
            status,
            examined_count,
            processed_count,
            successes,
            failures,
            skipped,
            blocked,
            pending_after,
            error_message[:1000],
            run_id,
        ),
    )
    conn.commit()


def list_sourcing_runs(conn: DatabaseConnection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM sourcing_runs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def mark_sourcing_url_processing(conn: DatabaseConnection, queue_id: int) -> None:
    conn.execute(
        """
        UPDATE sourcing_queue
        SET status = 'processing', attempts = attempts + 1, date_update = ?
        WHERE id = ?
        """,
        (_now_iso(), queue_id),
    )
    conn.commit()


def mark_sourcing_url_success(conn: DatabaseConnection, queue_id: int, annonce_id: int) -> None:
    now = _now_iso()
    conn.execute(
        """
        UPDATE sourcing_queue
        SET status = 'done', annonce_id = ?, last_error = '', last_processed_at = ?, date_update = ?
        WHERE id = ?
        """,
        (annonce_id, now, now, queue_id),
    )
    conn.commit()


def mark_sourcing_url_failure(conn: DatabaseConnection, queue_id: int, error_message: str) -> None:
    now = _now_iso()
    conn.execute(
        """
        UPDATE sourcing_queue
        SET status = 'failed', last_error = ?, last_processed_at = ?, date_update = ?
        WHERE id = ?
        """,
        (error_message[:1000], now, now, queue_id),
    )
    conn.commit()


def mark_sourcing_url_skipped(conn: DatabaseConnection, queue_id: int, reason: str) -> None:
    now = _now_iso()
    conn.execute(
        """
        UPDATE sourcing_queue
        SET status = 'skipped', last_error = ?, last_processed_at = ?, date_update = ?
        WHERE id = ?
        """,
        (reason[:1000], now, now, queue_id),
    )
    conn.commit()


def mark_sourcing_url_blocked(conn: DatabaseConnection, queue_id: int, reason: str) -> None:
    now = _now_iso()
    conn.execute(
        """
        UPDATE sourcing_queue
        SET status = 'blocked', last_error = ?, last_processed_at = ?, date_update = ?
        WHERE id = ?
        """,
        (reason[:1000], now, now, queue_id),
    )
    conn.commit()


def reset_identity_sequences(conn: DatabaseConnection) -> None:
    """Aligne les sequences PostgreSQL apres une importation avec ids explicites."""

    if not conn.is_postgres:
        return

    for table in (
        "annonces",
        "simulation_runs",
        "simulation_results",
        "extraction_runs",
        "analysis_runs",
        "sourcing_queue",
        "sourcing_runs",
    ):
        row = conn.execute(f"SELECT COALESCE(MAX(id), 0) AS max_id FROM {table}").fetchone()
        max_id = int(row["max_id"])
        if max_id > 0:
            conn.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), ?, true)",
                (max_id,),
            )
    conn.commit()
