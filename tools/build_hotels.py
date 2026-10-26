"""Датасет настоящих объектов размещения для всех направлений каталога — из Overture Maps Places.

    .venv/bin/python -m tools.build_hotels            # докачать недостающие направления
    .venv/bin/python -m tools.build_hotels --force    # перекачать всё
    .venv/bin/python -m tools.build_hotels sochi      # только указанные направления

Overture Maps (overturemaps.org) — открытый датасет мест (Meta, Microsoft, Foursquare и др.; CDLA Permissive 2.0 /
Apache 2.0), лежит в публичном S3 в GeoParquet; DuckDB читает только нужные куски по bbox, без ключей и скрапинга.
Берём отели, резорты, гостевые дома, хостелы, апартаменты, коттеджи: название, координаты, сайт, адрес,
уверенность источника; для морских направлений — пляжи (расстояние до моря считаем по ним); координаты
аэропортов — из OurAirports (public domain). Результат: domains/trips/data/hotels.json.
Рейтингов, цен, питания и условий отмены в открытых данных нет — их по-прежнему моделирует offers.py.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import time
from pathlib import Path
from urllib.request import Request, urlopen

from domains.trips.geo import DESTINATIONS, ORIGINS, distance_km

OUT = Path(__file__).resolve().parent.parent / "domains" / "trips" / "data" / "hotels.json"
RELEASE = "2026-10-21.0"
PLACES = (f"read_parquet('s3://overturemaps-us-west-2/release/{RELEASE}/theme=places/type=place/*', "
          "hive_partitioning=1)")
# Категория Overture → тип размещения в offers.py
KINDS = {"hotel": "hotel", "lodging": "hotel", "resort": "resort", "beach_resort": "resort", "motel": "motel",
         "hostel": "hostel", "inn": "guest_house",
         "bed_and_breakfast": "guest_house", "guest_house": "guest_house", "holiday_rental_home": "apartment",
         "vacation_rental": "apartment", "service_apartment": "apartment", "apartment_hotel": "apartment",
         "cottage": "chalet", "cabin": "chalet", "chalet": "chalet", "lodge": "chalet", "mountain_hut": "chalet"}
MIN_CONFIDENCE = 0.5
MAX_PER_DEST = None  # берём все объекты, прошедшие фильтры (уверенность, страна, радиус)
# Радиус поиска вокруг центра направления, км: курортные регионы шире города
RADIUS = {"sochi": 50, "altai": 100, "baikal": 75, "murmansk": 130, "dagestan": 130, "kamchatka": 70,
          "karelia": 60, "antalya": 60, "dubai": 35, "hurghada": 30, "sharm": 25, "phuket": 30, "nhatrang": 35,
          "sanya": 35, "maldives": 60, "srilanka": 110, "bali": 50, "goa": 45, "kaliningrad": 45, "sheregesh": 15,
          "kislovodsk": 30, "vladivostok": 30}
# Объект должен быть в стране направления: у Сочи в радиус попадает Абхазия, у Батуми — Турция
ISO = {"Россия": "RU", "Турция": "TR", "ОАЭ": "AE", "Египет": "EG", "Таиланд": "TH", "Вьетнам": "VN", "Китай": "CN",
       "Мальдивы": "MV", "Шри-Ланка": "LK", "Грузия": "GE", "Армения": "AM", "Узбекистан": "UZ", "Азербайджан": "AZ",
       "Беларусь": "BY", "Казахстан": "KZ", "Индонезия": "ID", "Индия": "IN"}
AIRPORTS_CSV = "https://davidmegginson.github.io/ourairports-data/airports.csv"
UA = {"User-Agent": "o-odin-zapros/1.0 (hackathon prototype)"}


def connect():
    import duckdb  # только для сборки датасета: requirements-dev.txt

    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    return con


def bbox(lat: float, lon: float, km: float) -> tuple[float, float, float, float]:
    dlat = km / 111.0
    dlon = km / (111.0 * math.cos(math.radians(lat)))
    return lon - dlon, lon + dlon, lat - dlat, lat + dlat


def places(con, box: tuple[float, float, float, float], where: str) -> list[tuple]:
    x0, x1, y0, y1 = box
    sql = f"""
        select id, names.primary, coalesce(names.common['ru'], names.primary), taxonomy.primary, confidence,
               websites[1], addresses[1].freeform, addresses[1].locality, brand.names.primary, addresses[1].country,
               (bbox.ymin + bbox.ymax) / 2, (bbox.xmin + bbox.xmax) / 2
        from {PLACES}
        where bbox.xmin between {x0} and {x1} and bbox.ymin between {y0} and {y1} and {where}"""
    for attempt in range(4):
        try:
            return con.sql(sql).fetchall()
        except Exception as err:  # обрыв чтения из S3 — повторяем
            print(f"  {type(err).__name__}: {str(err)[:120]}; повтор через {10 * (attempt + 1)} с")
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("Overture недоступен")


def inside(d, row: tuple) -> bool:
    """В круге радиуса (bbox шире круга) и в стране направления."""
    country, lat, lon = row[9], row[10], row[11]
    if country and country != ISO.get(d.country, country):
        return False
    return distance_km(lat, lon, d.lat, d.lon) <= RADIUS.get(d.id, 22)


def hotel_record(row: tuple) -> dict | None:
    pid, name, name_ru, cat, conf, web, street, city, brand, _country, lat, lon = row
    name = (name_ru or name or "").strip()
    if not name or len(name) > 80 or conf is None or conf < MIN_CONFIDENCE:
        return None
    rec = {"id": f"o{pid.replace('-', '')[:16]}", "name": name, "kind": KINDS[cat],
           "lat": round(lat, 5), "lon": round(lon, 5), "conf": round(conf, 2)}
    for key, value in (("web", web), ("street", street), ("city", city), ("brand", brand)):
        if value:
            rec[key] = value[:120]
    return rec


def quality(rec: dict) -> tuple:
    """Кого оставить, если объектов больше лимита: надёжнее источник, есть сайт, классический отель — первыми."""
    order = {"hotel": 0, "resort": 0, "apartment": 1, "guest_house": 2, "chalet": 3, "motel": 4, "hostel": 5}
    return (-round(rec["conf"], 1), "web" not in rec, order.get(rec["kind"], 9), rec["name"])


def airports(codes: set[str]) -> dict[str, list[float]]:
    with urlopen(Request(AIRPORTS_CSV, headers=UA), timeout=120) as resp:
        rows = csv.DictReader(io.StringIO(resp.read().decode("utf-8")))
    found = {}
    for row in rows:
        if row.get("iata_code") in codes and row["type"] in ("large_airport", "medium_airport", "small_airport"):
            found[row["iata_code"]] = [round(float(row["latitude_deg"]), 4), round(float(row["longitude_deg"]), 4)]
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("only", nargs="*", help="id направлений (по умолчанию — все)")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    data["source"] = (f"Overture Maps Places {RELEASE} (CDLA Permissive 2.0 / Apache 2.0); "
                      "аэропорты — OurAirports, public domain")
    data.setdefault("hotels", {})
    data.setdefault("beaches", {})
    if not data.get("airports"):
        codes = {d.iata for d in DESTINATIONS} | {o.iata for o in ORIGINS} | {"SVO", "DME", "VKO"}
        data["airports"] = airports(codes)
        print("аэропорты:", len(data["airports"]))

    con = connect()
    cats = ", ".join(f"'{c}'" for c in KINDS)
    for d in DESTINATIONS:
        if (args.only and d.id not in args.only) or (d.id in data["hotels"] and not args.force and not args.only):
            continue
        started = time.time()
        box = bbox(d.lat, d.lon, RADIUS.get(d.id, 22))
        rows = places(con, box, f"taxonomy.primary in ({cats}) and coalesce(operating_status, 'open') = 'open'")
        recs = {rec["id"]: rec for row in rows if inside(d, row) and (rec := hotel_record(row))}
        hotels = sorted(recs.values(), key=quality)[:MAX_PER_DEST]
        data["hotels"][d.id] = hotels
        if d.sea:
            beaches = places(con, box, "taxonomy.primary = 'beach'")
            data["beaches"][d.id] = [[round(r[10], 4), round(r[11], 4)] for r in beaches if inside(d, r)][:1500]
        print(f"{d.name}: {len(rows)} объектов → {len(hotels)}; пляжей {len(data['beaches'].get(d.id, []))}; "
              f"{time.time() - started:.0f} с", flush=True)
        OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    total = sum(len(v) for v in data["hotels"].values())
    print(f"Итого объектов размещения: {total}; файл {OUT.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
