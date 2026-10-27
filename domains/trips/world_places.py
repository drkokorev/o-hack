"""Read-only lookup of geographical names, separate from the offer catalogue."""
from __future__ import annotations

import sqlite3
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .textparse import norm

DATABASE = Path(__file__).with_name("data") / "world_cities.sqlite3"
COUNTRY_NAMES = frozenset(json.loads((DATABASE.parent / "countries_ru.json").read_text(encoding="utf-8")).values())


@dataclass(frozen=True)
class Place:
    id: int
    name: str
    country: str
    lat: float
    lon: float
    population: int


@lru_cache(maxsize=1024)
def find_world_places(name: str) -> tuple[Place, ...]:
    """Return exact name matches, including duplicates; never invent an offer."""
    key = norm(name.strip())
    if len(key) < 3 or not DATABASE.is_file():
        return ()
    uri = DATABASE.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        rows = db.execute(
            "SELECT c.id, c.name, c.country, c.lat, c.lon, c.population "
            "FROM alias a JOIN city c ON c.id = a.city_id WHERE a.name = ? "
            "ORDER BY c.population DESC, c.id LIMIT 8", (key,)).fetchall()
    return tuple(Place(*row) for row in rows)
