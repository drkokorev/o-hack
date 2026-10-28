from datetime import date

import pytest
from pydantic import ValidationError

from core.agent import Agent
from domains.trips.arbiter import arbitrate
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate
from domains.trips.textparse import future_date, parse_dates
from tools.llm_check import ok


TODAY = date(2026, 10, 27)


@pytest.mark.parametrize("phrase", ["без самолёта", "без перелёта", "не хочу лететь"])
def test_excluding_flights_uses_only_the_available_ground_transport(phrase):
    agent = Agent(TripsDomain(), None, today=lambda: TODAY)
    session = agent.new_session()
    step = agent.handle(session, f"Казань из Санкт-Петербурга 10–14 июля 2027 двое взрослых, {phrase}")
    assert session.state.transport == "train"
    assert step.payload["kind"] == "packages"
    assert all(item["out"]["mode"] == "train" and item["back"]["mode"] == "train"
               for item in step.payload["items"])


def test_saying_no_long_flights_is_not_a_ban_on_flying():
    result = rule_extract(TripState(), "без долгих перелётов", TODAY)
    assert result.transport is None
    assert result.max_travel_hours is None and result.prefer_short_travel is True


@pytest.mark.parametrize("phrase", ["без самолёта и без поезда", "без самолёта, на машине"])
def test_unsupported_transport_is_not_silently_replaced(phrase):
    agent = Agent(TripsDomain(), None, today=lambda: TODAY)
    session = agent.new_session()
    step = agent.handle(session, f"Казань из Санкт-Петербурга 10–14 июля 2027 двое взрослых, {phrase}")
    assert session.state.transport == "none"
    assert step.payload["kind"] == "question"
    assert "только самолёт и поезд" in step.reply
    step = agent.handle(session, "тогда поедем поездом")
    assert session.state.transport == "train"
    assert step.payload["kind"] == "packages"


def test_explicit_no_flights_wins_over_an_incorrect_model_answer():
    text = "Казань без самолёта"
    rules = rule_extract(TripState(), text, TODAY)
    result, _ = arbitrate(TripState(), text, TripUpdate(transport="plane"), rules)
    assert result.transport == "train"


def test_total_of_two_with_a_child_means_one_adult_and_one_child():
    result = rule_extract(TripState(), "на двоих с ребёнком", TODAY)
    assert result.adults == 1
    assert result.children == 1


def test_explicit_adults_are_not_reduced_by_children():
    result = rule_extract(TripState(), "два взрослых и ребёнок", TODAY)
    assert result.adults == 2
    assert result.children == 1


def test_pet_in_a_list_is_kept_in_the_trip_requirements():
    result = rule_extract(TripState(), "двое взрослых и собака", TODAY)
    assert result.pets is True


@pytest.mark.parametrize(("text", "expected"), [
    ("с 10 по 14 ноября 2027 года", (date(2027, 11, 10), date(2027, 11, 14))),
    ("05.11.2028 — 12.11.2028", (date(2028, 11, 5), date(2028, 11, 12))),
    ("28 декабря 2027 — 4 января 2028", (date(2027, 12, 28), date(2028, 1, 4))),
    ("5–12.11.2028", (date(2028, 11, 5), date(2028, 11, 12))),
    ("12 ноября 2028 на неделю", (date(2028, 11, 12), date(2028, 11, 19))),
])
def test_explicit_years_are_preserved(text, expected):
    assert parse_dates(text, TODAY) == expected


@pytest.mark.parametrize("text", ["Казань с 10 по 14 ноября 2025", "Казань с 14 по 10 ноября 2028"])
def test_invalid_or_past_date_ranges_are_not_offered_as_bookable(text):
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)
    session = agent.new_session()
    step = agent.handle(session, text)
    assert step.payload["kind"] == "question"
    assert "дат" in step.reply.lower()


def test_leap_day_uses_next_valid_year_without_crashing():
    assert future_date(29, 2, date(2026, 10, 27)) == date(2028, 2, 29)
    assert future_date(31, 2, date(2026, 10, 27)) is None


def test_model_comparison_accepts_either_catalog_id_or_city_name():
    assert ok(TripUpdate(destination="kazan"), {"destination": "Казань"})
    assert ok(TripUpdate(destination="Казань"), {"destination": "Казань"})
    assert not ok(TripUpdate(destination="sochi"), {"destination": "Казань"})


def test_model_cannot_silently_invent_day_for_a_month_only_request():
    text = "В Сочи на неделю в ноябре 2027 с собакой"
    rules = rule_extract(TripState(), text, TODAY)
    model = TripUpdate(month=11, date_from=date(2027, 11, 1), date_to=date(2027, 11, 8), nights=7)
    result, notes = arbitrate(TripState(), text, model, rules)
    assert result.year == 2027
    assert result.month == 11
    assert result.date_from is None and result.date_to is None
    assert notes


def test_a_month_with_explicit_year_uses_that_year_and_marks_assumed_dates():
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)
    session = agent.new_session()
    step = agent.handle(session, "В Сочи из Москвы на неделю в ноябре 2028 двое взрослых с собакой")
    assert step.payload["kind"] == "packages"
    assert session.state.date_from.year == 2028
    assert session.state.dates_assumed
    assert any("даты" in assumption for assumption in session.state.assumptions)


def test_out_of_range_month_and_year_from_model_are_rejected():
    with pytest.raises(ValidationError):
        TripUpdate(month=13)
    with pytest.raises(ValidationError):
        TripUpdate(year=10000)
