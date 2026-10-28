"""Build a read-only, source-labelled map index from the repository snapshots.

    python -m tools.build_map_catalog

This does not fetch data or invent hotel availability. All source files and
their licensing descriptions are shipped with the application.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "domains" / "trips" / "data"
OUT = DATA / "map_catalog.sqlite3"


def main():
    hotel_path, city_path, airport_path, camp_path = (DATA / "hotels.json", DATA / "world_cities.sqlite3",
                                                      DATA / "ourairports.json", DATA / "campgrounds.json")
    hotels = json.loads(hotel_path.read_text(encoding="utf-8"))
    airports = json.loads(airport_path.read_text(encoding="utf-8"))
    campgrounds = json.loads(camp_path.read_text(encoding="utf-8"))
    country_names = json.loads((DATA / "countries_ru.json").read_text(encoding="utf-8"))
    reverse_countries = {}
    for code, name in country_names.items():
        reverse_countries[name] = code if name not in reverse_countries else None
    source_digest = hashlib.sha256()
    source_digest.update(b"map-catalog-schema-1-xk-v1")
    for path in (hotel_path, city_path, airport_path, camp_path, DATA / "geo.json", DATA / "countries_ru.json"):
        source_digest.update(path.name.encode())
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                source_digest.update(chunk)
    # A temporary database is used so an incomplete build never replaces the
    # working catalogue. The filename belongs solely to this script.
    temp = OUT.with_name("map_catalog.building.sqlite3")
    if temp.exists():
        raise FileExistsError(f"Remove or inspect an earlier incomplete build first: {temp}")
    db = sqlite3.connect(temp)
    try:
        db.executescript("""
            PRAGMA journal_mode=DELETE;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE sources (id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
                                  license TEXT NOT NULL, release TEXT, accessed_at TEXT, note TEXT);
            CREATE TABLE point (rowid INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
                                name TEXT, lat REAL NOT NULL, lon REAL NOT NULL, source TEXT NOT NULL,
                                source_id TEXT, id_quality TEXT NOT NULL, subtype TEXT, address TEXT,
                                website TEXT, country_name TEXT, country_code TEXT, code TEXT, confidence REAL,
                                destination_id TEXT, extra TEXT);
            CREATE VIRTUAL TABLE point_geo USING rtree(rowid, min_lon, max_lon, min_lat, max_lat);
        """)
        sources = [
            ("overture", "Overture Maps Places", "https://docs.overturemaps.org/attribution/#places",
             "CDLA Permissive 2.0 / Apache 2.0 / CC0, depending on contributor", "2026-10-21.0", None,
             "Snapshot, not current availability; old records may retain only a partial source ID."),
            ("overture_added", "Overture Maps Places", "https://docs.overturemaps.org/attribution/#places",
             "CDLA Permissive 2.0 / Apache 2.0 / CC0, depending on contributor", "2026-10-21.0",
             hotels["added_cities_20261027"]["accessed"], "Six added cities; no live availability."),
            ("overture_camping", "Overture Maps Places", "https://docs.overturemaps.org/attribution/#places",
             "CDLA Permissive 2.0 / Apache 2.0 / CC0, depending on contributor", campgrounds["release"],
             campgrounds["accessed_at"], "Campground map category; tent pitches, fire permission and prices are unverified."),
            ("ourairports", "OurAirports", "https://ourairports.com/data/", "Public domain", None,
             airports["accessed_at"], "Static airport records; the source does not prove that flights or tickets exist."),
            ("geonames", "GeoNames via geonamescache", "https://www.geonames.org/", "CC BY 4.0",
             "geonamescache 3.0.1", None, "City coordinates and names, not accommodation availability."),
        ]
        db.executemany("INSERT INTO sources VALUES (?,?,?,?,?,?,?)", sources)
        insert = "INSERT INTO point (id,kind,name,lat,lon,source,source_id,id_quality,subtype,address,website,country_name,country_code,code,confidence,destination_id,extra) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"

        seen = {}
        for dest_id, records in sorted(hotels["hotels"].items()):
            for record in sorted(records, key=lambda row: row["id"]):
                key = record["id"]
                signature = (record["lat"], record["lon"], record["name"])
                if key in seen:
                    if seen[key] != signature:
                        raise ValueError(f"Conflicting shortened Overture id: {key}")
                    continue
                seen[key] = signature
                full_id = record.get("overture_id")
                db.execute(insert, ("overture:" + key, "hotel", record["name"], record["lat"], record["lon"],
                                    "overture_added" if full_id else "overture", full_id or key,
                                    "full" if full_id else "partial", record.get("kind"), record.get("street"),
                                    record.get("web"), None, None, None, record.get("conf"), dest_id,
                                    json.dumps({"destination_id": dest_id}, ensure_ascii=False)))

        beaches = sorted({tuple(item) for rows in hotels.get("beaches", {}).values() for item in rows})
        for lat, lon in beaches:
            db.execute(insert, (f"overture:beach:{lat:.4f}:{lon:.4f}", "beach", None, lat, lon, "overture", None,
                                "rounded_coordinates", "beach", None, None, None, None, None, None, None, None))

        seen_camps = {}
        for region, records in sorted(campgrounds["campgrounds"].items()):
            for record in records:
                signature = (record["lat"], record["lon"], record["name"])
                if record["id"] in seen_camps:
                    if seen_camps[record["id"]] != signature:
                        raise ValueError(f"Conflicting campground id: {record['id']}")
                    continue
                seen_camps[record["id"]] = signature
                db.execute(insert, ("overture:camp:" + record["id"], "camping", record["name"], record["lat"],
                                    record["lon"], "overture_camping", record["id"], "full", "campground",
                                    record.get("street"), record.get("website"), None, None, None,
                                    record.get("conf"), region, json.dumps({"destination_id": region})))

        for row in airports["airports"]:
            db.execute(insert, ("ourairports:" + row["id"], "airport", row["name"], row["lat"], row["lon"],
                                "ourairports", row["id"], "full", row["type"], row.get("city"), None,
                                None, row.get("country"), row.get("iata"), None, None,
                                json.dumps({"scheduled_service": row.get("scheduled_service")})))

        uri = city_path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as cities:
            for ident, name, country, lat, lon, population in cities.execute(
                    "SELECT id,name,country,lat,lon,population FROM city ORDER BY id"):
                if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                db.execute(insert, (f"geonames:{ident}", "city", name, lat, lon, "geonames", str(ident), "full",
                                    "city", None, None, "Косово" if country == "XK" else country,
                                    "XK" if country == "XK" else reverse_countries.get(country), None, None, None,
                                    json.dumps({"population": population})))

        db.execute("INSERT INTO point_geo SELECT rowid,lon,lon,lat,lat FROM point")
        db.execute("CREATE INDEX point_kind_rowid ON point(kind,rowid)")
        db.execute("CREATE INDEX point_destination ON point(kind,destination_id,confidence)")
        db.execute("CREATE INDEX point_country ON point(country_code,kind,rowid)")
        counts = dict(db.execute("SELECT kind,count(*) FROM point GROUP BY kind").fetchall())
        metadata = {"schema": 1, "source_digest": source_digest.hexdigest(),
                    "built_at": datetime.now(timezone.utc).isoformat(), "counts": counts}
        db.executemany("INSERT INTO metadata VALUES (?,?)", [(key, json.dumps(value, ensure_ascii=False))
                                                             for key, value in metadata.items()])
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Map catalogue failed SQLite integrity check")
    finally:
        db.close()
    temp.replace(OUT)
    print("Map points:", counts, "size:", OUT.stat().st_size, "bytes", "digest:", source_digest.hexdigest())


if __name__ == "__main__":
    main()
