"""Demonstration flow for travellers who bring their own accommodation."""
from __future__ import annotations

import zlib
from typing import Callable

from core.agent import Step
from core.ru import fmt_money

from .offers import Leg, transport_options
from .planner import Trip, _leg_ok, leg_text
from .state import TripState


def tent_order(state: TripState) -> Step:
    return Step("Демонстрация завершена: денег не списано, билеты не куплены и место стоянки не забронировано.",
                payload={"kind": "tent_order", "order": state.order or {}})


def tent_step(state: TripState, trip: Trip, act: dict, changed: bool,
              trip_card: Callable[[Trip], dict], leg_card: Callable[[Leg, int], dict]) -> Step:
    """Show transport alone and never create a fictitious campsite or hotel."""
    outs = [leg for leg in transport_options(trip.origin, trip.dest, trip.date_in, trip.mode) if _leg_ok(leg, trip)]
    backs = [leg for leg in transport_options(trip.origin, trip.dest, trip.date_out, trip.mode) if _leg_ok(leg, trip)]
    if not outs or not backs:
        return Step("В демонстрационных данных нет подходящей дороги на эти даты. "
                    "Попробуйте изменить даты или транспорт.", payload={"kind": "question"})
    pairs = sorted(((out, back) for out in outs for back in backs),
                   key=lambda p: (p[0].price_per_person + p[1].price_per_person, p[0].minutes + p[1].minutes))[:3]
    if changed and state.stage in ("cart", "payment"):
        state.stage, state.package, state.payment_method = "plan", None, None
    pick = act.get("pick")
    if state.stage == "plan" and isinstance(pick, int) and 1 <= pick <= len(pairs):
        state.package, state.stage = f"tent-{pick - 1}", "cart"
    try:
        selected = int((state.package or "tent-0").removeprefix("tent-"))
    except ValueError:
        selected = 0
    selected = max(0, min(selected, len(pairs) - 1))
    out, back = pairs[selected]
    total = (out.price_per_person + back.price_per_person) * trip.people
    trip_data = trip_card(trip)
    if state.stage == "cart" and act.get("confirm") is False:
        state.stage, state.package = "plan", None
    elif state.stage == "cart" and act.get("confirm") is True:
        state.stage = "payment"
    elif state.stage == "payment":
        if act.get("confirm") is False:
            state.stage, state.payment_method = "cart", None
        elif act.get("payment_method"):
            state.payment_method = act["payment_method"]
        elif act.get("confirm") is True and state.payment_method:
            number = f"DEMO-{zlib.crc32(f'{out.id}{back.id}'.encode()) % 1_000_000:06d}"
            state.order = {"kind": "transport_only", "number": number, "total": total, "dest": trip.dest.name,
                           "origin": trip.origin.name, "out": leg_text(out), "back": leg_text(back)}
            state.stage, state.showing = "booked", None
            return tent_order(state)
    if state.stage == "payment":
        names = {"card": "Демонстрационная карта", "sbp": "Демонстрация СБП"}
        return Step("Выберите демонстрационный способ оплаты и подтвердите. Денег не спишем, билеты не купим.",
                    payload={"kind": "payment", "trip": trip_data, "total": fmt_money(total),
                             "method": state.payment_method, "method_name": names.get(state.payment_method or "")})
    card = {"out": leg_card(out, trip.people), "back": leg_card(back, trip.people), "total": fmt_money(total)}
    if state.stage == "cart":
        return Step("В корзине только демонстрационная стоимость дороги. Место стоянки, питание и трансферы "
                    "не выбраны и в сумму не входят. Перейти к выбору способа оплаты?",
                    payload={"kind": "tent_cart", "trip": trip_data, **card})
    state.stage, state.showing = "plan", "tent_transport"
    items = [{"out": leg_card(o, trip.people), "back": leg_card(b, trip.people),
              "total": fmt_money((o.price_per_person + b.price_per_person) * trip.people)} for o, b in pairs]
    warning = ("Нормы багажа поездов не проверены; уточните их у перевозчика. " if trip.baggage_required and
               any(leg.mode == "train" for pair in pairs for leg in pair) else "")
    return Step("Учёл вашу палатку и не добавляю отель. Ниже — примерные варианты дороги; расписание и цены "
                "демонстрационные. Стоянка, питание и трансфер не рассчитаны — их нужно проверить отдельно. "
                + warning + "Какой вариант дороги посмотреть?",
                payload={"kind": "tent_transport", "trip": trip_data, "items": items})
