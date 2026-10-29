"""Сборка поездки: варианты «оптимальный / экономный / комфорт», объяснения, компромиссы и проверка состыковок."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from math import prod

from core.ru import fmt_money

from .climate import climate
from .geo import Destination, Origin
from .offers import AMENITIES, MEALS, Hotel, Leg, Transfer, hotel_day_factors, hotel_price, hotels_for, transfer, transport_options

MEAL_RANK = {"room_only": 0, "meal_included": 1, "breakfast": 1, "half_board": 2, "all_inclusive": 3}
VIA_PREP = {"Москва": "Москве", "Стамбул": "Стамбуле", "Дубай": "Дубае", "Белград": "Белграде", "Пекин": "Пекине"}
PACKAGE_TITLES = {"optimal": "Оптимальный", "budget": "Экономный", "comfort": "Комфорт"}


@dataclass
class Trip:
    origin: Origin
    dest: Destination
    date_in: date
    date_out: date
    adults: int
    children: int
    pets: bool = False
    budget: int | None = None
    budget_night: int | None = None
    mode: str | None = None
    seat_class: str | None = None
    direct_only: bool = False
    baggage_required: bool = False
    max_hours: float | None = None
    meal: str | None = None
    free_cancellation: bool = False
    stars_min: int | None = None
    wishes: list[str] = field(default_factory=list)
    trip_types: list[str] = field(default_factory=list)
    room_guests: list[tuple[int, int]] = field(default_factory=list)  # explicit adults, children per room
    transfer_kind: str | None = None

    @property
    def nights(self) -> int:
        return (self.date_out - self.date_in).days

    @property
    def people(self) -> int:
        return self.adults + self.children


@dataclass
class Package:
    key: str
    out: Leg
    back: Leg
    hotel: Hotel
    hotel_total: int
    transfer_in: Transfer
    transfer_out: Transfer
    hotel_in: date | None = None       # заезд по факту прибытия (ночной поезд/рейс сдвигает его)
    hotel_out: date | None = None
    why: list[str] = field(default_factory=list)
    tradeoffs: list[str] = field(default_factory=list)
    checks: list[tuple[str, str]] = field(default_factory=list)  # (ok | warn | risk, текст)

    def total(self, people: int) -> int:
        return (self.out.price_per_person + self.back.price_per_person) * people + self.hotel_total \
            + self.transfer_in.price + self.transfer_out.price

    @property
    def title(self) -> str:
        return PACKAGE_TITLES[self.key]


def _leg_matches(leg: Leg, *, direct_only: bool = False, pets: bool = False,
                 baggage_required: bool = False, max_hours: float | None = None, seat_class: str | None = None) -> bool:
    if seat_class and leg.seat_class != seat_class:
        return False
    if direct_only and leg.stops:
        return False
    if pets and not leg.pets_ok:
        return False
    if baggage_required and leg.mode == "plane" and not leg.baggage:
        return False
    if max_hours is not None and leg.minutes > max_hours * 60:
        return False
    return True


def _leg_ok(leg: Leg, trip: Trip) -> bool:
    # A train's baggage rules are unknown and must be disclosed separately.
    return _leg_matches(leg, direct_only=trip.direct_only, pets=trip.pets,
                        baggage_required=trip.baggage_required, max_hours=trip.max_hours, seat_class=trip.seat_class)


def _leg_penalty(leg: Leg, trip: Trip) -> float:
    """Чем меньше, тем лучше: деньги плюс время и неудобства в рублях."""
    p = leg.price_per_person * trip.people
    p += leg.minutes * (25 if trip.children else 15) * trip.people
    if leg.stops:
        p += 4000 + (3000 if trip.children else 0)
        if leg.layover_min < 90:
            p += 3000
    hour = leg.depart.hour
    if hour < 6 or hour >= 23:  # ночной рейс: не выспаться, а обратно — выезд из отеля ночью
        p += 6000 * trip.people + (8000 if trip.children else 0)
    arr = leg.arrive.hour
    if arr < 6 and leg.mode == "plane":
        p += 2000 * trip.people
    if not leg.baggage and (trip.children or trip.nights >= 5):
        p += 3000 * trip.people
    return p


RELAX_STEPS = (  # ослабляем по одному условию, от наименее важного; пишем пользователю, что именно
    ("wishes", "удобства из пожеланий сделал желательными"),
    ("free_cancellation", "бесплатную отмену сделал желательной"),
    ("budget_night", "снял ограничение цены за ночь"),
    ("stars_min", "снял ограничение по звёздам"),
    ("meal", "снял требование к питанию"),
)


def _hotel_filter(h: Hotel, trip: Trip, relaxed: set[str], peak_night: date) -> bool:
    if trip.pets and "pets" not in h.amenities:
        return False
    if "budget_night" not in relaxed and trip.budget_night:
        if _stay_price(h, trip, peak_night, 1) > trip.budget_night:
            return False
    if "stars_min" not in relaxed and trip.stars_min and h.stars < trip.stars_min:
        return False
    if "meal" not in relaxed and trip.meal and MEAL_RANK[h.meal] < MEAL_RANK.get(trip.meal, 0):
        return False
    if "free_cancellation" not in relaxed and trip.free_cancellation and h.free_cancel_days is None:
        return False
    if "wishes" not in relaxed and any(w not in h.amenities for w in trip.wishes if w != "pets"):
        return False
    return True


def _stay_price(h: Hotel, trip: Trip, start: date, nights: int) -> int:
    """Demo price is summed once per explicitly allocated room."""
    guests = trip.room_guests or [(trip.adults, trip.children)]
    return sum(hotel_price(h, start, nights, adults, children) for adults, children in guests)


def _hotel_value(h: Hotel, price: int, trip: Trip) -> float:
    beach = bool({"sea", "beach"} & set(trip.trip_types)) or "beach_line" in trip.wishes
    v = h.rating * 4000 * trip.nights - price
    if beach and h.beach_km is not None:
        v -= h.beach_km * 2500 * trip.nights
    elif not beach:
        v -= min(h.center_km, 15) * 800 * trip.nights
    if trip.children and "kids_club" in h.amenities:
        v += 1500 * trip.nights
    if trip.children and "pool" in h.amenities:
        v += 1000 * trip.nights
    for w in trip.wishes:
        if w in h.amenities:
            v += 1200 * trip.nights
    if trip.free_cancellation and h.free_cancel_days is not None:
        v += 3000
    return v


def candidate_hotels(trip: Trip) -> tuple[list[tuple[Hotel, int]], list[str]]:
    """Отели по фильтрам; если пусто — ослабляем по одному условию. Второе значение — что пришлось ослабить."""
    relaxed: set[str] = set()
    notes: list[str] = []
    active = {"wishes": bool([w for w in trip.wishes if w != "pets"]), "free_cancellation": trip.free_cancellation,
              "budget_night": bool(trip.budget_night), "stars_min": bool(trip.stars_min), "meal": bool(trip.meal)}
    # The daily season/weekend multiplier is shared by every hotel in this
    # destination. Check its most expensive night once per hotel, not every
    # night per hotel. Other multipliers are constant across the stay.
    peak_night = max((trip.date_in + timedelta(days=i) for i in range(trip.nights)),
                     key=lambda day: prod(hotel_day_factors(trip.dest, day)), default=trip.date_in) if trip.budget_night else trip.date_in
    for key, note in ((None, None), *RELAX_STEPS):
        if key is not None:
            if not active[key]:
                continue
            relaxed.add(key)
            notes.append(note)
        hotels = [h for h in hotels_for(trip.dest.id) if _hotel_filter(h, trip, relaxed, peak_night)]
        if hotels:
            priced = [(h, _stay_price(h, trip, trip.date_in, trip.nights)) for h in hotels]
            return priced, notes
    return [], notes


def make_packages(trip: Trip, pinned_hotel: str | None = None, *, hidden_hotels=(), preferred_hotels=()) -> tuple[list[Package], list[str]]:
    outs = [leg for leg in transport_options(trip.origin, trip.dest, trip.date_in, trip.mode) if _leg_ok(leg, trip)]
    backs = [leg for leg in transport_options(trip.origin, trip.dest, trip.date_out, trip.mode)
             if _leg_ok(leg, trip)]
    if not outs or not backs:
        return [], ["нет подходящего транспорта на эти даты"]
    hotels, relaxed = candidate_hotels(trip)
    hotels = [hp for hp in hotels if hp[0].id not in hidden_hotels]
    if not hotels:
        return [], ["нет отелей, которые принимают ваши условия"]

    if trip.children or trip.nights >= 5:  # с ребёнком или на неделю без багажа не летают…
        night = lambda leg: leg.depart.hour < 6 or leg.depart.hour >= 23  # noqa: E731
        with_bag_out = [leg for leg in outs if leg.baggage]
        with_bag_back = [leg for leg in backs if leg.baggage]
        # …но если с багажом остались только ночные рейсы, оставляем и дневные без багажа — пусть решит пользователь
        outs = with_bag_out if with_bag_out and not all(map(night, with_bag_out)) else outs
        backs = with_bag_back if with_bag_back and not all(map(night, with_bag_back)) else backs
    best_out = min(outs, key=lambda leg: _leg_penalty(leg, trip))
    best_back = min(backs, key=lambda leg: _leg_penalty(leg, trip))
    cheap_out = min(outs, key=lambda leg: (leg.price_per_person, leg.minutes))
    cheap_back = min(backs, key=lambda leg: (leg.price_per_person, leg.minutes))
    def comfort_key(leg: Leg) -> tuple:
        night = leg.depart.hour < 6 or leg.depart.hour >= 23
        return (leg.stops, night, leg.minutes // 30, leg.price_per_person)

    fast_out = min(outs, key=comfort_key)
    fast_back = min(backs, key=comfort_key)

    by_value = sorted(hotels, key=lambda hp: (hp[0].id not in preferred_hotels, -_hotel_value(hp[0], hp[1], trip)))
    pinned = next((hp for hp in hotels if hp[0].id == pinned_hotel), None)
    if pinned_hotel and pinned is None:
        return [], ["выбранный отель не подходит под текущие условия или отсутствует в демонстрационном каталоге"]
    def stay_cost(hp: tuple[Hotel, int]) -> int:  # отель вместе с трансферами туда и обратно
        return hp[1] + transfer(hp[0], trip.people, outs[0].mode == "train", trip.transfer_kind).price * 2

    # Для отдыха на море даже «Экономный» и «Комфорт» — не дальше пешей прогулки до пляжа (если такие есть)
    beach = bool({"sea", "beach"} & set(trip.trip_types)) or "beach_line" in trip.wishes
    near = [hp for hp in hotels if hp[0].beach_km is not None and hp[0].beach_km <= 1.5] if beach else hotels
    near = near or hotels
    decent = [hp for hp in near if hp[0].rating >= 7.5] or near
    cheap_hotel = min(decent, key=stay_cost)
    comfy = [hp for hp in near if hp[0].stars >= 4] or near

    # Оптимальный: лучший отель по ценности, который вместе с дорогой укладывается в бюджет
    optimal_hotel = pinned or by_value[0]
    if trip.budget and not pinned:
        for hp in by_value:
            if _total(best_out, best_back, hp[1], trip) <= trip.budget:
                optimal_hotel = hp
                break
    # «Комфорт» — лучший по рейтингу и звёздам, но другой отель, чем в «Оптимальном»: иначе сравнивать нечего
    comfort_pool = [hp for hp in comfy if hp[0].id != optimal_hotel[0].id] or comfy
    comfort_hotel = max(comfort_pool, key=lambda hp: (hp[0].rating, hp[0].stars, -hp[1]))

    if stay_cost(optimal_hotel) < stay_cost(cheap_hotel):  # «Экономный» обязан быть самым дешёвым
        cheap_hotel = optimal_hotel
    packages = []
    for key, out, back, (hotel, price) in (
        ("optimal", best_out, best_back, optimal_hotel),
        ("budget", cheap_out, cheap_back, pinned or cheap_hotel),
        ("comfort", fast_out, fast_back, pinned or comfort_hotel),
    ):
        hotel_in = max(trip.date_in, out.arrive.date() if out.arrive.hour >= 5 else out.arrive.date() - timedelta(days=1))
        hotel_out = min(trip.date_out, back.depart.date())
        if (hotel_in, hotel_out) != (trip.date_in, trip.date_out) and hotel_out > hotel_in:
            price = _stay_price(hotel, trip, hotel_in, (hotel_out - hotel_in).days)
        pkg = Package(key, out, back, hotel, price,
                      transfer(hotel, trip.people, out.mode == "train", trip.transfer_kind),
                      transfer(hotel, trip.people, back.mode == "train", trip.transfer_kind), hotel_in, hotel_out)
        if any(p.out.id == pkg.out.id and p.back.id == pkg.back.id and p.hotel.id == pkg.hotel.id
               for p in packages):
            continue
        packages.append(pkg)
    for pkg in packages:
        explain(pkg, trip, packages)
        pkg.checks = check(pkg, trip)
    return packages, [r for r in relaxed if r]


def _total(out: Leg, back: Leg, hotel_price_: int, trip: Trip) -> int:
    return (out.price_per_person + back.price_per_person) * trip.people + hotel_price_ + 3000


def hm(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h} ч {m:02d} мин" if h and m else (f"{h} ч" if h else f"{m} мин")


def leg_text(leg: Leg) -> str:
    kind = "поезд" if leg.mode == "train" else "рейс"
    via = f", пересадка в {VIA_PREP.get(leg.via or '', leg.via)} {hm(leg.layover_min)}" if leg.stops else (", без пересадок" if leg.mode == "plane" else "")
    bag = "" if leg.mode == "train" else (", с багажом" if leg.baggage else ", только ручная кладь")
    return (f"{kind} {leg.carrier} {leg.number}: {leg.depart:%d.%m %H:%M} → {leg.arrive:%d.%m %H:%M} "
            f"({hm(leg.minutes)}{via}{bag}, класс {leg.seat_class})")


def explain(pkg: Package, trip: Trip, all_: list[Package]) -> None:
    h = pkg.hotel
    why = [f"{h.name}, {h.stars}★, рейтинг {h.rating:.1f} ({h.reviews} отзывов, демо)"]
    if h.beach_km is not None and {"sea", "beach"} & set(trip.trip_types):
        why.append("первая линия" if h.beach_km <= 0.2 else f"{h.beach_km:g} км до пляжа")
    elif h.center_km <= 2:
        why.append(f"{h.center_km:g} км от центра")
    if MEAL_RANK[h.meal] > 0:
        why.append(MEALS[h.meal])
    if trip.children and {"kids_club", "pool"} & set(h.amenities):
        why.append("для детей: " + ", ".join(AMENITIES[a] for a in ("kids_club", "pool") if a in h.amenities))
    if trip.pets:
        why.append("животные указаны в демо-каталоге; условия размещения не проверены")
    if h.free_cancel_days is not None:
        why.append(f"бесплатная отмена за {h.free_cancel_days} дн.")
    if not pkg.out.stops and pkg.out.mode == "plane":
        why.append("перелёт без пересадок")
    if pkg.out.mode == "train":
        why.append("поезд — без аэропортов, " + pkg.out.note)
    pkg.why = why

    people = trip.people
    totals = {p.key: p.total(people) for p in all_}
    trade = []
    cheapest_key = min(totals, key=totals.get)
    if totals[pkg.key] > totals[cheapest_key]:
        trade.append(f"дороже варианта «{PACKAGE_TITLES[cheapest_key]}» на {fmt_money(totals[pkg.key] - totals[cheapest_key])}")
    best = max(all_, key=lambda p: p.hotel.rating)
    if h.rating < best.hotel.rating - 0.3:
        trade.append(f"рейтинг отеля ниже, чем в варианте «{best.title}» ({h.rating:.1f} против {best.hotel.rating:.1f})")
    fastest = min(p.out.minutes for p in all_)
    if pkg.out.minutes > fastest + 60:
        trade.append(f"дорога дольше на {hm(pkg.out.minutes - fastest)}")
    for leg, label in ((pkg.out, "туда"), (pkg.back, "обратно")):
        if leg.depart.hour < 6 or leg.depart.hour >= 23:
            trade.append(f"ночное отправление {label} в {leg.depart:%H:%M}")
    if h.free_cancel_days is None:
        trade.append("невозвратный тариф отеля")
    if not pkg.out.baggage and pkg.out.mode == "plane":
        trade.append("без багажа — только ручная кладь")
    if h.complaints:
        trade.append(f"в демо-отзывах жалуются: {h.complaints[0].lower()}")
    pkg.tradeoffs = trade


def _parse_time(day: date, hhmm: str) -> datetime:
    hh, mm = map(int, hhmm.split(":"))
    return datetime.combine(day, time(hh, mm))


def check(pkg: Package, trip: Trip) -> list[tuple[str, str]]:
    """Состыковки: прибытие → трансфер → заселение, выезд → трансфер → отправление, пересадки, бюджет."""
    out: list[tuple[str, str]] = []
    if pkg.hotel_in and pkg.hotel_in > trip.date_in:
        out.append(("warn", f"прибываете {pkg.out.arrive:%d.%m} — отель беру с {pkg.hotel_in:%d.%m}, "
                            "чтобы не платить за пустую ночь"))
    travel = pkg.out.minutes + pkg.back.minutes
    if travel > trip.nights * 24 * 60 * 0.35:
        alt = "самолёт" if pkg.out.mode == "train" else "направление поближе"
        out.append(("risk", f"в дороге {hm(travel)} туда-обратно при {trip.nights} ночах — "
                            f"много для такой поездки, может, {alt}?"))
    exit_min = 40 if pkg.out.mode == "plane" else 15
    at_hotel = pkg.out.arrive + timedelta(minutes=exit_min + pkg.transfer_in.minutes)
    # Учитываем уже оплаченную предыдущую ночь: приезд после полуночи не
    # становится ранним заездом следующего дня.
    check_in = _parse_time(pkg.hotel_in or trip.date_in, pkg.hotel.check_in)
    if at_hotel < check_in - timedelta(hours=2):
        fee = pkg.hotel.early_checkin_fee
        early = "ранний заезд бесплатно" if fee == 0 else (
            f"ранний заезд за {fmt_money(fee)} при наличии; доплата не включена в итог" if fee
            else "ранний заезд только по наличию — оставите багаж")
        out.append(("warn", f"в отеле в {at_hotel:%H:%M}, заселение с {pkg.hotel.check_in}: {early}"))
    elif at_hotel.hour >= 23 or at_hotel.hour < 5:
        out.append(("warn" if not trip.children else "risk",
                    f"в отеле в {at_hotel:%H:%M} — поздний заезд, нужно предупредить отель"))
    else:
        out.append(("ok", f"прибытие → трансфер {hm(pkg.transfer_in.minutes)} → в отеле в {at_hotel:%H:%M}, "
                          f"заселение с {pkg.hotel.check_in}"))

    buffer = 120 if pkg.back.mode == "plane" else 40
    leave = pkg.back.depart - timedelta(minutes=buffer + pkg.transfer_out.minutes)
    hotel_out = pkg.hotel_out or trip.date_out
    check_out = _parse_time(hotel_out, pkg.hotel.check_out)
    if leave.date() < hotel_out:
        out.append(("risk", f"обратный рейс в {pkg.back.depart:%H:%M}: выезжать из отеля ночью накануне"))
    elif leave > check_out + timedelta(hours=4):
        out.append(("warn", f"выезд из номера в {pkg.hotel.check_out}, а ехать на "
                            f"{'вокзал' if pkg.back.mode == 'train' else 'рейс'} в {leave:%H:%M} — "
                            "можно запросить поздний выезд или хранение багажа"))
    elif leave.hour < 5:
        out.append(("warn", f"выезд из отеля в {leave:%H:%M} — очень рано"))
    else:
        out.append(("ok", f"выезд в {leave:%H:%M} → {'вокзал' if pkg.back.mode == 'train' else 'аэропорт'} "
                          f"с запасом {hm(buffer)}"))

    for leg, label in ((pkg.out, "туда"), (pkg.back, "обратно")):
        if leg.stops and leg.layover_min < 90:
            out.append(("risk", f"пересадка {label} всего {hm(leg.layover_min)} — можно не успеть"))
        elif leg.stops and leg.layover_min > 360:
            out.append(("warn", f"пересадка {label} {hm(leg.layover_min)} — долго ждать"))

    total = pkg.total(trip.people)
    if trip.budget:
        if total <= trip.budget:
            out.append(("ok", f"в бюджете: остаётся {fmt_money(trip.budget - total)}"))
        else:
            out.append(("risk", f"дороже бюджета на {fmt_money(total - trip.budget)}"))
    if trip.dest.abroad:
        out.append(("warn", f"виза по демо-справочнику: {trip.dest.visa}; проверьте требования к документам"))
        if trip.pets:
            out.append(("warn", "с животным: уточните правила ввоза и необходимые документы"))
    if trip.pets and pkg.out.mode == "plane":
        out.append(("warn", "животное: перевозку, место, ограничения переноски и доплату нужно подтвердить у перевозчика"))
    weather = climate(trip.dest.id, trip.date_in.month)
    if weather and {"sea", "beach"} & set(trip.trip_types) and weather.sea is not None and weather.sea < 22:
        out.append(("warn", f"море в это время {weather.sea:+.0f}° — прохладно для купания"))
    if weather and weather.rain_days >= 10:
        out.append(("warn", f"сезон дождей: ~{weather.rain_days} дождливых дней в месяц"))
    if pkg.hotel.free_cancel_days is not None:
        last = (pkg.hotel_in or trip.date_in) - timedelta(days=pkg.hotel.free_cancel_days)
        out.append(("ok", f"отмена отеля бесплатно до {last:%d.%m}"))
    return out


def timeline(pkg: Package, trip: Trip) -> list[dict]:
    """Лента поездки для интерфейса: точки времени с уровнем риска (ok | warn | risk)."""
    exit_min = 40 if pkg.out.mode == "plane" else 15
    at_hotel = pkg.out.arrive + timedelta(minutes=exit_min + pkg.transfer_in.minutes)
    hotel_in = pkg.hotel_in or trip.date_in
    check_in_available = _parse_time(hotel_in, pkg.hotel.check_in)
    check_in = max(at_hotel, check_in_available)
    buffer = 120 if pkg.back.mode == "plane" else 40
    leave = pkg.back.depart - timedelta(minutes=buffer + pkg.transfer_out.minutes)
    check_out_deadline = _parse_time(pkg.hotel_out or trip.date_out, pkg.hotel.check_out)
    check_out = min(leave, check_out_deadline)
    night = lambda d: d.hour < 6 or d.hour >= 23  # noqa: E731
    wait_in = at_hotel < check_in_available - timedelta(hours=2)
    wait_out = leave > check_out_deadline + timedelta(hours=4)
    station = "вокзал" if pkg.back.mode == "train" else "аэропорт"
    return [
        {"t": f"{pkg.out.depart:%d.%m %H:%M}", "label": f"Отправление {trip.origin.from_}",
         "level": "warn" if night(pkg.out.depart) else "ok"},
        {"t": f"{pkg.out.arrive:%d.%m %H:%M}", "label": f"Прибытие, {trip.dest.name}", "level": "ok"},
        {"t": f"{at_hotel:%d.%m %H:%M}", "label": f"В отеле — трансфер {hm(pkg.transfer_in.minutes)}",
         "level": "warn" if wait_in or night(at_hotel) else "ok"},
        {"t": f"{check_in:%d.%m %H:%M}", "label": "Заселение", "level": "warn" if wait_in else "ok"},
        {"t": f"{check_out:%d.%m %H:%M}", "label": "Выезд из номера", "level": "warn" if wait_out else "ok"},
        {"t": f"{leave:%d.%m %H:%M}", "label": f"Трансфер в {station}", "level": "risk" if leave.date() < check_out_deadline.date() else "ok"},
        {"t": f"{pkg.back.depart:%d.%m %H:%M}", "label": "Обратно", "level": "warn" if night(pkg.back.depart) else "ok"},
        {"t": f"{pkg.back.arrive:%d.%m %H:%M}", "label": "Дома", "level": "ok"},
    ]


def cheapest_start(origin: Origin, dest: Destination, first: date, last: date, nights: int,
                   mode: str | None = None, *, baggage_required: bool = False, direct_only: bool = False,
                   pets: bool = False, max_hours: float | None = None, seat_class: str | None = None) -> date | None:
    """Самая выгодная дата заезда в окне [first, last] по цене дороги туда-обратно (её же видит календарь цен)."""
    best, best_cost = None, None
    day = first
    constraints = {"baggage_required": baggage_required, "direct_only": direct_only,
                   "pets": pets, "max_hours": max_hours, "seat_class": seat_class}
    while day <= last:
        out = [leg for leg in transport_options(origin, dest, day, mode) if _leg_matches(leg, **constraints)]
        back = [leg for leg in transport_options(origin, dest, day + timedelta(days=nights), mode)
                if _leg_matches(leg, **constraints)]
        if out and back:
            cost = min(o.price_per_person for o in out) + min(b.price_per_person for b in back)
            if best_cost is None or cost < best_cost:
                best, best_cost = day, cost
        day += timedelta(days=1)
    return best


def month_window(month: int, part: str | None, today: date, year: int | None = None) -> tuple[date, date]:
    """Окно дат заезда: весь месяц или его начало (1–10), середина (11–20), конец (21+)."""
    from calendar import monthrange

    explicit_year = year is not None
    year = year if year is not None else today.year + (1 if month < today.month else 0)
    end = monthrange(year, month)[1]
    lo, hi = {"early": (1, 10), "mid": (11, 20), "late": (21, end)}.get(part or "", (1, end - 1))
    first = max(date(year, month, lo), today + timedelta(days=3))
    last = date(year, month, hi)
    if first > last and not explicit_year:  # для явно названного года не подменяем год
        first, last = date(year + 1, month, lo), date(year + 1, month, hi)
    return first, last
