from achat_immo.sourcing_agents import llm_agent


def test_resolve_chromium_executable_prefere_la_variable_env(monkeypatch) -> None:
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "/opt/chrome/chromium")
    monkeypatch.setattr(llm_agent, "which", lambda _: "/usr/bin/chromium")

    assert llm_agent.resolve_chromium_executable() == "/opt/chrome/chromium"


def test_chromium_launch_options_utilise_un_chromium_systeme(monkeypatch) -> None:
    monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", raising=False)
    monkeypatch.setattr(llm_agent, "which", lambda name: "/usr/bin/chromium" if name == "chromium" else None)

    options = llm_agent.chromium_launch_options()

    assert options["headless"] is True
    assert options["executable_path"] == "/usr/bin/chromium"
    assert "--no-sandbox" in options["args"]


def test_browser_context_options_reutilise_la_session_jinka(monkeypatch, tmp_path) -> None:
    storage_state = tmp_path / "jinka_state.json"
    storage_state.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("JINKA_STORAGE_STATE_PATH", str(storage_state))

    options = llm_agent.browser_context_options("https://www.jinka.fr/ad/abc")

    assert options["storage_state"] == str(storage_state)


def test_browser_context_options_ignore_la_session_pour_un_autre_domaine(monkeypatch, tmp_path) -> None:
    storage_state = tmp_path / "jinka_state.json"
    storage_state.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("JINKA_STORAGE_STATE_PATH", str(storage_state))

    options = llm_agent.browser_context_options("https://example.test/ad/abc")

    assert "storage_state" not in options
