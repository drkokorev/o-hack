"""Contract checks for the standalone map snapshot and approximate location."""
import gzip
import sqlite3

from fastapi.testclient import TestClient

from apps import location, map_catalog_snapshot as catalogue, map_snapshot
from apps.web import build_app
from core.agent import Agent
from domains.trips.domain import TripsDomain


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


def test_snapshot_restores_atomically_without_leaving_a_temporary_database(tmp_path, monkeypatch):
    original = tmp_path / "source.sqlite3"
    with sqlite3.connect(original) as db:
        db.execute("CREATE TABLE sample (n INTEGER)")
        db.execute("INSERT INTO sample VALUES (42)")
    archive = tmp_path / "snapshot.gz"
    with gzip.open(archive, "wb") as compressed:
        compressed.write(original.read_bytes())
    restored = tmp_path / "result.sqlite3"
    monkeypatch.setattr(map_snapshot, "DATA", tmp_path)
    monkeypatch.setattr(map_snapshot, "ARCHIVE", archive)
    monkeypatch.setattr(map_snapshot, "DATABASE", restored)
    assert map_snapshot.ensure_snapshot() == restored
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT n FROM sample").fetchone() == (42,)
    assert not list(tmp_path.glob("odin-map-*.sqlite3"))


def test_country_is_approximate_and_does_not_return_or_trust_client_ip():
    assert location.visitor_country("127.0.0.1")["country_code"] is None
    assert location.visitor_country("8.8.8.8")["country_code"] == "US"
    with TestClient(build_app(Agent(TripsDomain(), None))) as client:
        response = client.get("/api/visitor-country", headers={"X-Forwarded-For": "8.8.8.8"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["country_code"] is None
    assert "8.8.8.8" not in response.text
