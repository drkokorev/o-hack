"""Цикл обработки реплики: guard → извлечение (LLM, иначе правила) → merge → детерминированный шаг домена."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Protocol

from pydantic import BaseModel

from .guard import contains_sensitive_data, looks_like_injection, sanitize
from .llm import LLM, Message, extract, strip_think

log = logging.getLogger(__name__)


@dataclass
class Step:
    reply: str            # детерминированный ответ — всегда безопасно показать
    facts: str = ""       # факты для NLG-перефразирования; пусто — не перефразировать
    payload: Any = None   # данные для UI (карточки отелей)
    done: bool = False    # сценарий завершён (например, запись создана)


class Domain(Protocol):
    # Свойства только для чтения: так протокол принимает конкретные подклассы BaseModel
    @property
    def name(self) -> str: ...
    @property
    def state_model(self) -> type[BaseModel]: ...
    @property
    def update_model(self) -> type[BaseModel]: ...
    @property
    def off_topic_reply(self) -> str: ...

    def extraction_messages(
        self, state: BaseModel, history: list[Message], text: str, today: date
    ) -> list[Message]: ...

    def merge(self, state: BaseModel, update: BaseModel) -> BaseModel: ...

    # Необязательно: def rule_extract(self, state, text, today) -> update_model
    # Детерминированный разбор — fallback, когда LLM нет, она упала или ничего не извлекла.
    # Необязательно: def arbitrate(self, state, text, llm_update, rule_update) -> (update, notes)
    # Сверка ответа LLM с текстом и правилами: что принять, что отбросить и почему.

    def step(self, state: BaseModel) -> Step:
        """Policy домена. Может обновлять служебные поля состояния (предложенные слоты, запись)."""
        ...


@dataclass
class Session:
    state: BaseModel
    history: list[Message] = field(default_factory=list)
    last: Step | None = None
    last_nlu: str = ""  # кто разобрал последнюю реплику: llm | llm+rules | rules | none
    last_notes: list[str] = field(default_factory=list)  # что отброшено из ответа LLM и почему


NLG_SYSTEM = (
    "Перефразируй черновик ответа ассистента дружелюбно и кратко, на русском языке. "
    "Используй только факты из черновика и блока фактов: ничего не добавляй, "
    "не меняй цифры, даты, время и названия, сохрани нумерацию вариантов."
)


class Agent:
    def __init__(
        self,
        domain: Domain,
        llm: LLM | None,
        *,
        nlg: bool = False,
        today: Callable[[], date] = date.today,
        history_messages: int = 6,
    ):
        self.domain = domain
        self.llm = llm
        self.nlg = nlg
        self.today = today
        self.history_messages = history_messages

    def new_session(self) -> Session:
        return Session(state=self.domain.state_model())

    def handle(self, session: Session, text: str) -> Step:
        text = sanitize(text)
        if not text:
            step = Step("Напишите, пожалуйста, ваш запрос.")
        elif contains_sensitive_data(text):
            text = "[личные данные скрыты]"
            session.last_nlu, session.last_notes = "none", []
            step = Step("Для демонстрации не вводите личные и платёжные данные. Удалите их из сообщения и повторите запрос.")
        elif looks_like_injection(text):
            step = Step(self.domain.off_topic_reply)
        else:
            update, session.last_nlu = self._understand(session, text)
            session.state = self.domain.merge(session.state, update)
            step = self.domain.step(session.state)
            if self.nlg and step.facts:
                step.reply = self._rephrase(step)
        session.history += [
            {"role": "user", "content": text},
            {"role": "assistant", "content": step.reply},
        ]
        session.history = session.history[-self.history_messages:] if self.history_messages > 0 else []
        session.last = step
        return step

    def _understand(self, session: Session, text: str) -> tuple[BaseModel, str]:
        """LLM — основной путь; домен сверяет её ответ с текстом и правилами, правила заменяют её при сбое."""
        today = self.today()
        session.last_notes = []
        rules = getattr(self.domain, "rule_extract", None)
        by_rules = rules(session.state, text, today) if rules is not None else None
        if self.llm is not None:
            messages = self.domain.extraction_messages(
                session.state, session.history[-self.history_messages :], text, today
            )
            update = extract(self.llm, self.domain.update_model, messages)
            if update.model_dump(exclude_none=True):
                arbitrate = getattr(self.domain, "arbitrate", None)
                if arbitrate is not None and by_rules is not None:
                    update, session.last_notes = arbitrate(session.state, text, update, by_rules)
                    if session.last_notes:
                        log.info("Сверка LLM: отклонено или исправлено полей: %d", len(session.last_notes))
                    return update, "llm+rules" if by_rules.model_dump(exclude_none=True) else "llm"
                if by_rules is None:
                    return update, "llm"
                gaps = {k: v for k, v in by_rules.model_dump(exclude_none=True).items()
                        if getattr(update, k) is None}
                return (update.model_copy(update=gaps), "llm+rules") if gaps else (update, "llm")
        if by_rules is not None and by_rules.model_dump(exclude_none=True):
            return by_rules, "rules"
        return self.domain.update_model(), "none"

    def _rephrase(self, step: Step) -> str:
        if self.llm is None:
            return step.reply
        messages = [
            {"role": "system", "content": NLG_SYSTEM},
            {"role": "user", "content": f"Факты:\n{step.facts}\n\nЧерновик ответа:\n{step.reply}"},
        ]
        try:
            return strip_think(self.llm.complete(messages)) or step.reply
        except Exception:
            return step.reply
