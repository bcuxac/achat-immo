from pathlib import Path

from streamlit.testing.v1 import AppTest

def _profile_form_app() -> None:
    import os

    from achat_immo.storage import open_database
    from app.views.automation import _render_investment_profile

    conn = open_database(os.environ["INVESTMENT_PROFILE_TEST_DB"])
    try:
        _render_investment_profile(conn)
    finally:
        conn.close()


def test_profile_form_renders_configurable_choices(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("INVESTMENT_PROFILE_TEST_DB", str(tmp_path / "profile-ui.sqlite"))

    app = AppTest.from_function(_profile_form_app).run(timeout=10)

    assert not app.exception
    labels = {element.label for element in app.number_input}
    assert "Budget total min" in labels
    assert "Budget total max" in labels
    assert "Apport min" in labels
    assert "Duree du credit (ans)" in labels
    assert "TRI P10 min (%)" in labels
    assert "Biens hypothetiques" in labels
    assert app.button[0].label == "Enregistrer une nouvelle version"
