from datetime import date

from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.world_places import find_world_places


TODAY = date(2026, 10, 27)


def new_agent():
    return Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)


def test_cities_outside_offer_catalog_are_known_without_fake_offers():
    agent = new_agent()
    session = agent.new_session()
    answer = agent.handle(session, "хочу поехать в Рейкьявик")
    assert answer.payload["kind"] == "place_info"
    assert answer.payload["place"]["country"] == "Исландия"
    assert "цен" in answer.reply and "нет" in answer.reply
    assert session.state.dest_id is None and session.state.order is None


def test_unknown_city_with_wrong_country_does_not_become_another_city():
    agent = new_agent()
    session = agent.new_session()
    answer = agent.handle(session, "хочу в Валлетту в Италии")
    assert answer.payload["kind"] == "question"
    assert "Мальта" in answer.reply and "Италия" in answer.reply
    answer = agent.handle(session, "в Мальте")
    assert answer.payload["kind"] == "place_info" and answer.payload["place"]["country"] == "Мальта"


def test_ambiguous_city_requires_clarification():
    assert len(find_world_places("киров")) > 1
    agent = new_agent()
    answer = agent.handle(agent.new_session(), "хочу в Киров")
    assert answer.payload["kind"] == "question" and "нескольких" in answer.reply
