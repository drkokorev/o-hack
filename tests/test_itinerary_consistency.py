from datetime import date, datetime, timedelta
from dataclasses import replace

from core.agent import Agent
from core.ru import fmt_money
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID, ORIGIN_BY_NAME
from domains.trips.planner import Trip, check, make_packages, timeline


TODAY = date(2026, 10, 27)


def _new_agent():
    return Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)


def _amount(text):
    return int("".join(char for char in text if char.isdigit()))


def test_night_train_stay_dates_survive_cart_and_booking():
    agent = _new_agent()
    session = agent.new_session()
    plan = agent.handle(session, "Хочу в Сочи на неделю в ноябре с собакой, до 120 тысяч на двоих")
    items = plan.payload["items"]
    index = next(i for i, item in enumerate(items) if item["key"] == "budget")
    hotel = items[index]["hotel"]

    # Поезд отправляется 20-го, а до отеля добирается 21-го: это шесть ночей в отеле.
    assert hotel["date_in"] == "2026-11-21"
    assert hotel["date_out"] == "2026-11-27"
    assert hotel["per_night"] == fmt_money(_amount(hotel["price"]) // 6)

    cart = agent.handle(session, f"беру {index + 1} вариант")
    assert cart.payload["package"]["hotel"]["dates"] == "21–27 ноября (6 ночей)"
    assert "21–27 ноября (6 ночей)" in cart.reply

    order = agent.handle(session, "да, оформляй")
    assert order.payload["order"]["date_in"] == "2026-11-20"  # дата отправления не меняется
    assert order.payload["order"]["hotel_date_in"] == "2026-11-21"
    assert order.payload["order"]["hotel_date_out"] == "2026-11-27"
    assert "21–27 ноября (6 ночей)" in order.reply
    days = hotel["free_cancel_days"]
    if days is not None:
        assert order.payload["order"]["cancel_until"] == (date(2026, 11, 21) - timedelta(days=days)).isoformat()


def test_timeline_never_places_checkin_before_arrival_or_checkout_after_transfer():
    agent = _new_agent()
    session = agent.new_session()
    plan = agent.handle(session, "Хочу в Сочи на неделю в ноябре с собакой, до 120 тысяч на двоих")
    for package in plan.payload["items"]:
        points = package["timeline"]
        parsed = [datetime.strptime(point["t"] + " 2026", "%d.%m %H:%M %Y") for point in points]
        assert parsed == sorted(parsed), (package["key"], points)


def test_demo_post_sale_does_not_promise_a_real_email_or_request():
    agent = _new_agent()
    session = agent.new_session()
    agent.handle(session, "Сочи с 20 по 27 ноября на двоих")
    agent.handle(session, "беру 1 вариант")
    order = agent.handle(session, "да, оформляй")
    assert "не отправ" in order.reply.lower()
    reply = agent.handle(session, "запроси ранний заезд")
    assert "имитац" in reply.reply.lower() or "демо" in reply.reply.lower()
    assert "не отправ" in reply.reply.lower()


def test_arrival_after_midnight_uses_the_room_booked_from_previous_day():
    trip = Trip(origin=ORIGIN_BY_NAME["Москва"], dest=BY_ID["sochi"],
                date_in=date(2026, 11, 20), date_out=date(2026, 11, 27), adults=2, children=0)
    package = make_packages(trip)[0][0]
    package = replace(
        package,
        out=package.out.model_copy(update={"depart": datetime(2026, 11, 20, 21),
                                          "arrive": datetime(2026, 11, 20, 23, 30)}),
        transfer_in=package.transfer_in.model_copy(update={"minutes": 60}),
        hotel_in=date(2026, 11, 20), hotel_out=date(2026, 11, 27),
    )
    warnings = [text for level, text in check(package, trip) if level != "ok"]
    assert not any("ранний заезд" in text for text in warnings)
    assert any("поздний заезд" in text for text in warnings)
    points = timeline(package, trip)
    assert next(point["t"] for point in points if point["label"] == "Заселение") == "21.11 01:10"
