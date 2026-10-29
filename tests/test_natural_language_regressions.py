from datetime import date

import pytest
from pydantic import ValidationError

from core.agent import Agent
from domains.trips.arbiter import arbitrate
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate
from domains.trips.geo import BY_ID
from domains.trips.textparse import future_date, norm, parse_dates
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


# ---------- найдено живым прогоном с моделью (eval.simulate, 28.10) ----------

@pytest.mark.parametrize("phrase", ["долго лететь не хотим", "не хотим долго лететь", "далеко лететь не готовы"])
def test_long_flight_reluctance_is_a_preference_not_a_ban_on_planes(phrase):
    update = rule_extract(TripState(), f"Хотим на море в ноябре, {phrase}", TODAY)
    assert update.prefer_short_travel is True and update.transport is None


@pytest.mark.parametrize("phrase", ["Всё отлично, бронируй этот вариант", "Нормально уже, бронируйте",
                                    "Всё отлично, оформляйте заказ.", "Хорошо, оформляй"])
def test_approval_before_booking_verb_confirms(phrase):
    assert rule_extract(TripState(), phrase, TODAY).confirm is True


def test_named_dates_win_over_relative_shift_in_same_phrase():
    update = rule_extract(TripState(), "Давай сдвинем на два дня позже, с 12 по 17 декабря", TODAY)
    assert (update.date_from, update.date_to) == (date(2026, 12, 12), date(2026, 12, 17))
    assert update.shift_days is None and update.trip_days_min is None


def test_cart_accepts_booking_after_approval_words():
    agent = Agent(TripsDomain(), None, today=lambda: TODAY)
    session = agent.new_session()
    agent.handle(session, "Казань из Москвы 13–15 ноября 2026 двое взрослых")
    agent.handle(session, "беру первый")
    assert session.state.stage == "cart"
    agent.handle(session, "Всё отлично, бронируй этот вариант")
    assert session.state.stage == "payment"


# ---------- ручная проверка 28.10: «пляж → нояюрь → с 7 по 13 → грузия» ----------

def test_month_typo_and_day_range_without_month_are_understood():
    state = TripState()
    assert rule_extract(state, "нояюрь", TODAY).month == 11
    update = rule_extract(state.model_copy(update={"month": 11}), "с 7 по 13", TODAY)
    assert (update.date_from, update.date_to) == (date(2026, 11, 7), date(2026, 11, 13))
    assert norm("янтаря") == "янтаря" and norm("октябрьский") == "октябрьский"


def test_beach_ideas_respect_season_and_single_country_place_is_chosen():
    agent = Agent(TripsDomain(), None, today=lambda: TODAY)
    session = agent.new_session()
    agent.handle(session, "хочу на пляж с белым песком")
    agent.handle(session, "нояюрь")
    ideas_shown = {BY_ID[d].name for d in session.state.suggested}
    assert ideas_shown and not ideas_shown & {"Батуми", "Сочи", "Будва", "Барселона"}  # в ноябре не купальный сезон
    agent.handle(session, "с 7 по 13")
    reply = agent.handle(session, "грузия").reply
    assert session.state.dest_id == "batumi" and "не купальный сезон" in reply
    assert (session.state.date_from, session.state.date_to) == (date(2026, 11, 7), date(2026, 11, 13))


# ---------- короткие ответы на вопросы агента (eval/short_answers_live.py) ----------

def test_short_answers_to_agent_questions_are_understood_without_model():
    from eval.short_answers_live import CASES, TODAY as CASE_DAY, _ok

    agent = Agent(TripsDomain(today=lambda: CASE_DAY), None, today=lambda: CASE_DAY, nlg=False)
    failures = []
    for question, (opening, answers) in CASES.items():
        for answer, expected in answers:
            session = agent.new_session()
            agent.handle(session, opening)
            assert session.state.pending_question == question, opening
            agent.handle(session, answer)
            failures += [f"«{answer}»: {problem}" for problem in _ok(session.state, expected)]
    assert not failures


def test_question_about_direct_flights_answers_and_keeps_conditions():
    agent = Agent(TripsDomain(), None, today=lambda: TODAY)
    session = agent.new_session()
    agent.handle(session, "Гоа из Кирова с 16 по 27 декабря 2026 двое взрослых")
    reply = agent.handle(session, "из кирова прямые рейсы летают на гоа?").reply
    assert session.state.direct_only is None and "пересадка в Москве" in reply and "демонстрац" in reply


def test_model_numbers_are_accepted_only_next_to_their_unit():
    state = TripState(pending_question="duration")
    for text, nights, accepted in (("11 дн", 10, True), ("полторы недели", 10, True), ("через 3 дня", 3, False),
                                   ("хочу недорого", 7, False)):
        result, _ = arbitrate(state, text, TripUpdate(nights=nights), rule_extract(state, text, TODAY))
        assert (result.nights is not None or bool(result.trip_days_min)) == accepted, text


# ---------- модель главная: значения со ссылкой на реплику ----------

def test_model_values_with_evidence_win_where_rules_do_not_understand():
    text = "мы с женой из пинзы в стамбл на 11 дн в нояюре"
    model = TripUpdate(origin="Пенза", destination="Стамбул", nights=10, adults=2, month=11,
                       evidence={"origin": "из пинзы", "destination": "в стамбл", "nights": "11 дн",
                                 "adults": "мы с женой", "month": "в нояюре"})
    result, _ = arbitrate(TripState(), text, model, rule_extract(TripState(), text, TODAY))
    assert (result.origin, result.nights, result.month) == ("Пенза", 10, 11)
    assert result.adults is None  # «с женой» возраст не подтверждает — агент уточнит про детей
    assert result.destination in ("Стамбул", "istanbul")


def test_evidence_that_does_not_support_the_value_is_rejected():
    text = "хочу недорого отдохнуть с семьей"
    model = TripUpdate(budget_total=100000, nights=7, adults=2,
                       evidence={"budget_total": "недорого", "nights": "отдохнуть", "adults": "с семьей"})
    result, _ = arbitrate(TripState(), text, model, rule_extract(TripState(), text, TODAY))
    assert result.budget_total is None and result.nights is None and result.adults is None
    fake = TripUpdate(origin="Москва", evidence={"origin": "из Москвы"})  # ссылки нет в реплике
    result, _ = arbitrate(TripState(), "хочу в Сочи", fake, rule_extract(TripState(), "хочу в Сочи", TODAY))
    assert result.origin is None


def test_together_does_not_make_adults_even_with_evidence():
    text = "едем втроём в Казань"
    model = TripUpdate(adults=3, evidence={"adults": "втроём"})
    result, _ = arbitrate(TripState(), text, model, rule_extract(TripState(), text, TODAY))
    assert result.adults is None
