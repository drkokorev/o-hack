import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from core.config import get_settings


@pytest.fixture
def example_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith(("LLM_", "GIGACHAT_")):
            monkeypatch.delenv(name)
    example = Path(__file__).resolve().parents[1] / ".env.example"
    for name, value in dotenv_values(example).items():
        if value is not None:
            monkeypatch.setenv(name, value)
    monkeypatch.setattr("core.config.load_dotenv", lambda: None)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_switching_example_to_gigachat_uses_its_own_endpoint_and_model(example_env):
    example_env.setenv("LLM_PROVIDER", "gigachat")
    example_env.setenv("GIGACHAT_AUTH_KEY", "test-key")
    settings = get_settings()
    assert settings.llm_base_url == "https://api.giga.chat/v1"
    assert settings.llm_model == "GigaChat-2-Max"
    assert not settings.llm_json_mode
    assert settings.llm_enabled


def test_example_defaults_to_gigachat_max_without_a_key(example_env):
    settings = get_settings()
    assert settings.llm_provider == "gigachat"
    assert settings.llm_base_url == "https://api.giga.chat/v1"
    assert settings.llm_model == "GigaChat-2-Max"
    assert not settings.llm_json_mode
    assert settings.llm_timeout == 30
    assert not settings.llm_enabled


def test_example_lists_variables_without_values():
    example = Path(__file__).resolve().parents[1] / ".env.example"
    values = dotenv_values(example)
    assert values and all(value == "" for value in values.values())
    assert {"LLM_PROVIDER", "LLM_API_KEY", "GIGACHAT_AUTH_KEY", "SESSION_TTL_SECONDS"} <= values.keys()


def test_empty_session_timeout_allows_application_start(example_env):
    from apps.web import build_app

    example_env.setenv("SESSION_TTL_SECONDS", "")
    example_env.setenv("ODIN_MODE", "rules")
    app = build_app()
    assert any(route.path == "/health" for route in app.routes)


def test_explicit_provider_overrides_are_preserved(example_env):
    example_env.setenv("LLM_PROVIDER", "gigachat")
    example_env.setenv("LLM_BASE_URL", "https://example.test/v1")
    example_env.setenv("LLM_MODEL", "custom-model")
    example_env.setenv("LLM_JSON_MODE", "1")
    settings = get_settings()
    assert settings.llm_base_url == "https://example.test/v1"
    assert settings.llm_model == "custom-model"
    assert settings.llm_json_mode
