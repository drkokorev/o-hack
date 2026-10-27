from datetime import date

import pytest

from core.agent import Agent
from domains.trips.domain import TripsDomain


TODAY = date(2026, 10, 27)


def new_agent():
    return Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)


@pytest.mark.parametrize(("text", "city", "actual_country"), [
    ("Казань в Казахстане на неделю в ноябре", "Казань", "Россия"),
    ("Париж в Италии на неделю в ноябре", "Париж", "Франция"),
    ("Сочи в Грузии в декабре на неделю", "Сочи", "Россия"),
])
def test_city_country_conflict_requires_clarification(text, city, actual_country):
    agent = new_agent()
    session = agent.new_session()
    step = agent.handle(session, text)
    assert step.payload["kind"] == "question"
    assert city in step.reply and actual_country in step.reply
    assert not session.state.order


def test_country_clarification_resumes_search():
    agent = new_agent()
    session = agent.new_session()
    agent.handle(session, "Казань в Казахстане на неделю в ноябре")
    step = agent.handle(session, "Казань в России")
    assert step.payload["kind"] == "question" and session.state.dest_id == "kazan"
    step = agent.handle(session, "из Москвы двое взрослых")
    assert step.payload["kind"] == "packages"
    assert session.state.dest_id == "kazan"


def test_lowercase_unknown_origin_is_not_silently_replaced_with_moscow():
    agent = new_agent()
    session = agent.new_session()
    step = agent.handle(session, "из краснодара в сочи на неделю в ноябре")
    assert step.payload["kind"] == "question"
    assert "краснодар" in step.reply.lower()
    step = agent.handle(session, "из Москвы двое взрослых")
    assert step.payload["kind"] == "packages"
    assert session.state.origin == "Москва"


def test_lowercase_unknown_destination_is_named_instead_of_silent_substitution():
    agent = new_agent()
    session = agent.new_session()
    step = agent.handle(session, "хочу в рейкьявик в декабре")
    assert "рейкьявик" in step.reply.lower()
    assert session.state.dest_id is None


def test_obvious_short_typo_is_explained():
    agent = new_agent()
    session = agent.new_session()
    step = agent.handle(session, "в Соче на неделю в ноябре")
    assert session.state.dest_id == "sochi"
    assert "Сочи" in step.reply and ("понял" in step.reply.lower() or "имели в виду" in step.reply.lower())


def test_malo_deneg_is_not_a_country_conflict_with_mali():
    agent = new_agent()
    session = agent.new_session()
    agent.handle(session, "хочу в Сочи, мало денег")
    assert session.state.dest_id == "sochi" and session.state.country_conflict is None


def test_explicit_home_city_is_not_misread_as_destination():
    agent = new_agent()
    session = agent.new_session()
    agent.handle(session, "хочу в Сочи, живу в Москве")
    assert session.state.origin == "Москва" and session.state.dest_id == "sochi"


def test_country_does_not_silently_turn_into_one_arbitrary_city():
    agent = new_agent()
    session = agent.new_session()
    step = agent.handle(session, "хочу в Турцию на неделю в июле из Москвы двое взрослых")
    assert session.state.dest_id is None and session.state.country == "Турция"
    assert step.payload["kind"] == "ideas" and all(item["country"] == "Турция" for item in step.payload["items"])
    agent.handle(session, "давай Стамбул")
    assert session.state.dest_id == "istanbul"


def test_changing_country_does_not_keep_a_city_from_the_old_country():
    agent = new_agent()
    session = agent.new_session()
    agent.handle(session, "Сочи из Москвы в декабре на неделю двое взрослых")
    answer = agent.handle(session, "лучше в Турцию")
    assert session.state.dest_id is None and session.state.country == "Турция"
    assert answer.payload["kind"] == "ideas" and all(item["country"] == "Турция" for item in answer.payload["items"])
