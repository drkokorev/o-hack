"""Questions and unpriced inspiration for incomplete travel requests."""
from __future__ import annotations

from core.agent import Step

from .geo import DESTINATIONS
from .state import TripState


def missing_for_trip(state: TripState) -> tuple[str, str] | None:
    if not (state.month or state.date_from):
        seasons = {"summer": "летом (июнь, июль или август)", "autumn": "осенью", "winter": "зимой", "spring": "весной"}
        if state.season:
            return "when", f"Какой месяц {seasons[state.season]} вам подходит? Можно указать примерные даты."
        return "when", "Когда хотите поехать? Можно назвать месяц или примерные даты."
    if not (state.nights or (state.date_from and state.date_to)):
        return "duration", "На сколько ночей планируете поездку? Можно ответить приблизительно."
    if not state.origin:
        return "origin", "Из какого города планируете отправляться?"
    if not state.adults:
        if state.party_size:
            return "people", f"Сколько из {state.party_size} путешественников — взрослые?"
        return "people", "Сколько взрослых едет?"
    if state.children_unknown:
        return "children", "Сколько детей едет?"
    return None


def ideas(state: TripState, *, exclude_shown: bool = False) -> Step:
    """Ideas never pretend to know dates, departure city, price or journey time."""
    excluded = set(state.rejected) | (set(state.seen) if exclude_shown else set())
    requested = set(state.trip_types or [])
    places = [d for d in DESTINATIONS if d.id not in excluded and
              (state.abroad is None or d.abroad == state.abroad) and
              (not state.country or d.country == state.country)]
    if requested:
        core = requested - {"warm", "food"}
        places = [d for d in places if core.issubset(d.tags) and
                  (core or requested.intersection(d.tags))]
        places.sort(key=lambda d: (-len(requested.intersection(d.tags)), d.name))
    else:
        places.sort(key=lambda d: d.name)
    places = places[:3]
    if not places:
        return Step("По этим пожеланиям пока не нашёл подходящих направлений в демонстрационном каталоге. "
                    "Можно изменить условия или назвать место самому.", payload={"kind": "question"})
    state.stage, state.showing = "destination", "destinations"
    state.suggested = [d.id for d in places]
    state.seen = sorted(set(state.seen) | set(state.suggested))
    items = [{"id": d.id, "name": d.name, "country": d.country, "lat": d.lat, "lon": d.lon,
              "highlights": list(d.highlights)} for d in places]
    payload = {"kind": "ideas", "items": items}
    state.last_view = payload
    lines = ["Вот несколько идей. Это направления для вдохновения: даты, стоимость и время в пути пока не рассчитывал."]
    lines += [f"{i}. {d.name}, {d.country} — {', '.join(d.highlights[:2])}" for i, d in enumerate(places, 1)]
    if state.lodging == "tent":
        lines.append("Учту, что вы хотите свою палатку; место стоянки и питание нужно будет проверить отдельно.")
    lines.append("Какое направление интересно? Можно назвать город или попросить ещё варианты.")
    return Step("\n".join(lines), payload=payload)
