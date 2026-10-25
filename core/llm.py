"""Клиент LLM и структурированное извлечение в Pydantic-модель — с защитой от типовых сбоев.

Что учтено (по опыту прошлого проекта и обзору практик, docs/04_decisions.md, ADR 020–024):
- предохранитель: после серии сбоев LLM не вызывается какое-то время, агент сразу идёт по правилам;
- короткий таймаут и без повторов на уровне SDK — ждать модель дольше, чем пользователь готов, бессмысленно;
- провайдер отверг response_format (HTTP 400) — повторяем без него и больше его не шлём;
- модель вернула не объект, а «схему со значениями» ({"properties": {...}}) — разворачиваем;
- невалидный JSON — одна попытка ремонта с текстом ошибки, затем пустая модель (агент не падает).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar, get_args, get_origin

from pydantic import BaseModel

from .config import Settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Message = dict[str, str]

_THINK = re.compile(r"<think>.*?</think>", re.S)


class LLM(Protocol):
    def complete(self, messages: list[Message], *, json_mode: bool = False,
                 schema: dict | None = None) -> str: ...


@dataclass
class Breaker:
    """Предохранитель: `threshold` сбоев подряд — пауза `cooldown` секунд, затем одна пробная попытка."""

    threshold: int = 3
    cooldown: float = 30.0
    failures: int = 0
    total_failures: int = 0
    calls: int = 0
    opened_at: float | None = None
    last_error: str = ""
    last_ms: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allow(self) -> bool:
        with self._lock:
            if self.opened_at is None:
                return True
            if time.monotonic() - self.opened_at >= self.cooldown:
                self.opened_at = time.monotonic()
                return True
            return False

    def ok(self, ms: int) -> None:
        with self._lock:
            self.calls += 1
            self.failures, self.opened_at, self.last_ms = 0, None, ms

    def fail(self, exc: BaseException | None = None) -> None:
        with self._lock:
            self.calls += 1
            self.failures += 1
            self.total_failures += 1
            self.last_error = type(exc).__name__ if exc else "invalid"
            if self.failures >= self.threshold:
                if self.opened_at is None:
                    log.warning("LLM: %d сбоя подряд — %d с работаем по правилам", self.failures, self.cooldown)
                self.opened_at = time.monotonic()

    @property
    def state(self) -> str:
        if self.opened_at is not None and time.monotonic() - self.opened_at < self.cooldown:
            return "down"
        return "degraded" if self.failures else "ok"


class OpenAICompatLLM:
    """Любой OpenAI-совместимый API (Cloud.ru, Yandex AI Studio, vLLM, Ollama) по base_url и ключу."""

    def __init__(self, settings: Settings, http_client: Any = None):
        from openai import OpenAI

        self._settings = settings
        self._model = settings.llm_model
        self._json_mode = settings.llm_json_mode
        self._schema_mode = settings.llm_schema_mode
        self._client = OpenAI(base_url=settings.llm_base_url, api_key=self._api_key() or "none",
                              timeout=settings.llm_timeout, max_retries=0, http_client=http_client)
        self.breaker = Breaker()

    def _api_key(self) -> str:
        return self._settings.llm_api_key

    def _before_call(self) -> None:
        """Точка для обновления токена (GigaChat)."""

    def _model_extras(self) -> dict:
        """Особенности семейств моделей: рассуждения gpt-oss съедают лимит токенов, Qwen3 по умолчанию «думает»."""
        name = self._model.lower()
        if "gpt-oss" in name or re.search(r"\bo[134]\b", name):
            return {"extra_body": {"reasoning_effort": self._settings.llm_reasoning_effort}}
        if "qwen3" in name and "instruct" not in name:
            return {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
        return {}

    def complete(self, messages: list[Message], *, json_mode: bool = False, schema: dict | None = None) -> str:
        from openai import BadRequestError

        self._before_call()
        extra: dict = self._model_extras()
        if schema is not None and self._schema_mode:
            extra["response_format"] = {"type": "json_schema",
                                        "json_schema": {"name": "update", "strict": True, "schema": schema}}
        elif json_mode and self._json_mode:
            extra["response_format"] = {"type": "json_object"}
        try:
            resp = self._client.chat.completions.create(model=self._model, messages=messages, temperature=0,
                                                        max_tokens=1500, **extra)
        except BadRequestError as err:
            if "response_format" not in extra and "extra_body" not in extra:
                raise
            log.warning("Провайдер отверг параметры запроса (%s) — повторяю без response_format и extra_body",
                        type(err).__name__)
            self._json_mode = self._schema_mode = False
            resp = self._client.chat.completions.create(model=self._model, messages=messages, temperature=0,
                                                        max_tokens=1500)
        return resp.choices[0].message.content or ""


class GigaChatLLM(OpenAICompatLLM):
    """GigaChat: ключ авторизации обменивается на токен доступа (живёт 30 минут), токен обновляется сам.

    Сертификат API выпущен Минцифры: укажите путь к корневому сертификату в GIGACHAT_VERIFY_SSL
    или (только для разработки) GIGACHAT_VERIFY_SSL=0.
    """

    def __init__(self, settings: Settings):
        import httpx

        verify: bool | str = settings.gigachat_verify_ssl
        verify = {"1": True, "0": False}.get(str(verify), verify)
        self._http = httpx.Client(verify=verify, timeout=settings.llm_timeout)
        self._token, self._expires = "", 0.0
        self._lock = threading.Lock()
        super().__init__(settings, http_client=self._http)

    def _refresh(self) -> None:
        s = self._settings
        resp = self._http.post(s.gigachat_oauth_url, data={"scope": s.gigachat_scope},
                               headers={"Authorization": f"Basic {s.gigachat_auth_key}",
                                        "RqUID": str(uuid.uuid4()), "Accept": "application/json"})
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._expires = body.get("expires_at", 0) / 1000 or time.time() + 25 * 60
        self._client.api_key = self._token

    def _before_call(self) -> None:
        with self._lock:
            if not self._token or time.time() > self._expires - 60:
                self._refresh()


def build_llm(settings: Settings) -> OpenAICompatLLM | None:
    if not settings.llm_enabled:
        return None
    return GigaChatLLM(settings) if settings.llm_provider == "gigachat" else OpenAICompatLLM(settings)


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


def unwrap(data: Any, schema: type[BaseModel]) -> Any:
    """Модель скопировала схему и положила значения в properties или обернула ответ в один ключ."""
    if not isinstance(data, dict):
        return data
    fields = set(schema.model_fields)
    if fields & set(data):
        return data
    for key in ("properties", "update", "result", "data", schema.__name__):
        inner = data.get(key)
        if isinstance(inner, dict) and fields & set(inner):
            return {k: (v.get("value") if isinstance(v, dict) and "value" in v else v) for k, v in inner.items()}
    if len(data) == 1 and isinstance(next(iter(data.values())), dict):
        return unwrap(next(iter(data.values())), schema)
    return data


def _type_name(annotation: Any) -> str:
    args = [a for a in get_args(annotation) if a is not type(None)]
    inner = args[0] if args else annotation
    origin = get_origin(inner)
    if origin is list:
        return "список строк"
    return {int: "целое", float: "число", bool: "true/false", str: "строка"}.get(inner, "дата YYYY-MM-DD")


def schema_hint(schema: type[BaseModel]) -> str:
    """Шаблон ответа: поля с типами и описаниями плюс пример из null — так модели реже копируют саму схему."""
    lines = [f"- {name} ({_type_name(f.annotation)}): {f.description or ''}" for name, f in schema.model_fields.items()]
    template = json.dumps({name: None for name in schema.model_fields}, ensure_ascii=False)
    return "\n".join(lines) + "\nФормат ответа (заполни нужные поля, остальные оставь null):\n" + template


def strict_schema(schema: type[BaseModel]) -> dict:
    """JSON Schema для строгого режима structured outputs: все поля обязательны (null допустим), без лишних."""
    raw = schema.model_json_schema()
    props = {}
    for name, prop in raw.get("properties", {}).items():
        prop = {k: v for k, v in prop.items() if k not in ("title", "default")}
        if "anyOf" in prop:
            prop["anyOf"] = [{k: v for k, v in alt.items() if k != "title"} for alt in prop["anyOf"]]
        props[name] = prop
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def extract(llm: LLM, schema: type[T], messages: list[Message]) -> T:
    """Извлечение с одной попыткой ремонта. При любом сбое — пустая модель (агент не падает)."""
    breaker: Breaker | None = getattr(llm, "breaker", None)
    if breaker is not None and not breaker.allow():
        return schema()
    msgs = list(messages)
    started = time.perf_counter()
    for attempt in range(2):
        try:
            raw = llm.complete(msgs, json_mode=True, schema=strict_schema(schema))
        except Exception as err:
            log.warning("LLM недоступна (%s), извлечение по правилам", type(err).__name__)
            if breaker is not None:
                breaker.fail(err)
            return schema()
        try:
            data = unwrap(json.loads(parse_json_object(raw)), schema)
            result = schema.model_validate(data)
            if breaker is not None:
                breaker.ok(int((time.perf_counter() - started) * 1000))
            return result
        except ValueError as err:  # json.JSONDecodeError и pydantic.ValidationError — подклассы ValueError
            log.warning("Невалидный ответ LLM (попытка %d): %s", attempt + 1, str(err)[:200])
            msgs += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"Ответ невалиден: {str(err)[:300]}. Верни только исправленный JSON-объект."},
            ]
    if breaker is not None:
        breaker.fail()
    return schema()
