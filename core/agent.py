"""Цикл обработки реплики: guard → извлечение (LLM, иначе правила) → merge → детерминированный шаг домена."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Protocol

from pydantic import BaseModel

from .guard import looks_like_injection, sanitize
from .llm import LLM, Message, extract, strip_think


@dataclass
class Step:
    reply: str            # детерминированный ответ — всегда безопасно показать
    facts: str = ""       # факты для NLG-перефразирования; пусто — не перефразировать
    payload: Any = None   # данные для UI (карточки отелей, слоты)
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

    def step(self, state: BaseModel) -> Step:
        """Policy домена. Может обновлять служебные поля состояния (предложенные слоты, запись)."""
        ...


@dataclass
class Session:
    state: BaseModel
    history: list[Message] = field(default_factory=list)
    last: Step | None = None
    last_nlu: str = ""  # кто разобрал последнюю реплику: llm | rules | none


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
        session.last = step
        return step

    def _understand(self, session: Session, text: str) -> tuple[BaseModel, str]:
        today = self.today()
        if self.llm is not None:
            messages = self.domain.extraction_messages(
                session.state, session.history[-self.history_messages :], text, today
            )
            update = extract(self.llm, self.domain.update_model, messages)
            if update.model_dump(exclude_none=True):
                return update, "llm"
        rules = getattr(self.domain, "rule_extract", None)
        if rules is not None:
            return rules(session.state, text, today), "rules"
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
