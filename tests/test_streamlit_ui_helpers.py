from __future__ import annotations

from inspect import signature
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType

from app import streamlit_app as ui
from app import runtime_config
from app.sections.comparison import filter_comparison_rows
from app.sections.sourcing_queue import queue_rows_for_view
from app.views.pipeline import filter_pipeline_items
from achat_immo.models import ModeLocation, RegimeFiscal


def test_field_origins_identify_deduced_and_advanced_fields() -> None:
    assert ui.field_origin("loyer_hc_mensuel") == "Saisi"
    assert ui.field_origin("prelevements_sociaux_pct") == "Deduit"
    assert ui.field_origin("abattement_micro_bic_pct") == "Deduit"
    assert ui.field_origin("part_terrain_pct") == "Avance"
    assert ui.is_deduced_field("prelevements_sociaux_pct")
    assert ui.is_advanced_field("duree_amortissement_bien_annees")


def test_non_applicable_costs_are_forced_by_mode_and_regime() -> None:
    assert ui.effective_cfe_value(ModeLocation.NUE, 450.0) == 0.0
    assert ui.effective_cfe_value(ModeLocation.MEUBLEE, 450.0) == 450.0
    assert ui.effective_comptable_lmnp_value(RegimeFiscal.MICRO_BIC, 650.0) == 0.0
    assert ui.effective_comptable_lmnp_value(RegimeFiscal.LMNP_REEL, 650.0) == 650.0


def test_derived_fiscal_values_use_regime_constants() -> None:
    lmnp = ui.derived_fiscalite_values(RegimeFiscal.LMNP_REEL)
    nu = ui.derived_fiscalite_values(RegimeFiscal.LOCATION_NUE_REEL)

    assert lmnp["prelevements_sociaux_pct"] == 18.6
    assert nu["prelevements_sociaux_pct"] == 17.2
    assert lmnp["abattement_micro_bic_pct"] == 50.0
    assert nu["abattement_micro_foncier_pct"] == 30.0


def test_guided_interface_section_labels_are_centralized() -> None:
    assert ui.SIMULATION_SECTION_LABELS == ("Exploitation", "Strategies testees", "Analyse")
    assert ui.PORTFOLIO_DECISION_LABEL == "Comparaison"


def test_main_navigation_exposes_workflow_pages() -> None:
    assert ui.APP_PAGE_LABELS == (
        "Pipeline",
        "Queue sourcing",
        "Fiche annonce",
        "Comparaison",
        "Parametres / Automatisation",
    )
    assert "Historique" not in ui.APP_PAGE_LABELS


def test_streamlit_ui_no_longer_imports_legacy_tabs_package() -> None:
    app_files = (ui.PROJECT_ROOT / "app").rglob("*.py")
    offenders = [
        path.relative_to(ui.PROJECT_ROOT).as_posix()
        for path in app_files
        if "app.tabs" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_property_data_form_does_not_short_circuit_sourcing_queue() -> None:
    annonce_source = Path(ui.PROJECT_ROOT / "app" / "sections" / "property_data.py").read_text(encoding="utf-8")
    workflow_source = Path(ui.PROJECT_ROOT / "app" / "views" / "property_workflow.py").read_text(encoding="utf-8")

    assert "LLMSourcingAgent" not in annonce_source
    assert "GEMINI_API_KEY" not in annonce_source
    assert "Remplissage automatique" not in annonce_source
    assert "enqueue_sourcing_url" in workflow_source


def test_pipeline_filters_keep_active_work_visible() -> None:
    items = [
        {"id": 1, "stage": "shortlist", "statut": "shortlist"},
        {"id": 2, "stage": "a_verifier", "statut": "a_analyser"},
        {"id": 3, "stage": "archive", "statut": "archive"},
    ]

    filtered = filter_pipeline_items(
        items,
        selected_stages=("shortlist", "a_verifier", "archive"),
        include_terminal=False,
    )

    assert [item["id"] for item in filtered] == [1, 2]


def test_sourcing_queue_views_are_operational_groups() -> None:
    rows = [
        {"id": 1, "status": "pending"},
        {"id": 2, "status": "processing"},
        {"id": 3, "status": "failed"},
        {"id": 4, "status": "blocked"},
        {"id": 5, "status": "done"},
    ]

    assert [row["id"] for row in queue_rows_for_view(rows, "A traiter")] == [1, 2]
    assert [row["id"] for row in queue_rows_for_view(rows, "Erreurs / blocages")] == [3, 4]


def test_comparison_filter_preserves_decision_ranking() -> None:
    rows = [
        {
            "annonce_id": 1,
            "decision_robuste": "a_creuser",
            "statut": "a_analyser",
            "pct_scenarios_viables": 80.0,
            "cashflow_prudent": 100.0,
        },
        {
            "annonce_id": 2,
            "decision_robuste": "interessant",
            "statut": "shortlist",
            "pct_scenarios_viables": 50.0,
            "cashflow_prudent": -20.0,
        },
        {
            "annonce_id": 3,
            "decision_robuste": "interessant",
            "statut": "archive",
            "pct_scenarios_viables": 90.0,
            "cashflow_prudent": 150.0,
        },
    ]

    filtered = filter_comparison_rows(
        rows,
        selected_decisions=("interessant", "a_creuser"),
        selected_statuses=("a_analyser", "shortlist"),
        require_positive_prudent_cashflow=False,
    )

    assert [row["annonce_id"] for row in filtered] == [2, 1]
    assert [row["rang"] for row in filtered] == [1, 2]


def test_runtime_secrets_are_exposed_to_environment(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fake_secret_section(key: str) -> dict[str, str]:
        if key == "database":
            return {"url": "postgresql://example.test/db"}
        if key == "gemini":
            return {"api_key": "gemini-secret"}
        return {}

    monkeypatch.setattr(runtime_config, "_secret_section", fake_secret_section)
    monkeypatch.setattr(runtime_config, "_secret_value", lambda key, default=None: default)

    runtime_config.apply_runtime_secrets_to_environment()

    assert os.environ["DATABASE_URL"] == "postgresql://example.test/db"
    assert os.environ["GEMINI_API_KEY"] == "gemini-secret"


def test_streamlit_imports_current_engine_api() -> None:
    assert not ui._runtime_api_errors()
    assert ui.grids_module.GRID_API_VERSION == ui.EXPECTED_GRID_API_VERSION
    assert ui.models_module.MODEL_API_VERSION == ui.EXPECTED_MODEL_API_VERSION
    grille_params = signature(ui.GrilleParametres).parameters
    scenario_params = signature(ui.Scenario).parameters
    count_params = signature(ui.compter_scenarios_grille).parameters
    simulate_params = signature(ui.simuler_grille_annonce).parameters

    assert {"modes_location", "regimes_fiscaux", "comparer_regimes", "appliquer_plafond_loyer"} <= set(grille_params)
    assert "taux_actualisation_pct" in scenario_params
    assert {"fiscalite", "gestion_agence_possible"} <= set(count_params)
    assert {"fiscalite", "scenario_base", "gestion_agence_possible"} <= set(simulate_params)
    assert ui.grids_module is sys.modules["achat_immo.grids"]
    assert ui.models_module is sys.modules["achat_immo.models"]
    assert ui.GrilleParametres is ui.grids_module.GrilleParametres
    assert ui.Scenario is ui.models_module.Scenario
    assert ui.compter_scenarios_grille is ui.grids_module.compter_scenarios_grille


def test_force_fresh_repo_source_package_removes_foreign_cached_modules(tmp_path) -> None:
    module = ModuleType("dummy_package")
    module.__file__ = str(tmp_path / "dummy_package" / "__init__.py")
    sys.modules["dummy_package"] = module

    ui._force_fresh_repo_source_package("dummy_package")

    assert "dummy_package" not in sys.modules


def test_force_fresh_repo_source_package_removes_same_path_cached_modules() -> None:
    package = ModuleType("dummy_package")
    package.__file__ = str(ui.SRC_PATH / "dummy_package" / "__init__.py")
    submodule = ModuleType("dummy_package.models")
    submodule.__file__ = str(ui.SRC_PATH / "dummy_package" / "models.py")
    sys.modules["dummy_package"] = package
    sys.modules["dummy_package.models"] = submodule

    ui._force_fresh_repo_source_package("dummy_package")

    assert "dummy_package" not in sys.modules
    assert "dummy_package.models" not in sys.modules


def test_streamlit_app_imports_from_non_project_cwd(tmp_path) -> None:
    script = (
        "import os, runpy; "
        f"os.chdir({str(tmp_path)!r}); "
        f"runpy.run_path({str(ui.PROJECT_ROOT / 'app' / 'streamlit_app.py')!r}, run_name='streamlit_probe')"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
