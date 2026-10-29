"""Multi-turn family, pregnancy, senior, animal and dietary requests."""
from datetime import date
import json

import pytest

from core.agent import Agent
from domains.trips.accessibility import classify
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.service_search import parse_room_allocations
from domains.trips.state import RoomAllocation, TripState
from tests.conftest import FakeLLM

TODAY = date(2026, 10, 29)


def agent(llm=None):
    return Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY, nlg=False)


def test_ages_answer_count_question_without_guessing_children_in_adult_only_trip():
    a = agent()
    s = a.new_session()
    a.handle(s, "В Сочи из Москвы 10–15 декабря 2027, 2 взрослых и дети")
    assert s.state.pending_question == "children"
    result = a.handle(s, "детям 2 и 7 лет")
    assert s.state.children == 2 and s.state.children_ages == [2, 7]
    assert result.payload["kind"] == "packages" and "детск" in result.reply.lower()
    assert "не подтверждён на даты" in result.reply


@pytest.mark.parametrize("answer", ["2 и 7 лет", "2 и 7 лет."])
def test_short_age_answer_to_child_count_stays_local(answer):
    model = FakeLLM({})
    a = agent(model)
    s = a.new_session()
    a.handle(s, "В Сочи из Москвы 10–15 декабря 2027, 2 взрослых и дети")
    model.calls.clear()
    a.handle(s, answer)
    assert s.state.children_ages == [2, 7] and s.last_input_sensitive and not model.calls


def test_room_allocation_ages_are_not_forwarded_in_later_model_context():
    domain = TripsDomain(today=lambda: TODAY)
    state = TripState(children=1, children_ages=[13], rooms=2,
                      room_allocations=[RoomAllocation(adults=1, children_ages=[13]), RoomAllocation(adults=1)])
    system = domain.extraction_messages(state, [], "добавьте бассейн", TODAY)[0]["content"]
    state_in_prompt = json.loads(system.split("Уже известно: ", 1)[1].split("\n", 1)[0])
    assert "room_allocations" not in state_in_prompt and "children_ages" not in state_in_prompt


def test_current_infant_age_is_not_assumed_to_be_the_age_at_a_future_hotel():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Только отель в Казани с 10 по 15 декабря 2027, 2 взрослых, ребёнку 8 месяцев")
    assert s.state.child_age_months == 8 and s.state.child_age_basis == "current"
    assert s.state.children_ages is None and result.payload["field"] == "children_ages"
    result = a.handle(s, "на дату заезда 18 месяцев")
    assert s.state.child_age_months == 18 and s.state.children_ages == [1]
    assert s.state.child_age_basis == "checkin" and result.payload["kind"] == "service_results"
    assert "льготы не проверены" in result.reply.lower() and s.last_input_sensitive


def test_two_child_ages_with_mixed_units_do_not_become_a_free_fare():
    a = agent()
    s = a.new_session()
    a.handle(s, "В Сочи из Москвы 10–15 декабря 2027, 2 взрослых и дети")
    result = a.handle(s, "детям 8 месяцев и 7 лет")
    assert s.state.children == 2 and s.state.children_ages == [0, 7]
    assert s.state.children_age_months_by_child == [8, None]
    assert s.state.child_age_basis == "unspecified"
    assert "детск" in result.reply.lower() and "не проверены" in result.reply.lower()


def test_hotel_accepts_multiple_child_ages_in_years_and_months_at_checkin():
    from apps.web import understood
    a = agent()
    s = a.new_session()
    question = a.handle(s, "Только отель в Казани с 10 по 15 декабря 2027, 2 взрослых, 2 ребенка")
    assert question.payload["field"] == "children_ages" and "в месяцах" in question.reply
    result = a.handle(s, "8 месяцев и 7 лет")
    assert s.state.children_ages == [0, 7] and s.state.children_age_months_by_child == [8, None]
    assert s.state.child_age_basis == "checkin" and s.last_input_sensitive
    assert result.payload["kind"] == "service_results"
    assert any("8 мес., 7 лет (на дату заезда)" in chip for chip in understood(s.state))


def test_unqualified_child_age_is_clarified_without_silently_keeping_old_age():
    a = agent()
    s = a.new_session()
    a.handle(s, "В Казань из Москвы 10–15 декабря 2027, 2 взрослых и ребенок 7 лет")
    result = a.handle(s, "ребенку будет 8 на дату поездки")
    assert result.payload["field"] == "children_age_unit" and s.state.children_ages == [7]
    a.handle(s, "лет")
    assert s.state.children_ages == [8] and s.state.child_age_basis == "checkin"


def test_child_age_unit_months_preserves_the_explicit_future_age():
    a = agent()
    s = a.new_session()
    a.handle(s, "В Казань из Москвы 10–15 декабря 2027, 2 взрослых и ребенок 7 лет")
    a.handle(s, "ребенку будет 8 на дату поездки")
    a.handle(s, "месяцев")
    assert s.state.child_age_months == 8 and s.state.children_ages == [0] and s.state.child_age_basis == "checkin"


def test_room_allocation_accepts_infant_months_for_age_at_checkin():
    rooms = parse_room_allocations("номер 1: 2 взрослых, ребёнок 8 месяцев; номер 2: 1 взрослый")
    assert rooms and rooms[0].children_ages == [0] and rooms[1].children_ages == []
    assert parse_room_allocations("номер 1: 2 взрослых, ребёнок 216 месяцев; номер 2: 1 взрослый") is None


def test_pregnancy_weeks_are_not_trip_duration_or_stored_medical_history():
    model = FakeLLM({})
    a = agent(model)
    s = a.new_session()
    first = a.handle(s, "Я беременна, 24 недели, хочу в Сочи на неделю")
    assert s.state.nights == 7 and s.state.travel_needs == ["pregnancy"]
    assert s.last_input_sensitive and not model.calls and s.state.asked_text is None
    assert "24" not in s.state.model_dump_json() and "24 недели" not in repr(vars(s.vault))
    assert "врач" in first.reply.lower() and "не проверены" in first.reply.lower()
    a.handle(s, "в июне")
    assert model.calls and "pregnancy" not in json.dumps(model.calls, ensure_ascii=False)
    assert s.state.travel_needs == ["pregnancy"]
    a.handle(s, "я не беременна")
    assert not s.state.travel_needs


@pytest.mark.parametrize("message,nights", [
    ("24-я неделя беременности, хочу в Сочи на 5 ночей", 5),
    ("у меня 20 недель беременности, хочу в Сочи на 3 ночи", 3),
])
def test_gestation_week_is_not_mistaken_for_trip_length(message, nights):
    a = agent()
    s = a.new_session()
    a.handle(s, message)
    assert s.state.nights == nights and s.state.travel_needs == ["pregnancy"]
    assert s.last_input_sensitive


def test_general_pregnancy_question_does_not_claim_person_is_pregnant_or_safe_to_fly():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Можно ли беременным лететь?")
    assert not s.state.travel_needs and "не могу оценить безопасность" in result.reply.lower()
    assert "врач" in result.reply.lower() and "страхов" in result.reply.lower()


def test_older_traveller_does_not_imply_a_mobility_problem():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Ищу поездку для пожилой мамы в Казань")
    assert s.state.travel_needs == ["older_traveler"]
    assert not s.state.accessibility_needs and not s.state.direct_only
    assert "не задают ограничений" in result.reply


def test_hotel_for_older_traveller_does_not_require_a_departure_city():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Для пожилой мамы нужен отель без лестниц в Казани")
    assert s.state.search_scope == "hotel_only" and "step_free" in s.state.accessibility_needs
    assert result.payload["field"] == "when" and s.state.origin is None


def test_retiree_status_does_not_automatically_mean_old_age_or_discount():
    a = agent()
    s = a.new_session()
    a.handle(s, "Я пенсионер, хочу в Казань")
    assert "retiree" in s.state.travel_needs and "older_traveler" not in s.state.travel_needs
    assert not s.state.accessibility_needs and s.state.budget_total is None
    answer = a.handle(s, "Есть ли скидка пенсионерам на поезд?")
    assert "скидки сейчас нет" in answer.reply.lower() and "к демоценам" in answer.reply.lower()


def test_senior_fare_question_does_not_create_a_retiree():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Есть ли скидка пенсионерам на поезд в Казань?")
    assert not s.state.travel_needs and "льготы" in result.reply.lower()
    assert "не применена" in result.reply.lower()


def test_multiple_foods_add_and_remove_individually_without_inventing_safety():
    a = agent()
    s = a.new_session()
    a.handle(s, "Хочу в Сочи, аллергия на арахис и молоко")
    assert set(s.state.accessibility_needs) == {"diet_peanuts", "diet_milk"}
    a.handle(s, "ещё исключить кунжут")
    assert set(s.state.accessibility_needs) == {"diet_peanuts", "diet_milk", "diet_sesame"}
    result = a.handle(s, "арахис больше можно")
    assert set(s.state.accessibility_needs) == {"diet_milk", "diet_sesame"}
    assert "не отобраны" in result.reply and "перекрёстного" in result.reply


def test_unrecognized_food_after_known_one_is_not_silently_dropped():
    add, _ = classify("аллергия на арахис и манго")
    assert "diet_peanuts" in add and "dietary" in add


def test_vegan_and_exclusions_are_preferences_not_an_assumed_allergy():
    add, _ = classify("Подбери веганское питание без мяса и рыбы")
    assert {"diet_vegan", "diet_meat", "diet_fish"} <= add
    assert not classify("На завтрак каша на молоке, потом на рыбалку")[0]


def test_vegan_preference_can_be_removed_in_follow_up():
    a = agent()
    s = a.new_session()
    a.handle(s, "Хочу в Казань, веганское питание")
    assert "diet_vegan" in s.state.accessibility_needs
    a.handle(s, "не веганское питание")
    assert "diet_vegan" not in (s.state.accessibility_needs or [])


def test_child_equipment_and_senior_discount_can_be_removed_individually():
    a = agent()
    s = a.new_session()
    a.handle(s, "Я пенсионер, нужна льгота и детское автокресло, еду в Казань")
    assert {"retiree", "senior_fare", "child_seat"} <= set(s.state.travel_needs)
    a.handle(s, "автокресло не нужно")
    assert "child_seat" not in s.state.travel_needs and "senior_fare" in s.state.travel_needs
    a.handle(s, "скидка не нужна")
    assert s.state.travel_needs == ["retiree"]


def test_single_pet_weight_and_cabin_are_preserved_changed_and_removed():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Нужен перелёт из Москвы в Казань 10.12.2027 с собакой 9 кг в салоне в одну сторону")
    assert s.state.pet_types == ["dog"] and s.state.pet_weight_kg == 9 and s.state.pet_cabin is True
    assert "не проверены" in result.reply and "запрос не отправлен" in result.reply
    assert "до 8 кг" not in result.reply and "в багажном отсеке" not in result.reply
    a.handle(s, "собака 4 кг")
    assert s.state.pet_weight_kg == 4 and s.state.pet_cabin is True
    a.handle(s, "без собаки")
    assert s.state.pets is False and s.state.pet_types is None and s.state.pet_weight_kg is None and s.state.pet_cabin is None


def test_persons_weight_is_not_assigned_to_the_pet():
    a = agent()
    s = a.new_session()
    a.handle(s, "Хочу в Казань с собакой, я вешу 70 кг")
    assert s.state.pets is True and s.state.pet_weight_kg is None
    assert s.last_input_sensitive


def test_luggage_in_cabin_is_not_silently_a_pet_cabin_request():
    a = agent()
    s = a.new_session()
    a.handle(s, "В Казань с собакой и багажом в салоне")
    assert s.state.pets is True and s.state.pet_cabin is None


def test_guide_dog_and_cat_remain_different_requirements():
    a = agent()
    s = a.new_session()
    a.handle(s, "Едем с собакой-проводником и кошкой")
    assert "guide_dog" in s.state.accessibility_needs
    assert s.state.pets is True and s.state.pet_types == ["cat"]


def test_removing_one_kind_of_pet_preserves_the_other():
    a = agent()
    s = a.new_session()
    a.handle(s, "Хочу в Казань с собакой и с кошкой")
    assert set(s.state.pet_types) == {"dog", "cat"}
    a.handle(s, "без собаки")
    assert s.state.pets is True and s.state.pet_types == ["cat"]
    a.handle(s, "без кошки")
    assert s.state.pets is False and not s.state.pet_types


def test_multiple_pets_are_not_given_one_unverified_weight():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "В Казань с двумя собаками, одна собака 4 кг")
    assert s.state.pets is True and s.state.pet_count == 2 and s.state.pet_weight_kg is None
    assert s.state.adults is None and s.state.party_size is None
    assert "отдельно не сохраняются" in result.reply


def test_different_pets_do_not_share_one_species_count_or_cabin_preference():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "В Казань с двумя собаками и кошкой, собака 4 кг в салоне")
    assert set(s.state.pet_types) == {"dog", "cat"}
    assert s.state.pet_count is None and s.state.pet_weight_kg is None and s.state.pet_cabin is None
    assert s.state.adults is None and "отдельно не сохраняются" in result.reply
    a.handle(s, "собака 5 кг")
    assert set(s.state.pet_types) == {"dog", "cat"} and s.state.pet_weight_kg is None


def test_multiple_pets_do_not_inherit_single_pets_cabin_preference():
    a = agent()
    s = a.new_session()
    a.handle(s, "В Казань с собакой 4 кг в салоне")
    assert s.state.pet_cabin is True
    a.handle(s, "две собаки")
    assert s.state.pet_count == 2 and s.state.pet_cabin is None and s.state.pet_weight_kg is None


def test_hypothetical_pet_question_does_not_create_a_pet():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Можно ли остановиться с собакой?")
    assert s.state.pets is None and not s.state.pet_types
    assert "проверенных условий" in result.reply


def test_cat_hotel_query_is_not_treated_as_a_hotel_name():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Ищу отель в Казани с кошкой")
    assert s.state.search_scope == "hotel_only" and s.state.pet_types == ["cat"]
    assert result.payload["field"] == "when"
    a.handle(s, "это кот 5 кг")
    assert s.state.pet_weight_kg == 5


def test_pet_transport_does_not_impose_a_universal_eight_kilo_rule():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Из Москвы в Казань 10–15 декабря 2027, 2 взрослых с собакой")
    assert result.payload["kind"] == "packages"
    assert "до 8 кг" not in result.reply and "иначе в багажном отсеке" not in result.reply
    assert "не проверены" in result.reply


def test_trip_without_pets_does_not_introduce_an_animal():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Из Москвы в Казань 10–15 декабря 2027, 2 взрослых")
    assert result.payload["kind"] == "packages"
    assert "животн" not in result.reply.lower() and "питом" not in result.reply.lower()


def test_explicit_child_seat_and_cot_do_not_assume_their_availability():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Нужен трансфер в Сочи из аэропорта в отель завтра в 14:30, 2 человека в одну сторону, детское автокресло")
    assert "child_seat" in s.state.travel_needs and result.payload["kind"] == "service_results"
    assert "наличие" in result.reply.lower() and "подтвердить" in result.reply.lower()
    assert s.state.children is None


def test_unaccompanied_minor_is_not_given_an_invented_adult_or_service():
    a = agent()
    s = a.new_session()
    result = a.handle(s, "Только перелёт из Москвы в Казань 10.12.2027 в одну сторону, ребёнок 12 лет летит один")
    assert s.state.children == 1 and s.state.adults is None
    assert "unaccompanied_minor" in s.state.travel_needs
    assert "сопровождающего" in result.reply and "не проверены" in result.reply
