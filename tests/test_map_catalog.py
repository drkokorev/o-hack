"""Contract tests for the real-source map index, including full pagination."""
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient

from apps.web import build_app
from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips import map_catalog


@pytest.fixture(scope="module", autouse=True)
def index():
    if not map_catalog.DATABASE.exists():
        subprocess.run([sys.executable, "-m", "tools.build_map_catalog"],
                       cwd=Path(__file__).resolve().parents[1], check=True)


@pytest.fixture
def client():
    return TestClient(build_app(Agent(TripsDomain(), None)))


def test_catalog_counts_and_provenance(client):
    response = client.get("/api/map/catalog")
    assert response.status_code == 200
    data = response.json()
    assert data["counts"] == {"hotel": 65924, "airport": 48101, "city": 161662, "beach": 7866, "camping": 8}
    assert {"overture", "overture_added", "overture_camping", "ourairports", "geonames"} <= data["sources"].keys()
    assert "наличие не проверены" in data["notice"]


def test_every_hotel_can_be_paged_without_duplicates(client):
    ids, cursor, pages = set(), 0, 0
    while cursor is not None:
        response = client.get("/api/map/points", params={"kind": "hotel", "limit": 1000, "cursor": cursor})
        assert response.status_code == 200
        body = response.json()
        items = body["items"]
        assert all(item["kind"] == "hotel" and item["source"] in {"overture", "overture_added"} for item in items)
        assert all("price" not in item and "availability" not in item for item in items)
        assert len({item["id"] for item in items}) == len(items)
        assert not ids.intersection(item["id"] for item in items)
        ids.update(item["id"] for item in items)
        cursor, pages = body["next_cursor"], pages + 1
        assert pages <= 67
    assert len(ids) == 65924 and pages == 66


def test_global_clusters_account_for_every_hotel(client):
    response = client.get("/api/map/clusters", params={"kind": "hotel", "zoom": 3})
    assert response.status_code == 200
    assert sum(item["count"] for item in response.json()["items"]) == 65924


def test_individual_point_details_keep_source_information(client):
    point = client.get("/api/map/points", params={"kind": "hotel", "limit": 1}).json()["items"][0]
    response = client.get("/api/map/point/" + point["id"])
    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == point["id"] and detail["name"] == point["name"]
    assert detail["source_url"] and detail["source_name"]
    assert "price" not in detail and "availability" not in detail
    assert client.get("/api/map/point/nonexistent").status_code == 404


def test_country_and_destination_catalogs_and_filters(client):
    country_response = client.get("/api/map/countries")
    assert country_response.status_code == 200 and len(country_response.json()["items"]) == 250
    russia = next(item for item in country_response.json()["items"] if item["code"] == "RU")
    assert russia["city_records"] > 0 and russia["airport_records"] > 0
    destinations = client.get("/api/map/destinations").json()["items"]
    yaroslavl = next(item for item in destinations if item["id"] == "yaroslavl")
    assert len(destinations) == 75 and yaroslavl["country_code"] == "RU" and yaroslavl["hotel_records"] == 87
    cities = client.get("/api/map/points", params={"kind": "city", "country_code": "RU", "limit": 100}).json()
    assert cities["items"] and all(item["country_code"] == "RU" for item in cities["items"])
    kosovo = client.get("/api/map/points", params={"kind": "city", "country_code": "XK", "limit": 100}).json()
    assert len(kosovo["items"]) == 58 and kosovo["next_cursor"] is None
    assert all(item["country_code"] == "XK" for item in kosovo["items"])
    hotels = client.get("/api/map/points", params={"kind": "hotel", "destination_id": "yaroslavl", "limit": 100}).json()
    assert len(hotels["items"]) == 87 and hotels["next_cursor"] is None
    assert all(item["destination_id"] == "yaroslavl" for item in hotels["items"])
    russian_hotels = client.get("/api/map/points", params={"kind": "hotel", "country_code": "RU", "limit": 100}).json()
    russian_destinations = {item["id"] for item in destinations if item["country_code"] == "RU"}
    assert len(russian_hotels["items"]) == 100
    assert all(item["destination_id"] in russian_destinations for item in russian_hotels["items"])
    clusters = client.get("/api/map/clusters", params={"kind": "hotel", "destination_id": "yaroslavl", "zoom": 3}).json()
    assert sum(item["count"] for item in clusters["items"]) == 87


def test_antimeridian_cluster_count_matches_source_database(client):
    params = {"kind": "airport", "west": 170, "east": -170, "south": -90, "north": 90, "zoom": 3}
    response = client.get("/api/map/clusters", params=params)
    assert response.status_code == 200
    actual = sum(item["count"] for item in response.json()["items"])
    with sqlite3.connect(map_catalog.DATABASE) as db:
        expected = db.execute("SELECT COUNT(*) FROM point WHERE kind='airport' AND (lon >= 170 OR lon <= -170)").fetchone()[0]
    assert actual == expected and actual > 0


@pytest.mark.parametrize("params", [
    {"kind": "hotel", "destination_id": "yaroslavl", "zoom": 3},
    {"kind": "city", "country_code": "RU", "zoom": 4},
    {"kind": "airport", "west": 170, "east": -170, "zoom": 3},
])
def test_cluster_anchor_is_an_actual_matching_point(client, params):
    body = client.get("/api/map/clusters", params=params).json()
    assert body["items"]
    for cluster in body["items"]:
        point = client.get("/api/map/point/" + cluster["representative_id"]).json()
        assert point["lat"] == cluster["lat"] and point["lon"] == cluster["lon"]
        assert point["kind"] == params["kind"]
        if "destination_id" in params:
            assert point["destination_id"] == params["destination_id"]
        if "country_code" in params:
            assert point["country_code"] == params["country_code"]
        if "west" in params:
            assert point["lon"] >= params["west"] or point["lon"] <= params["east"]


def test_map_hotel_selection_preserves_identity_in_trip(client):
    point = client.get("/api/map/points", params={"kind": "hotel", "destination_id": "yaroslavl", "limit": 1}).json()["items"][0]
    selected = client.post("/api/chat", json={"text": "Выбираю отель", "map_point_id": point["id"]}).json()
    assert selected["map_selection"]["accepted"] is True
    assert point["name"] in selected["reply"] and "не проверены" in selected["reply"]
    plan = client.post("/api/chat", json={"session_id": selected["session_id"],
        "text": "Из Москвы с 10 по 14 июля 2027, двое взрослых, поездом"}).json()
    packages = plan["payload"]["items"]
    assert packages and all(package["hotel"]["id"] == "yaroslavl-h" + point["id"].removeprefix("overture:")
                            for package in packages)


def test_map_hotel_does_not_replace_a_different_active_trip(client):
    first = client.post("/api/chat", json={"text": "Хочу в Сочи"}).json()
    point = client.get("/api/map/points", params={"kind": "hotel", "destination_id": "yaroslavl", "limit": 1}).json()["items"][0]
    second = client.post("/api/chat", json={"session_id": first["session_id"], "text": "Выбираю отель",
                                             "map_point_id": point["id"]}).json()
    assert second["map_selection"]["accepted"] is False
    assert second["trip_summary"]["destination"] == first["trip_summary"]["destination"]
    assert "другая поездка" in second["reply"]


def test_invalid_map_hotel_is_rejected(client):
    city = client.get("/api/map/points", params={"kind": "city", "limit": 1}).json()["items"][0]
    assert client.post("/api/chat", json={"text": "Выбираю", "map_point_id": city["id"]}).status_code == 422
    assert client.post("/api/chat", json={"text": "Выбираю", "map_point_id": "overture:missing"}).status_code == 422


def test_map_country_selection_is_preserved_by_code(client):
    answer = client.post("/api/chat", json={"text": "Хочу поехать: Россия", "map_country_code": "RU"}).json()
    assert answer["map_selection"]["accepted"] is True
    assert "Россия" in answer["understood"] and answer["trip_summary"]["destination"] == "Россия"
    assert client.post("/api/chat", json={"text": "Выбираю", "map_country_code": "ZZ"}).status_code == 422


def test_selected_hotel_address_comes_from_source_or_is_explicitly_unknown():
    today = date(2026, 10, 27)
    agent = Agent(TripsDomain(today=lambda: today), None, today=lambda: today)
    session = agent.new_session()
    agent.handle(session, "Из Москвы в Ярославль с 10 по 14 июля 2027, двое взрослых, поездом")
    cart = agent.handle(session, "выбираю первый вариант")
    hotel = cart.payload["package"]["hotel"]
    record = map_catalog.lookup("overture:" + hotel["id"].split("-h", 1)[1])
    assert record is not None
    answer = agent.handle(session, "Какой адрес отеля?")
    if record["address"]:
        assert record["address"] in answer.reply
        assert record["source_name"] in answer.reply and record["source_release"] in answer.reply
        assert "проверить" in answer.reply
    else:
        assert "адрес не указан" in answer.reply.lower()


def test_address_question_before_selecting_a_hotel_does_not_guess():
    today = date(2026, 10, 27)
    agent = Agent(TripsDomain(today=lambda: today), None, today=lambda: today)
    session = agent.new_session()
    agent.handle(session, "Из Москвы в Ярославль с 10 по 14 июля 2027, двое взрослых, поездом")
    answer = agent.handle(session, "Какой адрес отеля?")
    assert "о каком отеле" in answer.reply.lower()


def test_real_hotel_request_uses_source_without_dates_or_modelled_rates():
    today = date(2026, 10, 27)
    agent = Agent(TripsDomain(today=lambda: today), None, today=lambda: today)
    session = agent.new_session()
    answer = agent.handle(session, "В Ярославль, покажи реальные отели")
    records = map_catalog.hotels_in_destination("yaroslavl")
    assert records and records[0]["name"] in answer.reply
    assert "Overture Maps" in answer.reply and "снимок 2026-10-21.0" in answer.reply
    assert "цены, наличие, удобства" in answer.reply.lower() and "₽" not in answer.reply
    assert session.state.origin is None and session.state.date_from is None


def test_camping_data_is_sourced_and_does_not_claim_tent_or_fire_permission(client):
    from domains.trips.campgrounds import campground_hint
    response = client.get("/api/map/points", params={"kind": "camping", "limit": 20})
    assert response.status_code == 200 and len(response.json()["items"]) == 8
    assert all(item["source"] == "overture_camping" for item in response.json()["items"])
    hint = campground_hint("altai")
    assert "Overture Maps" in hint and "нужно уточнить" in hint


@pytest.mark.parametrize("params", [
    {"south": 30, "north": -30}, {"west": -181}, {"north": "nan"}, {"limit": 1001}, {"kind": "unknown"},
    {"country_code": "ZZ"}, {"destination_id": "unknown"},
])
def test_bad_viewports_and_page_size_are_rejected(client, params):
    assert client.get("/api/map/points", params=params).status_code == 422
