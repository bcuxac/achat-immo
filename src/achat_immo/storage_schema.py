"""Schema SQL et migrations de stockage."""

from __future__ import annotations

from achat_immo.storage_connection import DatabaseConnection


def init_db(conn: DatabaseConnection) -> None:
    """Cree le schema minimal de l'application."""

    if conn.is_postgres:
        conn.executescript(_POSTGRES_SCHEMA)
    else:
        conn.executescript(_SQLITE_SCHEMA)
    _migrate_annonces(conn)
    _migrate_hypotheses_achat(conn)
    _migrate_simulation_results(conn)
    _migrate_analysis_runs(conn)
    _migrate_viability_points(conn)
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
            statut TEXT NOT NULL DEFAULT 'a_verifier',
            notes TEXT NOT NULL DEFAULT '',
            tri_p50 REAL,
            tri_p10 REAL,
            probabilite_cashflow_positif REAL,
            prix_cible_recommande REAL,
            cashflow_p50 REAL,
            coc_p50 REAL
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
            mode_location TEXT NOT NULL DEFAULT '',
            regime_fiscal TEXT NOT NULL DEFAULT '',
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
            tri_annuel_pct REAL,
            van REAL,
            cash_on_cash_return_pct REAL,
            impots_total_horizon REAL NOT NULL DEFAULT 0,
            impot_plus_value REAL NOT NULL DEFAULT 0,
            patrimoine_net_horizon REAL NOT NULL,
            patrimoine_net_sortie REAL NOT NULL DEFAULT 0,
            break_even_year INTEGER,
            nb_annees_cashflow_negatif INTEGER NOT NULL DEFAULT 0,
            score INTEGER NOT NULL,
            decision TEXT NOT NULL,
            alertes TEXT NOT NULL DEFAULT '',
            diagnostics TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (run_id) REFERENCES simulation_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS extraction_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annonce_id INTEGER NOT NULL,
            date_run TEXT NOT NULL,
            source_url TEXT NOT NULL DEFAULT '',
            final_url TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            input_chars INTEGER NOT NULL DEFAULT 0,
            raw_content_hash TEXT NOT NULL DEFAULT '',
            extracted_source TEXT NOT NULL DEFAULT '',
            red_flags TEXT NOT NULL DEFAULT '',
            missing_fields TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS analysis_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annonce_id INTEGER NOT NULL,
            date_run TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '',
            scenario_seed INTEGER NOT NULL DEFAULT 0,
            nb_scenarios INTEGER NOT NULL DEFAULT 0,
            solver_status TEXT NOT NULL DEFAULT '',
            solver_iterations INTEGER NOT NULL DEFAULT 0,
            price_floor REAL,
            price_ceiling REAL,
            target_tri_median REAL NOT NULL DEFAULT 0,
            target_tri_p10 REAL NOT NULL DEFAULT 0,
            target_coc REAL NOT NULL DEFAULT 0,
            target_cashflow REAL NOT NULL DEFAULT 0,
            tri_p50 REAL,
            tri_p10 REAL,
            probabilite_cashflow_positif REAL,
            coc_p50 REAL,
            cashflow_p50 REAL,
            recommended_price REAL,
            recommended_project_cost REAL,
            recommended_apport REAL,
            recommended_loan_amount REAL,
            summary_json TEXT NOT NULL DEFAULT '',
            diagnostics TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sourcing_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_creation TEXT NOT NULL,
            date_update TEXT NOT NULL,
            source_url TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            annonce_id INTEGER,
            last_error TEXT NOT NULL DEFAULT '',
            last_processed_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS sourcing_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_start TEXT NOT NULL,
            date_end TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'running',
            url_limit INTEGER NOT NULL DEFAULT 0,
            source_limit INTEGER,
            allowed_domains TEXT NOT NULL DEFAULT '',
            skip_prefilter INTEGER NOT NULL DEFAULT 0,
            pending_at_start INTEGER NOT NULL DEFAULT 0,
            examined_count INTEGER NOT NULL DEFAULT 0,
            processed_count INTEGER NOT NULL DEFAULT 0,
            successes INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            blocked INTEGER NOT NULL DEFAULT 0,
            pending_after INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS jinka_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_creation TEXT NOT NULL,
            date_update TEXT NOT NULL,
            alert_id TEXT NOT NULL UNIQUE,
            source_url TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'jinka_email',
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_notification_count INTEGER,
            last_seen_at TEXT NOT NULL DEFAULT '',
            last_collected_at TEXT NOT NULL DEFAULT '',
            discovered_ads_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS investment_profile_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_key TEXT NOT NULL,
            date_creation TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            config_hash TEXT NOT NULL,
            config_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS viability_maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_creation TEXT NOT NULL,
            city TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            map_version TEXT NOT NULL,
            config_json TEXT NOT NULL,
            point_count INTEGER NOT NULL,
            viable_count INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS viability_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id INTEGER NOT NULL,
            sample_id INTEGER NOT NULL,
            surface_m2 REAL NOT NULL,
            price REAL NOT NULL,
            monthly_rent REAL NOT NULL,
            annual_charges REAL NOT NULL,
            property_tax REAL NOT NULL,
            initial_works REAL NOT NULL,
            equity REAL NOT NULL,
            total_project_cost REAL NOT NULL,
            legal_rent_cap_per_m2 REAL,
            rent_cap_category_id TEXT,
            rent_sector TEXT,
            room_count INTEGER,
            construction_period TEXT,
            rent_legality_verifiable INTEGER NOT NULL DEFAULT 1,
            sample_kind TEXT NOT NULL DEFAULT 'sobol',
            qualification TEXT NOT NULL,
            reasons TEXT NOT NULL DEFAULT '',
            tri_median REAL,
            tri_p10 REAL,
            cash_on_cash_median REAL,
            prudent_monthly_cashflow REAL,
            positive_cashflow_probability REAL,
            first_year_monthly_cashflow_median REAL,
            first_year_monthly_cashflow_p10 REAL,
            all_years_positive_cashflow_probability REAL,
            cumulative_positive_cashflow_probability REAL,
            valid_scenarios INTEGER NOT NULL,
            FOREIGN KEY (map_id) REFERENCES viability_maps(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS qualification_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annonce_id INTEGER NOT NULL,
            map_id INTEGER,
            date_run TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            qualification TEXT NOT NULL,
            viable_neighbor_ratio REAL,
            distance_to_viable REAL,
            estimated_max_price REAL,
            missing_fields TEXT NOT NULL DEFAULT '',
            reasons TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE,
            FOREIGN KEY (map_id) REFERENCES viability_maps(id) ON DELETE SET NULL
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
            statut TEXT NOT NULL DEFAULT 'a_verifier',
            notes TEXT NOT NULL DEFAULT '',
            tri_p50 DOUBLE PRECISION,
            tri_p10 DOUBLE PRECISION,
            probabilite_cashflow_positif DOUBLE PRECISION,
            prix_cible_recommande DOUBLE PRECISION,
            cashflow_p50 DOUBLE PRECISION,
            coc_p50 DOUBLE PRECISION
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
            mode_location TEXT NOT NULL DEFAULT '',
            regime_fiscal TEXT NOT NULL DEFAULT '',
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
            tri_annuel_pct DOUBLE PRECISION,
            van DOUBLE PRECISION,
            cash_on_cash_return_pct DOUBLE PRECISION,
            impots_total_horizon DOUBLE PRECISION NOT NULL DEFAULT 0,
            impot_plus_value DOUBLE PRECISION NOT NULL DEFAULT 0,
            patrimoine_net_horizon DOUBLE PRECISION NOT NULL,
            patrimoine_net_sortie DOUBLE PRECISION NOT NULL DEFAULT 0,
            break_even_year INTEGER,
            nb_annees_cashflow_negatif INTEGER NOT NULL DEFAULT 0,
            score INTEGER NOT NULL,
            decision TEXT NOT NULL,
            alertes TEXT NOT NULL DEFAULT '',
            diagnostics TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (run_id) REFERENCES simulation_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS extraction_runs (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            annonce_id INTEGER NOT NULL,
            date_run TEXT NOT NULL,
            source_url TEXT NOT NULL DEFAULT '',
            final_url TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            input_chars INTEGER NOT NULL DEFAULT 0,
            raw_content_hash TEXT NOT NULL DEFAULT '',
            extracted_source TEXT NOT NULL DEFAULT '',
            red_flags TEXT NOT NULL DEFAULT '',
            missing_fields TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS analysis_runs (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            annonce_id INTEGER NOT NULL,
            date_run TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '',
            scenario_seed INTEGER NOT NULL DEFAULT 0,
            nb_scenarios INTEGER NOT NULL DEFAULT 0,
            solver_status TEXT NOT NULL DEFAULT '',
            solver_iterations INTEGER NOT NULL DEFAULT 0,
            price_floor DOUBLE PRECISION,
            price_ceiling DOUBLE PRECISION,
            target_tri_median DOUBLE PRECISION NOT NULL DEFAULT 0,
            target_tri_p10 DOUBLE PRECISION NOT NULL DEFAULT 0,
            target_coc DOUBLE PRECISION NOT NULL DEFAULT 0,
            target_cashflow DOUBLE PRECISION NOT NULL DEFAULT 0,
            tri_p50 DOUBLE PRECISION,
            tri_p10 DOUBLE PRECISION,
            probabilite_cashflow_positif DOUBLE PRECISION,
            coc_p50 DOUBLE PRECISION,
            cashflow_p50 DOUBLE PRECISION,
            recommended_price DOUBLE PRECISION,
            recommended_project_cost DOUBLE PRECISION,
            recommended_apport DOUBLE PRECISION,
            recommended_loan_amount DOUBLE PRECISION,
            summary_json TEXT NOT NULL DEFAULT '',
            diagnostics TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sourcing_queue (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            date_creation TEXT NOT NULL,
            date_update TEXT NOT NULL,
            source_url TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            annonce_id INTEGER,
            last_error TEXT NOT NULL DEFAULT '',
            last_processed_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (annonce_id) REFERENCES annonces(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS sourcing_runs (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            date_start TEXT NOT NULL,
            date_end TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'running',
            url_limit INTEGER NOT NULL DEFAULT 0,
            source_limit INTEGER,
            allowed_domains TEXT NOT NULL DEFAULT '',
            skip_prefilter INTEGER NOT NULL DEFAULT 0,
            pending_at_start INTEGER NOT NULL DEFAULT 0,
            examined_count INTEGER NOT NULL DEFAULT 0,
            processed_count INTEGER NOT NULL DEFAULT 0,
            successes INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            skipped INTEGER NOT NULL DEFAULT 0,
            blocked INTEGER NOT NULL DEFAULT 0,
            pending_after INTEGER NOT NULL DEFAULT 0,
            error_message TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS jinka_alerts (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            date_creation TEXT NOT NULL,
            date_update TEXT NOT NULL,
            alert_id TEXT NOT NULL UNIQUE,
            source_url TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'jinka_email',
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_notification_count INTEGER,
            last_seen_at TEXT NOT NULL DEFAULT '',
            last_collected_at TEXT NOT NULL DEFAULT '',
            discovered_ads_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS investment_profile_versions (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            profile_key TEXT NOT NULL,
            date_creation TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            config_hash TEXT NOT NULL,
            config_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS viability_maps (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            date_creation TEXT NOT NULL,
            city TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            map_version TEXT NOT NULL,
            config_json TEXT NOT NULL,
            point_count INTEGER NOT NULL,
            viable_count INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS viability_points (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            map_id INTEGER NOT NULL REFERENCES viability_maps(id) ON DELETE CASCADE,
            sample_id INTEGER NOT NULL,
            surface_m2 DOUBLE PRECISION NOT NULL,
            price DOUBLE PRECISION NOT NULL,
            monthly_rent DOUBLE PRECISION NOT NULL,
            annual_charges DOUBLE PRECISION NOT NULL,
            property_tax DOUBLE PRECISION NOT NULL,
            initial_works DOUBLE PRECISION NOT NULL,
            equity DOUBLE PRECISION NOT NULL,
            total_project_cost DOUBLE PRECISION NOT NULL,
            legal_rent_cap_per_m2 DOUBLE PRECISION,
            rent_cap_category_id TEXT,
            rent_sector TEXT,
            room_count INTEGER,
            construction_period TEXT,
            rent_legality_verifiable BOOLEAN NOT NULL DEFAULT TRUE,
            sample_kind TEXT NOT NULL DEFAULT 'sobol',
            qualification TEXT NOT NULL,
            reasons TEXT NOT NULL DEFAULT '',
            tri_median DOUBLE PRECISION,
            tri_p10 DOUBLE PRECISION,
            cash_on_cash_median DOUBLE PRECISION,
            prudent_monthly_cashflow DOUBLE PRECISION,
            positive_cashflow_probability DOUBLE PRECISION,
            first_year_monthly_cashflow_median DOUBLE PRECISION,
            first_year_monthly_cashflow_p10 DOUBLE PRECISION,
            all_years_positive_cashflow_probability DOUBLE PRECISION,
            cumulative_positive_cashflow_probability DOUBLE PRECISION,
            valid_scenarios INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS qualification_runs (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            annonce_id INTEGER NOT NULL REFERENCES annonces(id) ON DELETE CASCADE,
            map_id INTEGER REFERENCES viability_maps(id) ON DELETE SET NULL,
            date_run TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            qualification TEXT NOT NULL,
            viable_neighbor_ratio DOUBLE PRECISION,
            distance_to_viable DOUBLE PRECISION,
            estimated_max_price DOUBLE PRECISION,
            missing_fields TEXT NOT NULL DEFAULT '',
            reasons TEXT NOT NULL DEFAULT ''
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
        "tri_p50": "ALTER TABLE annonces ADD COLUMN tri_p50 REAL",
        "tri_p10": "ALTER TABLE annonces ADD COLUMN tri_p10 REAL",
        "probabilite_cashflow_positif": "ALTER TABLE annonces ADD COLUMN probabilite_cashflow_positif REAL",
        "prix_cible_recommande": "ALTER TABLE annonces ADD COLUMN prix_cible_recommande REAL",
        "cashflow_p50": "ALTER TABLE annonces ADD COLUMN cashflow_p50 REAL",
        "coc_p50": "ALTER TABLE annonces ADD COLUMN coc_p50 REAL",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)
    conn.execute("UPDATE annonces SET statut = ? WHERE statut = ?", ("a_verifier", "a_analyser"))


def _migrate_hypotheses_achat(conn: DatabaseConnection) -> None:
    """Ajoute les hypotheses de location aux bases deja creees."""

    columns = _table_columns(conn, "hypotheses_achat")
    migrations = {
        "mode_location": "ALTER TABLE hypotheses_achat ADD COLUMN mode_location TEXT NOT NULL DEFAULT 'meublee'",
        "cfe_annuelle": "ALTER TABLE hypotheses_achat ADD COLUMN cfe_annuelle REAL NOT NULL DEFAULT 0",
        "regime_fiscal": "ALTER TABLE hypotheses_achat ADD COLUMN regime_fiscal TEXT NOT NULL DEFAULT 'lmnp_reel'",
        "tmi_pct": "ALTER TABLE hypotheses_achat ADD COLUMN tmi_pct REAL NOT NULL DEFAULT 30",
        "prelevements_sociaux_pct": (
            "ALTER TABLE hypotheses_achat ADD COLUMN prelevements_sociaux_pct REAL NOT NULL DEFAULT 18.6"
        ),
        "part_terrain_pct": "ALTER TABLE hypotheses_achat ADD COLUMN part_terrain_pct REAL NOT NULL DEFAULT 15",
        "duree_amortissement_bien_annees": (
            "ALTER TABLE hypotheses_achat ADD COLUMN duree_amortissement_bien_annees INTEGER NOT NULL DEFAULT 30"
        ),
        "duree_amortissement_travaux_annees": (
            "ALTER TABLE hypotheses_achat ADD COLUMN duree_amortissement_travaux_annees INTEGER NOT NULL DEFAULT 15"
        ),
        "duree_amortissement_meubles_annees": (
            "ALTER TABLE hypotheses_achat ADD COLUMN duree_amortissement_meubles_annees INTEGER NOT NULL DEFAULT 7"
        ),
        "abattement_micro_bic_pct": (
            "ALTER TABLE hypotheses_achat ADD COLUMN abattement_micro_bic_pct REAL NOT NULL DEFAULT 50"
        ),
        "abattement_micro_foncier_pct": (
            "ALTER TABLE hypotheses_achat ADD COLUMN abattement_micro_foncier_pct REAL NOT NULL DEFAULT 30"
        ),
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
        "mode_location": "ALTER TABLE simulation_results ADD COLUMN mode_location TEXT NOT NULL DEFAULT ''",
        "regime_fiscal": "ALTER TABLE simulation_results ADD COLUMN regime_fiscal TEXT NOT NULL DEFAULT ''",
        "tri_annuel_pct": "ALTER TABLE simulation_results ADD COLUMN tri_annuel_pct REAL",
        "van": "ALTER TABLE simulation_results ADD COLUMN van REAL",
        "cash_on_cash_return_pct": "ALTER TABLE simulation_results ADD COLUMN cash_on_cash_return_pct REAL",
        "impots_total_horizon": (
            "ALTER TABLE simulation_results ADD COLUMN impots_total_horizon REAL NOT NULL DEFAULT 0"
        ),
        "impot_plus_value": "ALTER TABLE simulation_results ADD COLUMN impot_plus_value REAL NOT NULL DEFAULT 0",
        "patrimoine_net_sortie": (
            "ALTER TABLE simulation_results ADD COLUMN patrimoine_net_sortie REAL NOT NULL DEFAULT 0"
        ),
        "break_even_year": "ALTER TABLE simulation_results ADD COLUMN break_even_year INTEGER",
        "nb_annees_cashflow_negatif": (
            "ALTER TABLE simulation_results ADD COLUMN nb_annees_cashflow_negatif INTEGER NOT NULL DEFAULT 0"
        ),
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)


def _migrate_analysis_runs(conn: DatabaseConnection) -> None:
    """Ajoute les colonnes recentes des analyses automatiques."""

    columns = _table_columns(conn, "analysis_runs")
    migrations = {
        "recommended_project_cost": "ALTER TABLE analysis_runs ADD COLUMN recommended_project_cost REAL",
        "recommended_apport": "ALTER TABLE analysis_runs ADD COLUMN recommended_apport REAL",
        "recommended_loan_amount": "ALTER TABLE analysis_runs ADD COLUMN recommended_loan_amount REAL",
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)


def _migrate_viability_points(conn: DatabaseConnection) -> None:
    """Ajoute les dimensions reglementaires et les metriques explicites de la carte v2."""

    columns = _table_columns(conn, "viability_points")
    real_type = "DOUBLE PRECISION" if conn.is_postgres else "REAL"
    boolean_type = "BOOLEAN NOT NULL DEFAULT TRUE" if conn.is_postgres else "INTEGER NOT NULL DEFAULT 1"
    migrations = {
        "rent_cap_category_id": "ALTER TABLE viability_points ADD COLUMN rent_cap_category_id TEXT",
        "rent_sector": "ALTER TABLE viability_points ADD COLUMN rent_sector TEXT",
        "room_count": "ALTER TABLE viability_points ADD COLUMN room_count INTEGER",
        "construction_period": "ALTER TABLE viability_points ADD COLUMN construction_period TEXT",
        "rent_legality_verifiable": (
            f"ALTER TABLE viability_points ADD COLUMN rent_legality_verifiable {boolean_type}"
        ),
        "sample_kind": (
            "ALTER TABLE viability_points ADD COLUMN sample_kind TEXT NOT NULL DEFAULT 'sobol'"
        ),
        "first_year_monthly_cashflow_median": (
            f"ALTER TABLE viability_points ADD COLUMN first_year_monthly_cashflow_median {real_type}"
        ),
        "first_year_monthly_cashflow_p10": (
            f"ALTER TABLE viability_points ADD COLUMN first_year_monthly_cashflow_p10 {real_type}"
        ),
        "all_years_positive_cashflow_probability": (
            f"ALTER TABLE viability_points ADD COLUMN all_years_positive_cashflow_probability {real_type}"
        ),
        "cumulative_positive_cashflow_probability": (
            f"ALTER TABLE viability_points ADD COLUMN cumulative_positive_cashflow_probability {real_type}"
        ),
    }
    for column, statement in migrations.items():
        if column not in columns:
            conn.execute(statement)
