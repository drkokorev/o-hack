"""Prevent invalid manually curated map content from reaching the interface."""

import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from domains.trips.geo import BY_ID

STATIC = Path(__file__).resolve().parents[1] / "apps" / "static"


def load(name):
    return json.loads((STATIC / name).read_text(encoding="utf-8"))


def valid_location(item):
    return -90 <= item["lat"] <= 90 and -180 <= item["lon"] <= 180


def valid_source(url):
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


def test_events_have_distinct_ids_valid_dates_and_sources():
    data = load("events.json")
    date.fromisoformat(data["checked_at"])
    events = data["events"]
    assert events and len({event["id"] for event in events}) == len(events)
    for event in events:
        assert all(event.get(key) for key in ("name", "city", "country", "dates", "category", "source", "icon"))
        assert date.fromisoformat(event["start"]) <= date.fromisoformat(event["end"])
        assert valid_location(event) and valid_source(event["url"])


def test_landmarks_and_inspiration_are_consistent_with_catalog():
    data = load("landmarks.json")
    date.fromisoformat(data["checked_at"])
    landmarks = data["landmarks"]
    assert landmarks and len({place["city"] for place in landmarks}) == len(landmarks)
    assert all(place.get("name") and place.get("icon") and valid_location(place) and valid_source(place["url"])
               for place in landmarks)
    inspiration = load("inspiration.json")
    assert all(place["id"] in BY_ID and place.get("label") for place in inspiration["places"])
    assert all(prompt.get("label") and prompt.get("text") for prompt in inspiration["starters"])


def test_map_viewpoints_are_valid():
    settings = load("map-settings.json")
    for center in [settings["world_center"], *(view["center"] for view in settings["regional_overviews"])]:
        assert len(center) == 2 and -180 <= center[0] <= 180 and -90 <= center[1] <= 90
    assert all(0.5 <= zoom <= 16 for zoom in settings["world_zoom"].values())
    assert all(view.get("country") and 0.5 <= view["zoom"] <= 16 for view in settings["regional_overviews"])
