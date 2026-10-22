from datetime import date

import pytest
from fastapi.testclient import TestClient

from apps.web import build_app
from core.agent import Agent
from domains.hotels.domain import HotelsDomain
from domains.hotels.loader import detect_mapping, load_hotels, to_hotels
from domains.hotels.rules import parse_budget, parse_dates, parse_guests
from domains.hotels.state import HotelState
from tests.conftest import FakeLLM

THURSDAY = date(2026, 10, 22)


@pytest.mark.parametrize("text, expected", [
    ("на выходные", (date(2026, 10, 23), date(2026, 10, 25))),
    ("с 7 по 9 ноября", (date(2026, 11, 7), date(2026, 11, 9))),
    ("с 28 декабря по 3 января", (date(2026, 12, 28), date(2027, 1, 3))),
    ("на 3 ночи с 15 декабря", (date(2026, 12, 15), date(2026, 12, 18))),
    ("завтра на 2 ночи", (date(2026, 10, 23), date(2026, 10, 25))),
    ("07.11-10.11", (date(2026, 11, 7), date(2026, 11, 10))),
    ("5 марта", (date(2027, 3, 5), None)),  # прошедшая дата — следующий год
])
def test_parse_dates(text, expected):
    assert parse_dates(text, THURSDAY) == expected


def test_parse_budget_ignores_dates_and_stars_and_detects_total():
    assert parse_budget("с 7 по 9 ноября до 8к") == (8000, False)
    assert parse_budget("по 3 звезды") == (None, False)
    assert parse_budget("до 20к на всю поездку") == (20000, True)
    assert parse_budget("до 7,5 тыс") == (7500, False)


def test_parse_guests():
    assert parse_guests("едем вдвоём") == 2
    assert parse_guests("нас трое") == 3
    assert parse_guests("3 взрослых") == 3
    assert parse_guests("на 3 ночи") is None


def test_rules_work_without_llm_and_split_total_budget():
    agent = Agent(HotelsDomain(), None, today=lambda: THURSDAY)
    s = agent.new_session()
    step = agent.handle(s, "Хочу в Казань с 7 по 9 ноября вдвоём, без завтрака, бюджет 15000 за всё")
    assert s.last_nlu == "rules"
    assert (s.state.city, s.state.guests, s.state.budget_max) == ("Казань", 2, 7500)
    assert not s.state.amenities  # «без завтрака» — не требование завтрака
    assert step.payload.matches


def test_rules_fill_gaps_left_by_llm():
    agent = Agent(HotelsDomain(), FakeLLM({"city": "Сочи"}), today=lambda: THURSDAY)
    s = agent.new_session()
    agent.handle(s, "Сочи у моря на выходные")
    assert s.last_nlu == "llm+rules"
    assert (s.state.city, s.state.near_sea, s.state.check_in) == ("Сочи", True, date(2026, 10, 23))


def test_clear_and_cheaper():
    domain = HotelsDomain()
    agent = Agent(domain, None, today=lambda: THURSDAY)
    s = agent.new_session()
    agent.handle(s, "Москва, 4 звезды, до 15000")
    shown = list(s.state.shown_prices)
    agent.handle(s, "звёзды не важны")
    assert s.state.stars_min is None and s.state.budget_max == 15000
    agent.handle(s, "а подешевле?")
    assert s.state.budget_max < sorted(shown)[len(shown) // 2]


def test_loader_detects_columns_and_normalizes(tmp_path):
    path = tmp_path / "h.csv"
    path.write_text(
        "hotel_id;Name;City;star_rating;min_rate;review_score;Latitude;Longitude;amenities\n"
        '1;А;казань;4;5 200,00;4.6;55.79;49.12;"Free Wi-Fi, Breakfast included"\n'
        "2;Б;Казань;3;3000;3.9;55.75;49.20;Parking\n"
        "3;;Казань;;;;;;\n",
        encoding="utf-8",
    )
    hotels = load_hotels(path)
    assert [h.name for h in hotels] == ["А", "Б"]  # строка без названия и цены пропущена
    a = hotels[0]
    assert (a.city, a.price_per_night, a.rating, a.stars) == ("Казань", 5200, 9.2, 4)  # шкала 0–5 → 0–10
    assert a.amenities == ["breakfast", "wifi"]
    assert a.distance_center_km > 0  # посчитано по координатам


def test_loader_requires_core_columns():
    assert detect_mapping(["Название", "Город", "Цена"]) == {"name": "Название", "city": "Город", "price_per_night": "Цена"}
    with pytest.raises(ValueError, match="mapping"):
        to_hotels([{"foo": 1}])


def test_domain_works_on_loaded_catalog_with_missing_fields():
    hotels = to_hotels([{"name": "Х", "city": "Казань", "price": 4000}])
    step = HotelsDomain(hotels).step(HotelState(city="Казань"))
    assert "Х" in step.reply and step.payload.matches


@pytest.fixture
def client():
    return TestClient(build_app(Agent(HotelsDomain(), None, today=lambda: THURSDAY)))


def test_web_chat_cards_chips_and_clear(client):
    r = client.post("/api/chat", json={"text": "Питер на выходные до 8 тысяч, с завтраком"}).json()
    assert r["hotels"] and r["nlu"] == "rules"
    fields = {c["field"] for c in r["chips"]}
    assert {"city", "check_in", "budget_max", "amenity:breakfast"} <= fields
    assert len(r["summary"]) < len(r["reply"])  # в чате коротко, варианты — карточками

    r2 = client.post("/api/clear", json={"session_id": r["session_id"], "field": "budget_max"}).json()
    assert "budget_max" not in {c["field"] for c in r2["chips"]}
    r3 = client.post("/api/clear", json={"session_id": r["session_id"], "field": "amenity:breakfast"}).json()
    assert "amenity:breakfast" not in {c["field"] for c in r3["chips"]}
    assert client.post("/api/clear", json={"session_id": r["session_id"], "field": "city"}).status_code == 400


def test_web_health_and_index(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["llm"] is None and h["hotels"] == 40
    assert "Один запрос" in client.get("/").text
