"""Contract checks for the integrated map catalog and approximate location."""
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from apps import location
from apps.web import build_app
from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips import map_catalog as catalogue


@pytest.fixture(scope="module", autouse=True)
def index():
    if not catalogue.DATABASE.exists():
        subprocess.run([sys.executable, "-m", "tools.build_map_catalog"],
                       cwd=Path(__file__).resolve().parents[1], check=True)


def test_snapshot_covers_the_catalog_and_global_clusters():
    data = catalogue.catalogue()
    assert data["counts"] == {"airport": 48101, "beach": 7866, "camping": 8,
                              "city": 161662, "hotel": 65924}
    groups = catalogue.clusters("all", -180, -90, 180, 90, 3)
    assert groups["catalog_version"] == data["catalog_version"]
    assert sum(group["count"] for group in groups["items"]) == 283561
    assert len(catalogue.destinations()["items"]) == 75


def test_map_pages_are_distinct_and_point_provenance_is_returned():
    first = catalogue.points("hotel", 37.4, 55.6, 37.8, 55.9, limit=10)
    assert first["next_cursor"] is not None
    second = catalogue.points("hotel", 37.4, 55.6, 37.8, 55.9,
                              cursor=first["next_cursor"], limit=10)
    assert len(first["items"]) == len(second["items"]) == 10
    assert {p["id"] for p in first["items"]}.isdisjoint(p["id"] for p in second["items"])
    point = catalogue.lookup(first["items"][0]["id"])
    assert point["kind"] == "hotel"
    assert point["source_name"] and point["source_url"]
    assert "price" not in point and "availability" not in point


def test_missing_catalog_produces_a_safe_unavailable_response(tmp_path, monkeypatch):
    monkeypatch.setattr(catalogue, "DATABASE", tmp_path / "missing.sqlite3")
    with TestClient(build_app(Agent(TripsDomain(), None))) as client:
        response = client.get("/api/map/catalog")
    assert response.status_code == 503
    assert response.json() == {"detail": "Каталог карты недоступен"}


def test_country_is_approximate_and_does_not_return_or_trust_client_ip():
    assert location.visitor_country("127.0.0.1")["country_code"] is None
    assert location.visitor_country("8.8.8.8")["country_code"] == "US"
    with TestClient(build_app(Agent(TripsDomain(), None))) as client:
        response = client.get("/api/visitor-country", headers={"X-Forwarded-For": "8.8.8.8"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["country_code"] is None
    assert "8.8.8.8" not in response.text
