from datetime import date

import pytest

from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.map_catalog import hotels_in_destination, search_hotels
from domains.trips.state import TripState
from tests.conftest import FakeLLM


TODAY = date(2026, 10, 28)


def scenario(llm=None):
    agent = Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY)
    session = agent.new_session()
    agent.handle(session, "из Москвы в Париж с 1 декабря по 7 двое взрослых только без пересадок")
    step = agent.handle(session, "покажи реальные отели")
    return agent, session, step


@pytest.mark.parametrize("mode", ["number", "name"])
def test_source_hotels_can_be_selected_and_retained_when_allowing_transfer(mode):
    agent, session, step = scenario()
    shown = hotels_in_destination("paris")
    assert step.payload["kind"] == "real_hotels" and len(shown) >= 2
    assert "номер" in step.reply.lower() and "₽" not in step.reply
    item = shown[1]
    selected = agent.handle(session, "2" if mode == "number" else item["name"].lower())
    assert session.state.selected_real_hotel["id"] == item["id"]
    assert item["name"] in selected.reply and "₽" not in selected.reply
    assert session.state.hotel_id == "paris-h" + item["id"].removeprefix("overture:")
    pinned = session.state.hotel_id
    after = agent.handle(session, "можно с пересадкой")
    assert session.state.direct_only is False and session.state.hotel_id == pinned
    assert after.payload["kind"] == "packages"
    assert all(option["hotel"]["id"] == pinned for option in after.payload["items"])
    assert "демонстрацион" in after.reply.lower()


def test_model_cannot_replace_exact_named_source_record_with_a_different_destination():
    llm = FakeLLM({}, {}, {"destination": "Казань", "pick": 1})
    agent, session, _ = scenario(llm)
    second = session.state.real_hotels_shown[1]
    agent.handle(session, second["name"])
    assert session.state.dest_id == "paris"
    assert session.state.selected_real_hotel["id"] == second["id"]


def test_ambiguous_identical_names_are_not_silently_chosen():
    state = TripState(showing="real_hotels", real_hotels_shown=[{"id": "a", "name": "Central Hotel"},
                                                                  {"id": "b", "name": "Central Hotel"}])
    from domains.trips.arbiter import arbitrate
    from domains.trips.rules import rule_extract
    from domains.trips.state import TripUpdate
    text = "выбираю central hotel"
    rules = rule_extract(state, text, TODAY)
    assert rules.pick is None
    result, _ = arbitrate(state, text, TripUpdate(pick=1), rules)
    assert result.pick is None


def test_changed_destination_clears_selected_source_hotel():
    agent, session, _ = scenario()
    agent.handle(session, "2")
    agent.handle(session, "лучше в Сочи")
    assert session.state.dest_id == "sochi"
    assert session.state.selected_real_hotel is None and session.state.hotel_id is None


def test_searches_the_open_hotel_snapshot_by_name_and_selects_the_result():
    agent, session, _ = scenario()
    answer = agent.handle(session, "найди отель Campanile Taverny")
    assert answer.payload["kind"] == "real_hotels"
    assert any(item["name"] == "Campanile Taverny" for item in answer.payload["items"])
    selected = agent.handle(session, "1")
    assert session.state.selected_real_hotel["name"] == "Campanile Taverny"
    assert "₽" not in selected.reply


def test_hotel_name_search_does_not_treat_sql_syntax_as_a_query():
    assert search_hotels("paris", "' OR 1=1 --") == []


def test_missing_selected_hotel_is_not_replaced_by_another():
    from domains.trips.planner import make_packages
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)
    session = agent.new_session()
    agent.handle(session, "из Москвы в Париж с 1 декабря по 7 двое взрослых")
    trip, _ = agent.domain._trip(session.state, TODAY)
    packages, reason = make_packages(trip, "paris-hnot-a-real-hotel")
    assert packages == [] and "выбранный отель" in reason[0]
