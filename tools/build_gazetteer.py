"""Build a small, offline place index from the GeoNames geonamescache wheel.

Usage: python -m tools.build_gazetteer path/to/geonamescache.whl path/to/country-ru.json
The city data is CC BY 4.0; see THIRD_PARTY.md for source and provenance.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

from domains.trips.textparse import norm


def build(wheel: Path, countries_file: Path, output: Path) -> tuple[int, int]:
    with zipfile.ZipFile(wheel) as source:
        cities = json.loads(source.read("geonamescache/data/cities1000.json"))
    countries = json.loads(countries_file.read_text(encoding="utf-8"))
    if output.exists():
        output.unlink()
    db = sqlite3.connect(output)
    db.executescript("""
      PRAGMA journal_mode=OFF;
      PRAGMA synchronous=OFF;
      CREATE TABLE city (id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL,
                         lat REAL NOT NULL, lon REAL NOT NULL, population INTEGER NOT NULL);
      CREATE TABLE alias (name TEXT NOT NULL, city_id INTEGER NOT NULL,
                          PRIMARY KEY(name, city_id)) WITHOUT ROWID;
    """)
    name_filter = re.compile(r"^[a-zа-яё\- .']{3,70}$", re.IGNORECASE)
    alias_count = 0
    with db:
        for city in cities.values():
            city_id = int(city["geonameid"])
            country = countries.get(city.get("countrycode"), city.get("countrycode") or "")
            db.execute("INSERT INTO city VALUES (?, ?, ?, ?, ?, ?)",
                       (city_id, city["name"], country, city["latitude"], city["longitude"], city.get("population") or 0))
            names = {norm(name.strip()) for name in [city["name"], *city.get("alternatenames", [])]
                     if isinstance(name, str) and name_filter.fullmatch(name.strip())}
            db.executemany("INSERT OR IGNORE INTO alias VALUES (?, ?)", ((name, city_id) for name in names))
            alias_count += len(names)
    db.close()
    return len(cities), alias_count


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    target = Path(__file__).resolve().parents[1] / "domains/trips/data/world_cities.sqlite3"
    count, aliases = build(Path(sys.argv[1]), Path(sys.argv[2]), target)
    print(f"{count} cities, {aliases} aliases, {target.stat().st_size} bytes")
