"""OpenAI-совместимый клиент и структурированное извлечение в Pydantic-модель."""

from __future__ import annotations

import json
import logging
import re
from typing import Protocol, TypeVar

from pydantic import BaseModel

from .config import Settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Message = dict[str, str]

_THINK = re.compile(r"<think>.*?</think>", re.S)


class LLM(Protocol):
    def complete(self, messages: list[Message], *, json_mode: bool = False) -> str: ...


class OpenAICompatLLM:
    """Cloud.ru Foundation Models, vLLM, Ollama, OpenRouter — всё через base_url."""

    def __init__(self, settings: Settings):
        from openai import OpenAI

        self._client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "none",
            timeout=settings.llm_timeout,
            max_retries=1,
        )
        self._model = settings.llm_model
        self._json_mode = settings.llm_json_mode

    def complete(self, messages: list[Message], *, json_mode: bool = False) -> str:
        extra = {"response_format": {"type": "json_object"}} if json_mode and self._json_mode else {}
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages, temperature=0.1, **extra
        )
        return resp.choices[0].message.content or ""


def strip_think(text: str) -> str:
    """Убирает рассуждения reasoning-моделей (<think>…</think>)."""
    return _THINK.sub("", text).strip()


def parse_json_object(raw: str) -> str:
    """Вырезает JSON-объект из ответа: модели любят обрамлять его ```json и пояснениями."""
    text = strip_think(raw)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("в ответе нет JSON-объекта")
    return text[start : end + 1]


def schema_hint(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), ensure_ascii=False)


def extract(llm: LLM, schema: type[T], messages: list[Message]) -> T:
    """Извлечение с одной попыткой ремонта. При любом сбое — пустая модель (бот не падает)."""
    msgs = list(messages)
    for _ in range(2):
        try:
            raw = llm.complete(msgs, json_mode=True)
        except Exception:
            log.exception("LLM недоступна, извлечение пропущено")
            return schema()
        try:
            return schema.model_validate_json(parse_json_object(raw))
        except ValueError as err:  # pydantic.ValidationError — подкласс ValueError
            log.warning("Невалидный JSON от LLM: %s", err)
            msgs += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"Ответ невалиден: {err}. Верни только исправленный JSON-объект."},
            ]
    return schema()

