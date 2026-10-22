"""Модель отеля и мок-каталог. После 23 окт сюда добавится адаптер под данные Островка."""

from __future__ import annotations

import random
from typing import Any

from pydantic import BaseModel, Field

AMENITIES = {
    "breakfast": "завтрак",
    "pool": "бассейн",
    "parking": "парковка",
    "spa": "спа",
    "gym": "фитнес",
    "pets": "можно с животными",
    "kids": "детская комната",
    "wifi": "Wi-Fi",
    "transfer": "трансфер",
}

TRIP_PURPOSES = {
    "family": "подходит для семьи",
    "business": "удобен для работы",
    "romantic": "хорош для пары",
    "budget": "бюджетный вариант",
}

CITY_ALIASES = {
    "питер": "Санкт-Петербург",
    "спб": "Санкт-Петербург",
    "петербург": "Санкт-Петербург",
    "ленинград": "Санкт-Петербург",
    "мск": "Москва",
}


class Hotel(BaseModel):
    id: str
    name: str
    city: str
    district: str = ""
    stars: int = 0
    price_per_night: int
    rating: float = 0.0
    reviews_count: int = 0
    distance_center_km: float = 0.0
    distance_sea_km: float | None = None
    amenities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    review_highlights: list[str] = Field(default_factory=list)
    lat: float | None = None
    lon: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict, description="Исходные поля, которые не легли в схему")


def normalize_city(raw: str) -> str:
    key = raw.strip().lower().replace("ё", "е")
    return CITY_ALIASES.get(key, raw.strip().title())


# город → (базовая цена за ночь, [(район, км до центра, км до моря | None)])
_CITIES: dict[str, tuple[int, list[tuple[str, float, float | None]]]] = {
    "Москва": (7000, [("Тверской", 0.8, None), ("Арбат", 1.5, None), ("Замоскворечье", 2.0, None),
                      ("Пресненский", 3.5, None), ("Сокольники", 7.0, None), ("Останкино", 9.0, None)]),
    "Санкт-Петербург": (5500, [("Центральный", 0.7, None), ("Адмиралтейский", 1.2, None),
                               ("Петроградский", 3.0, None), ("Василеостровский", 3.8, None),
                               ("Московский", 7.5, None)]),
    "Казань": (4200, [("Вахитовский", 0.6, None), ("Старо-Татарская слобода", 1.3, None),
                      ("Ново-Савиновский", 5.0, None)]),
    "Сочи": (6500, [("Центральный", 0.5, 0.3), ("Хоста", 15.0, 0.2), ("Адлер", 25.0, 0.4),
                    ("Красная Поляна", 45.0, None)]),
    "Калининград": (4000, [("Центральный", 0.8, None), ("Амалиенау", 3.0, None),
                           ("Ленинградский", 4.5, None)]),
}
_PREFIXES = ["Гранд", "Ривьера", "Сити", "Норд", "Резиденция", "Панорама", "Европа",
             "Империал", "Променад", "Атриум", "Модерн", "Альтаир"]
_KINDS = ["Отель", "Палас", "Апарт-отель", "Бутик-отель", "Хаус"]
_AMENITY_REVIEWS = {
    "breakfast": "Вкусный и разнообразный завтрак",
    "pool": "Чистый бассейн, детям понравилось",
    "spa": "Хороший спа, отлично отдохнули",
    "parking": "Удобная парковка прямо у входа",
    "gym": "Неплохой фитнес-зал",
    "pets": "Без проблем заселились с собакой",
    "kids": "Есть детская комната и аниматоры",
    "transfer": "Трансфер из аэропорта без задержек",
}
_GENERIC_REVIEWS = [
    "Чистые номера и удобные кровати",
    "Вежливый персонал, быстро заселили",
    "Тихо, хорошая шумоизоляция",
    "Отличное соотношение цены и качества",
]


def generate_hotels(seed: int = 42, per_city: int = 8) -> list[Hotel]:
    rng = random.Random(seed)
    hotels: list[Hotel] = []
    for city, (base_price, districts) in _CITIES.items():
        names = rng.sample([f"{p} {k}" for p in _PREFIXES for k in _KINDS], per_city)
        for name in names:
            district, center_km, sea_km = rng.choice(districts)
            stars = rng.choice([2, 3, 3, 4, 4, 5])
            price = int(round(base_price * (0.4 + 0.25 * stars) * rng.uniform(0.8, 1.25), -2))
            rating = round(min(9.8, 6.0 + 0.6 * stars + rng.uniform(-0.6, 0.8)), 1)
            chances = {"breakfast": 0.3 + 0.1 * stars, "parking": 0.5, "pool": 0.1 * stars,
                       "spa": 0.12 * stars - 0.2, "gym": 0.15 * stars, "pets": 0.25,
                       "kids": 0.3, "transfer": 0.1 * stars}
            amenities = ["wifi"] + [a for a, p in chances.items() if rng.random() < p]
            center = round(center_km * rng.uniform(0.6, 1.4), 1)
            sea = round(sea_km * rng.uniform(0.5, 1.5), 1) if sea_km is not None else None

            tags = []
            if "kids" in amenities or "pool" in amenities:
                tags.append("family")
            if "gym" in amenities or (center < 3 and stars >= 4):
                tags.append("business")
            if "spa" in amenities or (stars >= 4 and center < 2):
                tags.append("romantic")
            if price < base_price * 0.9:
                tags.append("budget")

            reviews = [_AMENITY_REVIEWS[a] for a in amenities if a in _AMENITY_REVIEWS][:2]
            reviews.append(rng.choice(_GENERIC_REVIEWS))
            if center <= 1.5:
                reviews.insert(0, "До главных достопримечательностей пешком")

            hotels.append(Hotel(
                id=f"h{len(hotels) + 1:03d}", name=name, city=city, district=district, stars=stars,
                price_per_night=price, rating=rating, reviews_count=rng.randint(40, 2500),
                distance_center_km=center, distance_sea_km=sea, amenities=amenities, tags=tags,
                review_highlights=reviews,
            ))
    return hotels
