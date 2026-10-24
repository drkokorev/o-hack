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
     {"trip_types": ["sea", "warm"], "month": 11, "children": 1, "max_travel_hours": 5.0, "cheaper": True}),
    ("Казань из Питера на выходные с собакой, поездом",
     {"destination": "kazan", "origin": "Санкт-Петербург", "pets": True, "transport": "train",
      "date_from": date(2026, 10, 30), "date_to": date(2026, 11, 1)}),
    ("Новый год на море, всё включено, 4 звезды",
     {"date_from": date(2026, 12, 30), "meal": "all_inclusive", "stars_min": 4}),
    ("мы с мужем и двумя детьми хотим в Сочи на неделю с 3 ноября до 300 тысяч",
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
    s, step = talk(a, "Хочу к тёплому морю в ноябре, недорого, с ребёнком, без долгих перелётов")
    assert s.state.stage == "destination" and len(step.payload["items"]) == 3
    assert "вылет из Москвы" in s.state.assumptions  # предположения названы явно
    step = a.handle(s, "давай первый")
    assert s.state.stage == "plan" and step.payload["kind"] == "packages"
    assert s.state.date_from.month == 11  # месяц из первой реплики сохранился
    step = a.handle(s, "беру 1 вариант")
    assert s.state.stage == "cart" and step.payload["kind"] == "cart"
    step = a.handle(s, "да, оформляй")
    assert s.state.stage == "booked" and step.payload["order"]["number"].startswith("OST-")
    step = a.handle(s, "запроси ранний заезд")
    assert "ранний заезд" in step.reply and s.state.requests


def test_rebuild_keeps_hotel_and_reports_diff():
    a = agent()
    s, step = talk(a, "Сочи с 5 по 12 декабря вдвоём", )
    hotel = step.payload["items"][0]["hotel"]["name"]
    step = a.handle(s, "а если на два дня позже?")
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
    s, step = talk(agent(), "хочу в Лиссабон в мае")
    assert s.state.stage == "destination"


def test_web_api_and_health():
    client = TestClient(build_app(agent()))
    assert client.get("/health").json() == {"status": "ok"}
    info = client.get("/api/info").json()
    assert info["destinations"] >= 30 and info["llm"] is None
    r = client.post("/api/chat", json={"text": "Казань из Питера на выходные с собакой, поездом"}).json()
    assert r["stage"] == "plan" and r["payload"]["kind"] == "packages" and "с питомцем" in r["understood"]
    r = client.post("/api/chat", json={"text": "беру 1 вариант", "session_id": r["session_id"]}).json()
    assert r["stage"] == "cart"
    assert "Один запрос" in client.get("/").text or "О!дин запрос" in client.get("/").text
