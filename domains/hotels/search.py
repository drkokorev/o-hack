"""Фильтрация с лестницей ослабления и скоринг с объяснимыми причинами."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from core.ru import plural

from .catalog import AMENITIES, TRIP_PURPOSES, Hotel
from .state import HotelState


@dataclass
class Match:
    hotel: Hotel
    score: float
    reasons: list[str]


@dataclass
class SearchResult:
    matches: list[Match]
    relaxed: list[str] = field(default_factory=list)  # что ослабили, чтобы что-то найти
    total: int = 0


# Применяются по очереди и накопительно, пока не найдётся хоть что-то. Город не ослабляем никогда.
_RELAXATIONS: list[tuple[str, Callable[[HotelState], HotelState]]] = [
    ("снял ограничение по звёздам", lambda q: q.model_copy(update={"stars_min": None})),
    ("расширил бюджет на 25%", lambda q: q.model_copy(
        update={"budget_max": round(q.budget_max * 1.25)}) if q.budget_max else q),
    ("сделал удобства необязательными", lambda q: q.model_copy(update={"amenities": []})),
]


def _fits(h: Hotel, q: HotelState) -> bool:
    return (
        h.city == q.city
        and (q.budget_max is None or h.price_per_night <= q.budget_max)
        and (q.stars_min is None or h.stars >= q.stars_min)
        and set(q.amenities or []) <= set(h.amenities)
    )


def _score(h: Hotel, q: HotelState, price_ref: int) -> Match:
    score = 0.5 * h.rating / 10
    reasons = []
    if h.rating:
        count = f" ({h.reviews_count} {plural(h.reviews_count, 'отзыв', 'отзыва', 'отзывов')})" if h.reviews_count else ""
        reasons.append(f"рейтинг {h.rating:.1f}{count}")

    score += 0.2 * max(0.0, 1 - h.price_per_night / price_ref)
    if q.budget_max and h.price_per_night <= 0.8 * q.budget_max:
        reasons.append("заметно дешевле бюджета")

    if q.near_center:
        score += 0.2 * max(0.0, 1 - h.distance_center_km / 5)
        if h.distance_center_km <= 2:
            reasons.append(f"{h.distance_center_km:g} км от центра")
    if q.near_sea and h.distance_sea_km is not None:
        score += 0.2 * max(0.0, 1 - h.distance_sea_km / 2)
        if h.distance_sea_km <= 1:
            reasons.append(f"{h.distance_sea_km:g} км до моря")
    if q.district and h.district and q.district.lower() in h.district.lower():
        score += 0.2
        reasons.append(f"район {h.district}")

    if q.trip_purpose and q.trip_purpose in h.tags:
        score += 0.1
        reasons.append(TRIP_PURPOSES[q.trip_purpose])
    matched = [AMENITIES[a] for a in (q.amenities or []) if a in h.amenities]
    if matched:
        reasons.append("есть " + ", ".join(matched))
    return Match(h, round(score, 4), reasons)


def search(hotels: list[Hotel], q: HotelState, limit: int = 3) -> SearchResult:
    query, relaxed = q, []
    candidates = [h for h in hotels if _fits(h, query)]
    for note, relax in _RELAXATIONS:
        if candidates:
            break
        loosened = relax(query)
        if loosened == query:
            continue
        query = loosened
        relaxed.append(note)
        candidates = [h for h in hotels if _fits(h, query)]

    if not candidates:
        return SearchResult([], relaxed, 0)
    price_ref = query.budget_max or max(h.price_per_night for h in candidates)
    ranked = sorted((_score(h, q, price_ref) for h in candidates), key=lambda m: -m.score)
    return SearchResult(ranked[:limit], relaxed, len(candidates))
