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


def test_extract_original_link_from_text_ignore_jinka_et_assets() -> None:
    text = """
    --- LIENS DETECTES DANS LA PAGE ---
    https://www.jinka.fr/ad/abc
    https://res.cloudinary.com/image.png
    https://www.seloger.com/annonces/achat/appartement/grenoble-38/123.htm
    """

    assert (
        llm_agent.extract_original_link_from_text(text)
        == "https://www.seloger.com/annonces/achat/appartement/grenoble-38/123.htm"
    )


def test_extract_original_link_evite_gemini_si_un_lien_est_detecte() -> None:
    class FailingModels:
        def generate_content(self, **_kwargs):  # noqa: ANN003, ANN201
            raise AssertionError("Gemini ne doit pas etre appele.")

    class FailingClient:
        models = FailingModels()

    agent = object.__new__(llm_agent.LLMSourcingAgent)
    agent.client = FailingClient()
    text = """
    --- LIENS DETECTES DANS LA PAGE ---
    https://www.bienici.com/annonce/vente/grenoble/appartement/123
    """

    assert agent.extract_original_link(text) == "https://www.bienici.com/annonce/vente/grenoble/appartement/123"


def test_gemini_min_interval_est_configurable(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_MIN_INTERVAL_SECONDS", "0")

    assert llm_agent.gemini_min_interval_seconds() == 0.0
