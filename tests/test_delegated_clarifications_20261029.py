from datetime import date

import pytest

from core.agent import Agent
from apps.web import contextual_suggestions
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID
from domains.trips.rules import rule_extract
from domains.trips.arbiter import arbitrate
from domains.trips.state import TripState, TripUpdate
from tests.conftest import FakeLLM


TODAY = date(2026, 10, 29)


def make_agent():
    return Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY, nlg=False)


@pytest.mark.parametrize("reply", [
    "предложи сам", "Предложите сами", "сам предложи", "ну тогда подбери сам",
    "на твое усмотрение", "как посоветуешь", "давай пока без дат", "you choose",
])
def test_delegating_the_time_question_gives_unpriced_ideas(reply):
    agent = make_agent()
    session = agent.new_session()
    first = agent.handle(session, "Хочу в горы, красивый вид и спокойные прогулки. Предложи направления.")
    assert session.state.pending_question == "when" and first.payload["kind"] == "question"
    result = agent.handle(session, reply)
    assert result.payload["kind"] == "ideas" and result.payload["items"]
    assert all("mountains" in BY_ID[item["id"]].tags for item in result.payload["items"])
    assert session.state.date_from is None and session.state.month is None and session.state.nights is None
    assert "не понял" not in result.reply.lower() and "цены" in result.reply.lower()
    assert session.state.order is None


def test_repeated_delegation_does_not_reenter_clarification_loop():
    agent = make_agent()
    session = agent.new_session()
    agent.handle(session, "Хочу в горы, красивый вид и спокойные прогулки. Предложи направления.")
    first = agent.handle(session, "предложи сам")
    repeated = agent.handle(session, "предложи сам")
    assert first.payload["kind"] == repeated.payload["kind"] == "ideas"
    assert "не понял" not in repeated.reply.lower() and session.state.order is None


def test_suggested_buttons_actually_work_for_the_question_that_shows_them():
    agent = make_agent()
    for answer in ("предложи сам", "пока не знаю"):
        session = agent.new_session()
        question = agent.handle(session, "Хочу в горы, предложи направления")
        assert answer in contextual_suggestions(session.state, question)
        result = agent.handle(session, answer)
        assert result.payload["kind"] == "ideas" and result.payload["items"]


def test_explicit_month_is_not_discarded_with_a_suggestion_request():
    result = rule_extract(TripState(pending_question="when"), "предложи сам, но в июне", TODAY)
    assert result.month == 6 and result.unsure is None


def test_room_allocation_delegation_preserves_required_field_and_can_resume():
    agent = make_agent()
    session = agent.new_session()
    first = agent.handle(session, "Только отель в Казани с 10 по 15 декабря 2026, 3 взрослых и ребенок, 2 номера")
    assert first.payload["field"] == "room_allocation"
    deferred = agent.handle(session, "предложи сам")
    assert deferred.payload["field"] == "room_allocation" and session.state.pending_question == "room_allocation"
    assert "не буду придумывать" in deferred.reply and not session.state.room_allocations
    completed = agent.handle(session, "номер 1: 2 взрослых, ребёнок 7 лет; номер 2: 1 взрослый")
    assert completed.payload["kind"] == "service_results" and len(session.state.room_allocations) == 2


def test_transfer_time_delegation_does_not_guess_and_can_resume():
    agent = make_agent()
    session = agent.new_session()
    first = agent.handle(session, "Нужен трансфер в Сочи из аэропорта в отель завтра, 2 человека в одну сторону")
    assert first.payload["field"] == "transfer_time"
    deferred = agent.handle(session, "выбери сам")
    assert deferred.payload["field"] == "transfer_time" and session.state.transfer_time is None
    assert "время подачи" in deferred.reply.lower()
    result = agent.handle(session, "14:30")
    assert result.payload["kind"] == "service_results" and session.state.transfer_time == "14:30"


def test_delegation_is_not_a_booking_or_payment_confirmation():
    for text in ("предложи сам", "сам реши", "на твое усмотрение"):
        update = rule_extract(TripState(stage="payment"), text, TODAY)
        assert update.confirm is None and update.pick is None and update.payment_method is None


def test_model_understands_a_new_delegation_with_verbatim_evidence():
    agent = make_agent()
    session = agent.new_session()
    agent.handle(session, "Хочу в горы, предложи направления")
    assert session.state.pending_question == "when"
    agent.llm = FakeLLM({"unsure": True, "evidence": {"unsure": "ориентируйся на свой опыт"}})
    result = agent.handle(session, "ориентируйся на свой опыт")
    assert result.payload["kind"] == "ideas" and session.state.date_from is None
    assert session.last_nlu == "llm" and session.state.order is None


def test_model_cannot_defer_without_evidence_or_against_an_explicit_answer():
    state = TripState(pending_question="when")
    text = "в июне"
    rules = rule_extract(state, text, TODAY)
    proposed = TripUpdate(unsure=True, evidence={"unsure": text})
    result, _ = arbitrate(state, text, proposed, rules)
    assert result.month == 6 and result.unsure is None
    text = "ориентируйся на свой опыт"
    proposed = TripUpdate(unsure=True, evidence={"unsure": "чужая фраза"})
    result, _ = arbitrate(state, text, proposed, rule_extract(state, text, TODAY))
    assert result.unsure is None
    state = TripState(stage="payment")
    result, _ = arbitrate(state, text, TripUpdate(unsure=True, confirm=True, evidence={"unsure": text}),
                          rule_extract(state, text, TODAY))
    assert result.unsure is None and result.confirm is None


def test_rejected_model_interpretation_gets_a_narrow_semantic_retry():
    agent = make_agent()
    session = agent.new_session()
    agent.handle(session, "Хочу в горы, предложи направления")
    text = "ориентируйся на свой опыт"
    agent.llm = FakeLLM({"hesitate": True, "evidence": {"hesitate": text}},
                        {"intent": "delegate", "evidence": text})
    result = agent.handle(session, text)
    assert result.payload["kind"] == "ideas" and session.last_nlu == "llm"
    assert len(agent.llm.calls) == 2 and session.state.date_from is None and session.state.order is None


def test_semantic_retry_requires_actual_quote_and_is_not_a_transaction():
    agent = make_agent()
    session = agent.new_session()
    agent.handle(session, "Хочу в горы")
    text = "ориентируйся на свой опыт"
    agent.llm = FakeLLM({"hesitate": True}, {"intent": "delegate", "evidence": "чужая реплика"})
    result = agent.handle(session, text)
    assert result.payload["kind"] == "question" and session.state.pending_question == "when"
    assert session.state.date_from is None and session.state.order is None


def test_model_timeout_does_not_trigger_another_request():
    agent = make_agent()
    session = agent.new_session()
    agent.handle(session, "Хочу в горы")
    agent.llm = FakeLLM(TimeoutError())
    agent.handle(session, "ориентируйся на свой опыт")
    assert len(agent.llm.calls) == 1 and session.state.pending_question == "when"
