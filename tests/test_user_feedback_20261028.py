from datetime import date
from types import SimpleNamespace

from apps.web import contextual_suggestions
from core.agent import Agent, Step
from domains.trips.arbiter import arbitrate
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID, ORIGIN_BY_NAME
from domains.trips.planner import Trip
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate
from domains.trips.textparse import parse_budget_scopes

TODAY = date(2026, 10, 28)


def agent():
    return Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)


def test_seven_days_do_not_invent_dates_or_six_nights():
    a = agent()
    session = a.new_session()
    first = a.handle(session, "Хочу в Сочи на 7 дней")
    assert session.state.trip_days_min == session.state.trip_days_max == 7
    assert session.state.nights is None and session.state.date_from is None and session.state.date_to is None
    assert "когда" in first.reply.lower() or "числа" in first.reply.lower()
    month = a.handle(session, "в ноябре")
    assert session.state.date_from is None and session.state.nights is None and "числа" in month.reply.lower()
    dated = a.handle(session, "10 ноября 2027")
    assert session.state.date_from == date(2027, 11, 10) and session.state.date_to is None
    assert session.state.nights is None and "ночей" in dated.reply.lower()
    a.handle(session, "6 ночей")
    assert session.state.nights == 6 and session.state.date_to == date(2027, 11, 16)


def test_duration_range_and_spelling_are_not_a_single_night_count():
    update = rule_extract(TripState(), "Бали, 100 тысяч рублей, 3-7 дей с отелем", TODAY)
    assert update.trip_days_min == 3 and update.trip_days_max == 7 and update.nights is None
    assert update.date_from is None and update.date_to is None and update.budget_total == 100000


def test_refusing_a_pair_of_days_removes_the_old_duration():
    state = TripState(nights=2, date_from=date(2026, 11, 28), date_to=date(2026, 11, 30))
    update = rule_extract(state, "не пару дней", TODAY)
    assert update.clear_duration and update.trip_days_min is None
    merged = TripsDomain(today=lambda: TODAY).merge(state, update)
    assert merged.nights is None and merged.date_to is None


def test_new_or_edit_choice_prevents_silent_carry_over():
    a = agent()
    session = a.new_session()
    a.handle(session, "Казань из Питера на выходные с собакой")
    question = a.handle(session, "Хочу к тёплому морю в ноябре, недорого, с ребёнком, без долгих перелётов")
    assert question.payload["field"] == "trip_choice"
    assert session.state.dest_id == "kazan" and session.state.pets is True
    answer = a.handle(session, "новая поездка")
    assert "новую поездку" in answer.reply.lower()
    assert session.state.pets is None and session.state.origin is None and session.state.date_from is None
    assert session.state.nights is None and session.state.children == 1 and session.state.month == 11
    assert session.state.prefer_short_travel and session.state.max_travel_hours is None


def test_edit_current_trip_keeps_other_conditions_explicitly():
    a = agent()
    session = a.new_session()
    a.handle(session, "Казань из Питера на выходные с собакой")
    a.handle(session, "Хочу к тёплому морю в ноябре")
    answer = a.handle(session, "изменить текущую")
    assert session.state.pets is True and session.state.origin == "Санкт-Петербург"
    assert "остальные сохранил" in answer.reply.lower()


def test_party_count_cannot_silently_remove_a_previously_mentioned_child():
    a = agent()
    session = a.new_session()
    a.handle(session, "Сочи из Москвы с 10 по 14 июня 2027, с ребёнком")
    a.handle(session, "на двоих")
    assert session.state.party_size == 2 and session.state.children == 1
    question = a.handle(session, "2 взрослых")
    assert question.payload["field"] == "people_conflict" and session.state.children == 1
    assert "ребёнок" in question.reply.lower()
    result = a.handle(session, "без ребёнка")
    assert not session.state.group_conflict and session.state.children == 0
    assert result.payload["kind"] == "packages"


def test_party_conflict_can_be_resolved_by_updating_total():
    a = agent()
    session = a.new_session()
    a.handle(session, "Сочи из Москвы с 10 по 14 июня 2027, с ребёнком")
    a.handle(session, "на двоих")
    a.handle(session, "2 взрослых")
    result = a.handle(session, "нас трое")
    assert not session.state.group_conflict and session.state.party_size == 3
    assert session.state.adults == 2 and session.state.children == 1 and result.payload["kind"] == "packages"


def test_surf_budget_and_meal_are_saved_without_inventing_duration():
    a = agent()
    session = a.new_session()
    a.handle(session, "Хочу к тёплому морю в ноябре, недорого")
    answer = a.handle(session, "хочу серфинг тысяч за 100 на двоих из москвы не пару дней хотя бы с проживанием и питанием")
    assert {"sea", "warm", "surf"} <= set(session.state.trip_types)
    assert session.state.origin == "Москва" and session.state.party_size == 2
    assert session.state.budget_total == 100000 and session.state.meal == "meal_included"
    assert session.state.nights is None
    assert answer.payload["kind"] == "ideas" and all(item["id"] in {"bali", "srilanka"}
                                                      for item in answer.payload["items"])
    assert "условия и сезон нужно проверить" in answer.reply


def test_dubai_budget_and_unspecified_meal_update_the_current_request():
    state = TripState(destination="Бали", dest_id="bali", origin="Москва", adults=2, budget_total=100000)
    update = rule_extract(state, "150 к дубаи тогда давай и 4 звездочный отель с питанием", TODAY)
    assert update.destination == "dubai" and update.budget_total == 150000
    assert update.stars_min == 4 and update.meal == "meal_included" and not update.needs_trip_choice


def test_named_amounts_do_not_get_confused_with_dates_or_nights():
    assert parse_budget_scopes("тысяч за 100 на двоих") == (100000, None)
    assert parse_budget_scopes("Бали, 100 тысяч рублей, 3-7 дней") == (100000, None)
    assert parse_budget_scopes("10 июня 2027, 150 к на всю поездку") == (150000, None)


def test_vague_short_flight_preference_is_not_an_invented_five_hour_limit():
    state = TripState()
    text = "без долгих перелётов"
    rules = rule_extract(state, text, TODAY)
    result, _ = arbitrate(state, text, TripUpdate(max_travel_hours=5), rules)
    assert result.max_travel_hours is None and result.prefer_short_travel


def sample_trip(**kwargs):
    return Trip(ORIGIN_BY_NAME["Москва"], BY_ID["bali"], date(2026, 12, 1), date(2026, 12, 3), 2, 0, **kwargs)


def test_no_transport_explains_actual_limit_and_offers_checked_relaxation(monkeypatch):
    leg = SimpleNamespace(minutes=600, stops=0, pets_ok=True)
    monkeypatch.setattr("domains.trips.domain.transport_options", lambda *args: [leg])
    result = TripsDomain._transport_failure(TripState(), sample_trip(max_hours=5))
    assert "не более 5 ч" in result.reply and "ограничение времени" in result.reply
    assert "время в пути не важно" in result.payload["suggestions"]
    assert "убрать «только прямые»" not in result.reply and "только без пересадок" not in result.payload["suggestions"]


def test_multiple_blockers_are_not_claimed_solved_by_one_change(monkeypatch):
    leg = SimpleNamespace(minutes=600, stops=1, pets_ok=True)
    monkeypatch.setattr("domains.trips.domain.transport_options", lambda *args: [leg])
    result = TripsDomain._transport_failure(TripState(), sample_trip(max_hours=5, direct_only=True))
    assert "в сочетании" in result.reply and "время в пути не важно" not in result.payload["suggestions"]


def test_empty_hotel_list_does_not_ask_user_to_choose_a_nonexistent_item(monkeypatch):
    monkeypatch.setattr("domains.trips.planner.candidate_hotels", lambda trip: ([], []))
    monkeypatch.setattr("domains.trips.domain.hotels_for", lambda dest_id: [])
    result = TripsDomain(today=lambda: TODAY)._hotels(TripState(), sample_trip())
    assert result.payload["kind"] == "question" and result.payload["reason"] == "no_hotels"
    assert "Какой взять" not in result.reply


def test_contextual_suggestions_do_not_leak_package_actions_into_empty_results():
    state = TripState(stage="plan")
    step = Step("нет дороги", payload={"kind": "question", "reason": "no_transport",
                                      "suggestions": ["другое направление"]})
    choices = contextual_suggestions(state, step)
    assert choices == ["другое направление"]
    assert "подешевле" not in choices and "только без пересадок" not in choices
