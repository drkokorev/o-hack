"""The normal runtime must not quietly start without the configured models."""
import os
import time

import pytest
from fastapi.testclient import TestClient

from apps.web import build_app
from core.config import get_settings


def default_models(monkeypatch):
    monkeypatch.delenv("ODIN_MODE", raising=False)
    get_settings.cache_clear()


def test_missing_gigachat_access_prevents_default_start(monkeypatch):
    default_models(monkeypatch)
    with pytest.raises(RuntimeError, match="языковой модели"):
        build_app()


def test_missing_local_voice_directory_prevents_default_start(monkeypatch, tmp_path):
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "test-key")
    monkeypatch.setenv("VOICE_MODEL_DIR", str(tmp_path / "missing"))
    default_models(monkeypatch)
    with pytest.raises(RuntimeError, match="GigaAM"):
        build_app()


@pytest.mark.parametrize("status,expected", [("ready", 200), ("unavailable", 503)])
def test_default_health_waits_for_voice_model(monkeypatch, tmp_path, status, expected):
    class FakeVoice:
        def __init__(self, model_dir):
            self.model_dir = model_dir
            self.status = "loading"

        def load(self):
            self.status = status

    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "test-key")
    monkeypatch.setenv("VOICE_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr("apps.web.LocalVoice", FakeVoice)
    monkeypatch.setattr("apps.web.build_llm", lambda _settings: object())
    default_models(monkeypatch)
    with TestClient(build_app()) as client:
        for _ in range(50):
            if client.get("/api/voice").json()["status"] == status:
                break
            time.sleep(0.01)
        assert client.get("/api/voice").json()["status"] == status
        assert client.get("/health").status_code == expected


def test_external_private_config_fills_only_missing_model_settings(monkeypatch, tmp_path):
    config = tmp_path / "private.env"
    config.write_text("GIGACHAT_AUTH_KEY=test-only\nLLM_MODEL=other-model\nUNRELATED_VALUE=should-not-load\n", encoding="utf-8")
    monkeypatch.setenv("ODIN_SECRET_ENV_FILE", str(config))
    monkeypatch.setenv("LLM_MODEL", "explicit-model")
    monkeypatch.delenv("UNRELATED_VALUE", raising=False)
    default_models(monkeypatch)
    settings = get_settings()
    assert settings.gigachat_auth_key == "test-only"
    assert settings.llm_model == "explicit-model"
    assert "UNRELATED_VALUE" not in os.environ
    assert "GIGACHAT_AUTH_KEY" not in os.environ


def test_explicit_rules_mode_works_without_models(monkeypatch):
    monkeypatch.setenv("ODIN_MODE", "rules")
    monkeypatch.setenv("ODIN_SECRET_ENV_FILE", "missing-private-file")
    monkeypatch.delenv("VOICE_MODEL_DIR", raising=False)
    get_settings.cache_clear()
    with TestClient(build_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/info").json()["llm"] is None
        assert client.get("/api/voice").json()["backend"] == "browser"


def test_provider_failure_discloses_the_rules_fallback():
    from core.agent import Agent
    from core.llm import Breaker
    from domains.trips.domain import TripsDomain

    class UnavailableLLM:
        breaker = Breaker()

        def complete(self, *_args, **_kwargs):
            raise TimeoutError("simulated failure")

    with TestClient(build_app(Agent(TripsDomain(), UnavailableLLM()))) as client:
        reply = client.post("/api/chat", json={"text": "Хочу в Казань"}).json()
    assert reply["nlu"] == "rules"
    assert "модель временно недоступна" in reply["reply"].lower()
