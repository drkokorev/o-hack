from datetime import date

from core.agent import Agent
from domains.trips.arbiter import arbitrate
from domains.trips.domain import TripsDomain
from domains.trips.state import TripState, TripUpdate

TODAY = date(2026, 10, 28)


def make_agent(llm=None):
    return Agent(TripsDomain(today=lambda: TODAY), llm, nlg=True, today=lambda: TODAY)


def test_flight_only_is_not_a_hotel_search():
    a = make_agent()
    session = a.new_session()
    result = a.handle(session, "Только перелёт из Москвы в Казань 10 декабря 2026 в одну сторону")
    assert session.state.search_scope == "flight_only"
    assert result.payload["kind"] == "flight_results"
    assert "Демонстрационные перелёты" in result.reply
    assert "отель" not in result.reply.lower()


def test_flight_scope_asks_for_missing_direction_without_inventing_return():
    a = make_agent()
    session = a.new_session()
    result = a.handle(session, "Только билеты из Москвы в Казань 10 декабря 2026")
    assert result.payload["field"] == "flight_direction"
    result = a.handle(session, "в одну сторону")
    assert result.payload["kind"] == "flight_results"
    assert "Обратно:" not in result.reply


def test_flight_search_requests_missing_origin_and_round_trip_date():
    a = make_agent()
    session = a.new_session()
    result = a.handle(session, "Только перелёт в Казань")
    assert result.payload["field"] == "origin"
    session = a.new_session()
    result = a.handle(session, "Только перелёт из Москвы в Казань 10 декабря 2026 туда и обратно")
    assert result.payload["field"] == "when"
    assert "обе даты" in result.reply


def test_flight_does_not_promise_prices_for_children_or_purchase():
    a = make_agent()
    session = a.new_session()
    result = a.handle(session, "Только перелёт из Москвы в Казань с 10 по 15 декабря 2026 туда и обратно, 2 взрослых и ребёнок")
    assert result.payload["kind"] == "flight_results"
    assert "Обратно:" in result.reply
    assert "детские тарифы не рассчитаны" in result.reply
    assert "нельзя купить" in result.reply


def test_direct_flight_constraint_does_not_remove_hotel():
    a = make_agent()
    session = a.new_session()
    a.handle(session, "Из Москвы в Сочи 10–15 декабря 2026, двое взрослых, только прямой перелёт")
    assert session.state.search_scope is None
    assert session.state.direct_only is True


def test_operator_tour_is_not_silently_relabelled_as_a_real_tour():
    a = make_agent()
    session = a.new_session()
    result = a.handle(session, "Хочу пакетный тур в Турцию")
    assert session.state.search_scope == "operator_tour"
    assert "туроператоров сейчас не подключены" in result.reply
    result = a.handle(session, "собери самостоятельную поездку")
    assert session.state.search_scope == "trip"
    assert "туроператоров сейчас не подключены" not in result.reply


def test_model_cannot_invent_month_or_year_for_a_quoted_day():
    update, _ = arbitrate(TripState(), "вылет 7 числа", TripUpdate(
        date_from=date(2028, 12, 7), evidence={"date_from": "7 числа"}), TripUpdate())
    assert update.date_from is None


def test_guide_sources_never_prove_current_visa_or_weather():
    domain = TripsDomain(today=lambda: TODAY)
    assert domain._topic_sources("istanbul", "visa", "нужна ли виза") == []
    assert domain._topic_sources("istanbul", "weather", "какая погода") == []


def test_sensitive_and_offer_replies_are_not_freely_rewritten():
    from core.agent import Step
    domain = TripsDomain(today=lambda: TODAY)
    state = TripState(stage="plan", answered_question="visa")
    assert not domain.allow_answer_generation(state, Step("Актуальные требования не проверял."))
    state.answered_question = None
    assert not domain.allow_answer_generation(state, Step("Демо", payload={"kind": "packages"}))


def test_flight_only_through_chat_api_keeps_the_session():
    from fastapi.testclient import TestClient
    from apps.web import build_app

    client = TestClient(build_app(make_agent()))
    first = client.post("/api/chat", json={"text": "Только билеты из Москвы в Казань 10 декабря 2026"})
    assert first.status_code == 200
    data = first.json()
    assert data["payload"]["field"] == "flight_direction"
    second = client.post("/api/chat", json={"session_id": data["session_id"], "text": "в одну сторону"})
    assert second.status_code == 200
    assert second.json()["payload"]["kind"] == "flight_results"
    assert "Демонстрационные перелёты" in second.json()["reply"]
