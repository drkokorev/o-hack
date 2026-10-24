"""Модельные предложения: отели, перелёты, поезда, трансферы.

Всё синтетическое, но правдоподобное и детерминированное: одинаковый запрос даёт одинаковую выдачу.
Время в пути считается по реальному расстоянию между городами, цены — по сезону направления.
Перевозчики вымышленные («Авиа Альфа»…), чтобы не выдавать моки за реальные рейсы.
"""

from __future__ import annotations

import zlib
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from random import Random

from pydantic import BaseModel, Field

from .geo import BY_ID, Area, Destination, Origin, distance_km

AIRLINES = ("Авиа Альфа", "Авиа Бета", "Авиа Гамма", "Авиа Дельта", "Авиа Сигма")
HUB_MOSCOW = (55.756, 37.617)

MEALS = {"room_only": "без питания", "breakfast": "завтраки", "half_board": "полупансион",
         "all_inclusive": "всё включено"}
AMENITIES = {
    "pool": "бассейн", "kids_club": "детский клуб", "spa": "спа", "gym": "фитнес", "parking": "парковка",
    "pets": "можно с животными", "beach_line": "первая линия", "wifi": "Wi-Fi", "kitchen": "кухня в номере",
}
_ALL_INCLUSIVE_PLACES = {"antalya", "hurghada", "sharm", "sanya", "dubai"}


def _rng(*parts: object) -> Random:
    return Random(zlib.crc32("|".join(map(str, parts)).encode()))


def season_factor(dest: Destination, day: date) -> float:
    if day.month in dest.peak_months:
        return 1.35
    neighbours = {(m % 12) + 1 for m in dest.peak_months} | {((m - 2) % 12) + 1 for m in dest.peak_months}
    return 1.0 if day.month in neighbours else 0.82


# ---------- Отели ----------

class Hotel(BaseModel):
    id: str
    dest_id: str
    name: str
    kind: str
    stars: int
    area: str
    center_km: float
    beach_km: float | None
    airport_km: float
    rating: float
    reviews: int
    base_price: int                     # за ночь на двоих в средний сезон
    meal: str
    amenities: list[str]
    check_in: str = "14:00"
    check_out: str = "12:00"
    early_checkin_fee: int | None = None   # None — ранний заезд только по наличию
    free_cancel_days: int | None = None    # None — невозвратный тариф
    praise: list[str] = Field(default_factory=list)
    complaints: list[str] = Field(default_factory=list)


_PREFIX = ("Гранд", "Ривьера", "Панорама", "Лагуна", "Бриз", "Резиденция", "Атриум", "Модерн", "Солнечный",
           "Альпина", "Норд", "Опал", "Сапфир", "Верес", "Акварель", "Европа")
_KINDS = (("Отель", 0), ("Резорт", 1), ("Апарт-отель", 0), ("Бутик-отель", 0), ("Гостевой дом", -1))
_PRAISE = {
    "pool": "Большой чистый бассейн", "kids_club": "Аниматоры и детский клуб — дети в восторге",
    "spa": "Хороший спа", "beach_line": "Вышел из номера — и ты на пляже", "breakfast": "Вкусные завтраки",
    "all_inclusive": "Еды много и она разнообразная", "parking": "Удобная парковка",
    "pets": "Без проблем заселились с собакой", "center": "Всё рядом, гуляли пешком",
}
_COMPLAINTS = ("Шумно по вечерам", "Номера требуют ремонта", "Медленный Wi-Fi", "Тонкие стены",
               "Долгое заселение", "Далеко от магазинов", "Маленький пляж, рано занимают шезлонги")


@lru_cache(maxsize=None)
def hotels_for(dest_id: str, count: int = 12) -> tuple[Hotel, ...]:
    dest = BY_ID[dest_id]
    rng = _rng("hotels", dest_id)
    names = rng.sample([f"{p} {k}" for p in _PREFIX for k, _ in _KINDS], count)
    out = []
    for i, name in enumerate(names):
        kind = name.split(" ", 1)[1]
        kind_bonus = dict(_KINDS)[kind]
        stars = max(2, min(5, rng.choice([3, 3, 4, 4, 4, 5]) + kind_bonus))
        area: Area = rng.choice(dest.areas)
        price = int(round(dest.base_price * (0.45 + 0.2 * stars) * rng.uniform(0.8, 1.25), -2))
        rating = round(min(9.8, 6.2 + 0.55 * stars + rng.uniform(-0.7, 0.7)), 1)
        meal = "room_only"
        r = rng.random()
        if dest_id in _ALL_INCLUSIVE_PLACES and stars >= 4 and kind in ("Резорт", "Отель") and r < 0.75:
            meal = "all_inclusive"
            price = int(price * 1.45)
        elif r < 0.55 + 0.08 * stars:
            meal = "breakfast"
        elif r < 0.8:
            meal = "half_board" if "sea" in dest.tags and stars >= 4 else "breakfast"
        chances = {"pool": 0.12 * stars + (0.3 if "warm" in dest.tags else 0), "kids_club": 0.08 * stars,
                   "spa": 0.13 * stars - 0.15, "gym": 0.14 * stars, "parking": 0.55, "pets": 0.25,
                   "kitchen": 0.7 if kind == "Апарт-отель" else 0.05}
        amenities = ["wifi"] + [a for a, p in chances.items() if rng.random() < p]
        if area.beach_km is not None and area.beach_km <= 0.2:
            amenities.append("beach_line")
        praise = [_PRAISE[a] for a in amenities if a in _PRAISE][:2]
        if meal in _PRAISE:
            praise.insert(0, _PRAISE[meal])
        if area.center_km <= 1.5:
            praise.append(_PRAISE["center"])
        complaints = rng.sample(_COMPLAINTS, 1 if rating >= 8.5 else 2)
        out.append(Hotel(
            id=f"{dest_id}-h{i + 1:02d}", dest_id=dest_id, name=name, kind=kind, stars=stars, area=area.name,
            center_km=round(area.center_km * rng.uniform(0.7, 1.3), 1),
            beach_km=round(area.beach_km * rng.uniform(0.6, 1.4), 1) if area.beach_km is not None else None,
            airport_km=round(area.airport_km * rng.uniform(0.85, 1.15)), rating=rating,
            reviews=rng.randint(60, 3500), base_price=price, meal=meal, amenities=sorted(set(amenities)),
            check_in=rng.choice(["14:00", "14:00", "15:00"]),
            early_checkin_fee=rng.choice([None, int(price * 0.5 // 100 * 100), 0]) if stars >= 3 else None,
            free_cancel_days=rng.choice([None, 1, 3, 3, 7, 14]),
            praise=praise[:3], complaints=complaints,
        ))
    return tuple(out)


def hotel_price(hotel: Hotel, check_in: date, nights: int, adults: int, children: int) -> int:
    dest = BY_ID[hotel.dest_id]
    total = 0.0
    for i in range(nights):
        day = check_in + timedelta(days=i)
        weekend = 1.1 if day.weekday() in (4, 5) and "city" in dest.tags else 1.0
        total += hotel.base_price * season_factor(dest, day) * weekend
    guests = 1 + 0.3 * max(0, adults - 2) + 0.15 * children - (0.15 if adults == 1 and not children else 0)
    if hotel.meal == "all_inclusive":
        guests += 0.35 * max(0, adults + children - 2)
    refundable = 1.0 if hotel.free_cancel_days is not None else 0.9
    return int(round(total * guests * refundable, -2))


# ---------- Транспорт ----------

class Leg(BaseModel):
    """Один перелёт или поезд «от двери до двери» между городами (возможна пересадка)."""
    id: str
    mode: str                      # plane | train
    carrier: str
    number: str
    depart: datetime
    arrive: datetime
    stops: int = 0
    via: str | None = None
    layover_min: int = 0
    baggage: bool = True
    seat_class: str = "эконом"
    price_per_person: int = 0
    pets_ok: bool = True
    note: str = ""

    @property
    def minutes(self) -> int:
        return int((self.arrive - self.depart).total_seconds() // 60)


def _flight_minutes(km: float) -> int:
    return int(km / 780 * 60 + 35)


def _origin_has_direct(origin: Origin, dest: Destination, rng: Random) -> bool:
    if origin.hub:
        return dest.id != "kamchatka" or origin.name == "Москва"
    popular = {"sochi", "antalya", "dubai", "hurghada", "moscow", "spb", "kaliningrad"}
    return dest.id in popular or rng.random() < 0.35


def flights(origin: Origin, dest: Destination, day: date) -> list[Leg]:
    """Варианты перелёта на дату. Без прямого рейса — с пересадкой в Москве."""
    if origin.name == dest.name:
        return []
    km = distance_km(origin.lat, origin.lon, dest.lat, dest.lon)
    rng = _rng("fl", origin.iata, dest.iata, day.isoformat())
    out: list[Leg] = []
    direct = _origin_has_direct(origin, dest, _rng("direct", origin.iata, dest.iata))
    base = (2600 + km * 4.3) * season_factor(dest, day)
    if dest.abroad:
        base *= 1.25
    for i in range(rng.randint(2, 4)):
        hour = rng.choice([1, 6, 7, 9, 11, 13, 15, 17, 19, 21, 23])
        dep = datetime.combine(day, time(hour, rng.choice([0, 15, 30, 45])))
        airline = rng.choice(AIRLINES)
        baggage = rng.random() < 0.7
        if direct and (i < 2 or rng.random() < 0.5):
            minutes = _flight_minutes(km)
            price = base * rng.uniform(0.85, 1.3) * (1.0 if baggage else 0.82)
            out.append(Leg(id=f"{origin.iata}-{dest.iata}-{day:%m%d}-{i}", mode="plane", carrier=airline,
                           number=f"{airline.split()[1][0]}{rng.randint(100, 999)}", depart=dep,
                           arrive=dep + timedelta(minutes=minutes), baggage=baggage,
                           price_per_person=int(round(price, -2))))
        else:
            hub_km_1 = distance_km(origin.lat, origin.lon, *HUB_MOSCOW)
            hub_km_2 = distance_km(*HUB_MOSCOW, dest.lat, dest.lon)
            if hub_km_1 < 300 or hub_km_2 < 300:
                continue
            layover = rng.choice([80, 120, 180, 260, 420, 600])
            minutes = _flight_minutes(hub_km_1) + layover + _flight_minutes(hub_km_2)
            price = (2600 + (hub_km_1 + hub_km_2) * 3.6) * season_factor(dest, day) * rng.uniform(0.8, 1.1)
            out.append(Leg(id=f"{origin.iata}-MOW-{dest.iata}-{day:%m%d}-{i}", mode="plane", carrier=airline,
                           number=f"{airline.split()[1][0]}{rng.randint(100, 999)}", depart=dep,
                           arrive=dep + timedelta(minutes=minutes), stops=1, via="Москва",
                           layover_min=layover, baggage=baggage,
                           price_per_person=int(round(price * (1.0 if baggage else 0.85), -2))))
    return sorted(out, key=lambda leg: leg.depart)


def trains(origin: Origin, dest: Destination, day: date) -> list[Leg]:
    if not (origin.rail and dest.rail) or origin.name == dest.name:
        return []
    km = distance_km(origin.lat, origin.lon, dest.lat, dest.lon) * 1.25  # по рельсам длиннее
    if km > 3200 or origin.lon > 65:  # из Сибири поездом на курорт никто не едет
        return []
    rng = _rng("tr", origin.iata, dest.iata, day.isoformat())
    out: list[Leg] = []
    fast = km < 800
    for i in range(2 if fast else rng.randint(1, 2)):
        if fast:
            dep = datetime.combine(day, time(rng.choice([6, 7, 9, 13, 16, 19]), rng.choice([0, 30])))
            minutes = int(km / 150 * 60)
            out.append(Leg(id=f"T-{origin.iata}-{dest.iata}-{day:%m%d}-{i}", mode="train",
                           carrier="Скоростной поезд", number=f"{rng.randint(700, 799)}", depart=dep,
                           arrive=dep + timedelta(minutes=minutes), seat_class="сидячий",
                           price_per_person=int(round((900 + km * 4.5) * rng.uniform(0.9, 1.2), -2)),
                           pets_ok=True, note="без пересадок, из центра в центр"))
        else:
            dep = datetime.combine(day, time(rng.choice([17, 19, 20, 21, 22, 23]), rng.choice([0, 20, 40])))
            minutes = int(km / 70 * 60)
            out.append(Leg(id=f"T-{origin.iata}-{dest.iata}-{day:%m%d}-{i}", mode="train",
                           carrier="Фирменный поезд", number=f"{rng.randint(1, 120):03d}", depart=dep,
                           arrive=dep + timedelta(minutes=minutes), seat_class="купе",
                           price_per_person=int(round((1500 + km * 3.0) * season_factor(dest, day)
                                                      * rng.uniform(0.9, 1.15), -2)),
                           pets_ok=True, note="ночь в поезде, животных можно в купе целиком"))
    return out


def transport_options(origin: Origin, dest: Destination, day: date, mode: str | None = None) -> list[Leg]:
    legs: list[Leg] = []
    if mode in (None, "plane"):
        legs += flights(origin, dest, day)
    if mode in (None, "train"):
        legs += trains(origin, dest, day)
    return legs


# ---------- Трансфер ----------

class Transfer(BaseModel):
    kind: str          # taxi | shuttle
    minutes: int
    price: int         # за машину / за всех
    note: str = ""


def transfer(hotel: Hotel, guests: int, train: bool = False) -> Transfer:
    dest = BY_ID[hotel.dest_id]
    km = hotel.center_km + 2 if train else hotel.airport_km
    per_km = 45 if dest.abroad else 35
    minutes = int(km / 40 * 60) + 15
    taxi = int(round((400 + km * per_km) * (1.4 if guests > 4 else 1.0), -1))
    if km > 40 and guests <= 3 and not train:
        shuttle = int(round(guests * (300 + km * 9), -1))
        if shuttle < taxi * 0.7:
            return Transfer(kind="shuttle", minutes=minutes + 40, price=shuttle,
                            note="групповой трансфер, может заезжать в другие отели")
    return Transfer(kind="taxi", minutes=minutes, price=taxi,
                    note="минивэн" if guests > 4 else "индивидуальный трансфер")
