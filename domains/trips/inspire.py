"""Вдохновение: подбор направлений под размытый запрос с объяснением, ценой, погодой и временем в пути."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import median

from .climate import MonthClimate, climate
from .geo import DESTINATIONS, TAG_NAMES, Destination, Origin
from .offers import hotel_price, hotels_for, transport_options


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
             stars_min: int | None = None) -> tuple[int, int, str, int] | None:
    """Оценка поездки тем же планировщиком, что соберёт варианты: (цена «от», минут в пути, транспорт, пересадок)."""
    from datetime import timedelta

    from .planner import Trip, make_packages

    trip = Trip(origin, dest, start, start + timedelta(days=nights), adults, children, pets=pets, mode=mode,
                meal=meal, stars_min=stars_min)
    packages, _ = make_packages(trip)
    if not packages:
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
            stars_min: int | None = None, window: tuple[date, date] | None = None) -> list[Suggestion]:
    from .planner import MEAL_RANK, cheapest_start

    wants = set(trip_types)
    beach = bool(wants & {"sea", "beach"})
    warm = "warm" in wants or beach
    max_minutes = (max_hours or (6 if children else 9)) * 60
    out: list[Suggestion] = []
    for dest in DESTINATIONS:
        if dest.name == origin.name or (exclude and dest.id in exclude):
            continue
        if abroad is False and dest.abroad or abroad is True and not dest.abroad:
            continue
        hotels = hotels_for(dest.id)
        if meal and not any(MEAL_RANK[h.meal] >= MEAL_RANK.get(meal, 0) for h in hotels):
            continue  # просили «всё включено» — туда, где его нет, не зовём
        if stars_min and not any(h.stars >= stars_min for h in hotels):
            continue
        day = (cheapest_start(origin, dest, window[0], window[1], nights, mode) if window else start) or start
        est = estimate(origin, dest, day, nights, adults, children, mode, pets, meal, stars_min)
        if est is None:
            continue
        total, minutes, leg_mode, stops = est
        weather = climate(dest.id, day.month)
        score, reasons, risks = 0.0, [], []

        core = wants - {"warm", "sea", "beach", "food"}
        if core and not core & set(dest.tags):
            continue  # просили горы, природу, город — направление без этого не предлагаем
        matched = [TAG_NAMES[t] for t in wants & set(dest.tags) if t not in ("sea", "beach", "warm")]
        score += 0.6 * len(matched)
        if beach:
            if weather and weather.beach_ok:
                score += 3
                reasons.append(f"можно купаться: море {weather.sea:+.0f}°, днём {weather.t_day:+.0f}°")
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
            if total > budget * 1.15:
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
                risks.append("за границу с животным: ветпаспорт, чип и правила страны")
            if dest.visa != "не нужна":
                risks.append(f"виза: {dest.visa}")
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
    if not out and wants:  # ничего не подошло строго — ослабляем тип отдыха, а не молчим
        return suggest(origin, start, nights, adults, children, trip_types=[t for t in trip_types if t in ("sea", "warm")],
                       budget=budget, max_hours=max_hours, abroad=abroad, pets=pets, mode=mode, exclude=exclude,
                       limit=limit, economy=economy, meal=meal, stars_min=stars_min, window=window) if set(trip_types) - {"sea", "warm"} else []
    return out[:limit]
