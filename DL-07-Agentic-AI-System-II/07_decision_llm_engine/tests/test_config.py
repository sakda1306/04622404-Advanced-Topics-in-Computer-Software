from decision_engine.config import Settings


def test_settings_gemini_config():
    s = Settings(
        _env_file=None,
        llm_model_explainer="gemini-2.0-flash",
        llm_api_key="test-key",
    )
    assert s.llm_model_explainer == "gemini-2.0-flash"
    assert s.llm_api_key.get_secret_value() == "test-key"
    assert s.gemini_api_base == "https://generativelanguage.googleapis.com/v1beta"
    assert s.llm_timeout == 5.0


def test_settings_gemini_api_key_alias(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "alias-key")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    s = Settings(_env_file=None)
    assert s.llm_api_key.get_secret_value() == "alias-key"
