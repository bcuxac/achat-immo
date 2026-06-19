"""Configuration runtime et authentification de l'application Streamlit."""

from __future__ import annotations

import os
from typing import Any

import streamlit as st

from achat_immo.auth import verify_password


def _secret_value(key: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(key, default)
    except FileNotFoundError:
        return default


def _secret_section(key: str) -> dict[str, Any]:
    value = _secret_value(key, {})
    if value is None:
        return {}
    return dict(value)


def configured_database_url() -> str:
    database = _secret_section("database")
    value = (
        database.get("url")
        or _secret_value("DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    )
    return str(value).strip()


def configured_gemini_api_key() -> str:
    gemini = _secret_section("gemini")
    value = (
        gemini.get("api_key")
        or _secret_value("GEMINI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or ""
    )
    return str(value).strip()


def apply_runtime_secrets_to_environment() -> None:
    """Expose les secrets Streamlit aux clients qui lisent encore os.environ."""

    database_url = configured_database_url()
    if database_url:
        os.environ["DATABASE_URL"] = database_url

    gemini_api_key = configured_gemini_api_key()
    if gemini_api_key:
        os.environ["GEMINI_API_KEY"] = gemini_api_key


def _auth_users() -> dict[str, str]:
    auth = _secret_section("auth")
    users = dict(auth.get("users", {}) or {})
    if users:
        return {str(user): str(password_hash) for user, password_hash in users.items()}

    password_hash = auth.get("password_hash") or auth.get("password")
    if password_hash:
        return {"": str(password_hash)}
    return {}


def _auth_enabled() -> bool:
    auth = _secret_section("auth")
    if "enabled" in auth:
        return bool(auth["enabled"])
    return bool(_auth_users())


def require_authentication() -> None:
    if not _auth_enabled():
        return

    users = _auth_users()
    if not users:
        st.error("Authentification active mais aucun utilisateur n'est configure.")
        st.stop()

    if st.session_state.get("authenticated"):
        auth_user = st.session_state.get("auth_user", "")
        if auth_user:
            st.sidebar.caption(f"Connecte : {auth_user}")
        if st.sidebar.button("Deconnexion"):
            st.session_state.pop("authenticated", None)
            st.session_state.pop("auth_user", None)
            st.rerun()
        return

    st.title("Connexion")
    with st.form("login-form"):
        username = ""
        if "" not in users:
            username = st.text_input("Utilisateur")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter")

    if submitted:
        expected = users.get(username)
        if expected and verify_password(password, expected):
            st.session_state["authenticated"] = True
            st.session_state["auth_user"] = username
            st.rerun()
        st.error("Identifiants invalides.")

    st.stop()
