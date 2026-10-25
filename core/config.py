"""Настройки из окружения (.env)."""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    llm_provider: str          # openai — любой OpenAI-совместимый API; gigachat — GigaChat с OAuth-токеном
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_json_mode: bool
    llm_schema_mode: bool      # строгая JSON-схема (structured outputs), если провайдер умеет
    llm_timeout: float
    llm_nlg: bool
    llm_reasoning_effort: str  # для рассуждающих моделей (gpt-oss): low — быстрее и дешевле
    gigachat_auth_key: str
    gigachat_scope: str
    gigachat_oauth_url: str
    gigachat_verify_ssl: str   # "1", "0" или путь к файлу корневого сертификата

    @property
    def llm_enabled(self) -> bool:
        """Без ключа LLM не вызывается: работает только разбор по правилам домена."""
        if self.llm_provider == "gigachat":
            return bool(self.gigachat_auth_key)
        return bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    gigachat = provider == "gigachat"
    return Settings(
        llm_provider=provider,
        llm_base_url=os.getenv("LLM_BASE_URL", "https://gigachat.devices.sberbank.ru/api/v1" if gigachat
                               else "https://foundation-models.api.cloud.ru/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "GigaChat-2" if gigachat else "Qwen/Qwen3-235B-A22B-Instruct-2507"),
        llm_json_mode=os.getenv("LLM_JSON_MODE", "0" if gigachat else "1") == "1",
        llm_schema_mode=os.getenv("LLM_SCHEMA_MODE", "0") == "1",
        llm_timeout=float(os.getenv("LLM_TIMEOUT", "8")),
        llm_nlg=os.getenv("LLM_NLG", "0") == "1",
        llm_reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "low"),
        gigachat_auth_key=os.getenv("GIGACHAT_AUTH_KEY", ""),
        gigachat_scope=os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
        gigachat_oauth_url=os.getenv("GIGACHAT_OAUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"),
        gigachat_verify_ssl=os.getenv("GIGACHAT_VERIFY_SSL", "1"),
    )
