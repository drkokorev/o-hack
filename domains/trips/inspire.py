"""Вдохновение: подбор направлений под размытый запрос с объяснением, ценой, погодой и временем в пути."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .climate import MonthClimate, climate
from .geo import DESTINATIONS, TAG_NAMES, Destination, Origin, destination_has_tag
from .offers import hotels_for, transport_options
from .temperature import matches_history


@dataclass
class Suggestion:
    dest: Destination
    score: float
    est_total: int
    minutes: int
    mode: str
    stops: int
    weather: MonthClimate | None
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    start: date | None = None


def estimate(origin: Origin, dest: Destination, start: date, nights: int, adults: int, children: int,
             mode: str | None = None, pets: bool = False, meal: str | None = None,
             stars_min: int | None = None, baggage_required: bool = False, *, direct_only: bool = False,
             max_hours: float | None = None, free_cancellation: bool = False, budget_night: int | None = None,
             wishes: list[str] | None = None, seat_class: str | None = None) -> tuple[int, int, str, int] | None:
    """Оценка поездки тем же планировщиком, что соберёт варианты: (цена «от», минут в пути, транспорт, пересадок)."""
    from datetime import timedelta

    from .planner import Trip, make_packages

    trip = Trip(origin, dest, start, start + timedelta(days=nights), adults, children, pets=pets, mode=mode,
                meal=meal, stars_min=stars_min, baggage_required=baggage_required, direct_only=direct_only,
                max_hours=max_hours, free_cancellation=free_cancellation, budget_night=budget_night,
                wishes=wishes or [], seat_class=seat_class)
    packages, relaxed = make_packages(trip)
    if not packages or relaxed:
        return None
    cheapest = min(p.total(trip.people) for p in packages)
    best = packages[0].out
    return int(cheapest // 1000 * 1000), best.minutes, best.mode, best.stops


def _hours(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h} ч {m:02d} мин" if m else f"{h} ч"


def suggest(origin: Origin, start: date, nights: int, adults: int, children: int, *, trip_types: list[str],
            budget: int | None, max_hours: float | None, abroad: bool | None, pets: bool, mode: str | None,
            exclude: set[str] | None = None, limit: int = 3, economy: bool = False, meal: str | None = None,
            stars_min: int | None = None, window: tuple[date, date] | None = None, short_travel: bool = False,
            baggage_required: bool = False, direct_only: bool = False, free_cancellation: bool = False,
            budget_night: int | None = None, wishes: list[str] | None = None,
            air_min_temp: float | None = None, air_max_temp: float | None = None,
            sea_min_temp: float | None = None, sea_max_temp: float | None = None,
            seat_class: str | None = None) -> list[Suggestion]:
    from .planner import MEAL_RANK, cheapest_start

    wants = set(trip_types)
    core = wants - {"warm", "sea", "beach", "food"}
    beach = bool(wants & {"sea", "beach"})
    warm = "warm" in wants or beach
    max_minutes = (max_hours or (5 if short_travel else 6 if children else 9)) * 60
    out: list[Suggestion] = []
    for dest in DESTINATIONS:
        if dest.name == origin.name or (exclude and dest.id in exclude):
            continue
        if abroad is False and dest.abroad or abroad is True and not dest.abroad:
            continue
        # Сначала дешёвые ограничения по направлению и климату: не строим тысячи отелей,
        # если направление заведомо не подходит пользователю.
        if "surf" in core and not destination_has_tag(dest, "surf"):
            continue
        other_core = core - {"surf"}
        if other_core and not other_core & set(dest.tags):
            continue
        day = (cheapest_start(origin, dest, window[0], window[1], nights, mode,
                              baggage_required=baggage_required, direct_only=direct_only, pets=pets,
                              max_hours=max_hours, seat_class=seat_class) if window else start) or start
        weather = climate(dest.id, day.month)
        thresholds = {"air_min_temp": air_min_temp, "air_max_temp": air_max_temp,
                      "sea_min_temp": sea_min_temp, "sea_max_temp": sea_max_temp}
        if any(value is not None for value in thresholds.values()) and matches_history(weather, **thresholds) is not True:
            continue
        if beach and not (weather and (weather.beach_ok or (weather.sea is not None and weather.sea >= 21))):
            continue
        if not beach and warm and not (weather and weather.warm):
            continue
        if "ski" in wants and ("ski" not in dest.tags or not weather or weather.t_day > 2):
            continue
        # Если даже самый короткий транспорт не укладывается в явный лимит,
        # полный подбор отелей для этого направления не изменит решение.
        if max_hours and not any(leg.minutes <= max_minutes for leg in transport_options(origin, dest, day, mode)):
            continue
        hotels = hotels_for(dest.id)
        if meal and not any(MEAL_RANK[h.meal] >= MEAL_RANK.get(meal, 0) for h in hotels):
            continue  # просили «всё включено» — туда, где его нет, не зовём
        if stars_min and not any(h.stars >= stars_min for h in hotels):
            continue
        est = estimate(origin, dest, day, nights, adults, children, mode, pets, meal, stars_min, baggage_required,
                       direct_only=direct_only, max_hours=max_hours, free_cancellation=free_cancellation,
                       budget_night=budget_night, wishes=wishes, seat_class=seat_class)
        if est is None:
            continue
        total, minutes, leg_mode, stops = est
        score, reasons, risks = 0.0, [], []

        matched = [TAG_NAMES[t] for t in wants if t not in ("sea", "beach", "warm") and destination_has_tag(dest, t)]
        score += 0.6 * len(matched)
        if beach:
            if weather and weather.beach_ok:
                score += 3
                reasons.append(f"исторические средние: море {weather.sea:+.0f}°, днём {weather.t_day:+.0f}°; не прогноз")
            elif weather and weather.sea is not None and weather.sea >= 21:
                score += 1
                risks.append(f"море прохладное, {weather.sea:+.0f}°")
            else:
                continue
        elif warm:
            if not (weather and weather.warm):
                continue
            score += 2
            reasons.append(f"тепло: днём {weather.t_day:+.0f}°")
        if "ski" in wants:
            if "ski" not in dest.tags or not weather or weather.t_day > 2:
                continue
            score += 3
            reasons.append(f"сезон катания: днём {weather.t_day:+.0f}°")
        if matched:
            reasons.append("есть то, что вы ищете: " + ", ".join(matched))
        if weather and weather.rain_days >= 10:
            score -= 1
            risks.append(f"дождливо: ~{weather.rain_days} дождливых дней в месяц")

        if minutes > max_minutes:
            if max_hours:
                continue
            score -= (minutes - max_minutes) / 120
        score -= minutes / 240
        way = "поезд" if leg_mode == "train" else ("перелёт без пересадок" if not stops else "перелёт с пересадкой")
        reasons.append(f"{way} — {_hours(minutes)}")
        if children and minutes > 6 * 60:
            risks.append("долгая дорога для ребёнка")

        if budget:
            if total > budget:
                continue
            score += 1.5 * (1 - total / budget)
            if total <= budget:
                reasons.append("укладываемся в бюджет")
            else:
                risks.append(f"чуть дороже бюджета, на ~{total - budget:,} ₽".replace(",", " "))
        else:
            score -= total / (120_000 if economy else 400_000)
        if economy and not budget:
            reasons.append(f"≈ {total // max(adults + children, 1) // 1000} тыс. ₽ на человека")
        if day.month in dest.peak_months:
            score += 0.6  # сейчас там сезон — поэтому туда и едут
        if dest.abroad:
            if pets:
                score -= 2
                risks.append("за границу с животным: уточните правила ввоза страны")
            if dest.visa != "не нужна":
                risks.append(f"виза (демо): {dest.visa}; уточните требования страны")
        if day.month in dest.peak_months:
            risks.append("высокий сезон — цены выше")
        out.append(Suggestion(dest, round(score, 3), total, minutes, leg_mode, stops, weather, reasons, risks, day))
    out.sort(key=lambda s: -s.score)
    if not wants:  # пожеланий нет — показываем разные типы отдыха, а не три похожих города
        diverse, kinds = [], set()
        for s in out:
            if s.weather and s.weather.warm:
                kind = "warm"
            elif "ski" in s.dest.tags and s.weather and s.weather.t_day <= 2:
                kind = "ski"
            else:
                kind = "nature" if "nature" in s.dest.tags else "city"
            if kind not in kinds:
                diverse.append(s)
                kinds.add(kind)
        out = diverse + [s for s in out if s not in diverse]
    return out[:limit]
