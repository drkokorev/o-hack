from datetime import date
import json
from pathlib import Path

import pytest

from apps.web import understood
from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.state import TripState
from domains.trips.textparse import parse_dates
from tests.conftest import FakeLLM


TODAY = date(2026, 10, 28)
MATRIX = json.loads((Path(__file__).parents[1] / "eval" / "parameter_matrix_20261028.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", MATRIX["development"] + MATRIX["new_phrases"],
                         ids=lambda case: case["id"])
def test_parameter_matrix(case):
    actual = rule_extract(TripState(), case["text"], TODAY).model_dump(mode="json")
    assert {key: actual[key] for key in case["expected"]} == case["expected"]


def test_user_paris_message_keeps_every_parameter_and_asks_for_origin():
    text = "в париж с 1 декабря по 7 с евушкой за 200 тысяч рублей на самолете"
    model = FakeLLM({"destination": "Париж", "date_from": "2026-12-01", "date_to": "2026-12-07",
                     "party_size": 2, "adults": 2, "budget_total": 200000, "transport": "plane"})
    agent = Agent(TripsDomain(today=lambda: TODAY), model, today=lambda: TODAY)
    session = agent.new_session()
    answer = agent.handle(session, text)
    state = session.state
    assert (state.dest_id, state.date_from, state.date_to) == ("paris", date(2026, 12, 1), date(2026, 12, 7))
    assert state.nights == 6 and state.party_size == 2
    assert state.adults is None  # Two travellers do not establish their ages.
    assert (state.budget_total, state.transport) == (200000, "plane")
    assert answer.payload["field"] == "origin"
    assert "6 ночей" in answer.reply and "какого города" in answer.reply.lower()


@pytest.mark.parametrize(("text", "expected"), [
    ("с 1 декабря по 7", (date(2026, 12, 1), date(2026, 12, 7))),
    ("с 5 ноября до 10", (date(2026, 11, 5), date(2026, 11, 10))),
    ("1 декабря — 7", (date(2026, 12, 1), date(2026, 12, 7))),
    ("с 1 декабря 2027 по 7", (date(2027, 12, 1), date(2027, 12, 7))),
    ("с 20 февраля по 25 2028 года", (date(2028, 2, 20), date(2028, 2, 25))),
    ("28 декабря по 4 января 2027", (date(2026, 12, 28), date(2027, 1, 4))),
    ("через неделю", (date(2026, 11, 4), None)),
])
def test_common_date_phrasings(text, expected):
    assert parse_dates(text, TODAY) == expected


def test_missing_end_month_is_not_silently_moved_to_the_next_month():
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)
    session = agent.new_session()
    answer = agent.handle(session, "в Сочи с 28 декабря по 4")
    assert session.state.date_from == date(2026, 12, 28)
    assert session.state.date_to == date(2026, 12, 4)
    assert "окончания" in answer.reply.lower()


@pytest.mark.parametrize("companion", ["девушкой", "евушкой", "парнем", "моей девушкой", "молодым человеком"])
def test_companion_means_two_travellers_without_guessing_age(companion):
    update = rule_extract(TripState(), f"в Париж с {companion}", TODAY)
    assert update.party_size == 2 and update.adults is None


def test_tentative_companion_is_not_treated_as_confirmed():
    update = rule_extract(TripState(), "возможно, поеду с девушкой", TODAY)
    assert update.party_size == 2 and update.tentative_fields == ["party_size"]


def test_negated_companion_is_not_counted():
    assert rule_extract(TripState(), "в Париж не с девушкой", TODAY).party_size is None


def test_for_two_and_sunny_are_understood_as_separate_parameters():
    update = rule_extract(TripState(), "хочу за границу, чтобы было солнечно, до 180 тысяч для двоих", TODAY)
    assert update.party_size == 2 and update.trip_types == ["warm"]
    assert update.abroad is True and update.budget_total == 180000


def test_economy_preference_is_visible_in_the_trip_summary():
    assert "недорого" in understood(TripState(economy=True))


def test_year_after_end_day_does_not_become_a_budget():
    update = rule_extract(TripState(), "в Сочи с 20 февраля по 25 2028 года", TODAY)
    assert (update.date_from, update.date_to) == (date(2028, 2, 20), date(2028, 2, 25))
    assert update.budget_total is None


def test_nightly_price_is_not_a_destination():
    update = rule_extract(TripState(), "до 9 тысяч в сутки на отель", TODAY)
    assert update.budget_night == 9000 and update.unknown_place is None and update.destination is None


def test_thousands_with_spaces_remain_a_valid_budget():
    update = rule_extract(TripState(), "в Париж с 1 декабря по 7, бюджет до 200 000 рублей", TODAY)
    assert update.budget_total == 200000


def test_conflicting_dates_and_nights_are_clarified_before_offers():
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)
    session = agent.new_session()
    answer = agent.handle(session, "из Москвы в Париж с 1 декабря по 7 на 5 ночей двое взрослых")
    assert answer.payload["field"] == "duration_conflict"
    assert "6 ночей" in answer.reply and "5 ночей" in answer.reply
    assert (session.state.date_to, session.state.nights) == (date(2026, 12, 7), 5)
    answer = agent.handle(session, "на 5 ночей")
    assert session.state.date_to == date(2026, 12, 6)
    assert session.state.nights == 5
    assert answer.payload["kind"] == "packages"
