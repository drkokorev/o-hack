"""Модельные предложения: отели, перелёты, поезда, трансферы.

Всё синтетическое, но правдоподобное и детерминированное: одинаковый запрос даёт одинаковую выдачу.
Время в пути считается по реальному расстоянию между городами, цены — по сезону направления.
Перевозчики вымышленные («Авиа Альфа»…), чтобы не выдавать моки за реальные рейсы.
"""

from __future__ import annotations

import json
import re
import zlib
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from random import Random


from ..geo import BY_ID, DESTINATIONS, HUBS, Area, Destination, Origin, distance_km
from ..spatial import GeoPointIndex

from ..offer_models import AMENITIES, MEALS, Hotel, Leg, Transfer
from .demo_config import load_demo_config

DEMO = load_demo_config()

AIRLINES = DEMO.airlines
HUB_MOSCOW = DEMO.hub_moscow

_ALL_INCLUSIVE_PLACES = DEMO.all_inclusive_places


def _rng(*parts: object) -> Random:
    return Random(zlib.crc32("|".join(map(str, parts)).encode()))


def season_factor(dest: Destination, day: date) -> float:
    if day.month in dest.peak_months:
        return 1.35
    neighbours = {(m % 12) + 1 for m in dest.peak_months} | {((m - 2) % 12) + 1 for m in dest.peak_months}
    return 1.0 if day.month in neighbours else 0.82


def hotel_day_factors(dest: Destination, day: date) -> tuple[float, float]:
    weekend = 1.1 if day.weekday() in (4, 5) and "city" in dest.tags else 1.0
    return season_factor(dest, day), weekend


# ---------- Отели ----------



_PREFIX = DEMO.prefix
_KINDS = DEMO.kinds
_PRAISE = DEMO.praise
_COMPLAINTS = DEMO.complaints


def _attributes(rng: Random, dest: Destination, stars: int, kind: str, beach_km: float | None,
                center_km: float, known: set[str] = frozenset()) -> dict:
    """Модельные атрибуты отеля: цена, рейтинг, питание, удобства, условия — их нет в открытых данных."""
    price = int(round(dest.base_price * (0.45 + 0.2 * stars) * rng.uniform(0.8, 1.25), -2))
    if kind in ("Хостел", "Гостевой дом", "База отдыха"):
        price = int(price * 0.7)
    rating = round(min(9.8, 6.2 + 0.55 * stars + rng.uniform(-0.7, 0.7)), 1)
    meal = "room_only"
    r = rng.random()
    if dest.id in _ALL_INCLUSIVE_PLACES and stars >= 4 and kind in ("Резорт", "Отель") and r < 0.75:
        meal = "all_inclusive"
        price = int(price * 1.45)
    elif r < 0.55 + 0.08 * stars and kind not in ("Апартаменты", "Хостел"):
        meal = "breakfast"
    elif r < 0.8 and kind == "Отель":
        meal = "half_board" if "sea" in dest.tags and stars >= 4 else "breakfast"
    chances = {"pool": 0.12 * stars + (0.3 if "warm" in dest.tags else 0), "kids_club": 0.08 * stars,
               "spa": 0.13 * stars - 0.15, "gym": 0.14 * stars, "parking": 0.55, "pets": 0.25,
               "kitchen": 0.8 if kind in ("Апартаменты", "Апарт-отель") else 0.05}
    amenities = {"wifi"} | {a for a, p in chances.items() if rng.random() < p} | set(known)
    if beach_km is not None and beach_km <= 0.25:
        amenities.add("beach_line")
    praise = [_PRAISE[a] for a in sorted(amenities) if a in _PRAISE][:2]
    if meal in _PRAISE:
        praise.insert(0, _PRAISE[meal])
    if center_km <= 1.5:
        praise.append(_PRAISE["center"])
    return dict(stars=stars, base_price=price, rating=rating, reviews=rng.randint(30, 3500), meal=meal,
                amenities=sorted(amenities), check_in=rng.choice(["14:00", "14:00", "15:00"]),
                early_checkin_fee=rng.choice([None, int(price * 0.5 // 100 * 100), 0]) if stars >= 3 else None,
                free_cancel_days=rng.choice([None, 1, 3, 3, 7, 14]), praise=praise[:3],
                complaints=rng.sample(_COMPLAINTS, 1 if rating >= 8.5 else 2))


@lru_cache(maxsize=1)
def _real() -> dict:
    """Настоящие объекты размещения (tools/build_hotels.py: Overture Maps Places)."""
    path = Path(__file__).parent.parent / "data" / "hotels.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


@lru_cache(maxsize=1)
def hotel_count() -> int:
    """Размер каталога без генерации объектов и расчёта расстояний для каждого отеля."""
    records = _real().get("hotels", {})
    return sum(len(records[d.id]) if records.get(d.id) else 12 for d in DESTINATIONS)


_REAL_KINDS = DEMO.real_kinds
_KIND_STARS = DEMO.kind_stars
# Категория в открытых данных грубая («hotel» у базы отдыха и хостела) — уточняем по названию
_NAME_KINDS = (
    (re.compile(r"хостел|hostel", re.I), "Хостел"),
    (re.compile(r"база отдыха|турбаз|кемпинг|camping|глэмпинг|glamping", re.I), "База отдыха"),
    (re.compile(r"санатори|пансионат|sanatori", re.I), "Санаторий"),
    (re.compile(r"гостев|guest ?house|гостиный двор|мини-?отель|mini.?hotel|вилла|villa|homestay", re.I),
     "Гостевой дом"),
    (re.compile(r"апарт|apart|квартир|\bflat|studio|студи", re.I), "Апартаменты"),
    (re.compile(r"resort|резорт|курорт", re.I), "Резорт"),
)
_BRAND_STARS = (
    (re.compile(r"four seasons|ritz|st\.? regis|waldorf|mandarin|kempinski|rixos|jumeirah|swiss[oô]tel|"
                r"mriya|мрия|sheraton|hilton|marriott|hyatt|intercontinental|fairmont|sofitel|movenpick|"
                r"mövenpick|radisson collection|shangri", re.I), 5),
    (re.compile(r"radisson|novotel|holiday inn|park inn|hampton|courtyard|doubletree|crowne|pullman|"
                r"mercure|azimut|азимут|cosmos|космос|ramada|wyndham|barcel[oó]|alean|алеан", re.I), 4),
    (re.compile(r"\bibis\b|ibis budget|ibis styles|days inn|motel one", re.I), 3),
)
_STARS_IN_NAME = re.compile(r"(\d)\s?(?:\*|★|зв[её]зд|stars?)", re.I)


def _real_kind_stars(rng: Random, rec: dict) -> tuple[str, int]:
    name = rec["name"]
    kind = next((k for rx, k in _NAME_KINDS if rx.search(name)), _REAL_KINDS.get(rec.get("kind"), "Отель"))
    stars = rec.get("stars")
    if not stars and (m := _STARS_IN_NAME.search(name)) and 1 <= int(m.group(1)) <= 5:
        stars = int(m.group(1))
    if not stars:
        stars = next((s for rx, s in _BRAND_STARS if rx.search(name + " " + rec.get("brand", ""))), None)
    return kind, stars or rng.choice(_KIND_STARS[kind])


_NOT_OFFICIAL = re.compile(r"wikipedia|wikidata|facebook|instagram|vk\.com|ok\.ru|t\.me|booking\.|tripadvisor|"
                          r"ostrovok|airbnb|expedia|agoda|hotels\.com|yandex|google|2gis|tiktok|youtube", re.I)


def _clean_name(name: str) -> str:
    """«so_white_club_resort» → «So White Club Resort»: в открытых данных встречаются технические названия."""
    if "_" in name or name.islower():
        name = " ".join(w[:1].upper() + w[1:] for w in name.replace("_", " ").split())
    return name


def _official_site(url: str | None) -> str | None:
    """Ссылка «сайт» — только на собственный сайт отеля, не на агрегаторы и соцсети."""
    return url if url and not _NOT_OFFICIAL.search(url) else None


def _from_real(dest: Destination, records: list[dict], data: dict) -> list[Hotel]:
    beaches = data.get("beaches", {}).get(dest.id, [])
    beach_index = GeoPointIndex(beaches)
    airport = data.get("airports", {}).get(dest.iata)
    out = []
    for rec in records:
        rng = _rng("real", rec["id"])
        kind, stars = _real_kind_stars(rng, rec)
        center = round(distance_km(rec["lat"], rec["lon"], dest.lat, dest.lon), 1)
        beach = beach_index.nearest_km(rec["lat"], rec["lon"])
        known = {f for f in rec.get("features", []) if f in AMENITIES}
        attrs = _attributes(rng, dest, stars, kind, beach, center, known)
        area = rec.get("street") or rec.get("city") or dest.name
        lat, lon = rec["lat"], rec["lon"]
        out.append(Hotel(
            id=f"{dest.id}-h{rec['id']}", dest_id=dest.id, name=_clean_name(rec["name"]), kind=kind, area=area[:60],
            center_km=center, beach_km=beach,
            airport_km=round(distance_km(rec["lat"], rec["lon"], *airport)) if airport else 25,
            source="overture", website=_official_site(rec.get("web")),
            map_url=f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}",
            lat=lat, lon=lon, **attrs))
    return out


def hotels_for(dest_id: str, count: int = 12, *, catalog: dict | None = None) -> tuple[Hotel, ...]:
    """Отели направления: настоящие из открытого датасета, если есть, иначе модельные."""
    dest = BY_ID[dest_id]
    data = _real() if catalog is None else catalog
    records = data.get("hotels", {}).get(dest_id)
    if records:
        return tuple(_from_real(dest, records, data))
    rng = _rng("hotels", dest_id)
    names = rng.sample([f"{p} {k}" for p in _PREFIX for k, _ in _KINDS], count)
    out = []
    for i, name in enumerate(names):
        kind = name.split(" ", 1)[1]
        stars = max(2, min(5, rng.choice([3, 3, 4, 4, 4, 5]) + dict(_KINDS)[kind]))
        area: Area = rng.choice(dest.areas)
        center = round(area.center_km * rng.uniform(0.7, 1.3), 1)
        beach = round(area.beach_km * rng.uniform(0.6, 1.4), 1) if area.beach_km is not None else None
        out.append(Hotel(id=f"{dest_id}-h{i + 1:02d}", dest_id=dest_id, name=name, kind=kind, area=area.name,
                         center_km=center, beach_km=beach, airport_km=round(area.airport_km * rng.uniform(0.85, 1.15)),
                         **_attributes(rng, dest, stars, kind, beach, center)))
    return tuple(out)


def hotel_price(hotel: Hotel, check_in: date, nights: int, adults: int, children: int) -> int:
    dest = BY_ID[hotel.dest_id]
    total = 0.0
    for i in range(nights):
        day = check_in + timedelta(days=i)
        season, weekend = hotel_day_factors(dest, day)
        total += hotel.base_price * season * weekend
    guests = 1 + 0.3 * max(0, adults - 2) + 0.15 * children - (0.15 if adults == 1 and not children else 0)
    if hotel.meal == "all_inclusive":
        guests += 0.35 * max(0, adults + children - 2)
    refundable = 1.0 if hotel.free_cancel_days is not None else 0.9
    return int(round(total * guests * refundable, -2))


# ---------- Транспорт ----------



def _flight_minutes(km: float) -> int:
    return int(km / 780 * 60 + 35)


def _origin_has_direct(origin: Origin, dest: Destination, rng: Random) -> bool:
    if dest.via:  # из России туда прямых нет — только с пересадкой в хабе
        return False
    if origin.hub:
        return dest.id != "kamchatka" or origin.name == "Москва"
    if origin.airport_km is not None:
        # Города из расширенного справочника (Киров, Пенза…): прямые — в столицы и Сочи, изредка в Анталью;
        # дальнее зарубежье только с пересадкой
        return dest.id in {"moscow", "spb", "sochi"} or (dest.id == "antalya" and rng.random() < 0.3)
    popular = {"sochi", "antalya", "dubai", "hurghada", "moscow", "spb", "kaliningrad"}
    return dest.id in popular or rng.random() < 0.35


def flights(origin: Origin, dest: Destination, day: date) -> list[Leg]:
    """Варианты перелёта на дату. Без прямого рейса — с пересадкой в Москве или в хабе направления (`via`)."""
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
            hub_name = dest.via or "Москва"
            hub = HUBS.get(hub_name, HUB_MOSCOW)
            hub_km_1 = distance_km(origin.lat, origin.lon, *hub)
            hub_km_2 = distance_km(*hub, dest.lat, dest.lon)
            if hub_km_1 < 300 or hub_km_2 < 300:
                continue
            layover = rng.choice([80, 120, 180, 260, 420, 600])
            minutes = _flight_minutes(hub_km_1) + layover + _flight_minutes(hub_km_2)
            price = (2600 + (hub_km_1 + hub_km_2) * (4.3 if dest.via else 3.6)) * season_factor(dest, day)
            price *= rng.uniform(0.8, 1.1) * (1.25 if dest.abroad else 1.0)
            out.append(Leg(id=f"{origin.iata}-{hub_name[:3]}-{dest.iata}-{day:%m%d}-{i}", mode="plane", carrier=airline,
                           number=f"{airline.split()[1][0]}{rng.randint(100, 999)}", depart=dep,
                           arrive=dep + timedelta(minutes=minutes), stops=1, via=hub_name,
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
                           pets_ok=True, note="ночь в поезде"))
    return out


def transport_options(origin: Origin, dest: Destination, day: date, mode: str | None = None) -> list[Leg]:
    legs: list[Leg] = []
    if mode in (None, "plane"):
        legs += flights(origin, dest, day)
    if mode in (None, "train"):
        legs += trains(origin, dest, day)
    return legs


# ---------- Трансфер ----------



def transfer(hotel: Hotel, guests: int, train: bool = False, preferred: str | None = None) -> Transfer:
    dest = BY_ID[hotel.dest_id]
    km = hotel.center_km + 2 if train else hotel.airport_km
    per_km = 45 if dest.abroad else 35
    minutes = int(km / 40 * 60) + 15
    taxi = int(round((400 + km * per_km) * (1.4 if guests > 4 else 1.0), -1))
    if preferred == "shuttle":
        return Transfer(kind="shuttle", minutes=minutes + 40,
                        price=int(round(guests * (300 + km * 9), -1)),
                        note="групповой трансфер, может заезжать в другие отели")
    if preferred != "taxi" and km > 40 and guests <= 3 and not train:
        shuttle = int(round(guests * (300 + km * 9), -1))
        if shuttle < taxi * 0.7:
            return Transfer(kind="shuttle", minutes=minutes + 40, price=shuttle,
                            note="групповой трансфер, может заезжать в другие отели")
    return Transfer(kind="taxi", minutes=minutes, price=taxi,
                    note="минивэн" if guests > 4 else "индивидуальный трансфер")


class DemoInventory:
    """Explicit demo provider. A catalog snapshot never proves prices/availability."""
    def __init__(self, catalog=_real):
        self.catalog = catalog

    def hotels_for(self, dest_id: str, count: int = 12) -> tuple[Hotel, ...]:
        return hotels_for(dest_id, count, catalog=self.catalog())

    def hotel_count(self) -> int:
        records = self.catalog().get('hotels', {})
        return sum(len(records[d.id]) if records.get(d.id) else 12 for d in DESTINATIONS)

    hotel_price = staticmethod(hotel_price)
    transport_options = staticmethod(transport_options)
    transfer = staticmethod(transfer)
