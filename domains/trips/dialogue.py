"""Questions and unpriced inspiration for incomplete travel requests."""
from __future__ import annotations

from core.agent import Step

from .geo import DESTINATIONS, destination_has_tag
from .campgrounds import campground_hint
from .state import TripState
from .climate import climate
from .temperature import TEMP_FIELDS, matches_history


# Fields that can answer each outstanding question. Shared by state updates and
# the question policy so a side comment is not mistaken for an answer.
QUESTION_INPUT_FIELDS = {
    "when": {"month", "season", "date_from"},
    "duration": {"nights", "date_to", "trip_days_min", "trip_days_max"},
    "origin": {"origin"},
    "destination": {"destination"},
    "people": {"adults", "party_size"},
    "children": {"children"},
    "lodging": {"lodging"},
    "transport": {"transport"},
}


def missing_for_trip(state: TripState) -> tuple[str, str] | None:
    if state.trip_days_min and not state.date_from:
        period = (f"{state.trip_days_min} дней" if state.trip_days_min == state.trip_days_max else
                  f"от {state.trip_days_min} до {state.trip_days_max} дней")
        return "when", f"Вы планируете {period}. Какого числа хотите начать поездку? Можно указать дату или диапазон дат."
    if not (state.month or state.date_from):
        seasons = {"summer": "летом (июнь, июль или август)", "autumn": "осенью", "winter": "зимой", "spring": "весной"}
        if state.season:
            return "when", f"Какой месяц {seasons[state.season]} вам подходит? Можно указать примерные даты."
        return "when", "Когда хотите поехать? Можно назвать месяц или примерные даты."
    if not (state.nights or (state.date_from and state.date_to)):
        if state.trip_days_min:
            return "duration", "Сколько ночей нужно жильё? Дни поездки и ночи проживания могут не совпадать."
        return "duration", "На сколько ночей планируете поездку? Можно ответить приблизительно."
    if not state.origin:
        return "origin", "Из какого города планируете отправляться?"
    if "party_size" in (state.tentative_fields or []):
        return "people", "Вы пока не уверены, кто поедет с вами. Сколько взрослых и детей планируют поездку?"
    if not state.adults:
        if state.party_size:
            return "people", f"Сколько из {state.party_size} путешественников — взрослые?"
        return "people", "Сколько взрослых едет?"
    if state.children_unknown:
        return "children", "Сколько детей едет?"
    if state.flight_concern:
        return "transport", "Вы сказали, что боитесь летать. Исключить самолёт или перелёт всё же возможен?"
    if "lodging" in (state.tentative_fields or []):
        return "lodging", "Какое размещение выбираете: палатка или отель?"
    if "transport" in (state.tentative_fields or []):
        return "transport", "Какой транспорт выбираете: самолёт или поезд?"
    return None


def ideas(state: TripState, *, exclude_shown: bool = False) -> Step:
    """Ideas never pretend to know dates, departure city, price or journey time."""
    excluded = set(state.rejected) | set(state.ui_preferences.get("hidden",[])) | (set(state.seen) if exclude_shown else set())
    requested = set(state.trip_types or [])
    places = [d for d in DESTINATIONS if d.id not in excluded and
              (state.abroad is None or d.abroad == state.abroad) and
              (not state.country or d.country == state.country) and
              d.country not in (state.excluded_countries or [])]
    if requested:
        core = requested - {"warm", "food"}
        places = [d for d in places if all(destination_has_tag(d, tag) for tag in core) and
                  (core or any(destination_has_tag(d, tag) for tag in requested))]
        places.sort(key=lambda d: (-sum(destination_has_tag(d, tag) for tag in requested), d.name))
    else:
        places.sort(key=lambda d: d.name)
    thresholds = {key: getattr(state, key) for key in TEMP_FIELDS if getattr(state, key) is not None}
    month = state.date_from.month if state.date_from else state.month
    if thresholds and month:
        places = [d for d in places if matches_history(climate(d.id, month), **thresholds) is True]
    places.sort(key=lambda d: d.id not in state.ui_preferences.get("saved",[]))
    places = places[:3]
    if not places:
        if thresholds and month:
            return Step("По указанным условиям и имеющимся историческим средним температуры подходящих "
                        "направлений в демо-каталоге нет или данных недостаточно. Это не прогноз; можно изменить условия.",
                        payload={"kind": "question"})
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
    if state.visa_free_requested:
        lines.append("Безвизовый въезд зависит от гражданства и других условий; актуальные требования я не проверял и по визам эти идеи не фильтровал.")
    if state.flight_concern:
        lines.append("Вы сказали, что боитесь летать. Уточним, исключать ли перелёт; время в пути пока не проверял.")
    if state.tentative_fields:
        lines.append("Упомянутые вами возможные пожелания предварительные, их можно изменить.")
    if thresholds:
        if month:
            lines.append("Пороги температуры сопоставлены с историческими средними 2022–2025; "
                         "направления без данных исключены. Это не прогноз на дни поездки.")
        else:
            lines.append("Пороги температуры сохранены; для сравнения с историческими средними нужен месяц. Это не прогноз.")
        if state.sea_min_temp is not None or state.sea_max_temp is not None:
            lines.append("Для воды здесь используется температура поверхности моря; озёра и реки не проверяются.")
    lines += [f"{i}. {d.name}, {d.country} — {', '.join(d.highlights[:2])}" for i, d in enumerate(places, 1)]
    if "surf" in requested:
        lines.append("Сёрфинг упомянут в демонстрационном описании направления; условия и сезон нужно проверить отдельно.")
    if state.lodging == "tent":
        lines.append(("Палатка — пока возможный вариант; " if "lodging" in (state.tentative_fields or []) else
                      "Учту, что вы хотите свою палатку; ") +
                     "место стоянки и питание нужно будет проверить отдельно.")
        for destination in places:
            if hint := campground_hint(destination.id):
                lines.append(f"{destination.name}: {hint}")
    lines.append("Какое направление интересно? Можно назвать город или попросить ещё варианты.")
    return Step("\n".join(lines), payload=payload)
