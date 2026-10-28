"""Read-only access to sourced map points; no prices or availability are inferred."""
from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from functools import lru_cache
from pathlib import Path

from .geo import DESTINATIONS

DATABASE = Path(__file__).with_name("data") / "map_catalog.sqlite3"
KINDS = {"hotel", "airport", "beach", "city", "camping", "all"}
COUNTRY_OVERRIDES = {"Доминикана": "DO", "США": "US", "Сейшелы": "SC", "Южная Корея": "KR"}


@lru_cache(maxsize=1)
def _countries() -> dict[str, str]:
    countries = json.loads((DATABASE.parent / "countries_ru.json").read_text(encoding="utf-8"))
    # GeoNames and OurAirports also use XK as a user-assigned code. It is not
    # an ISO 3166 country code, but omitting it would make records unfilterable.
    return {**countries, "XK": "Косово"}


def _destination_country(destination) -> str | None:
    if destination.country in COUNTRY_OVERRIDES:
        return COUNTRY_OVERRIDES[destination.country]
    matches = [code for code, name in _countries().items() if name == destination.country]
    return matches[0] if len(matches) == 1 else None


def _connection(path: Path | None = None) -> sqlite3.Connection:
    path = path or DATABASE
    if not path.is_file():
        raise FileNotFoundError("Пространственный каталог не собран; выполните python -m tools.build_map_catalog")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def validate_bounds(west: float, south: float, east: float, north: float) -> None:
    if (not all(math.isfinite(v) for v in (west, south, east, north)) or
            not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south <= north <= 90)):
        raise ValueError("Некорректные границы карты")


def _conditions(kind: str, west: float, south: float, east: float, north: float,
                country_code: str | None = None, destination_id: str | None = None):
    if kind not in KINDS:
        raise ValueError("Неизвестный тип точки")
    validate_bounds(west, south, east, north)
    world = west == -180 and east == 180 and south == -90 and north == 90
    clauses, values = [], []
    if kind != "all":
        clauses.append("p.kind = ?")
        values.append(kind)
    if destination_id:
        if not any(d.id == destination_id for d in DESTINATIONS):
            raise ValueError("Неизвестное направление")
        clauses.append("p.destination_id = ?")
        values.append(destination_id)
    if country_code:
        country_code = country_code.upper()
        if country_code not in _countries():
            raise ValueError("Неизвестный код страны")
        destinations = [d.id for d in DESTINATIONS if _destination_country(d) == country_code]
        if destinations:
            marks = ",".join("?" for _ in destinations)
            clauses.append(f"(p.country_code = ? OR p.destination_id IN ({marks}))")
            values.extend([country_code, *destinations])
        else:
            clauses.append("p.country_code = ?")
            values.append(country_code)
    if not world:
        # The R-tree uses outward-rounded coordinates; the exact checks against
        # the original values prevent edge points outside the viewport leaking in.
        clauses += ["g.min_lat <= ?", "g.max_lat >= ?", "p.lat >= ?", "p.lat <= ?"]
        values += [north, south, south, north]
        if west <= east:
            clauses += ["g.min_lon <= ?", "g.max_lon >= ?", "p.lon >= ?", "p.lon <= ?"]
            values += [east, west, west, east]
        else:  # a viewport crossing the antimeridian
            clauses += ["(g.max_lon >= ? OR g.min_lon <= ?)", "(p.lon >= ? OR p.lon <= ?)"]
            values += [west, east, west, east]
    tables = "point p" if world else "point_geo g JOIN point p ON p.rowid = g.rowid"
    return tables, clauses, values


def catalogue(path: Path | None = None) -> dict:
    with _connection(path) as db:
        meta = {row["key"]: json.loads(row["value"]) for row in db.execute("SELECT key,value FROM metadata")}
        sources = {row["id"]: dict(row) for row in db.execute("SELECT * FROM sources ORDER BY id")}
    return {"schema": meta["schema"], "catalog_version": meta["source_digest"], "built_at": meta["built_at"],
            "counts": meta["counts"], "sources": sources,
            "notice": "Снимки открытых источников: работа объектов, тарифы и наличие не проверены."}


def destinations(path: Path | None = None) -> dict:
    with _connection(path) as db:
        counts = {(row["destination_id"], row["kind"]): row["n"] for row in db.execute(
            "SELECT destination_id,kind,count(*) n FROM point WHERE destination_id IS NOT NULL "
            "GROUP BY destination_id,kind")}
        version = json.loads(db.execute("SELECT value FROM metadata WHERE key='source_digest'").fetchone()[0])
    items = [{"id": d.id, "name": d.name, "country_name": d.country, "country_code": _destination_country(d),
              "lat": d.lat, "lon": d.lon, "hotel_records": counts.get((d.id, "hotel"), 0),
              "camping_records": counts.get((d.id, "camping"), 0)} for d in DESTINATIONS]
    return {"catalog_version": version, "items": items,
            "notice": "Группы объектов относятся к району направления; страна каждого объекта не проверена."}


def countries(path: Path | None = None) -> dict:
    with _connection(path) as db:
        rows = db.execute("SELECT country_code,kind,count(*) n FROM point "
                          "WHERE country_code IS NOT NULL AND kind IN ('city','airport') "
                          "GROUP BY country_code,kind").fetchall()
    counts = {(row["country_code"], row["kind"]): row["n"] for row in rows}
    dest = destinations(path)
    dest_count = Counter(item["country_code"] for item in dest["items"] if item["country_code"])
    hotel_count = Counter()
    for item in dest["items"]:
        if item["country_code"]:
            hotel_count[item["country_code"]] += item["hotel_records"]
    items = [{"code": code, "name": name, "city_records": counts.get((code, "city"), 0),
              "airport_records": counts.get((code, "airport"), 0), "destination_count": dest_count[code],
              "hotel_records_near_destinations": hotel_count[code]}
             for code, name in sorted(_countries().items(), key=lambda item: item[1])]
    return {"catalog_version": dest["catalog_version"], "items": items,
            "notice": "Отели сгруппированы по стране направления; граница каждого объекта не проверялась. "
                      "Точки пляжей не имеют проверенной страны."}


def lookup(point_id: str, path: Path | None = None) -> dict | None:
    """Return one sourced record, including snapshot provenance, without enrichment."""
    with _connection(path) as db:
        row = db.execute("SELECT p.*,s.name source_name,s.url source_url,s.release source_release,"
                         "s.accessed_at source_accessed_at FROM point p JOIN sources s ON s.id=p.source "
                         "WHERE p.id = ?", (point_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result.pop("rowid")
    result["extra"] = json.loads(result["extra"]) if result["extra"] else None
    return result


def hotels_in_destination(dest_id: str, limit: int = 5, path: Path | None = None) -> list[dict]:
    """Only source fields for a known demo destination; never attach modelled attributes."""
    with _connection(path) as db:
        rows = db.execute("SELECT p.id,p.name,p.lat,p.lon,p.address,p.website,p.confidence,"
                          "s.name source_name,s.release source_release FROM point p "
                          "JOIN sources s ON s.id=p.source WHERE p.kind='hotel' AND p.destination_id=? "
                          "ORDER BY p.confidence DESC,p.id LIMIT ?", (dest_id, min(max(limit, 1), 20))).fetchall()
    return [dict(row) for row in rows]


def search_hotels(dest_id: str, name: str, limit: int = 5, path: Path | None = None) -> list[dict]:
    """Search the open snapshot by name in the selected destination; no rates or availability."""
    query = " ".join(name.casefold().split())
    if dest_id not in {d.id for d in DESTINATIONS} or not 3 <= len(query) <= 100:
        return []
    with _connection(path) as db:
        db.create_function("fold_name", 1, lambda value: " ".join(str(value or "").casefold().split()))
        rows = db.execute("SELECT p.id,p.name,p.lat,p.lon,p.address,p.website,p.confidence,"
                          "s.name source_name,s.release source_release FROM point p "
                          "JOIN sources s ON s.id=p.source WHERE p.kind='hotel' AND p.destination_id=? "
                          "AND instr(fold_name(p.name), ?) > 0 ORDER BY p.confidence DESC,p.id LIMIT ?",
                          (dest_id, query, min(max(limit, 1), 20))).fetchall()
    return [dict(row) for row in rows]


def points(kind: str, west: float, south: float, east: float, north: float, cursor: int = 0,
           limit: int = 500, path: Path | None = None, country_code: str | None = None,
           destination_id: str | None = None) -> dict:
    if cursor < 0 or not 1 <= limit <= 1000:
        raise ValueError("Некорректный размер страницы или курсор")
    tables, clauses, values = _conditions(kind, west, south, east, north, country_code, destination_id)
    clauses.append("p.rowid > ?")
    values.extend([cursor, limit + 1])
    sql = ("SELECT p.* FROM " + tables + " WHERE " + " AND ".join(clauses) +
           " ORDER BY p.rowid LIMIT ?")
    with _connection(path) as db:
        version = json.loads(db.execute("SELECT value FROM metadata WHERE key='source_digest'").fetchone()[0])
        rows = db.execute(sql, values).fetchall()
    items = []
    for row in rows[:limit]:
        item = dict(row)
        item.pop("rowid")
        item["extra"] = json.loads(item["extra"]) if item["extra"] else None
        items.append(item)
    return {"catalog_version": version, "kind": kind, "items": items,
            "next_cursor": rows[limit - 1]["rowid"] if len(rows) > limit else None}


def clusters(kind: str, west: float, south: float, east: float, north: float, zoom: int,
             path: Path | None = None, country_code: str | None = None, destination_id: str | None = None) -> dict:
    if not 0 <= zoom <= 8:
        raise ValueError("Кластеры доступны при масштабе 0–8")
    tables, clauses, values = _conditions(kind, west, south, east, north, country_code, destination_id)
    cell = 360.0 / (2 ** zoom)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    # Averages may land in the sea or in an unrelated country. Anchor each
    # group to one actual member so its marker and zoom target are a real
    # coordinate from the filtered source, not an invented location.
    sql = ("SELECT grouped.x,grouped.y,grouped.n,p.lat,p.lon,p.id representative_id FROM ("
           "SELECT CAST((p.lon+180.0)/? AS INTEGER) x, CAST((p.lat+90.0)/? AS INTEGER) y, "
           "COUNT(*) n, MIN(p.rowid) representative FROM " + tables + where +
           " GROUP BY x,y) grouped JOIN point p ON p.rowid=grouped.representative ORDER BY grouped.x,grouped.y")
    with _connection(path) as db:
        version = json.loads(db.execute("SELECT value FROM metadata WHERE key='source_digest'").fetchone()[0])
        rows = db.execute(sql, [cell, cell, *values]).fetchall()
    return {"catalog_version": version, "kind": kind, "zoom": zoom, "cell_degrees": cell,
            "items": [{"id": f"{row['x']}:{row['y']}", "count": row["n"],
                       "lat": row["lat"], "lon": row["lon"],
                       "representative_id": row["representative_id"]} for row in rows]}
