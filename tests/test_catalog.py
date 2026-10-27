import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.web import build_app
from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID, DESTINATIONS, HUBS, ORIGINS, _load_catalog
from domains.trips import offers


def test_versioned_catalog_keeps_destinations_and_relationships():
    assert len(DESTINATIONS) == 69
    assert len(ORIGINS) == 7
    assert BY_ID["sochi"].name == "Сочи"
    assert BY_ID["sochi"].areas and BY_ID["sochi"].rail
    assert all(not destination.via or destination.via in HUBS for destination in DESTINATIONS)


def test_duplicate_destination_ids_fail_instead_of_silently_overwriting(tmp_path):
    original = Path(__file__).resolve().parents[1] / "domains" / "trips" / "data" / "geo.json"
    catalog = json.loads(original.read_text(encoding="utf-8"))
    catalog["destinations"].append(catalog["destinations"][0])
    path = tmp_path / "geo.json"
    path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="повторяется id"):
        _load_catalog(path)


def test_app_info_does_not_generate_all_hotels(monkeypatch):
    def fail_if_hotels_are_generated(*args, **kwargs):
        raise AssertionError("Информация о приложении не должна генерировать каталог отелей")

    monkeypatch.setattr(offers, "hotels_for", fail_if_hotels_are_generated)
    client = TestClient(build_app(Agent(TripsDomain(), None)))
    response = client.get("/api/info")
    assert response.status_code == 200
    assert response.json()["hotels"] == 65107
