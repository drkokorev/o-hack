"""Типовые сбои понимания и LLM: необратимые действия только по явному согласию, повторы и выдумки модели
отбрасываются, сбои провайдера не ломают разговор."""

import json
from datetime import date

import httpx
import pytest

from core.agent import Agent
from core.config import get_settings
from core.llm import Breaker, OpenAICompatLLM, extract, unwrap
from domains.trips.domain import TripsDomain
from domains.trips.state import TripUpdate
from tests.conftest import FakeLLM

SAT = date(2026, 10, 24)
TO_CART = ("Сочи с 5 по 12 декабря вдвоём", "беру 1 вариант")


def agent(llm=None):
    return Agent(TripsDomain(today=lambda: SAT), llm, today=lambda: SAT)


def session_at(a, *messages):
    s = a.new_session()
    for m in messages:
        a.handle(s, m)
    return s


@pytest.mark.parametrize("text", ["давай подумаем", "да нет, наверное", "ок, а что с визой?", "подожди",
                                  "а дешевле нельзя?", "не уверен", "хм"])
def test_cart_is_not_booked_without_explicit_consent(text):
    a = agent()
    s = session_at(a, *TO_CART)
    assert s.state.stage == "cart"
    a.handle(s, text)
    assert s.state.stage != "booked" and s.state.order is None


@pytest.mark.parametrize("text", ["да, оформляй", "оформляй", "да", "бронируй", "подтверждаю", "ок"])
def test_explicit_consent_books(text):
    a = agent()
    s = session_at(a, *TO_CART)
    a.handle(s, text)
    assert s.state.stage == "booked"


def test_question_about_cancellation_does_not_cancel_and_cancel_needs_confirmation():
    a = agent()
    s = session_at(a, *TO_CART, "да, оформляй")
    step = a.handle(s, "а можно отменить бронь, если планы поменяются?")
    assert s.state.order and "Условия отмены" in step.reply
    step = a.handle(s, "отмени бронь")
    assert s.state.order and s.state.pending == "cancel"
    a.handle(s, "нет")
    assert s.state.order and s.state.stage == "booked"
    a.handle(s, "отмени бронь")
    a.handle(s, "да, отменить")
    assert s.state.order is None


def test_negated_after_sale_request_is_ignored():
    a = agent()
    s = session_at(a, *TO_CART, "да, оформляй")
    a.handle(s, "не хочу ранний заезд")
    assert not s.state.requests


def test_llm_yes_on_garbage_does_not_book():
    a = agent(FakeLLM({"destination": "Сочи", "date_from": "2026-12-05", "date_to": "2026-12-12", "adults": 2},
                      {"pick": 1}, {"confirm": True}))
    s = session_at(a, *TO_CART)
    assert s.state.stage == "cart"
    a.handle(s, "ээ мм ова")
    assert s.state.stage == "cart" and s.state.order is None
    assert any("confirm" in n for n in s.last_notes)


def test_llm_repeating_previous_action_is_dropped():
    a = agent(FakeLLM({"destination": "Сочи", "date_from": "2026-12-05", "date_to": "2026-12-12", "adults": 2},
                      {"shift_days": 2}, {"shift_days": 2, "pick": 1}))
    s = session_at(a, "Сочи с 5 по 12 декабря вдвоём", "на два дня позже")
    assert s.state.date_from == date(2026, 12, 7)
    a.handle(s, "давай первый")
    assert s.state.date_from == date(2026, 12, 7)  # второй сдвиг — повтор модели, не просьба пользователя


def test_llm_hallucinated_fields_are_dropped_and_rules_win_on_numbers():
    a = agent(FakeLLM({"destination": "Сочи", "pets": True, "budget_total": 50000, "date_from": "2026-12-05",
                       "date_to": "2026-12-12"}))
    s = session_at(a, "Сочи с 5 по 12 декабря, бюджет 150 тысяч")
    assert s.state.pets is None
    assert s.state.budget_total == 150_000
    assert any("pets" in n for n in s.last_notes) and any("budget_total" in n for n in s.last_notes)


def test_schema_shaped_answer_is_unwrapped():
    llm = FakeLLM({"properties": {"destination": "Казань", "nights": 3}})
    update = extract(llm, TripUpdate, [])
    assert update.destination == "Казань" and update.nights == 3
    assert unwrap({"TripUpdate": {"pick": 2}}, TripUpdate) == {"pick": 2}


def test_breaker_skips_llm_after_failures_and_dialog_continues():
    llm = FakeLLM(TimeoutError(), TimeoutError(), TimeoutError(), {"destination": "Сочи"})
    llm.breaker = Breaker(threshold=3, cooldown=60)
    a = agent(llm)
    s = a.new_session()
    for text in ("Сочи с 5 по 12 декабря", "вдвоём", "беру 1 вариант"):
        a.handle(s, text)
    assert s.last_nlu == "rules" and s.state.stage == "cart"
    calls = len(llm.calls)
    a.handle(s, "да, оформляй")
    assert len(llm.calls) == calls and s.state.stage == "booked"  # предохранитель: модель не звали


def test_provider_rejecting_response_format_falls_back(monkeypatch):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append("response_format" in body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format is not supported"}})
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": '{"destination": "Сочи"}'}}]})

    monkeypatch.setenv("LLM_API_KEY", "test")
    get_settings.cache_clear()
    try:
        llm = OpenAICompatLLM(get_settings(), http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        assert extract(llm, TripUpdate, [{"role": "user", "content": "Сочи"}]).destination == "Сочи"
        assert extract(llm, TripUpdate, [{"role": "user", "content": "Сочи"}]).destination == "Сочи"
        assert seen == [True, False, False]  # после отказа больше не шлём response_format
    finally:
        get_settings.cache_clear()
