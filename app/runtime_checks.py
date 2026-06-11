"""Controles de coherence du runtime Streamlit."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from inspect import getsourcefile, signature
import os
from pathlib import Path
import sys
from typing import Any

import streamlit as st


@dataclass(frozen=True, slots=True)
class RuntimeApiContext:
    expected_grid_api_version: str
    expected_model_api_version: str
    src_path: Path
    app_file: str
    grids_module: Any
    models_module: Any
    grille_parametres: Any
    scenario: Any
    compter_scenarios_grille: Any
    simuler_grille_annonce: Any


def require_current_runtime_api(context: RuntimeApiContext) -> None:
    errors = runtime_api_errors(context)
    if not errors:
        return
    st.error("Le code Python charge par l'application n'est pas synchronise avec l'interface Streamlit.")
    st.caption("Redeploie l'application avec le dernier commit et vide le cache de dependances si necessaire.")
    st.code("\n".join(errors))
    st.stop()


def runtime_api_errors(context: RuntimeApiContext) -> list[str]:
    return _runtime_api_errors(context)


def _runtime_api_errors(context: RuntimeApiContext) -> list[str]:
    errors: list[str] = []
    loaded_grids_module = sys.modules.get("achat_immo.grids")
    loaded_models_module = sys.modules.get("achat_immo.models")
    grille_params = signature(context.grille_parametres).parameters
    scenario_params = signature(context.scenario).parameters
    count_params = signature(context.compter_scenarios_grille).parameters
    simulate_params = signature(context.simuler_grille_annonce).parameters
    grid_api_version = getattr(context.grids_module, "GRID_API_VERSION", None)
    model_api_version = getattr(context.models_module, "MODEL_API_VERSION", None)

    if grid_api_version != context.expected_grid_api_version:
        errors.append(f"GRID_API_VERSION={grid_api_version!r}, attendu {context.expected_grid_api_version!r}.")
    if model_api_version != context.expected_model_api_version:
        errors.append(f"MODEL_API_VERSION={model_api_version!r}, attendu {context.expected_model_api_version!r}.")
    for field_name in ("modes_location", "regimes_fiscaux", "comparer_regimes", "appliquer_plafond_loyer"):
        if field_name not in grille_params:
            errors.append(f"GrilleParametres ne contient pas {field_name}.")
    if "taux_actualisation_pct" not in scenario_params:
        errors.append("Scenario ne contient pas taux_actualisation_pct.")
    for parameter_name in ("fiscalite", "gestion_agence_possible"):
        if parameter_name not in count_params:
            errors.append(f"compter_scenarios_grille ne supporte pas {parameter_name}.")
    for parameter_name in ("fiscalite", "scenario_base", "gestion_agence_possible"):
        if parameter_name not in simulate_params:
            errors.append(f"simuler_grille_annonce ne supporte pas {parameter_name}.")
    if context.grids_module is not loaded_grids_module:
        errors.append("grids_module ne correspond pas a sys.modules['achat_immo.grids'].")
    if context.models_module is not loaded_models_module:
        errors.append("models_module ne correspond pas a sys.modules['achat_immo.models'].")
    if context.grille_parametres is not getattr(context.grids_module, "GrilleParametres", None):
        errors.append("GrilleParametres ne vient pas de grids_module.GrilleParametres.")
    if context.scenario is not getattr(context.models_module, "Scenario", None):
        errors.append("Scenario ne vient pas de models_module.Scenario.")
    if context.compter_scenarios_grille is not getattr(context.grids_module, "compter_scenarios_grille", None):
        errors.append("compter_scenarios_grille ne vient pas de grids_module.compter_scenarios_grille.")
    if errors:
        _append_runtime_details(errors, context, loaded_grids_module, loaded_models_module)
    return errors


def _append_runtime_details(
    errors: list[str],
    context: RuntimeApiContext,
    loaded_grids_module: Any,
    loaded_models_module: Any,
) -> None:
    grids_file = getattr(loaded_grids_module, "__file__", None)
    models_file = getattr(loaded_models_module, "__file__", None)
    errors.append(f"commit env : {os.environ.get('STREAMLIT_GIT_COMMIT') or os.environ.get('GITHUB_SHA') or 'inconnu'}")
    errors.append(f"app chargee depuis : {context.app_file}")
    errors.append(f"app sha256 court : {_short_file_sha(context.app_file)}")
    errors.append(f"achat_immo.grids charge depuis : {grids_file or 'inconnu'}")
    errors.append(f"achat_immo.grids sha256 court : {_short_file_sha(grids_file)}")
    errors.append(f"achat_immo.models charge depuis : {models_file or 'inconnu'}")
    errors.append(f"achat_immo.models sha256 court : {_short_file_sha(models_file)}")
    errors.append(f"src attendu : {context.src_path}")
    errors.append(_runtime_module_detail("grids_module importe", context.grids_module))
    errors.append(_runtime_module_detail("achat_immo.grids charge", loaded_grids_module))
    errors.append(_runtime_module_detail("models_module importe", context.models_module))
    errors.append(_runtime_module_detail("achat_immo.models charge", loaded_models_module))
    errors.append(_runtime_object_detail("GrilleParametres importe", context.grille_parametres))
    errors.append(_runtime_object_detail("Scenario importe", context.scenario))
    errors.append(_runtime_object_detail("compter_scenarios_grille importe", context.compter_scenarios_grille))
    errors.append(_runtime_object_detail("simuler_grille_annonce importe", context.simuler_grille_annonce))


def _short_file_sha(path: str | None) -> str:
    if not path:
        return "inconnu"
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return "illisible"


def _runtime_object_detail(label: str, obj: Any) -> str:
    try:
        obj_signature = str(signature(obj))
    except (TypeError, ValueError):
        obj_signature = "n/a"
    return (
        f"{label}: type={type(obj).__name__}, module={getattr(obj, '__module__', 'inconnu')}, "
        f"id={id(obj)}, source={getsourcefile(obj) or 'inconnu'}, signature={obj_signature}, repr={obj!r}"
    )


def _runtime_module_detail(label: str, module: Any) -> str:
    if module is None:
        return f"{label}: absent de sys.modules"
    checked_attrs = (
        "GRID_API_VERSION",
        "MODEL_API_VERSION",
        "GrilleParametres",
        "Scenario",
        "compter_scenarios_grille",
        "simuler_grille_annonce",
    )
    present_attrs = [attr for attr in checked_attrs if hasattr(module, attr)]
    return (
        f"{label}: type={type(module).__name__}, id={id(module)}, "
        f"file={getattr(module, '__file__', 'inconnu')}, attrs_presents={present_attrs}"
    )
