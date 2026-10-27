"""Настройки из окружения (.env)."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


# Корневой сертификат Минцифры (публичный): им подписан API GigaChat, в системных хранилищах его нет
GIGACHAT_CA = Path(__file__).resolve().parent / "certs" / "russian_trusted_root_ca.pem"


def _env(name: str, default: str) -> str:
    """Пустые значения в .env.example означают настройки по умолчанию."""
    return os.getenv(name) or default


@dataclass(frozen=True)
class Settings:
    llm_provider: str          # openai, gigachat или local (локальный OpenAI-совместимый сервер)
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
        """Локальному серверу не нужен облачный ключ; его адрес и модель задаются явно."""
        if self.llm_provider == "gigachat":
            return bool(self.gigachat_auth_key)
        if self.llm_provider == "local":
            return bool(self.llm_base_url and self.llm_model)
        return bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    provider = _env("LLM_PROVIDER", "openai").lower()
    gigachat = provider == "gigachat"
    local = provider == "local"
    return Settings(
        llm_provider=provider,
        llm_base_url=_env("LLM_BASE_URL", "" if local else "https://api.giga.chat/v1" if gigachat
                          else "https://foundation-models.api.cloud.ru/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=_env("LLM_MODEL", "" if local else "GigaChat-2" if gigachat else "Qwen/Qwen3-235B-A22B-Instruct-2507"),
        llm_json_mode=_env("LLM_JSON_MODE", "0" if gigachat else "1") == "1",
        llm_schema_mode=_env("LLM_SCHEMA_MODE", "0") == "1",
        llm_timeout=float(_env("LLM_TIMEOUT", "8")),
        llm_nlg=_env("LLM_NLG", "0") == "1",
        llm_reasoning_effort=_env("LLM_REASONING_EFFORT", "low"),
        gigachat_auth_key=os.getenv("GIGACHAT_AUTH_KEY", ""),
        gigachat_scope=_env("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
        gigachat_oauth_url=_env("GIGACHAT_OAUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"),
        gigachat_verify_ssl=_env("GIGACHAT_VERIFY_SSL", str(GIGACHAT_CA)),
    )
