from datetime import date

import pytest
from fastapi.testclient import TestClient

from apps.web import build_app
from core.agent import Agent
from domains.trips.climate import climate
from domains.trips.domain import GREETING, TripsDomain
from domains.trips.geo import BY_ID, ORIGIN_BY_NAME
from domains.trips.inspire import suggest
from domains.trips.offers import hotels_for, transport_options
from domains.trips.planner import Trip, make_packages
from domains.trips.rules import rule_extract
from domains.trips.state import TripState
from tests.conftest import FakeLLM

SAT = date(2026, 10, 24)  # суббота
MOSCOW = ORIGIN_BY_NAME["Москва"]


def agent(llm=None):
    return Agent(TripsDomain(today=lambda: SAT), llm, today=lambda: SAT)


def talk(a, *messages):
    s = a.new_session()
    # The planner cases below start with these known preferences. Separate
    # dialogue tests verify that the actual app asks when they are missing.
    s.state.origin, s.state.adults = "Москва", 2
    step = None
    for m in messages:
        step = a.handle(s, m)
    return s, step


def test_climate_is_real_data_for_every_destination():
    for dest_id in BY_ID:
        assert climate(dest_id, 1) is not None
    assert climate("hurghada", 11).beach_ok and not climate("sochi", 11).beach_ok
    assert climate("sheregesh", 1).t_day < 0


def test_offers_are_deterministic_and_plausible():
    assert hotels_for("sochi") == hotels_for("sochi")
    legs = transport_options(MOSCOW, BY_ID["hurghada"], date(2026, 11, 10))
    assert legs == transport_options(MOSCOW, BY_ID["hurghada"], date(2026, 11, 10))
    direct = [leg for leg in legs if not leg.stops]
    assert direct and all(4 * 60 <= leg.minutes <= 5 * 60 + 30 for leg in direct)
    assert any(leg.mode == "train" for leg in transport_options(MOSCOW, BY_ID["spb"], date(2026, 11, 10)))
    assert not any(leg.mode == "train" for leg in transport_options(MOSCOW, BY_ID["dubai"], date(2026, 11, 10)))


def test_inspiration_for_warm_sea_in_november_with_a_child():
    items = suggest(MOSCOW, date(2026, 11, 10), 7, 2, 1, trip_types=["sea", "warm"], budget=250_000,
                    max_hours=5, abroad=None, pets=False, mode=None)
    assert items
    for s in items:
        assert s.weather.sea >= 21 and s.minutes <= 5 * 60 * 1.0 + 1
        assert s.est_total <= 250_000 * 1.15 and s.reasons


@pytest.mark.parametrize("text, expected", [
    ("Хочу к тёплому морю в ноябре, недорого, с ребёнком, без долгих перелётов",
     {"trip_types": ["sea", "warm"], "month": 11, "children": 1, "prefer_short_travel": True, "economy": True}),
    ("Казань из Питера на выходные с собакой, поездом",
     {"destination": "kazan", "origin": "Санкт-Петербург", "pets": True, "transport": "train",
      "date_from": date(2026, 10, 30), "date_to": date(2026, 11, 1)}),
    ("Новый год на море, всё включено, 4 звезды",
     {"meal": "all_inclusive", "stars_min": 4}),
    ("двое взрослых и двое детей хотят в Сочи на неделю с 3 ноября до 300 тысяч",
     {"destination": "sochi", "adults": 2, "children": 2, "nights": 7, "date_from": date(2026, 11, 3),
      "budget_total": 300_000}),
    ("а если на два дня позже?", {"shift_days": 2}),
    ("беру 2 вариант", {"pick": 2}),
    ("да, оформляй", {"confirm": True}),
])
def test_rules(text, expected):
    got = rule_extract(TripState(), text, SAT).model_dump(exclude_none=True)
    for key, value in expected.items():
        assert got.get(key) == value, (key, got)


def test_shift_does_not_change_trip_length():
    got = rule_extract(TripState(), "а если на два дня позже?", SAT)
    assert got.nights is None and got.date_from is None


def test_greeting_when_nothing_is_known():
    _, step = talk(agent(), "привет")
    assert step.reply == GREETING


def test_full_path_from_one_message_to_purchase_without_llm():
    a = agent()
    s, step = talk(a, "Хочу к тёплому морю в ноябре на неделю, недорого, с ребёнком, без долгих перелётов")
    assert s.state.stage == "destination" and len(step.payload["items"]) == 3
    assert s.state.origin == "Москва"  # город был известен до начала подбора
    step = a.handle(s, "давай первый")
    assert s.state.stage == "plan" and step.payload["kind"] == "packages"
    assert s.state.date_from.month == 11  # месяц из первой реплики сохранился
    step = a.handle(s, "беру 1 вариант")
    assert s.state.stage == "cart" and step.payload["kind"] == "cart"
    a.handle(s, "да, оформляй")
    a.handle(s, "оплата картой")
    step = a.handle(s, "да, подтверждаю")
    assert s.state.stage == "booked" and step.payload["order"]["number"].startswith("OST-")
    step = a.handle(s, "запроси ранний заезд")
    assert "ранний заезд" in step.reply and s.state.requests


def test_rebuild_keeps_hotel_and_reports_diff():
    a = agent()
    s, step = talk(a, "Сочи с 5 по 12 декабря вдвоём", )
    hotel = step.payload["items"][0]["hotel"]["name"]
    step = a.handle(s, "перенеси на два дня позже")
    assert s.state.date_from == date(2026, 12, 7) and s.state.date_to == date(2026, 12, 14)
    assert any("отель тот же" in d for d in step.payload["diff"])
    assert step.payload["items"][0]["hotel"]["name"] == hotel


def test_overnight_train_moves_hotel_check_in_and_warns_about_long_road():
    trip = Trip(ORIGIN_BY_NAME["Санкт-Петербург"], BY_ID["kazan"], date(2026, 10, 30), date(2026, 11, 1), 2, 0,
                mode="train")
    packages, _ = make_packages(trip)
    pkg = packages[0]
    assert pkg.hotel_in == pkg.out.arrive.date() > trip.date_in
    assert any(kind == "risk" and "в дороге" in text for kind, text in pkg.checks)


def test_missing_selected_hotel_is_not_replaced():
    trip = Trip(MOSCOW, BY_ID["sochi"], date(2027, 6, 11), date(2027, 6, 18), 2, 0)
    packages, reasons = make_packages(trip, "sochi-h-nonexistent")
    assert not packages and "выбранный отель" in reasons[0]


def test_pets_and_budget_constraints():
    trip = Trip(MOSCOW, BY_ID["sochi"], date(2026, 11, 10), date(2026, 11, 17), 2, 0, pets=True, budget=200_000)
    packages, _ = make_packages(trip)
    assert packages and all("pets" in p.hotel.amenities for p in packages)
    optimal = packages[0]
    assert optimal.total(2) <= 200_000 or all(p.total(2) > 200_000 for p in packages)
    assert any("животное" in text for _, text in optimal.checks)


def test_llm_understanding_and_fallback_to_rules():
    a = agent(FakeLLM({"destination": "Сочи", "date_from": "2026-12-05", "date_to": "2026-12-12", "adults": 2}))
    s, step = talk(a, "в Сочи 5–12 декабря вдвоём")
    assert s.last_nlu.startswith("llm") and s.state.dest_id == "sochi" and step.payload["kind"] == "packages"
    s, step = talk(agent(FakeLLM(TimeoutError(), TimeoutError())), "в Сочи с 5 по 12 декабря вдвоём")
    assert s.last_nlu == "rules" and s.state.dest_id == "sochi"


def test_unknown_destination_is_honest():
    s, step = talk(agent(), "хочу в Осло в мае")
    assert s.state.stage == "destination"


@pytest.mark.parametrize("text, dest_id, via", [
    ("хочу в Будву в Черногории в июле на неделю вдвоём", "budva", "Белград"),
    ("Нью-Йорк в декабре на 10 ночей", "newyork", "Стамбул"),
    ("на Айя-Напу на Кипре в июне на неделю", "cyprus", "Стамбул"),
    ("Токио весной, в апреле на неделю", "tokyo", "Пекин"),
])
def test_world_destinations_route_via_hub(text, dest_id, via):
    s, step = talk(agent(), text)
    assert s.state.dest_id == dest_id and s.state.stage == "plan"
    pkg = step.payload["items"][0]
    assert pkg["out"]["via"] == via


def test_web_api_and_health():
    client = TestClient(build_app(agent()))
    assert client.get("/health").json() == {"status": "ok"}
    info = client.get("/api/info").json()
    assert info["destinations"] >= 30 and info["llm"] is None
    r = client.post("/api/chat", json={"text": "Казань из Питера на выходные двое взрослых с собакой, поездом"}).json()
    assert r["stage"] == "plan" and r["payload"]["kind"] == "packages" and "с питомцем" in r["understood"]
    r = client.post("/api/chat", json={"text": "беру 1 вариант", "session_id": r["session_id"]}).json()
    assert r["stage"] == "cart"
    assert "Один запрос" in client.get("/").text or "О!дин запрос" in client.get("/").text


def test_requested_trip_type_is_required():
    s, step = talk(agent(), "Хочу в горы в июле вдвоём до 200 тысяч, по России")
    assert all(BY_ID[i["id"]].tags and "mountains" in BY_ID[i["id"]].tags for i in step.payload["items"])


def test_seasons_economy_and_ideas_without_details():
    assert rule_extract(TripState(), "хочу на Байкал зимой", SAT).season == "winter"
    assert rule_extract(TripState(), "куда-нибудь летом", SAT).season == "summer"
    assert rule_extract(TripState(), "что-нибудь недорогое", SAT).economy is True
    s, step = talk(agent(), "хочу отдохнуть", "не знаю")
    assert s.state.stage == "destination" and step.payload["kind"] == "ideas" and len(step.payload["items"]) == 3


def test_no_preferences_gives_different_kinds_of_trips():
    s, step = talk(agent(), "посоветуй, куда съездить в декабре на неделю")
    weathers = [i["weather"] for i in step.payload["items"]]
    assert any("море" in (w or "") for w in weathers)  # среди идей есть тёплое море, а не три похожих города


def test_questions_are_answered_without_changing_stage():
    a = agent()
    s, _ = talk(a, "Анталья с 5 по 12 декабря вдвоём", "беру 1 вариант")
    step = a.handle(s, "а виза нужна?")
    assert "виза" in step.reply.lower() and s.state.stage == "cart"
    step = a.handle(s, "а какая там погода?")
    assert "°" in step.reply and s.state.stage == "cart"
    step = a.handle(s, "давай подумаем")
    assert s.state.stage == "cart" and "не тороплю" in step.reply


@pytest.mark.parametrize("query", ["Анталья с 5 по 12 декабря вдвоём", "Хургада с 10 по 17 ноября, с ребёнком",
                                   "Сочи с 5 по 12 декабря вдвоём", "Калининград с 6 по 9 ноября",
                                   "Пхукет с 10 по 24 января вдвоём", "Казань из Питера на выходные с собакой, поездом"])
def test_package_invariants(query):
    _, step = talk(agent(), query)
    items = {i["key"]: i for i in step.payload["items"]}
    money = lambda s: int(s.replace("\xa0", "").replace("₽", "").replace(" ", ""))  # noqa: E731
    if "budget" in items:
        assert money(items["budget"]["total"]) <= min(money(i["total"]) for i in items.values())
    optimal = step.payload["items"][0]
    assert not any(c["level"] == "risk" and "ночью" in c["text"] for c in optimal["checks"])


def test_price_calendar_and_picking_a_day_keeps_trip_length():
    a = agent()
    s, step = talk(a, "Сочи с 5 по 12 декабря вдвоём")
    cal = step.payload["calendar"]
    assert len(cal) >= 10 and sum(d["chosen"] for d in cal) == 1 and any(d["cheap"] for d in cal)
    a.handle(s, "с 9 декабря")
    assert (s.state.date_from, s.state.date_to) == (date(2026, 12, 9), date(2026, 12, 16))


def test_images_are_attached_by_id(tmp_path):
    import json

    from apps.web import Images

    (tmp_path / "credits.json").write_text(json.dumps({
        "dest/sochi.jpg": {"author": "A", "license": "CC BY-SA 4.0", "page": "https://commons"},
        "hotel/resort-1.jpg": {"author": "B", "license": "CC0", "page": None}}))
    images = Images(tmp_path)
    payload = {"kind": "destinations", "items": [{"id": "sochi"}, {"id": "nowhere"}]}
    images.decorate(payload)
    assert payload["items"][0]["image"]["src"] == "/static/img/dest/sochi.jpg"
    assert payload["items"][1]["image"] is None
    assert images.hotel("sochi-h01", "sochi")["src"] == "/static/img/hotel/resort-1.jpg"


def test_dataset_records_become_real_hotels(monkeypatch):
    from domains.trips import offers

    fake = {"hotels": {"sochi": [
        {"id": "o1", "name": "Бриз Хаус", "kind": "hotel", "lat": 43.585, "lon": 39.723, "stars": 4, "web": "briz.example",
         "features": ["pool", "wifi"]},
        {"id": "o2", "name": "У моря", "kind": "guest_house", "lat": 43.43, "lon": 39.92}]},
        "beaches": {"sochi": [[43.584, 39.721], [43.43, 39.921]]}, "airports": {"AER": [43.4499, 39.9566]}}
    monkeypatch.setattr(offers, "_real", lambda: fake)
    offers.hotels_for.cache_clear()
    try:
        hotels = offers.hotels_for("sochi")
        assert [h.name for h in hotels] == ["Бриз Хаус", "У моря"]
        briz, guest = hotels
        assert briz.source == "overture" and briz.stars == 4 and briz.center_km == 0 and "pool" in briz.amenities
        assert "mlat=43.585" in briz.map_url and briz.website == "briz.example"
        assert guest.kind == "Гостевой дом" and guest.beach_km is not None and guest.beach_km < 0.3
        assert "beach_line" in guest.amenities and 2 <= guest.airport_km <= 5
        assert offers.hotels_for("sochi") == hotels  # детерминированно
    finally:
        offers.hotels_for.cache_clear()


def test_real_hotel_kind_stars_and_site_from_open_data():
    from random import Random

    from domains.trips import offers

    kind_stars = lambda rec: offers._real_kind_stars(Random(1), rec)  # noqa: E731
    assert kind_stars({"name": "База отдыха Адлер", "kind": "hotel"})[0] == "База отдыха"
    assert kind_stars({"name": "Хостел Пушкин", "kind": "hotel"}) == ("Хостел", 2)
    assert kind_stars({"name": "Hilton Garden", "kind": "hotel"}) == ("Отель", 5)
    assert kind_stars({"name": "Отель Москва 4*", "kind": "hotel"}) == ("Отель", 4)
    assert kind_stars({"name": "Holiday Inn", "kind": "hotel"}) == ("Отель", 4)  # не гостевой дом из-за «Inn»
    assert offers._official_site("https://ru.wikipedia.org/wiki/Адлер") is None
    assert offers._official_site("https://vk.com/hotel") is None
    assert offers._official_site("http://veleshotel.com") == "http://veleshotel.com"


def test_sea_trip_variants_stay_near_beach_and_differ():
    trip = Trip(origin=MOSCOW, dest=BY_ID["sochi"], date_in=date(2027, 6, 11),
                date_out=date(2027, 6, 18), adults=2, children=0, trip_types=["sea"])
    packages, _ = make_packages(trip)
    assert len(packages) == 3
    assert len({p.hotel.id for p in packages}) >= 2
    near = [h for h in hotels_for("sochi") if h.beach_km is not None and h.beach_km <= 1.5]
    if near:  # с настоящим датасетом у моря есть из чего выбрать
        assert all(p.hotel.beach_km is not None and p.hotel.beach_km <= 1.5 for p in packages[1:])


def test_more_pages_through_new_destinations():
    a = agent()
    s, step = talk(a, "Хочу на море в феврале, куда-нибудь экзотично")
    seen = {d["id"] for d in step.payload["items"]}
    for _ in range(3):
        step = a.handle(s, "ещё")
        ids = {d["id"] for d in step.payload["items"]}
        assert ids and not ids & seen  # каждый раз новые направления
        seen |= ids


def test_clean_hotel_names():
    from domains.trips.offers import _clean_name

    assert _clean_name("so_white_club_resort") == "So White Club Resort"
    assert _clean_name("Отель Велес") == "Отель Велес"
