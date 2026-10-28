from datetime import date

import pytest

from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.providers.ostrovok import RoomGuests, SearchQuery
from domains.trips.service_search import parse_room_allocations
from domains.trips.textparse import parse_dates

TODAY = date(2026, 10, 28)


def agent():
    return Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)


def test_official_occupancy_contract_two_different_rooms():
    q = SearchQuery(checkin=date(2027, 1, 1), checkout=date(2027, 1, 5), latitude=55, longitude=37,
                    rooms=(RoomGuests(2), RoomGuests(2, (7,))))
    assert q.body()["guests"] == [{"adults": 2, "children": []}, {"adults": 2, "children": [7]}]


def test_multiroom_adapter_sends_exact_allocations_and_marks_price_preliminary():
    import json
    import httpx
    from domains.trips.providers.ostrovok import OstrovokSearchClient

    q = SearchQuery(checkin=date(2027, 1, 1), checkout=date(2027, 1, 5), latitude=55, longitude=37,
                    rooms=(RoomGuests(2), RoomGuests(2, (7,))))
    def receive(req):
        assert json.loads(req.content)["guests"] == [{"adults": 2, "children": []}, {"adults": 2, "children": [7]}]
        return httpx.Response(200, json={"status": "ok", "data": {"hotels": [{"hid": 123, "rates": [
            {"payment_options": {"payment_types": [{"show_amount": "250", "show_currency_code": "RUB"}]}}
        ]}]}})
    result = OstrovokSearchClient("fixture", "fixture", httpx.MockTransport(receive)).search(q)
    assert len(result) == 1 and result[0].requires_revalidation


@pytest.mark.parametrize("rooms", [tuple(RoomGuests(1) for _ in range(10)), (RoomGuests(7),),
                                  (RoomGuests(1, (1, 2, 3, 4, 5)),), (RoomGuests(1, (18,)),)])
def test_official_occupancy_limits(rooms):
    with pytest.raises(ValueError):
        SearchQuery(checkin=date(2027, 1, 1), checkout=date(2027, 1, 5), latitude=55, longitude=37, rooms=rooms).body()


def test_ambiguous_flat_and_room_occupancy_is_rejected():
    with pytest.raises(ValueError):
        SearchQuery(checkin=date(2027, 1, 1), checkout=date(2027, 1, 5), latitude=55, longitude=37,
                    adults=2, rooms=(RoomGuests(2), RoomGuests(1))).body()


def test_ambiguous_or_missing_child_age_is_not_silently_dropped():
    assert [r.model_dump() for r in parse_room_allocations("номер 1: 2 взрослых, ребёнок 7 лет; номер 2: 1 взрослый")] == [
        {"adults": 2, "children_ages": [7]}, {"adults": 1, "children_ages": []}]
    assert parse_room_allocations("номер 1: 2 взрослых, 2 детей; номер 2: 1 взрослый") is None
    assert parse_room_allocations("номер 1: 2 взрослых; номер 1: 1 взрослый") is None
    assert parse_room_allocations("номер 1: 2 взрослых, не ребенок 7 лет; номер 2: 1 взрослый") is None


def test_explicit_room_response_does_not_send_ages_to_llm():
    from domains.trips.state import TripState
    from tests.conftest import FakeLLM
    llm = FakeLLM({"adults": 99})
    a = Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY)
    s = a.new_session()
    s.state = TripState(rooms=2, pending_question="room_allocation")
    update, source = a._understand(s, "номер 1: 2 взрослых, ребёнок 7 лет; номер 2: 1 взрослый")
    assert source == "rules" and not llm.calls
    assert update.room_allocations[0].children_ages == [7]


def test_hotel_only_two_rooms_are_calculated_separately():
    a, s = agent(), agent().new_session()
    result = a.handle(s, "Только отель в Казани с 10 по 15 декабря 2026, 3 взрослых и ребенок, 2 номера")
    assert result.payload["field"] == "room_allocation"
    result = a.handle(s, "номер 1: 2 взрослых, ребёнок 7 лет; номер 2: 1 взрослый")
    assert result.payload["kind"] == "service_results"
    assert "за все номера" in result.reply and "наличие" in result.reply.lower()
    assert [x.adults for x in s.state.room_allocations] == [2, 1]


def test_hotel_only_unknown_child_age_is_asked_not_invented():
    a, s = agent(), agent().new_session()
    result = a.handle(s, "Только отель в Казани с 10 по 15 декабря 2026, 2 взрослых и ребенок")
    assert result.payload["field"] == "children_ages"
    result = a.handle(s, "7 лет")
    assert result.payload["kind"] == "service_results"


def test_transfer_only_collects_route_time_without_creating_real_order():
    a, s = agent(), agent().new_session()
    result = a.handle(s, "Нужен трансфер в Сочи из аэропорта в отель завтра в 14:30, 2 человека в одну сторону")
    assert s.state.search_scope == "transfer_only"
    assert result.payload["kind"] == "service_results"
    assert "не заказ" in result.reply and "14:30" in result.reply and "29.10.2026" in result.reply
    assert s.state.order is None


def test_transfer_date_does_not_overwrite_or_assume_hotel_dates():
    from domains.trips.state import TripState
    a, s = agent(), agent().new_session()
    s.state = TripState(search_scope="transfer_only", dest_id="sochi", destination="Сочи",
                        date_from=date(2026, 12, 10), date_to=date(2026, 12, 15),
                        transfer_from="airport", transfer_to="hotel", transfer_direction="one_way")
    result = a.handle(s, "Нужен трансфер")
    assert result.payload["field"] == "transfer_date"
    a.handle(s, "завтра")
    assert s.state.transfer_date == date(2026, 10, 29)
    assert s.state.date_from == date(2026, 12, 10) and s.state.date_to == date(2026, 12, 15)


def test_model_cannot_apply_transfer_date_to_hotel_stay():
    from domains.trips.arbiter import arbitrate
    from domains.trips.rules import rule_extract
    from domains.trips.state import TripState, TripUpdate
    state = TripState(search_scope="transfer_only", date_from=date(2026, 12, 10), date_to=date(2026, 12, 15))
    text = "на 01.11.2026"
    rules = rule_extract(state, text, TODAY)
    result, _ = arbitrate(state, text, TripUpdate(date_from=date(2026, 11, 1),
                                                  evidence={"date_from": "01.11.2026"}), rules)
    assert result.transfer_date == date(2026, 11, 1)
    assert result.date_from is None and result.date_to is None


def test_hotel_only_does_not_add_an_ip_departure_city(monkeypatch):
    from fastapi.testclient import TestClient
    from apps import web
    monkeypatch.setattr(web, "visitor_city", lambda *args, **kwargs: {"city_name": "Москва", "origin": "Москва"})
    with TestClient(web.build_app(agent())) as client:
        response = client.post("/api/chat", json={"text": "Только отель в Казани"}).json()
    assert "предположительно" not in response["reply"]
    assert not any("из: Москва" in chip for chip in response["understood"])


def test_hotel_room_allocation_can_be_undone_without_erasing_the_query():
    from fastapi.testclient import TestClient
    from apps.web import build_app
    with TestClient(build_app(agent())) as client:
        first = client.post("/api/chat", json={"text": "Только отель в Казани с 10 по 15 декабря 2026, "
                                                       "3 взрослых и ребенок, 2 номера"}).json()
        second = client.post("/api/chat", json={"session_id": first["session_id"],
            "text": "номер 1: 2 взрослых, ребёнок 7 лет; номер 2: 1 взрослый"}).json()
        assert second["can_undo"] and second["payload"]["kind"] == "service_results"
        undone = client.post("/api/chat/undo", json={"session_id": second["session_id"],
                                                      "revision": second["revision"]}).json()
        assert undone["payload"]["field"] == "room_allocation"
        assert "распределение по номерам указано" not in undone["understood"]


def test_two_hotels_are_not_treated_as_two_rooms():
    a, s = agent(), agent().new_session()
    result = a.handle(s, "Хочу два отеля в Сочи")
    assert s.state.search_scope == "multi_hotel" and s.state.rooms is None
    assert "сравнить" in result.reply
    a.handle(s, "сравнить")
    assert s.state.search_scope == "hotel_only"


def test_two_sequential_hotels_can_be_compared_and_selected():
    a, s = agent(), agent().new_session()
    a.handle(s, "Хочу два отеля в Сочи")
    step = a.handle(s, "по очереди")
    assert step.payload["field"] == "split_stays"
    step = a.handle(s, "1: Казань 10.12.2026–12.12.2026; 2: Сочи 12.12.2026–15.12.2026")
    assert step.payload["field"] == "people"
    step = a.handle(s, "2 взрослых")
    assert step.payload["kind"] == "service_results" and "переезд между отелями не рассчитан" in step.reply
    assert len(s.state.split_displayed) > 0
    step = a.handle(s, "1")
    assert "Выбрана пара" in step.reply and "бронирование" in step.reply


def test_split_stays_with_gap_are_not_accepted():
    from domains.trips.service_search import parse_split_stays
    assert parse_split_stays("1: Казань 10.12.2026–12.12.2026; 2: Сочи 13.12.2026–15.12.2026", TODAY) is None


def test_split_choice_rechecks_exact_displayed_pairs():
    from domains.trips.service_search import split_hotels
    from domains.trips.state import StaySegment, TripState
    state = TripState(search_scope="split_hotel", adults=2, split_stays=[
        StaySegment(dest_id="kazan", checkin=date(2026, 12, 10), checkout=date(2026, 12, 12)),
        StaySegment(dest_id="sochi", checkin=date(2026, 12, 12), checkout=date(2026, 12, 15)),
    ])
    split_hotels(state, TODAY)
    state.split_displayed[0]["hotel_ids"][0] = "changed"
    state.split_choice = 1
    reply = split_hotels(state, TODAY).reply
    assert "изменились" in reply and "Выбрана пара" not in reply


@pytest.mark.parametrize("text,expected", [("после завтра", date(2026, 10, 30)), ("завтро", date(2026, 10, 29))])
def test_unambiguous_relative_date_typos(text, expected):
    assert parse_dates(text, TODAY)[0] == expected


def test_negated_tomorrow_is_not_accepted_as_departure():
    from domains.trips.rules import rule_extract
    from domains.trips.state import TripState
    parsed = rule_extract(TripState(), "не завтра, а в следующем месяце", TODAY)
    assert parsed.date_from is None and parsed.month == 11 and parsed.year == 2026
    assert parse_dates("завтра не могу", TODAY)[0] is None
    assert parse_dates("не завтра, а послезавтра", TODAY)[0] == date(2026, 10, 30)


def test_next_month_crosses_year_without_assuming_a_day():
    from domains.trips.rules import rule_extract
    from domains.trips.state import TripState
    parsed = rule_extract(TripState(), "в следующем месяце", date(2026, 12, 30))
    assert (parsed.year, parsed.month, parsed.date_from) == (2027, 1, None)


def test_limited_english_relative_dates_preserve_negation():
    from domains.trips.rules import rule_extract
    from domains.trips.state import TripState
    assert rule_extract(TripState(), "tomorrow", TODAY).date_from == date(2026, 10, 29)
    assert rule_extract(TripState(), "not tomorrow", TODAY).date_from is None
    assert rule_extract(TripState(), "next month", TODAY).month == 11
    assert rule_extract(TripState(), "not next month", TODAY).month is None
    assert rule_extract(TripState(), "не в следующем месяце", TODAY).month is None


def test_flight_business_is_not_silently_replaced_with_economy():
    a, s = agent(), agent().new_session()
    result = a.handle(s, "Только перелёт из Москвы в Казань 10 декабря 2026 в одну сторону бизнес-класс")
    assert s.state.seat_class == "бизнес"
    assert "нет перелётов" in result.reply and "бизнес" in result.reply


def test_train_only_does_not_turn_no_hotel_into_a_tent():
    a, s = agent(), agent().new_session()
    result = a.handle(s, "Только билет на поезд из Москвы в Казань 10 декабря 2026 в одну сторону без отеля")
    assert s.state.search_scope == "train_only" and s.state.lodging is None
    assert result.payload["kind"] == "flight_results"
    assert "Демонстрационные поезда" in result.reply


def test_question_about_business_is_not_a_hard_constraint():
    from domains.trips.rules import rule_extract
    from domains.trips.state import TripState
    assert rule_extract(TripState(), "Есть бизнес-класс?", TODAY).seat_class is None


def test_two_rooms_in_a_full_trip_require_explicit_distribution():
    a, s = agent(), agent().new_session()
    response = a.handle(s, "Из Москвы в Казань с 3 по 6 июня 2027 3 взрослых, 2 номера")
    assert response.payload["field"] == "room_allocation"
    response = a.handle(s, "номер 1: 2 взрослых; номер 2: 1 взрослый")
    assert response.payload["kind"] == "packages"
    assert "Рассчитано 2 номеров" in response.reply


def test_invalid_occupancy_does_not_reach_calculation():
    a, s = agent(), agent().new_session()
    a.handle(s, "Только отель в Казани с 10 по 15 декабря 2026, 3 взрослых и ребенок, 2 номера")
    result = a.handle(s, "номер 1: 2 взрослых, ребенок 7 лет; номер 2: 2 взрослых")
    assert result.payload["field"] == "room_allocation"
    assert "не совпадает" in result.reply


def test_multiroom_price_is_sum_of_each_room():
    from domains.trips.geo import BY_ID, ORIGIN_BY_NAME
    from domains.trips.offers import hotels_for, hotel_price
    from domains.trips.planner import Trip, _stay_price
    day = date(2027, 6, 3)
    trip = Trip(ORIGIN_BY_NAME["Москва"], BY_ID["kazan"], day, date(2027, 6, 6), 3, 1,
                room_guests=[(2, 1), (1, 0)])
    h = hotels_for("kazan")[0]
    assert _stay_price(h, trip, day, 3) == hotel_price(h, day, 3, 2, 1) + hotel_price(h, day, 3, 1, 0)


def test_nightly_budget_is_checked_for_each_night_not_average(monkeypatch):
    from datetime import timedelta
    from domains.trips import service_search
    from domains.trips.offers import hotels_for, hotel_price
    from domains.trips.state import RoomAllocation, TripState
    h = hotels_for("kazan")[0]
    start = date(2027, 6, 3)
    room = RoomAllocation(adults=2)
    nightly = [hotel_price(h, start + timedelta(days=i), 1, 2, 0) for i in range(4)]
    assert max(nightly) > min(nightly)
    monkeypatch.setattr(service_search, "hotels_for", lambda _: [h])
    state = TripState(budget_night=min(nightly))
    assert service_search._stay_candidates(state, "kazan", start, start + timedelta(days=4), [room]) == []


def test_child_fare_kinds_require_provider_prices_and_do_not_infer_from_age():
    from decimal import Decimal
    from domains.trips.fares import FareKind, PassengerFare, total_confirmed_fares
    adult = PassengerFare(FareKind.ADULT, Decimal("100"), "RUB", "fixture")
    child = PassengerFare(FareKind.CHILD_DISCOUNTED, Decimal("50"), "RUB", "fixture", True)
    infant = PassengerFare(FareKind.CHILD_FREE, Decimal("0"), "RUB", "fixture", False)
    assert total_confirmed_fares([adult, child, infant]) == (Decimal("150"), "RUB")
    assert total_confirmed_fares([adult, PassengerFare(FareKind.UNKNOWN, None, None, None)]) is None
    with pytest.raises(ValueError):
        PassengerFare(FareKind.CHILD_FREE, Decimal("10"), "RUB", "fixture")


def test_child_fare_question_does_not_invent_a_traveller_or_price():
    a, s = agent(), agent().new_session()
    result = a.handle(s, "Ребёнку 7 лет билет бесплатный?")
    assert s.state.children is None
    assert "бесплатным, со скидкой или по полному" in result.reply
    assert "не провер" in result.reply or "нет" in result.reply


@pytest.mark.parametrize("text,topic", [
    ("где перекусить недорого?", "food"), ("куда пойти вечером танцевать?", "nightlife"),
    ("где купить сувениры?", "shopping"), ("where to eat?", "food"),
    ("какие достопримичательности посмотреть?", "sights"),
])
def test_natural_guide_questions_remain_questions(text, topic):
    from domains.trips.rules import rule_extract
    from domains.trips.state import TripState
    found = rule_extract(TripState(dest_id="kazan", destination="Казань"), text, TODAY)
    assert topic in (found.question or "").split("|")
