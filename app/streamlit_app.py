"""Application Streamlit pour piloter les decisions locatives."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"


def _prepend_sys_path(path: Path) -> None:
    path_str = str(path)
    if path_str in sys.path:
        sys.path.remove(path_str)
    sys.path.insert(0, path_str)


_prepend_sys_path(PROJECT_ROOT)
_prepend_sys_path(SRC_PATH)


def _force_fresh_repo_source_package(package_name: str) -> None:
    """Supprime les modules locaux deja charges pour forcer une lecture du source courant."""

    importlib.invalidate_caches()
    for module_name in list(sys.modules):
        if module_name != package_name and not module_name.startswith(f"{package_name}."):
            continue
        del sys.modules[module_name]


_force_fresh_repo_source_package("achat_immo")

from achat_immo import grids as grids_module
from achat_immo import models as models_module
from achat_immo.grids import (
    GrilleParametres,
    compter_scenarios_grille,
    simuler_grille_annonce,
)
from achat_immo.models import (
    Scenario,
)
from achat_immo.storage import (
    DEFAULT_DB_PATH,
    open_database,
)
from app.tabs.annonce import annonce_page
from app.tabs.comparison import comparison_page
from app.tabs.dashboard import dashboard_page
from app.tabs.history import history_page
from app.tabs.hypotheses import hypotheses_page
from app.tabs.simulation import simulation_page
from app.runtime_config import (
    configured_database_url as _configured_database_url,
    require_authentication as _require_authentication,
)
from app.runtime_checks import (
    RuntimeApiContext,
    require_current_runtime_api as _require_current_runtime_api,
    runtime_api_errors as _runtime_api_errors_for_context,
)
from app.sidebar import load_bundle as _load_bundle, sidebar as _sidebar
from app.ui_helpers import (
    PORTFOLIO_DECISION_LABEL,
    SIMULATION_SECTION_LABELS as SIMULATION_SECTION_LABELS,
    derived_fiscalite_values as derived_fiscalite_values,
    effective_cfe_value as effective_cfe_value,
    effective_comptable_lmnp_value as effective_comptable_lmnp_value,
    field_origin as field_origin,
    is_advanced_field as is_advanced_field,
    is_deduced_field as is_deduced_field,
)


EXPECTED_GRID_API_VERSION = "multi_regime_grid_v1"
EXPECTED_MODEL_API_VERSION = "multi_regime_models_v1"
DB_CONNECTION_CACHE_VERSION = "postgres_no_prepared_statements_v1"
RUNTIME_API_CONTEXT = RuntimeApiContext(
    expected_grid_api_version=EXPECTED_GRID_API_VERSION,
    expected_model_api_version=EXPECTED_MODEL_API_VERSION,
    src_path=SRC_PATH,
    app_file=__file__,
    grids_module=grids_module,
    models_module=models_module,
    grille_parametres=GrilleParametres,
    scenario=Scenario,
    compter_scenarios_grille=compter_scenarios_grille,
    simuler_grille_annonce=simuler_grille_annonce,
)

@st.cache_resource
def _database(target: str, cache_version: str):
    return open_database(target)


def _runtime_api_errors() -> list[str]:
    return _runtime_api_errors_for_context(RUNTIME_API_CONTEXT)


def main() -> None:
    # Charger les variables d'environnement depuis .env (ex: GEMINI_API_KEY)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
        
    st.set_page_config(page_title="Simulateur d'Achat immobilier locatif", layout="wide")
    _require_authentication()
    st.title("Simulateur d'Achat immobilier locatif")
    _require_current_runtime_api(RUNTIME_API_CONTEXT)

    database_url = _configured_database_url()
    if database_url:
        st.sidebar.caption("Base : PostgreSQL cloud")
        database_target = database_url
    else:
        database_target = st.sidebar.text_input("Base SQLite", value=str(DEFAULT_DB_PATH))
    conn = _database(database_target, DB_CONNECTION_CACHE_VERSION)
    rows, selected_id = _sidebar(conn)
    annonce, hypotheses = _load_bundle(conn, selected_id)

    tab_dashboard, tab_annonce, tab_hypotheses, tab_simulation, tab_comparison, tab_history = st.tabs(
        ["Tableau de bord", "Annonce", "Hypotheses", "Simulation", PORTFOLIO_DECISION_LABEL, "Historique"]
    )

    with tab_dashboard:
        dashboard_page(conn, rows)
    with tab_annonce:
        annonce_page(conn, annonce, hypotheses)
    with tab_hypotheses:
        hypotheses_page(conn, annonce, hypotheses)
    with tab_simulation:
        simulation_page(conn, annonce, hypotheses)
    with tab_comparison:
        comparison_page(conn, rows, annonce)
    with tab_history:
        history_page(conn, selected_id)


if __name__ == "__main__":
    main()
