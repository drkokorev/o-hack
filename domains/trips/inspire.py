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


def estimate(origin: Origin, dest: Destination, start: date, nights: int, adults: int, children: int,
             mode: str | None = None) -> tuple[int, int, str, int] | None:
    """Оценка поездки: (итого, минут в пути, вид транспорта, пересадок). None — не добраться."""
    from datetime import timedelta

    out = transport_options(origin, dest, start, mode)
    back = transport_options(origin, dest, start + timedelta(days=nights), mode)
    if not out or not back:
        return None
    people = adults + children
    best_out = min(out, key=lambda leg: leg.price_per_person + leg.minutes * 15)
    cheapest_back = min(leg.price_per_person for leg in back)
    hotels = [h for h in hotels_for(dest.id) if 3 <= h.stars <= 4] or list(hotels_for(dest.id))
    stay = median(hotel_price(h, start, nights, adults, children) for h in hotels)
    total = int((best_out.price_per_person + cheapest_back) * people + stay + 3000)
    return int(round(total, -3)), best_out.minutes, best_out.mode, best_out.stops


def _hours(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h} ч {m:02d} мин" if m else f"{h} ч"


def suggest(origin: Origin, start: date, nights: int, adults: int, children: int, *, trip_types: list[str],
            budget: int | None, max_hours: float | None, abroad: bool | None, pets: bool, mode: str | None,
            exclude: set[str] | None = None, limit: int = 3) -> list[Suggestion]:
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
        est = estimate(origin, dest, start, nights, adults, children, mode)
        if est is None:
            continue
        total, minutes, leg_mode, stops = est
        weather = climate(dest.id, start.month)
        score, reasons, risks = 0.0, [], []

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
            score -= total / 400_000
        if dest.abroad:
            if pets:
                score -= 2
                risks.append("за границу с животным: ветпаспорт, чип и правила страны")
            if dest.visa != "не нужна":
                risks.append(f"виза: {dest.visa}")
        if start.month in dest.peak_months:
            risks.append("высокий сезон — цены выше")
        out.append(Suggestion(dest, round(score, 3), total, minutes, leg_mode, stops, weather, reasons, risks))
    out.sort(key=lambda s: -s.score)
    return out[:limit]
