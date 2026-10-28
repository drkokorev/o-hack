"""Add six Russian cities and bounded Overture lodging snapshots to the demo.

    python -m tools.expand_cities_20261027

Fetches Overture Places release 2026-10-21.0 and current OurAirports CSV.
City coordinates come from the project's GeoNames index (see THIRD_PARTY.md).
Prices, transport, hotel attributes and seasonality are demonstration models.
The process needs DuckDB and network access; the running application does not.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from domains.trips.geo import distance_km
from tools.build_hotels import KINDS, RELEASE, airports, bbox, connect, hotel_record, inside, places, quality

CITIES = [
    ("yaroslavl", "Ярославль", "IAR", 57.62987, 39.87368),
    ("yekaterinburg", "Екатеринбург", "SVX", 56.8519, 60.6122),
    ("samara", "Самара", "KUF", 53.20007, 50.15),
    ("ufa", "Уфа", "UFA", 54.74306, 55.96779),
    ("perm", "Пермь", "PEE", 58.01046, 56.25017),
    ("tyumen", "Тюмень", "TJM", 57.15222, 65.52722),
]
DATA = Path(__file__).resolve().parents[1] / "domains" / "trips" / "data"


def fetch() -> dict:
    result = {"cities": CITIES, "release": RELEASE, "accessed": date.today().isoformat(),
              "airports": airports({item[2] for item in CITIES}), "hotels": {}}
    con = connect()
    con.sql("PRAGMA disable_progress_bar")
    cats = ", ".join("'" + cat + "'" for cat in KINDS)
    for ident, name, _, lat, lon in CITIES:
        start = time.monotonic()
        destination = SimpleNamespace(id=ident, name=name, country="Россия", lat=lat, lon=lon)
        rows = places(con, bbox(lat, lon, 22),
                      f"taxonomy.primary in ({cats}) and coalesce(operating_status, 'open') = 'open'")
        records = {}
        for row in rows:
            if inside(destination, row) and (record := hotel_record(row)):
                record["overture_id"] = row[0]
                records[record["id"]] = record
        result["hotels"][ident] = sorted(records.values(), key=quality)[:300]
        print(f"{ident}: {len(rows)} source rows, {len(result['hotels'][ident])} retained, "
              f"{time.monotonic() - start:.1f}s", flush=True)
    return result


def apply(snapshot: dict) -> None:
    """Only commit the snapshot after every city and airport was retrieved."""
    if (snapshot.get("release") != RELEASE or [list(city) for city in snapshot.get("cities", [])] != [list(city) for city in CITIES]
            or not snapshot.get("accessed") or any(not snapshot["hotels"].get(ident)
            or iata not in snapshot["airports"] for ident, _, iata, _, _ in CITIES)):
        raise ValueError("Snapshot is incomplete; catalogue was not changed")
    for ident, _, _, lat, lon in CITIES:
        records = snapshot["hotels"][ident]
        if len(records) > 300 or len({record["id"] for record in records}) != len(records):
            raise ValueError(f"Invalid object count or duplicate ids for {ident}")
        if any(not record.get("overture_id") or record.get("conf", 0) < .5
               or distance_km(lat, lon, record["lat"], record["lon"]) > 22.01 for record in records):
            raise ValueError(f"Invalid provenance or coordinates for {ident}")
    geo_path, hotels_path = DATA / "geo.json", DATA / "hotels.json"
    geo = json.loads(geo_path.read_text(encoding="utf-8"))
    hotels = json.loads(hotels_path.read_text(encoding="utf-8"))
    known = {d["id"] for d in geo["destinations"]}
    for ident, name, iata, lat, lon in CITIES:
        if ident not in known:
            airport_lat, airport_lon = snapshot["airports"][iata]
            geo["destinations"].append({
                "id": ident, "name": name, "country": "Россия", "iata": iata,
                "lat": lat, "lon": lon, "tags": ["city", "culture"],
                "base_price": 7000,  # synthetic model input, not an observed price
                "highlights": ["городские прогулки", "культура и история"],
                "areas": [{"name": "Центр", "center_km": 0.0, "beach_km": None,
                           "airport_km": round(distance_km(lat, lon, airport_lat, airport_lon), 1)}],
                "visa": "не нужна", "rail": True, "sea": None, "peak_months": [],
                "aliases": [name.lower().replace("ё", "е")], "via": None,
            })
        hotels["hotels"][ident] = snapshot["hotels"][ident]
    hotels["airports"].update(snapshot["airports"])
    hotels["added_cities_20261027"] = {
        "source": f"Overture Maps Places release {RELEASE}; OurAirports and GeoNames",
        "accessed": snapshot["accessed"], "radius_km": 22, "max_per_city": 300,
        "fields": "name, category, coordinates, optional address/site/brand, Overture id and confidence",
    }
    geo_path.write_text(json.dumps(geo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    hotels_path.write_text(json.dumps(hotels, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, help="Apply a previously collected complete snapshot")
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else fetch()
    apply(snapshot)


if __name__ == "__main__":
    main()
