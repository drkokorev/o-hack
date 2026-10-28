"""Conversation and privacy regressions found during a separate review."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from apps.web import build_app
from core.agent import Agent
from domains.trips.arbiter import arbitrate
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate
from tests.conftest import FakeLLM


TODAY = date(2026, 10, 28)


def agent(llm=None):
    return Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY)


@pytest.mark.parametrize("question, key", [
    ("А можно будет отменить бронь?", "отмен"),
    ("Нужна ли виза?", "виз"),
    ("Какие условия с багажом?", "багаж"),
    ("Можно ли с собакой?", "животн"),
])
def test_side_question_is_answered_and_pending_question_is_preserved(question, key):
    a = agent()
    session = a.new_session()
    a.handle(session, "Хочу в Казань")
    result = a.handle(session, question)
    assert key in result.reply.lower()
    assert session.state.pending_question == "when"
    assert "when" not in session.state.skipped_questions
    assert result.reply.count("?") <= 1
    assert session.state.free_cancellation is None
    assert session.state.baggage is None and session.state.pets is None
    a.handle(session, "в июне")
    assert session.state.month == 6 and session.state.pending_question == "duration"


def test_weather_can_be_answered_before_all_trip_details_are_known():
    a = agent()
    session = a.new_session()
    a.handle(session, "Хочу в Сочи в июне")
    response = a.handle(session, "Какая там погода?")
    assert "средн" in response.reply.lower() and "прогноз" in response.reply.lower()
    assert session.state.pending_question == "duration"


def test_unrelated_new_details_do_not_mean_the_user_does_not_know_the_answer():
    a = agent()
    session = a.new_session()
    a.handle(session, "Хочу в Сочи на 7 ночей")
    response = a.handle(session, "из Москвы")
    assert session.state.origin == "Москва"
    assert "when" not in session.state.skipped_questions
    assert session.state.pending_question == "when"
    assert "когда" in response.reply.lower()


def test_question_does_not_add_cancellation_or_baggage_requirement():
    state = TripState()
    assert rule_extract(state, "Можно отменить бронь?", TODAY).free_cancellation is None
    assert rule_extract(state, "Какие условия с багажом?", TODAY).baggage is None
    assert rule_extract(state, "Нужен багаж и бесплатная отмена", TODAY).baggage is True
    assert rule_extract(state, "Нужен багаж и бесплатная отмена", TODAY).free_cancellation is True


@pytest.mark.parametrize("question, field", [
    ("Какие условия с багажом?", "baggage"),
    ("Можно отменить бронь?", "free_cancellation"),
])
def test_model_cannot_turn_a_question_into_a_preference(question, field):
    state = TripState()
    llm = TripUpdate.model_validate({field: True})
    result, _ = arbitrate(state, question, llm, rule_extract(state, question, TODAY))
    assert getattr(result, field) is None


def test_travel_question_describes_travel_not_an_unrelated_pet_policy():
    a = agent()
    session = a.new_session()
    a.handle(session, "Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых")
    response = a.handle(session, "Сколько ехать?")
    assert "в пути" in response.reply.lower() and "демо" in response.reply.lower()
    assert "животн" not in response.reply.lower()


@pytest.mark.parametrize("question, keyword", [
    ("Завтрак включён?", "питан"),
    ("Есть ли бассейн?", "бассейн"),
    ("Бассейн и парковка есть?", "парковк"),
    ("бассейн есть", "бассейн"),
    ("вайфай есть", "wi-fi"),
])
def test_hotel_question_is_answered_without_changing_preferences(question, keyword):
    a = agent()
    session = a.new_session()
    a.handle(session, "Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых")
    before = (session.state.meal, session.state.hotel_wishes)
    response = a.handle(session, question)
    assert (session.state.meal, session.state.hotel_wishes) == before
    assert keyword in response.reply.lower() and "демонстрацион" in response.reply.lower()


def test_preference_and_separate_question_in_one_message_are_distinguished():
    result = rule_extract(TripState(), "Нужен завтрак, а бассейн есть?", TODAY)
    assert result.meal == "breakfast" and not result.hotel_wishes
    assert result.question == "amenities:pool"


def test_hotel_preference_is_not_treated_as_a_question_without_punctuation():
    result = rule_extract(TripState(), "Нужен отель где есть бассейн и вайфай", TODAY)
    assert set(result.hotel_wishes or []) == {"pool", "wifi"}
    assert not result.question


def test_multiple_questions_are_both_answered_without_creating_filters():
    a = agent()
    session = a.new_session()
    a.handle(session, "Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых")
    response = a.handle(session, "Завтрак и бассейн есть?")
    assert "питан" in response.reply.lower() and "бассейн" in response.reply.lower()
    assert session.state.meal is None and not session.state.hotel_wishes
    assert response.reply.count("?") <= 1


def test_multiple_questions_before_dates_preserve_only_one_pending_question():
    a = agent()
    session = a.new_session()
    a.handle(session, "Хочу в Казань")
    response = a.handle(session, "Можно отменить и какие условия с багажом?")
    assert "отмен" in response.reply.lower() and "багаж" in response.reply.lower()
    assert session.state.pending_question == "when" and response.reply.count("?") <= 1
    assert session.state.free_cancellation is None and session.state.baggage is None


@pytest.mark.parametrize("number", [("одним", 1), ("двумя", 2), ("тремя", 3)])
def test_inflected_children_count_is_extracted_without_guessing(number):
    word, count = number
    update = rule_extract(TripState(), f"Едем с {word} детьми" if count > 1 else "Едем с одним ребёнком", TODAY)
    assert update.children == count


def test_known_total_and_child_count_complete_the_group_without_extra_question():
    a = agent()
    session = a.new_session()
    a.handle(session, "В Сочи с 10 по 15 июня 2027 из Москвы на двоих")
    response = a.handle(session, "с одним ребёнком")
    assert session.state.adults == 1 and session.state.children == 1
    assert response.payload["kind"] == "packages"


def test_unspecified_children_are_an_explicit_calculation_assumption():
    a = agent()
    session = a.new_session()
    response = a.handle(session, "Из Москвы в Казань с 10 по 15 июня 2027 двое взрослых")
    assert session.state.children is None
    assert "без детей" in response.reply.lower()


@pytest.mark.parametrize("private_text", [
    "Паспорт серия 1234 номер 567890",
    "Контакт: synthetic\u200b@example.com",
    "Мой номер +7\u200b 900 000-00-00",
    "Меня зовут Тестовый Иван Иванович",
    "Дата рождения 12.02.1980",
    "СНИЛС 123-456-789 01",
    "Мой адрес: улица Примерная, 1",
    "API key: synthetic-example-value",
    "CVV: 123",
])
def test_sensitive_input_does_not_reach_model_or_session(private_text):
    llm = FakeLLM({})
    a = agent(llm)
    session = a.new_session()
    response = a.handle(session, private_text)
    assert not llm.calls
    assert private_text not in repr(session.history)
    assert "данн" in response.reply.lower()


def test_overlong_input_is_rejected_without_forwarding_a_truncated_secret():
    llm = FakeLLM({})
    a = agent(llm)
    response = a.handle(a.new_session(), "а" * 995 + " 4111 1111 1111 1111")
    assert not llm.calls
    assert "сообщен" in response.reply.lower()


def test_rejected_input_does_not_replace_last_actionable_question():
    a = agent()
    session = a.new_session()
    original = a.handle(session, "Хочу в Казань")
    a.handle(session, "Мой телефон +7 900 000-00-00")
    assert session.last is original
    unclear = a.handle(session, "ыщшфл")
    assert "когда" in unclear.reply.lower() and session.state.pending_question == "when"


def test_question_during_payment_does_not_change_or_confirm_order():
    a = agent()
    session = a.new_session()
    for text in ("Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых",
                 "беру 1 вариант", "да, оформляй", "оплата СБП"):
        a.handle(session, text)
    answer = a.handle(session, "Какие условия отмены?")
    assert session.state.stage == "payment" and session.state.order is None
    assert "отмен" in answer.reply.lower() and "демонстрационный заказ" in answer.reply.lower()


def test_questions_do_not_erase_a_pending_cancellation():
    a = agent()
    session = a.new_session()
    for text in ("Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых", "беру 1 вариант",
                 "да, оформляй", "оплата СБП", "да, подтверждаю", "отмени бронь"):
        a.handle(session, text)
    assert session.state.order and session.state.pending == "cancel"
    answer = a.handle(session, "Какие условия отмены?")
    assert "отмен" in answer.reply.lower()
    assert session.state.order and session.state.pending == "cancel"
    a.handle(session, "нет")
    assert session.state.order and session.state.pending is None


def test_tent_trip_answers_question_without_adding_a_hotel():
    a = agent()
    session = a.new_session()
    a.handle(session, "Из Москвы в Казань с 10 по 15 июня 2027 двое взрослых с палаткой")
    answer = a.handle(session, "Сколько ехать?")
    assert "время в пути" in answer.reply.lower() and "демо" in answer.reply.lower()
    assert session.state.lodging == "tent" and answer.payload["kind"] == "tent_transport"
    assert not session.state.order


def test_model_receives_structured_context_without_past_free_text():
    llm = FakeLLM({}, {})
    a = agent(llm)
    session = a.new_session()
    a.handle(session, "Хочу в Казань, заметка-УникальныйМаркер")
    a.handle(session, "в июне")
    sent = str(llm.calls[-1])
    assert "УникальныйМаркер" not in sent
    assert "Казань" in sent and "when" in sent


def test_http_flow_preserves_context_after_rejecting_sensitive_input():
    llm = FakeLLM({}, {})
    client = TestClient(build_app(agent(llm)))
    first = client.post("/api/chat", json={"text": "Хочу в Казань"}).json()
    blocked = client.post("/api/chat", json={"text": "Мой телефон +7 900 000-00-00", "session_id": first["session_id"]})
    assert blocked.headers["cache-control"] == "no-store"
    assert "+7 900" not in blocked.text and len(llm.calls) == 1
    resumed = client.post("/api/chat", json={"text": "в июне", "session_id": first["session_id"]}).json()
    assert resumed["session_id"] == first["session_id"] and "ноч" in resumed["reply"].lower()
    assert "+7 900" not in str(llm.calls)


def test_answer_precedes_plan_when_one_turn_changes_preferences_and_asks():
    a = agent()
    session = a.new_session()
    a.handle(session, "Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых")
    response = a.handle(session, "Нужен завтрак, а парковка есть?")
    assert session.state.meal == "breakfast" and not session.state.hotel_wishes
    assert "парковк" in response.reply.split("\n\n", 1)[0].lower()
    assert response.payload["kind"] == "packages"


def test_requested_baggage_is_applied_to_both_flight_legs_and_can_be_removed():
    a = agent()
    session = a.new_session()
    plan = a.handle(session, "Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых, самолётом, нужен багаж")
    assert session.state.baggage is True and plan.payload["kind"] == "packages"
    assert all(item[direction]["mode"] == "plane" and item[direction]["baggage"]
               for item in plan.payload["items"] for direction in ("out", "back"))
    a.handle(session, "багаж не нужен")
    assert session.state.baggage is False


def test_train_baggage_is_not_claimed_as_verified():
    a = agent()
    session = a.new_session()
    plan = a.handle(session, "Из Москвы в Казань с 10 по 15 июня 2027 двое взрослых, поездом, нужен багаж")
    assert session.state.baggage is True and plan.payload["kind"] == "packages"
    assert "нормы багажа" in plan.reply.lower() and "не проверены" in plan.reply.lower()


def test_tent_routes_respect_baggage_requirement():
    a = agent()
    session = a.new_session()
    plan = a.handle(session, "Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых, самолётом с палаткой и багажом")
    assert session.state.baggage is True and plan.payload["kind"] == "tent_transport"
    assert all(item[direction]["baggage"] for item in plan.payload["items"] for direction in ("out", "back"))


def test_priced_ideas_do_not_silently_relax_hotel_or_travel_requirements():
    from domains.trips.geo import BY_ID, ORIGIN_BY_NAME
    from domains.trips.inspire import estimate

    args = (ORIGIN_BY_NAME["Москва"], BY_ID["sochi"], date(2027, 6, 10), 5, 2, 0)
    assert estimate(*args) is not None
    assert estimate(*args, max_hours=0.1) is None
    # No demo hotel has this invented amenity; returning a price after silently
    # relaxing it would misrepresent the user's requested conditions.
    assert estimate(*args, wishes=["test_only_unavailable_amenity"]) is None


@pytest.mark.parametrize("destination,start,end", [
    ("sochi", date(2027, 6, 10), date(2027, 6, 15)),
    ("kazan", date(2027, 6, 28), date(2027, 7, 3)),
])
def test_nightly_budget_checks_demo_price_for_each_night_and_labels_relaxation(destination, start, end):
    from domains.trips.geo import BY_ID, ORIGIN_BY_NAME
    from domains.trips.offers import hotel_price
    from domains.trips.planner import Trip, candidate_hotels

    trip = Trip(ORIGIN_BY_NAME["Москва"], BY_ID[destination], start, end,
                2, 0, budget_night=10_000)
    hotels, relaxed = candidate_hotels(trip)
    assert hotels and not relaxed
    assert all(hotel_price(hotel, trip.date_in + timedelta(days=day), 1, trip.adults, trip.children) <= trip.budget_night
               for hotel, _ in hotels for day in range(trip.nights))
    trip.budget_night = 1
    _, relaxed = candidate_hotels(trip)
    assert any("снял ограничение цены за ночь" in note for note in relaxed)
