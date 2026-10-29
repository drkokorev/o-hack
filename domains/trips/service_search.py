"""Explicit service requests and room occupancy; no real booking or supplier claims."""
from __future__ import annotations

import re
from datetime import date, timedelta

from core.agent import Step
from core.ru import fmt_money
from .geo import BY_ID
from .offers import Hotel, MEALS, hotel_price, hotels_for
from .planner import MEAL_RANK
from .state import RoomAllocation, StaySegment, TripState
from .textparse import norm, parse_dates


def parse_room_allocations(text: str) -> list[RoomAllocation] | None:
    """Accept explicitly numbered rooms; reject incomplete or ambiguous child ages."""
    t = norm(text)
    parts = list(re.finditer(r"\bномер\s*(\d{1,2})\s*[:—-]\s*", t))
    if not parts or parts[0].start() != 0 or len(parts) > 9:
        return None
    allocations = []
    for index, match in enumerate(parts):
        if int(match.group(1)) != index + 1:
            return None
        block = t[match.end():parts[index + 1].start() if index + 1 < len(parts) else len(t)].strip(" ;,.!")
        adults = re.search(r"\b(\d+)\s*взросл\w*", block)
        if not adults:
            return None
        block = block[:adults.start()] + " " + block[adults.end():]
        children = []
        for child in re.finditer(r"\b(?:ребенок|ребенку|ребенка)\s*(\d{1,2})\s*(?:год|года|лет)\b", block):
            children.append(int(child.group(1)))
        block = re.sub(r"\b(?:ребенок|ребенку|ребенка)\s*\d{1,2}\s*(?:год|года|лет)\b", " ", block)
        # Only punctuation and the conjunction "и" may remain. In particular,
        # negations and unsupported descriptions cannot silently add/drop guests.
        remainder = re.sub(r"\bи\b|[\s,;.!]+", "", block)
        if remainder:
            return None
        try:
            allocations.append(RoomAllocation(adults=int(adults.group(1)), children_ages=children))
        except ValueError:
            return None
    return allocations


def parse_split_stays(text: str, today: date) -> list[StaySegment] | None:
    """Two explicitly dated catalogue destinations, never guessing an overnight gap."""
    from .rules import find_destination

    t = norm(text)
    match = re.fullmatch(r"\s*1\s*:\s*(.+?)\s*;\s*2\s*:\s*(.+?)\s*[.!]?\s*", t)
    if not match:
        return None
    stays = []
    for block in match.groups():
        dates = list(re.finditer(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", block))
        if len(dates) != 2:
            return None
        place = block[:dates[0].start()].strip(" ,:-–—")
        if not place or re.search(r"\b(?:и|или)\b|[/,;]", place):
            return None
        destination = find_destination(place)
        checkin, checkout = parse_dates(block, today)
        if not destination or not checkin or not checkout or not (today <= checkin < checkout):
            return None
        if (checkout - checkin).days > 30:
            return None
        stays.append(StaySegment(dest_id=destination, checkin=checkin, checkout=checkout))
    return stays if stays[0].checkout == stays[1].checkin else None


def question(state: TripState, field: str, message: str) -> Step:
    state.pending_question = field
    return Step(message, payload={"kind": "question", "field": field})


def _stay_candidates(state: TripState, dest_id: str, checkin: date, checkout: date,
                     rooms: list[RoomAllocation]) -> list[tuple[int, Hotel]]:
    """Apply one set of hotel constraints to every accommodation search."""
    nights = (checkout - checkin).days
    candidates = []
    for hotel in hotels_for(dest_id):
        if state.pets and "pets" not in hotel.amenities:
            continue
        if state.stars_min and hotel.stars < state.stars_min:
            continue
        if state.meal and MEAL_RANK[hotel.meal] < MEAL_RANK.get(state.meal, 0):
            continue
        if state.free_cancellation and hotel.free_cancel_days is None:
            continue
        if any(w not in hotel.amenities for w in (state.hotel_wishes or [])):
            continue
        if state.budget_night:
            # The limit applies to all rooms together, each night, not an average.
            if any(sum(hotel_price(hotel, checkin + timedelta(days=day), 1, room.adults, len(room.children_ages))
                       for room in rooms) > state.budget_night for day in range(nights)):
                continue
        total = sum(hotel_price(hotel, checkin, nights, room.adults, len(room.children_ages)) for room in rooms)
        candidates.append((total, hotel))
    return sorted(candidates, key=lambda item: (item[0], item[1].id))


def hotel_only(state: TripState, today: date) -> Step:
    """Modelled hotel-only search: room occupancy remains explicit and auditable."""
    if not state.dest_id:
        return question(state, "destination", "В каком городе искать жильё?")
    if not state.date_from or not state.date_to:
        return question(state, "when", "Укажите даты заезда и выезда целиком.")
    if not state.adults:
        return question(state, "people", "Сколько взрослых будет проживать?")
    if state.children_unknown:
        return question(state, "children", "Сколько детей будет проживать?")
    count = state.rooms or 1
    if count > 9:
        return question(state, "rooms", "Для одного запроса поддерживается не более 9 номеров. Уточните число номеров.")
    if count > 1:
        allocations = state.room_allocations or []
        if len(allocations) != count:
            return question(state, "room_allocation", f"Как распределить гостей по {count} номерам? Например: "
                            "номер 1: 2 взрослых, ребёнок 7 лет; номер 2: 1 взрослый. Укажите возраст каждого ребёнка.")
        adults = sum(room.adults for room in allocations)
        children = sum(len(room.children_ages) for room in allocations)
        if adults != state.adults or (state.children is not None and children != state.children):
            return question(state, "room_allocation", f"В распределении {adults} взрослых и {children} детей; "
                            "это не совпадает с общим составом. Исправьте распределение или состав.")
        if state.children_ages is not None and sorted(age for room in allocations for age in room.children_ages) != sorted(state.children_ages):
            return question(state, "room_allocation", "Возраст детей в распределении не совпадает с указанным ранее. Уточните распределение.")
    else:
        try:
            allocations = [RoomAllocation(adults=state.adults, children_ages=state.children_ages or [])]
        except ValueError:
            return question(state, "rooms", "В одном номере может быть до 6 взрослых и 4 детей. Укажите число номеров и распределение.")
        # Missing ages do not become zero or a free-child assumption.
        if state.children and len(allocations[0].children_ages) != state.children:
            return question(state, "children_ages", "Укажите возраст каждого ребёнка в годах на дату заезда.")
    nights = (state.date_to - state.date_from).days
    if nights <= 0 or nights > 30:
        return question(state, "when", "Укажите даты заезда и выезда: от 1 до 30 ночей.")
    candidates = [(total, hotel) for total, hotel in _stay_candidates(
        state, state.dest_id, state.date_from, state.date_to, allocations)
        if not state.budget_total or total <= state.budget_total]
    if not candidates:
        return Step("По условиям нет вариантов в демонстрационных данных. В реальном поиске результаты могут отличаться; "
                    "можно изменить даты или ограничения.", payload={"kind": "service_results"})
    state.stage, state.showing, state.pending_question = "hotel_search", None, None
    lines = [f"Демонстрационный поиск жилья: {BY_ID[state.dest_id].name}, "
             f"{state.date_from:%d.%m.%Y}–{state.date_to:%d.%m.%Y}, номеров: {count}.",
             "Названия могут быть из открытого каталога; цены, звёзды и условия смоделированы. Наличие не проверено."]
    if count > 1 and state.budget_night:
        lines.append("Лимит на ночь применяется к сумме всех номеров на каждую ночь.")
    for total, hotel in candidates[:3]:
        lines.append(f"• {hotel.name}, {hotel.stars}★, {MEALS[hotel.meal]} — {fmt_money(total)} за все номера (демо)")
    child_note = "Возрастные льготы не проверены. " if state.children else ""
    lines.append("Это расчёт без дороги и трансфера. " + child_note + "Наличие нескольких номеров не проверено; "
                 "для настоящего тарифа нужны данные поставщика. Купить или забронировать здесь нельзя.")
    return Step("\n".join(lines), payload={"kind": "service_results"})


def transfer_only(state: TripState, today: date) -> Step:
    """Collect only essential categories; avoid retaining a free-form private address."""
    if not state.dest_id:
        return question(state, "destination", "В каком городе нужен трансфер?")
    if not state.transfer_from or not state.transfer_to:
        return question(state, "transfer_route", "Откуда и куда нужен трансфер: аэропорт, вокзал или отель?")
    if state.transfer_from == state.transfer_to:
        return question(state, "transfer_route", "Начало и конец маршрута совпадают. Уточните маршрут.")
    if not state.transfer_direction:
        return question(state, "transfer_direction", "Трансфер нужен в одну сторону или туда и обратно?")
    if not state.transfer_date:
        return question(state, "transfer_date", "На какую дату нужна подача машины?")
    if state.transfer_date < today:
        return question(state, "transfer_date", "Дата подачи уже прошла. Укажите новую дату трансфера.")
    if not state.transfer_time:
        return question(state, "transfer_time", "Во сколько подать машину? Укажите время, например 14:30.")
    people = state.party_size or ((state.adults or 0) + (state.children or 0))
    if not people:
        return question(state, "passengers", "Сколько всего пассажиров, включая детей?")
    if people > 8:
        return Step("В демонстрационных вариантах нет машины на такую группу. "
                    "Для реального подбора нужно уточнить доступность нескольких машин у поставщика.",
                    payload={"kind": "service_results"})
    state.stage, state.showing, state.pending_question = "transfer_search", None, None
    labels = {"airport": "аэропорт", "station": "вокзал", "hotel": "отель"}
    direction = "в одну сторону" if state.transfer_direction == "one_way" else "туда и обратно"
    options = "демонстрационные варианты: легковой автомобиль до 3 пассажиров или минивэн до 8" if people <= 3 else "демонстрационный вариант: минивэн до 8 пассажиров"
    return Step(f"Запрос трансфера: {BY_ID[state.dest_id].name}, {labels[state.transfer_from]} → {labels[state.transfer_to]}, "
                f"{direction}, {state.transfer_date:%d.%m.%Y} в {state.transfer_time}, пассажиров: {people}. "
                f"Для поездки туда возможны {options}. Это пример, не заказ. "
                "Реальные машины, цены и доступность не подключены. "
                + ("Детские кресла также нужно подтвердить у поставщика. " if state.children or state.children_unknown else "")
                + "Для точного предложения понадобятся конкретные пункты и поставщик. "
                + ("Дату и время обратного трансфера потребуется уточнить отдельно." if direction == "туда и обратно" else ""),
                payload={"kind": "service_results"})


def split_hotels(state: TripState, today: date) -> Step:
    """A choice of two sequential demo stays. No availability or booking is implied."""
    stays = state.split_stays or []
    if (len(stays) != 2 or stays[0].checkout != stays[1].checkin or
            any(s.dest_id not in BY_ID or not (today <= s.checkin < s.checkout) or
                (s.checkout - s.checkin).days > 30 for s in stays)):
        return question(state, "split_stays", "Укажите два периода без разрыва. Пример: "
                        "1: Казань 10.12.2026–12.12.2026; 2: Сочи 12.12.2026–15.12.2026.")
    if not state.adults:
        return question(state, "people", "Сколько взрослых будет проживать в обоих отелях?")
    if state.children_unknown:
        return question(state, "children", "Сколько детей будет проживать в обоих отелях?")
    if state.children and len(state.children_ages or []) != state.children:
        return question(state, "children_ages", "Укажите возраст каждого ребёнка в годах на дату заезда.")
    if (state.rooms or 1) > 1:
        return Step("Для двух последовательных отелей расчёт нескольких номеров одновременно пока не поддерживается. "
                    "Можно рассчитать два отеля с одним номером или несколько номеров в одном отеле.",
                    payload={"kind": "question", "field": "rooms"})
    if state.adults > 6 or (state.children or 0) > 4:
        return question(state, "rooms", "В одном номере может быть до 6 взрослых и 4 детей. Укажите состав.")
    rooms = [RoomAllocation(adults=state.adults, children_ages=state.children_ages or [])]
    options = [_stay_candidates(state, stay.dest_id, stay.checkin, stay.checkout, rooms)[:4] for stay in stays]
    pairs = sorted(((a, b) for a in options[0] for b in options[1] if a[1].id != b[1].id and
                    (not state.budget_total or a[0] + b[0] <= state.budget_total)),
                   key=lambda pair: (pair[0][0] + pair[1][0], pair[0][1].id, pair[1][1].id))[:3]
    if not pairs:
        return Step("По этим датам и ограничениям нет двух разных отелей в демонстрационных данных. "
                    "Это не означает, что настоящих предложений нет.", payload={"kind": "service_results"})
    state.stage, state.showing = "hotel_search", None
    lines = ["Два последовательных отеля: даты без разрыва. Цены и условия смоделированы, наличие не проверено; "
             "переезд между отелями не рассчитан."]
    for i, pair in enumerate(pairs, 1):
        lines.append(f"{i}. {pair[0][1].name} ({BY_ID[stays[0].dest_id].name}, "
                     f"{stays[0].checkin:%d.%m}–{stays[0].checkout:%d.%m}) → "
                     f"{pair[1][1].name} ({BY_ID[stays[1].dest_id].name}, "
                     f"{stays[1].checkin:%d.%m}–{stays[1].checkout:%d.%m}) — "
                     f"{fmt_money(pair[0][0] + pair[1][0])} за оба проживания (демо)")
    snapshot = [{"hotel_ids": [a[1].id, b[1].id], "total": a[0] + b[0],
                 "dates": [stays[0].checkin.isoformat(), stays[0].checkout.isoformat(), stays[1].checkout.isoformat()]}
                for a, b in pairs]
    if state.split_choice:
        if state.split_choice > len(pairs) or state.split_displayed != snapshot:
            state.split_choice = None
            lines.append("Показанные варианты изменились; выберите пару из обновлённого списка.")
        else:
            chosen = pairs[state.split_choice - 1]
            state.pending_question = None
            lines.append(f"Выбрана пара: {chosen[0][1].name} → {chosen[1][1].name}. "
                         "Это демонстрация: бронирование и доступность двух отелей не подтверждены.")
            return Step("\n".join(lines), payload={"kind": "service_results"})
    state.pending_question, state.split_displayed = "split_choice", snapshot
    lines.append("Выберите номер пары. Реального бронирования нет; " +
                 ("тарифы детей и " if state.children else "") + "переезд нужно проверить отдельно.")
    return Step("\n".join(lines), payload={"kind": "service_results"})
