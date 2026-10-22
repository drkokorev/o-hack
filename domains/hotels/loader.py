"""Загрузка каталога отелей из файла с данными: CSV, JSON, JSONL, Parquet, Excel.

Колонки определяются автоматически по распространённым названиям (англ. и рус.). Если данные
устроены иначе — передайте явное соответствие `mapping={"price_per_night": "min_rate", ...}`.
Расстояние до центра считается по координатам, если его нет в данных.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import re
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from .catalog import AMENITIES, Hotel, normalize_city

log = logging.getLogger(__name__)

# Поле Hotel → возможные названия колонок (сравниваются без регистра, пробелов и подчёркиваний)
COLUMN_ALIASES: dict[str, list[str]] = {
    "id": ["id", "hotel_id", "hid", "ota_hotel_id", "property_id", "uid"],
    "name": ["name", "hotel_name", "title", "название", "наименование", "отель"],
    "city": ["city", "city_name", "town", "region_name", "город", "населенный_пункт"],
    "district": ["district", "area", "neighbourhood", "neighborhood", "address", "район", "адрес"],
    "stars": ["stars", "star_rating", "star", "category", "class", "звезды", "звёзды", "звездность"],
    "price_per_night": ["price_per_night", "price", "min_price", "min_rate", "rate", "avg_price",
                        "цена", "стоимость", "цена_за_ночь"],
    "rating": ["rating", "review_score", "score", "guest_rating", "рейтинг", "оценка"],
    "reviews_count": ["reviews_count", "review_count", "num_reviews", "reviews_num", "количество_отзывов"],
    "distance_center_km": ["distance_center_km", "distance_to_center", "center_distance", "до_центра"],
    "distance_sea_km": ["distance_sea_km", "distance_to_sea", "beach_distance", "до_моря"],
    "lat": ["lat", "latitude", "широта"],
    "lon": ["lon", "lng", "long", "longitude", "долгота"],
    "amenities": ["amenities", "facilities", "services", "features", "amenity_groups", "удобства", "услуги"],
    "review_highlights": ["review_highlights", "reviews", "review_texts", "отзывы"],
    "tags": ["tags", "kind", "type", "hotel_type", "тип"],
}

# Ключевые слова удобств в исходных данных (англ. и рус.) → наш код
AMENITY_KEYWORDS: dict[str, list[str]] = {
    "breakfast": ["breakfast", "завтрак"],
    "pool": ["pool", "бассейн"],
    "parking": ["parking", "парков"],
    "spa": ["spa", "sauna", "спа", "сауна"],
    "gym": ["gym", "fitness", "фитнес", "тренаж"],
    "pets": ["pet", "animal", "животн"],
    "kids": ["kids", "children", "child", "детск"],
    "wifi": ["wi-fi", "wifi", "internet", "интернет"],
    "transfer": ["transfer", "shuttle", "трансфер"],
}


def _key(name: str) -> str:
    return re.sub(r"[\s_\-]+", "_", name.strip().lower().replace("ё", "е"))


def detect_mapping(columns: Iterable[str]) -> dict[str, str]:
    by_key = {_key(c): c for c in columns}
    mapping = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if _key(alias) in by_key:
                mapping[field] = by_key[_key(alias)]
                break
    return mapping


def read_rows(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
            return list(csv.DictReader(f, dialect=dialect))
    if suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):  # {"hotels": [...]} или {"data": [...]}
            data = next((v for v in data.values() if isinstance(v, list)), [data])
        return data
    if suffix in (".parquet", ".xlsx", ".xls"):
        import pandas as pd  # только для этих форматов

        df = pd.read_parquet(path) if suffix == ".parquet" else pd.read_excel(path)
        return df.where(df.notna(), None).to_dict("records")
    raise ValueError(f"Неизвестный формат файла: {path.name}")


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return None if isinstance(value, float) and math.isnan(value) else float(value)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(value).replace(" ", "").replace(" ", ""))
    return float(m.group(0).replace(",", ".")) if m else None


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                return _list(json.loads(text))
            except json.JSONDecodeError:
                pass
        return [p.strip() for p in re.split(r"[;,|\n]", text) if p.strip()]
    if isinstance(value, dict):
        return [str(k) for k, v in value.items() if v] + _list(value.get("amenities"))
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            out += _list(item) if isinstance(item, (list, dict)) else [str(item)]
        return out
    return [str(value)]


def amenity_codes(raw: Any) -> list[str]:
    text = " | ".join(_list(raw)).lower()
    codes = [code for code, words in AMENITY_KEYWORDS.items() if any(w in text for w in words)]
    return [c for c in codes if c in AMENITIES]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def to_hotels(rows: list[dict[str, Any]], mapping: dict[str, str] | None = None,
              city_centers: dict[str, tuple[float, float]] | None = None) -> list[Hotel]:
    if not rows:
        return []
    mapping = {**detect_mapping(rows[0].keys()), **(mapping or {})}
    missing = [f for f in ("name", "city", "price_per_night") if f not in mapping]
    if missing:
        raise ValueError(f"Не нашёл колонки для {missing}; колонки файла: {list(rows[0].keys())}. "
                         "Передайте mapping явно.")
    log.info("Соответствие колонок: %s", mapping)
    used = set(mapping.values())
    hotels: list[Hotel] = []
    skipped = 0
    for i, row in enumerate(rows):
        get = lambda field: row.get(mapping[field]) if field in mapping else None  # noqa: E731
        price = _num(get("price_per_night"))
        name, city = get("name"), get("city")
        if not name or not city or not price or price <= 0:
            skipped += 1
            continue
        rating = _num(get("rating")) or 0.0
        if rating > 10:  # шкала 0–100
            rating /= 10
        stars = int(_num(get("stars")) or 0)
        hotels.append(Hotel(
            id=str(get("id") or f"r{i + 1:05d}"),
            name=str(name).strip(),
            city=normalize_city(str(city)),
            district=str(get("district") or "").strip(),
            stars=min(max(stars, 0), 5),
            price_per_night=int(round(price)),
            rating=round(rating, 1),
            reviews_count=int(_num(get("reviews_count")) or 0),
            distance_center_km=round(_num(get("distance_center_km")) or 0.0, 1),
            distance_sea_km=_num(get("distance_sea_km")),
            lat=_num(get("lat")), lon=_num(get("lon")),
            amenities=amenity_codes(get("amenities")),
            tags=_list(get("tags")),
            review_highlights=_list(get("review_highlights"))[:3],
            extra={k: v for k, v in row.items() if k not in used and v not in (None, "")},
        ))
    ratings = [h.rating for h in hotels if h.rating]
    if ratings and max(ratings) <= 5:  # шкала 0–5 → 0–10, как в ранжировании
        for h in hotels:
            h.rating = round(h.rating * 2, 1)
    if skipped:
        log.warning("Пропущено строк без названия, города или цены: %d из %d", skipped, len(rows))
    if "distance_center_km" not in mapping:
        _fill_center_distance(hotels, city_centers or {})
    return hotels


def _fill_center_distance(hotels: list[Hotel], centers: dict[str, tuple[float, float]]) -> None:
    """Центр города — заданная точка или медиана координат отелей (отели тяготеют к центру)."""
    by_city: dict[str, list[Hotel]] = {}
    for h in hotels:
        if h.lat is not None and h.lon is not None:
            by_city.setdefault(h.city, []).append(h)
    for city, items in by_city.items():
        lat, lon = centers.get(city) or (median(h.lat for h in items), median(h.lon for h in items))  # type: ignore[misc]
        for h in items:
            h.distance_center_km = round(haversine_km(h.lat, h.lon, lat, lon), 1)  # type: ignore[arg-type]


def load_hotels(path: str | Path, mapping: dict[str, str] | None = None) -> list[Hotel]:
    hotels = to_hotels(read_rows(path), mapping)
    log.info("Загружено отелей: %d из %s", len(hotels), path)
    return hotels
