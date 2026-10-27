from datetime import date

import pytest

from apps.web import Sessions
from core.agent import Agent
from domains.trips.domain import TripsDomain
from tests.conftest import FakeLLM


@pytest.mark.parametrize("private_text", [
    "Мой телефон +7 900 000-00-00, поездка в Сочи",
    "Отправьте сведения на test@example.com",
    "Мой паспорт: 1234 567890",
    "Карта 4111 1111 1111 1111",
])
def test_obvious_private_data_is_not_sent_to_model_or_kept_in_history(private_text):
    llm = FakeLLM({"destination": "sochi"})
    agent = Agent(TripsDomain(), llm)
    session = agent.new_session()
    step = agent.handle(session, private_text)
    assert not llm.calls
    assert private_text not in str(session.history)
    assert "личн" in step.reply.lower() or "данн" in step.reply.lower()


def test_normal_dates_and_budgets_are_not_blocked():
    llm = FakeLLM({"destination": "kazan"})
    today = date(2026, 10, 27)
    agent = Agent(TripsDomain(today=lambda: today), llm, today=lambda: today)
    session = agent.new_session()
    agent.handle(session, "Казань с 10 по 14 ноября 2027, двое взрослых, бюджет 150000 рублей")
    assert llm.calls
    assert session.state.dest_id == "kazan"


def test_inactive_sessions_expire_and_reset_erases_them():
    now = [0.0]
    sessions = Sessions(Agent(TripsDomain(), None), ttl_seconds=60, clock=lambda: now[0])
    first_id, _ = sessions.get(None)
    now[0] = 40
    assert sessions.get(first_id)[0] == first_id
    now[0] = 101
    assert sessions.prune() == 1
    second_id, _ = sessions.get(first_id)
    assert second_id != first_id
    sessions.drop(second_id)
    assert second_id not in sessions._items


def test_model_history_is_bounded_to_needed_context():
    agent = Agent(TripsDomain(), None, history_messages=4)
    session = agent.new_session()
    for _ in range(5):
        agent.handle(session, "привет")
    assert len(session.history) == 4
