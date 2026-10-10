"""Настройки из окружения (.env)."""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_json_mode: bool
    llm_timeout: float
    llm_nlg: bool

    @property
    def llm_enabled(self) -> bool:
        """Без ключа LLM не вызывается: работает только разбор по правилам домена."""
        return bool(self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        llm_base_url=os.getenv("LLM_BASE_URL", "https://foundation-models.api.cloud.ru/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "Qwen/Qwen3-235B-A22B-Instruct-2507"),
        llm_json_mode=os.getenv("LLM_JSON_MODE", "1") == "1",
        llm_timeout=float(os.getenv("LLM_TIMEOUT", "30")),
        llm_nlg=os.getenv("LLM_NLG", "0") == "1",
    )
