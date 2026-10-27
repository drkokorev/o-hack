import httpx

from core.config import get_settings
from core.llm import OpenAICompatLLM, build_llm


def test_local_model_does_not_require_a_cloud_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:18080/v1")
    monkeypatch.setenv("LLM_MODEL", "local-model")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_enabled and build_llm(settings) is not None

        def handler(request):
            assert request.url.host == "127.0.0.1"
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "{}"}}]})

        transport = httpx.MockTransport(handler)
        llm = OpenAICompatLLM(settings, http_client=httpx.Client(transport=transport))
        assert llm.complete([{"role": "user", "content": "привет"}]) == "{}"
    finally:
        get_settings.cache_clear()


def test_local_model_is_disabled_until_address_and_name_are_set(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    try:
        assert not get_settings().llm_enabled
    finally:
        get_settings.cache_clear()
