"""Цикл обработки реплики: guard → извлечение (LLM, иначе правила) → merge → детерминированный шаг домена."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Callable, Protocol

from pydantic import BaseModel

from .guard import (MAX_INPUT_CHARS, contains_unresolved_sensitive_data, looks_like_injection,
                    mask_basic_data, mask_sensitive_data, sanitize)
from .answer import compose
from .llm import LLM, Message, extract
from .privacy import PrivacyFilteredLLM, Vault

log = logging.getLogger(__name__)


@dataclass
class Step:
    reply: str            # детерминированный ответ — всегда безопасно показать
    facts: str = ""       # факты для NLG-перефразирования; пусто — не перефразировать
    payload: Any = None   # данные для UI (карточки отелей)
    done: bool = False    # сценарий завершён (например, запись создана)
    sources: list[dict] = field(default_factory=list)  # фрагменты базы знаний (RAG) для ответа: text, cite, url


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
    ui_previous: Any = field(default=None, repr=False, compare=False)
    ui_revision: int = 0
    location_checked: bool = False  # один приблизительный результат на сессию, без хранения IP
    vault: Vault = field(default_factory=Vault, repr=False, compare=False)  # метки ↔ личные данные, только в памяти
    last_answer_by: str = ""  # кто написал последний ответ: llm (прошёл проверку) | template
    lock: Any = field(default_factory=threading.RLock, repr=False, compare=False)


PRIVACY_NOTICE = "Обнаруженные личные данные не использую для подбора. "
_PRIVACY_PLACEHOLDER = re.compile(r"\[(?:имя|почта|телефон|контакт|номер карты|счёт|паспорт|документ|дата рождения|секрет|адрес|адрес сети|номер клиента|номер брони|сведения о здоровье)(?:_\d+)?\]")
_PRIVACY_FILLER = re.compile(
    r"\b(?:мой|моя|моё|мое|наш|наша|телефон|номер|контакт|почта|паспорт|карта|"
    r"адрес|сведения|отправьте|отправить|пожалуйста|мне|на|для|это|вот|меня|зовут|я|фио|фамилия|имя)\b", re.IGNORECASE
)


def _privacy_only(text: str) -> bool:
    """Не отправляем модели сообщение, в котором остался только контакт/документ."""
    remainder = _PRIVACY_FILLER.sub(" ", _PRIVACY_PLACEHOLDER.sub(" ", text))
    return not bool(re.search(r"[\w]", remainder))


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
        self.llm = PrivacyFilteredLLM(llm, getattr(domain, "preserve_place", None)) if llm else None
        if hasattr(domain, "attach_llm"):
            domain.attach_llm(self.llm)  # домен может спросить модель сам (например, где достопримечательность)
        self.nlg = nlg
        self.today = today
        self.history_messages = history_messages

    def new_session(self) -> Session:
        return Session(state=self.domain.state_model())

    def handle(self, session: Session, text: str, *, after_merge: Callable[[BaseModel], None] | None = None) -> Step:
        # Reject instead of truncating: a document/card number cut at the limit
        # could otherwise evade inspection and be sent partially to the model.
        if len(text) > MAX_INPUT_CHARS:
            session.last_nlu, session.last_notes = "none", []
            return Step(f"Сообщение слишком длинное. Сократите его до {MAX_INPUT_CHARS} символов и отправьте снова.")
        privacy_unavailable = False
        try:
            text, masked = mask_sensitive_data(text, getattr(self.domain, "preserve_place", None), session.vault)
        except Exception as err:
            log.warning("Не удалось обработать сообщение для защиты данных (%s)", type(err).__name__)
            # If the full local detector fails, use rules only. Never forward
            # the uninspected text to the model as a fallback.
            privacy_unavailable = True
            try:
                text, masked = mask_basic_data(text, session.vault)
            except Exception:
                session.last_nlu, session.last_notes = "none", []
                return Step("Не удалось обработать сообщение. Попробуйте ещё раз.")
        text = sanitize(text)
        if not text:
            session.last_nlu, session.last_notes = "none", []
            return Step((PRIVACY_NOTICE if masked else "") + "Расскажите, какую поездку вы хотите.")
        if masked and _privacy_only(text):
            session.last_nlu, session.last_notes = "none", []
            previous = session.last
            if previous and isinstance(previous.payload, dict) and previous.payload.get("kind") == "question":
                return replace(previous, reply=PRIVACY_NOTICE + previous.reply)
            return Step(PRIVACY_NOTICE + "Расскажите, какую поездку вы хотите.")
        if looks_like_injection(text):
            session.last_nlu, session.last_notes = "none", []
            return Step(self.domain.off_topic_reply)
        unresolved = contains_unresolved_sensitive_data(text)
        context_risk = getattr(self.domain, "contains_unresolved_context", None)
        if context_risk is not None:
            try:
                unresolved = unresolved or context_risk(session.state)
            except Exception as err:
                log.warning("Не удалось проверить контекст для защиты данных (%s)", type(err).__name__)
                privacy_unavailable = True
        update, session.last_nlu = self._understand(session, text, use_llm=not (privacy_unavailable or unresolved))
        if not update.model_dump(exclude_none=True) and session.last is not None and after_merge is None:
            # A message with no understood action must not advance the
            # conversation, skip a pending question, or modify an order.
            previous = session.last
            question = isinstance(previous.payload, dict) and previous.payload.get("kind") == "question"
            previous_reply = previous.reply
            while previous_reply.startswith("Не понял сообщение. "):
                previous_reply = previous_reply.removeprefix("Не понял сообщение. ")
            step = Step("Не понял сообщение. " + (previous_reply if question else
                        "Расскажите о поездке или уточните, что хотите изменить."), payload=previous.payload)
        else:
            # An exact, server-validated map selection is an action even when
            # the already selected city adds no new natural-language fields.
            session.state = self.domain.merge(session.state, update)
            note_text = getattr(self.domain, "note_text", None)
            if note_text is not None:  # домену — замаскированный текст реплики, например для поиска по базе знаний
                note_text(session.state, text)
            if after_merge is not None:
                after_merge(session.state)
            step = self.domain.step(session.state)
            session.last_answer_by = "template"
            can_compose = getattr(self.domain, "allow_answer_generation", lambda _state, _step: True)
            if (not (privacy_unavailable or unresolved) and self.nlg and getattr(self.domain, "allow_nlg", True)
                    and can_compose(session.state, step)):
                step = self._compose(session, text, step)
        if self.history_messages > 0 and getattr(self.domain, "retain_history", True):
            session.history += [
                {"role": "user", "content": text},
                {"role": "assistant", "content": step.reply},
            ]
            session.history = session.history[-self.history_messages:]
        else:
            session.history = []
        session.last = step
        # Keep the notice out of the conversation state so it is not repeated
        # when a later unclear message resumes the pending question.
        notice = PRIVACY_NOTICE if masked else ""
        if privacy_unavailable:
            notice += "Сейчас использую локальный разбор; могу уточнить детали поездки. "
        elif unresolved:
            notice += "Для защиты данных обработаю это сообщение локально; могу уточнить детали поездки. "
        # Имена возвращаются только в показ пользователю; в истории и у модели остаются метки
        reply = session.vault.restore(notice + step.reply)
        return step if reply == step.reply else replace(step, reply=reply)

    def _understand(self, session: Session, text: str, *, use_llm: bool = True) -> tuple[BaseModel, str]:
        """LLM — основной путь; домен сверяет её ответ с текстом и правилами, правила заменяют её при сбое."""
        today = self.today()
        session.last_notes = []
        rules = getattr(self.domain, "rule_extract", None)
        by_rules = rules(session.state, text, today) if rules is not None else None
        # Structured answers to an explicit pending question are already
        # validated locally; avoid sending room allocations or retrying an LLM
        # that cannot authoritatively change these service fields.
        pending_fields = {
            "room_allocation": {"room_allocations", "rooms"}, "children_ages": {"children_ages"},
            "split_stays": {"split_stays"}, "split_choice": {"split_choice"},
            "multi_hotel": {"search_scope"}, "flight_direction": {"flight_direction"},
            "transfer_direction": {"transfer_direction"}, "transfer_time": {"transfer_time"},
        }
        pending = getattr(session.state, "pending_question", None)
        if by_rules is not None and pending in pending_fields:
            values = by_rules.model_dump(exclude_none=True)
            if set(values) & pending_fields[pending]:
                return by_rules, "rules"
        if self.llm is not None and use_llm:
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

    def _compose(self, session: Session, text: str, step: Step) -> Step:
        """Ответ пишет LLM по фактам шага и фрагментам RAG; не прошёл проверку — остаётся шаблон."""
        if self.llm is None or not step.reply:
            return step
        known = {token for token in re.findall(r"\[[а-яё ]+_\d+\]", text) if session.vault.known(token)}
        result = compose(self.llm, text, step.facts or step.reply, step.reply, step.sources, known)
        session.last_answer_by = result.by
        if result.problems:
            session.last_notes = session.last_notes + ["ответ: " + "; ".join(result.problems)]
        if result.by != "llm":
            return step
        cites = list(dict.fromkeys(s["cite"] for s in step.sources if s.get("cite")))
        reply = result.text + ("\n\nИсточник: " + "; ".join(cites) + " (CC BY-SA)" if cites else "")
        return replace(step, reply=reply)
