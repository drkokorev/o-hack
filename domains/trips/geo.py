"""Справочник направлений и городов вылета.

Координаты, страны и аэропорты настоящие. Цены, районы и характеристики отелей — модельные
(синтетика для прототипа), климат по месяцам — реальные данные Open-Meteo (`data/climate.json`).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Area:
    name: str
    center_km: float          # до центра города / курорта
    beach_km: float | None    # до пляжа; None — моря нет
    airport_km: float         # до аэропорта или вокзала прибытия


@dataclass(frozen=True)
class Destination:
    id: str
    name: str
    country: str
    iata: str
    lat: float
    lon: float
    tags: tuple[str, ...]           # sea, beach, warm, mountains, ski, city, culture, nature, food, spa, exotic
    base_price: int                 # средняя цена ночи в отеле 3–4★ в сезон, руб. (модель)
    highlights: tuple[str, ...]
    areas: tuple[Area, ...]
    visa: str = "не нужна"
    rail: bool = False              # можно доехать поездом из европейской части России
    sea: tuple[float, float] | None = None  # точка в море для температуры воды
    peak_months: tuple[int, ...] = ()       # высокий сезон: цены выше
    aliases: tuple[str, ...] = field(default_factory=tuple)
    via: str | None = None          # прямых рейсов из России нет — летим с пересадкой в этом хабе (HUBS)

    @property
    def abroad(self) -> bool:
        return self.country != "Россия"


@dataclass(frozen=True)
class Origin:
    name: str
    iata: str
    lat: float
    lon: float
    hub: bool = False
    rail: bool = True
    gen: str = ""   # «из кого/чего»: из Москвы

    @property
    def from_(self) -> str:
        return "из " + (self.gen or self.name)


def _load_catalog(path: Path | None = None) -> tuple[tuple[Origin, ...], dict[str, tuple[float, float]], tuple[Destination, ...]]:
    """Читает версионированный справочник и проверяет его согласованность при запуске."""
    path = path or Path(__file__).with_name("data") / "geo.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    origins = tuple(Origin(**item) for item in data["origins"])
    hubs = {name: tuple(coords) for name, coords in data["hubs"].items()}
    destinations = []
    for item in data["destinations"]:
        fields = dict(item)
        fields["areas"] = tuple(Area(**area) for area in fields["areas"])
        for key in ("tags", "highlights", "peak_months", "aliases"):
            fields[key] = tuple(fields[key])
        if fields["sea"] is not None:
            fields["sea"] = tuple(fields["sea"])
        destinations.append(Destination(**fields))
    if len({origin.name for origin in origins}) != len(origins):
        raise ValueError("В справочнике повторяется город отправления")
    if len({dest.id for dest in destinations}) != len(destinations):
        raise ValueError("В справочнике повторяется id направления")
    for dest in destinations:
        if not (-90 <= dest.lat <= 90 and -180 <= dest.lon <= 180):
            raise ValueError(f"Некорректные координаты направления {dest.id}")
        if dest.via and dest.via not in hubs:
            raise ValueError(f"Неизвестный пересадочный узел направления {dest.id}")
        if not dest.areas or dest.base_price <= 0:
            raise ValueError(f"В справочнике нет районов или базовой цены направления {dest.id}")
    return origins, hubs, tuple(destinations)


ORIGINS, HUBS, DESTINATIONS = _load_catalog()

BY_ID = {d.id: d for d in DESTINATIONS}
ORIGIN_BY_NAME = {o.name: o for o in ORIGINS}

TAG_NAMES = {
    "sea": "море", "beach": "пляж", "warm": "тепло", "mountains": "горы", "ski": "горные лыжи",
    "city": "город", "culture": "культура и история", "nature": "природа", "food": "гастрономия",
    "spa": "оздоровление", "exotic": "экзотика",
}


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, max(0.0, a))))
