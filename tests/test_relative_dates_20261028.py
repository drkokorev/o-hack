from datetime import date

import pytest

from apps.web import understood
from core.agent import Agent
from domains.trips.arbiter import arbitrate
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract, time_expression_not_place
from domains.trips.state import TripState, TripUpdate
from domains.trips.textparse import parse_dates
from tests.conftest import FakeLLM


TODAY = date(2026, 10, 28)


def test_user_sequence_with_model_mistakes_keeps_dates_and_not_a_fake_city():
    llm = FakeLLM(
        {"wants_ideas": True},
        {"destination": "следующем", "date_from": "2026-11-01"},
        {"nights": 3},
        {"destination": "следующем"},
    )
    agent = Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY)
    session = agent.new_session()
    agent.handle(session, "Хочу куда-нибудь отдохнуть")
    second = agent.handle(session, "в следующем месяце")
    assert session.last_nlu == "llm+rules"
    assert session.state.destination is None and session.state.dest_id is None
    assert (session.state.month, session.state.year) == (11, 2026)
    assert session.state.date_from is None
    assert "ноябрь" in " ".join(understood(session.state)).lower()
    assert "нет в каталоге" not in second.reply
    assert "учёл поездку в ноябре 2026" in second.reply.lower()

    third = agent.handle(session, "через 3 дня")
    assert session.state.date_from == date(2026, 10, 31)
    assert session.state.date_to is None and session.state.nights is None
    assert "начало: 31 октября 2026" in understood(session.state)
    assert "нет в каталоге" not in third.reply
    assert "31 октября 2026" in third.reply

    last = agent.handle(session, "1.11-7.11")
    assert (session.state.date_from, session.state.date_to) == (date(2026, 11, 1), date(2026, 11, 7))
    assert session.state.nights == 6 and session.state.destination is None
    assert "нет в каталоге" not in last.reply
    assert "1–7 ноября 2026" in last.reply
    assert len(llm.calls) == 4


@pytest.mark.parametrize("word", ["следующем", "следующем месяце", "месяце", "будущем", "неделе"])
def test_model_cannot_turn_a_time_expression_into_a_destination(word):
    text = f"в {word}"
    rules = rule_extract(TripState(), text, TODAY)
    result, _ = arbitrate(TripState(), text, TripUpdate(destination=word), rules)
    assert result.destination is None


def test_demonstrative_guard_does_not_reject_place_names_beginning_with_et():
    assert time_expression_not_place("этом месяце")
    assert not time_expression_not_place("Этна")
    assert not time_expression_not_place("Эфиопия")


@pytest.mark.parametrize(("text", "expected"), [
    ("через 3 дня", (date(2026, 10, 31), None)),
    ("через три дня на 2 ночи", (date(2026, 10, 31), date(2026, 11, 2))),
    ("через пару недель", (date(2026, 11, 11), None)),
    ("1.11-7.11", (date(2026, 11, 1), date(2026, 11, 7))),
])
def test_relative_and_numeric_dates(text, expected):
    assert parse_dates(text, TODAY) == expected


def test_next_month_rolls_over_year_without_inventing_a_day():
    update = rule_extract(TripState(), "в следующем месяце", date(2026, 12, 28))
    assert (update.month, update.year) == (1, 2027)
    assert update.date_from is None and update.date_to is None


def test_in_a_month_uses_calendar_month_and_preserves_nights():
    assert parse_dates("через месяц на неделю", date(2026, 1, 31)) == (date(2026, 2, 28), date(2026, 3, 7))


def test_a_date_repairs_legacy_invalid_time_destination_but_not_real_place():
    domain = TripsDomain(today=lambda: TODAY)
    update = rule_extract(TripState(), "1.11-7.11", TODAY)
    corrupted = domain.merge(TripState(destination="следующем"), update)
    real_place = domain.merge(TripState(destination="Рейкьявик"), update)
    assert corrupted.destination is None
    assert real_place.destination == "Рейкьявик"


def test_unrecognized_repeated_answer_does_not_accumulate_error_prefixes():
    agent = Agent(TripsDomain(today=lambda: TODAY), FakeLLM({}, {}, {}), today=lambda: TODAY)
    session = agent.new_session()
    agent.handle(session, "Хочу куда-нибудь отдохнуть")
    agent.handle(session, "абракадабра")
    result = agent.handle(session, "тарабарщина")
    assert result.reply.count("Не понял сообщение.") == 1
