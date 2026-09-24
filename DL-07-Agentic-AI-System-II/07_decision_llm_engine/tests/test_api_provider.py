from decision_engine.api import create_app
from decision_engine.config import Settings
from decision_engine.provider import GeminiExplanationProvider


def test_create_app_with_provider_enabled():
    settings = Settings(
        _env_file=None,
        llm_model_explainer="gemini-2.0-flash",
        llm_api_key="test-api-key",
    )
    app = create_app(settings)
    assert isinstance(app.state.provider, GeminiExplanationProvider)


def test_create_app_with_provider_disabled():
    settings = Settings(
        _env_file=None,
        llm_model_explainer="disabled",
        llm_api_key="test-api-key",
    )
    app = create_app(settings)
    assert app.state.provider is None
