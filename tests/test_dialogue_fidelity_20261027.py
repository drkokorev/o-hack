from datetime import date
import json

import pytest

from core.agent import Agent
from domains.trips.arbiter import arbitrate
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate
from domains.trips.textparse import parse_budget_scopes


TODAY = date(2026, 10, 27)


def agent(llm=None):
    return Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY)


@pytest.mark.parametrize("phrase", ["В Казань на майские", "В Сочи на Новый год"])
def test_holidays_do_not_create_exact_dates_or_duration(phrase):
    session = agent().new_session()
    agent().handle(session, phrase)
    assert session.state.date_from is None
    assert session.state.date_to is None
    assert session.state.nights is None


def test_removing_one_wish_preserves_other_wishes_and_route():
    a = agent()
    session = a.new_session()
    a.handle(session, "В Казань из Москвы с 10 по 14 июля 2027 двое взрослых, нужен бассейн и парковка")
    step = a.handle(session, "Бассейн больше не нужен, парковку оставь")
    assert session.state.hotel_wishes == ["parking"]
    assert session.state.dest_id == "kazan" and session.state.origin == "Москва"
    assert step.payload["kind"] == "packages"


def test_model_cannot_clear_all_wishes_when_only_one_was_removed():
    state = TripState(hotel_wishes=["pool", "parking"])
    text = "Бассейн больше не нужен, парковку оставь"
    rules = rule_extract(state, text, TODAY)
    update, _ = arbitrate(state, text, TripUpdate(clear=["hotel_wishes"]), rules)
    merged = TripsDomain(today=lambda: TODAY).merge(state, update)
    assert merged.hotel_wishes == ["parking"]


def test_pet_policy_question_does_not_add_an_animal_even_if_model_does():
    text = "Хочу в Сочи, можно ли с собакой?"
    state = TripState()
    rules = rule_extract(state, text, TODAY)
    update, notes = arbitrate(state, text, TripUpdate(pets=True), rules)
    assert update.pets is None and update.question == "pets" and notes
    a = agent()
    session = a.new_session()
    step = a.handle(session, text)
    assert session.state.pets is None
    assert "проверенных условий" in step.reply


def test_explicit_pet_preference_is_kept_when_question_is_also_asked():
    result = rule_extract(TripState(), "Едем с собакой. Какие условия в отеле?", TODAY)
    assert result.pets is True


def test_changed_group_size_does_not_invent_age_composition():
    a = agent()
    session = a.new_session()
    a.handle(session, "Хочу в Казань, едем вдвоём")
    a.handle(session, "Нас теперь трое")
    assert session.state.party_size == 3 and session.state.adults is None


def test_trip_word_does_not_override_an_explicit_flight_with_a_train():
    text = "Думаю про поездку с другом, денег мало, важны еда и перелет"
    result = rule_extract(TripState(), text, TODAY)
    assert result.transport == "plane" and result.economy is True and result.party_size == 2
    question = "Думаю про поездку с другом"
    result, _ = arbitrate(TripState(), question, TripUpdate(transport="train"),
                          rule_extract(TripState(), question, TODAY))
    assert result.transport is None


@pytest.mark.parametrize("friend", ["с другом", "с дргуом", "с друагом"])
def test_friend_spelling_retains_group_size_without_assuming_ages(friend):
    result = rule_extract(TripState(), f"Хочу в горы {friend}", TODAY)
    assert result.party_size == 2 and result.adults is None


def test_possible_companion_lodging_and_transport_are_not_confirmed():
    a = agent()
    session = a.new_session()
    first = a.handle(session, "Может горы, возможно с другом, может палатка, может самолет, денег мало")
    assert set(session.state.tentative_fields or []) == {"trip_types", "party_size", "lodging", "transport"}
    assert "возможные варианты" in first.reply
    assert session.state.date_from is None and session.state.nights is None


def test_possible_lodging_is_confirmed_before_a_priced_trip():
    a = agent()
    session = a.new_session()
    first = a.handle(session, "Из Москвы в Казань с 3 по 6 июня 2027 двое взрослых, возможно палатка")
    assert "lodging" in session.state.tentative_fields and first.payload["kind"] == "question"
    assert "размещение" in first.reply
    confirmed = a.handle(session, "отель")
    assert not session.state.tentative_fields and session.state.lodging == "hotel"
    assert confirmed.payload["kind"] == "packages"


def test_tent_can_be_declined_without_silently_switching_to_a_hotel():
    a = agent()
    session = a.new_session()
    a.handle(session, "Хочу горы, возможно палатка")
    a.handle(session, "передумал, без палатки")
    assert session.state.lodging is None and "lodging" in session.state.tentative_fields
    a.handle(session, "из Москвы в Казань с 3 по 6 июня 2027 двое взрослых")
    assert session.state.pending_question == "lodging"
    answer = a.handle(session, "отель")
    assert session.state.lodging == "hotel" and not session.state.tentative_fields
    assert answer.payload["kind"] == "packages"


def test_model_cannot_undo_explicit_tent_refusal():
    state = TripState(lodging="tent")
    text = "без палатки"
    rules = rule_extract(state, text, TODAY)
    result, _ = arbitrate(state, text, TripUpdate(lodging="tent"), rules)
    assert result.lodging is None and "lodging" in result.clear


def test_tent_refusal_is_preserved_when_model_returns_a_different_clear():
    state = TripState(lodging="tent")
    text = "без палатки, бюджет не важен"
    rules = rule_extract(state, text, TODAY)
    result, _ = arbitrate(state, text, TripUpdate(clear=["budget_total"]), rules)
    assert "lodging" in result.clear


def test_tent_idea_is_described_as_possible_when_uncertain():
    a = agent()
    session = a.new_session()
    a.handle(session, "Хочу горы, возможно палатка")
    answer = a.handle(session, "пока не знаю")
    assert "Палатка — пока возможный вариант" in answer.reply


@pytest.mark.parametrize("text", ["Хочу горы и летний вайб, с другом", "Хочу летнее настроение и горы"])
def test_summer_mood_does_not_imply_travel_season(text):
    update = rule_extract(TripState(), text, TODAY)
    assert "warm" in update.trip_types and "mountains" in update.trip_types
    assert update.season is None and update.month is None and update.date_from is None


def test_explicit_summer_is_retained_alongside_a_summer_mood():
    update = rule_extract(TripState(), "Хочу летний вайб, поедем летом", TODAY)
    assert update.season == "summer" and update.month is None


def test_model_summer_date_from_mood_is_not_accepted():
    text = "Хочу горы и летний вайб, с другом"
    state = TripState()
    rules = rule_extract(state, text, TODAY)
    model = TripUpdate(season="summer", month=7, date_from=date(2027, 7, 1))
    result, _ = arbitrate(state, text, model, rules)
    assert result.season is None and result.month is None and result.date_from is None


def test_tent_request_followed_by_only_russia_filters_all_ideas():
    from domains.trips.geo import BY_ID
    a = agent()
    session = a.new_session()
    a.handle(session, "Хочу горы, летний вайб, шашлык, с другом, мало денег, живём в палатках")
    step = a.handle(session, "только Россия")
    assert session.state.abroad is False and session.state.season is None and session.state.lodging == "tent"
    assert step.payload["kind"] == "ideas" and step.payload["items"]
    assert all(not BY_ID[item["id"]].abroad for item in step.payload["items"])


def test_model_cannot_override_explicit_only_russia():
    text = "только Россия"
    state = TripState()
    rules = rule_extract(state, text, TODAY)
    result, _ = arbitrate(state, text, TripUpdate(abroad=True), rules)
    assert result.abroad is False


def test_time_in_transit_question_does_not_create_a_place_or_lose_context():
    a = agent()
    session = a.new_session()
    a.handle(session, "Хочу горы, летний вайб, шашлык, с другом, мало денег, живём в палатках")
    a.handle(session, "только Россия")
    question = a.handle(session, "какое время в пути?")
    assert session.state.destination is None and session.state.dest_id is None and "откуда" in question.reply.lower()
    correction = a.handle(session, "я не говорил про семь ночей")
    assert session.state.destination is None and session.state.abroad is False and session.state.nights is None
    assert correction.payload["kind"] == "ideas" and "пути» пока нет" not in correction.reply


def test_model_cannot_turn_transit_question_into_destination():
    text = "какое время в пути?"
    state = TripState()
    rules = rule_extract(state, text, TODAY)
    result, _ = arbitrate(state, text, TripUpdate(destination="пути"), rules)
    assert result.destination is None and result.unknown_place is None


def test_explicit_travel_question_wins_over_model_misclassification():
    text = "какое время в пути?"
    state = TripState()
    rules = rule_extract(state, text, TODAY)
    result, _ = arbitrate(state, text, TripUpdate(question="weather"), rules)
    assert result.question == "travel"


@pytest.mark.parametrize("text, ages", [
    ("с ребенком, ребенку 6 лет", [6]),
    ("едем с детьми, детям 3 и 9 лет", [3, 9]),
    ("с малышом, малышу 8 месяцев", None),
    ("сыну исполнится 5 лет в июле", None),
])
def test_only_explicit_child_ages_in_years_are_preserved(text, ages):
    update = rule_extract(TripState(), text, TODAY)
    assert update.children_ages == ages


def test_model_cannot_invent_child_age_or_room_count():
    text = "Отдохнем с ребенком"
    state = TripState()
    rules = rule_extract(state, text, TODAY)
    result, _ = arbitrate(state, text, TripUpdate(children_ages=[4], rooms=2), rules)
    assert result.children_ages is None and result.rooms is None and result.children == 1


def test_child_ages_are_not_silently_reused_after_count_changes():
    domain = TripsDomain(today=lambda: TODAY)
    initial = TripState(children=1, children_ages=[6])
    assert domain.merge(initial, TripUpdate(children=2)).children_ages is None
    assert domain.merge(initial, TripUpdate(children=0)).children_ages is None


def test_count_after_known_ages_preserves_them_when_consistent():
    domain = TripsDomain(today=lambda: TODAY)
    initial = TripState(children_unknown=True, children_ages=[3, 9], pending_question="children")
    updated = domain.merge(initial, TripUpdate(children=2))
    assert updated.children == 2 and updated.children_ages == [3, 9]


def test_multiple_rooms_are_preserved_but_not_priced_as_one():
    a = agent()
    session = a.new_session()
    response = a.handle(session, "Из Москвы в Казань с 3 по 6 июня 2027 двое взрослых, нужно 2 номера")
    assert session.state.rooms == 2 and response.payload["kind"] == "question"
    assert "не могу проверить наличие" in response.reply and "несколько номеров" in response.reply
    response = a.handle(session, "один номер")
    assert session.state.rooms == 1 and response.payload["kind"] == "packages"


def test_child_tariff_is_not_claimed_to_be_verified():
    a = agent()
    session = a.new_session()
    response = a.handle(session, "Из Москвы в Казань с 3 по 6 июня 2027 двое взрослых с ребенком, ребенку 6 лет")
    assert session.state.children_ages == [6]
    assert response.payload["kind"] == "packages" and "льготы для детей по возрасту не проверены" in response.reply


def test_child_age_without_a_separate_count_does_not_price_as_no_children():
    a = agent()
    session = a.new_session()
    answer = a.handle(session, "Из Москвы в Казань с 3 по 6 июня 2027 двое взрослых, ребенку 6 лет")
    assert session.state.children == 1 and session.state.children_ages == [6]
    assert answer.payload["kind"] == "packages" and "льготы для детей по возрасту не проверены" in answer.reply


def test_named_ages_do_not_assume_there_are_only_two_children():
    update = rule_extract(TripState(), "Едем с детьми, детям 3 и 9 лет", TODAY)
    assert update.children is None and update.children_unknown and update.children_ages == [3, 9]


def test_stated_number_and_ages_of_children_are_preserved_separately():
    update = rule_extract(TripState(), "Двое взрослых, двое детей 3 и 9 лет", TODAY)
    assert update.adults == 2 and update.children == 2 and update.children_ages == [3, 9]


@pytest.mark.parametrize("text", ["ыщыр шрж шрж", "какой вкус у луны?", "расскажи анекдот",
                                  "летающий кот играет в шахматы"])
def test_gibberish_and_off_topic_text_does_not_invent_a_trip(text):
    a = agent()
    session = a.new_session()
    response = a.handle(session, text)
    assert not session.state.params().model_dump(exclude_none=True)
    assert response.payload["kind"] == "greeting" and "поездк" in response.reply


def test_gibberish_does_not_erase_a_pending_question_or_trip_details():
    a = agent()
    session = a.new_session()
    a.handle(session, "В Казань с 3 по 6 июня 2027 двое взрослых")
    assert session.state.pending_question == "origin"
    answer = a.handle(session, "летающий кот играет в шахматы")
    assert session.state.pending_question == "origin" and session.state.dest_id == "kazan"
    assert "Не понял" in answer.reply and "города" in answer.reply
    assert a.handle(session, "из Москвы").payload["kind"] == "packages"


@pytest.mark.parametrize("text, expected", [
    ("На всю поездку до 80000 рублей, отель до 6000 рублей за ночь", (80000, 6000)),
    ("Бюджет 120 тысяч и на отель 7 тысяч за ночь", (120000, 7000)),
    ("Не дороже 5 тысяч в сутки", (None, 5000)),
    ("На всё до 90 тысяч, проживание на 4 ночи", (90000, None)),
])
def test_total_and_nightly_budgets_keep_their_own_amounts(text, expected):
    assert parse_budget_scopes(text) == expected


def test_remove_breakfast_requirement_without_forgetting_the_trip():
    a = agent()
    session = a.new_session()
    a.handle(session, "Из Москвы в Казань с 3 по 6 июня 2027 двое взрослых, нужен завтрак")
    a.handle(session, "Передумал, завтрак не нужен")
    assert session.state.meal is None
    assert session.state.dest_id == "kazan" and session.state.origin == "Москва"


def test_model_budget_is_overruled_by_separately_extracted_scopes():
    text = "На всю поездку до 80000 рублей, отель до 6000 рублей за ночь"
    state = TripState()
    rules = rule_extract(state, text, TODAY)
    result, _ = arbitrate(state, text, TripUpdate(budget_night=80000), rules)
    assert result.budget_total == 80000 and result.budget_night == 6000


def test_hotel_list_and_transfer_answer_disclose_demonstration_data():
    a = agent()
    session = a.new_session()
    a.handle(session, "Из Москвы в Ярославль с 10 по 14 июля 2027 двое взрослых, поездом")
    hotels = a.handle(session, "покажи другие отели")
    assert hotels.payload["kind"] == "hotels" and "демонстрационные" in hotels.reply
    a.handle(session, "первый")
    transfer = a.handle(session, "Какой трансфер до отеля?")
    assert "демо-трансфер" in transfer.reply.lower() and "смоделированы" in transfer.reply


class FakeLLM:
    def __init__(self, replies):
        self.replies = iter(replies)

    def complete(self, messages, **kwargs):
        result = next(self.replies)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.parametrize("responses", [
    [TimeoutError("offline")],
    ["not-json", "also not-json"],
    [json.dumps({"month": 13}), json.dumps({"month": 13})],
])
def test_model_failure_falls_back_to_rules_without_losing_user_values(responses):
    a = agent(FakeLLM(responses))
    session = a.new_session()
    step = a.handle(session, "Хочу в Сочи летом с другом")
    assert session.last_nlu == "rules"
    assert session.state.dest_id == "sochi" and session.state.season == "summer"
    assert session.state.month is None and session.state.party_size == 2 and session.state.adults is None
    assert "июнь" in step.reply and "август" in step.reply


def test_extraction_evaluation_marks_unavailable_model_incomplete(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from eval import extraction_new_20261027 as evaluation

    class Unavailable:
        breaker = None

        def complete(self, messages, **kwargs):
            raise TimeoutError("offline")

    output = tmp_path / "incomplete.json"
    monkeypatch.setattr(evaluation, "get_settings", lambda: SimpleNamespace(
        llm_enabled=True, llm_provider="test", llm_model="unavailable"))
    monkeypatch.setattr(evaluation, "build_llm", lambda settings: Unavailable())
    monkeypatch.setattr(sys, "argv", ["extraction", "--output", str(output)])
    assert evaluation.main() == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "incomplete" and report["completed"] == 0
    assert report["calls"] == 1 and report["request_errors"] == 1
    assert report["cases"][0]["status"] == "INCOMPLETE"
