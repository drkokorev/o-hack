from datetime import date

from core.agent import Agent
from domains.trips.arbiter import arbitrate
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate


TODAY = date(2026, 10, 27)


def agent():
    return Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)


def test_user_dialogue_does_not_invent_dates_origin_or_repeat_empty_choice():
    a, s = agent(), None
    s = a.new_session()
    first = a.handle(s, "хочу увидеть горы, вайб лета, шашлыка, с другом, денег не много, главное еда и перелет, проживание в палатках")
    assert first.payload["kind"] == "question"
    second = a.handle(s, "горы")
    assert second.payload["kind"] == "ideas" and second.payload["items"]
    third = a.handle(s, "только по России")
    assert third.payload["kind"] == "ideas" and all(item["country"] == "Россия" for item in third.payload["items"])
    fourth = a.handle(s, "какое время пути")
    assert "откуда" in fourth.reply.lower()
    fifth = a.handle(s, "я не говорил про 7 ночей")
    assert "вы правы" in fifth.reply.lower() and s.state.nights is None
    assert s.state.origin is None and s.state.nights is None and s.state.month is None
    assert s.state.lodging == "tent"


def test_summer_is_not_silently_changed_to_july():
    state = TripState()
    rules = rule_extract(state, "хочу в Сочи летом", TODAY)
    assert rules.season == "summer" and rules.month is None
    merged, _ = arbitrate(state, "хочу в Сочи летом", TripUpdate(month=7), rules)
    assert merged.season == "summer" and merged.month is None
    a = agent()
    s = a.new_session()
    answer = a.handle(s, "хочу в Сочи летом")
    assert "август" in answer.reply.lower() and s.state.month is None


def test_demo_checkout_requires_method_and_separate_confirmation():
    a = agent()
    s = a.new_session()
    plan = a.handle(s, "Сочи из Москвы с 5 по 12 декабря двое взрослых")
    assert plan.payload["kind"] == "packages"
    cart = a.handle(s, "беру 1 вариант")
    assert cart.payload["kind"] == "cart"
    payment = a.handle(s, "да, оформляй")
    assert payment.payload["kind"] == "payment" and s.state.order is None
    # A confirmation cannot buy anything before a method is selected.
    payment = a.handle(s, "да")
    assert payment.payload["kind"] == "payment" and s.state.order is None
    payment = a.handle(s, "оплата СБП")
    assert payment.payload["method"] == "sbp" and s.state.order is None
    result = a.handle(s, "да, подтверждаю")
    assert result.payload["kind"] == "order"
    assert "не списано" in result.reply and "реальная бронь не создана" in result.reply


def test_demo_checkout_can_be_abandoned():
    a = agent()
    s = a.new_session()
    a.handle(s, "Сочи из Москвы с 5 по 12 декабря двое взрослых")
    a.handle(s, "беру 1 вариант")
    a.handle(s, "да, оформляй")
    result = a.handle(s, "нет")
    assert result.payload["kind"] == "cart" and s.state.order is None


def test_own_tent_prices_only_transport_and_never_creates_a_hotel_booking():
    a = agent()
    s = a.new_session()
    plan = a.handle(s, "в Сочи из Москвы с 5 по 12 декабря двое взрослых, перелет, живем в палатках")
    assert plan.payload["kind"] == "tent_transport" and plan.payload["items"]
    assert "отель" not in str(plan.payload).lower()
    cart = a.handle(s, "беру 1 вариант")
    assert cart.payload["kind"] == "tent_cart"
    assert "питание" in cart.reply and "не входят" in cart.reply
    assert a.handle(s, "да, оформляй").payload["kind"] == "payment"
    assert a.handle(s, "оплата картой").payload["method"] == "card"
    result = a.handle(s, "да, подтверждаю")
    assert result.payload["kind"] == "tent_order"
    assert "не куплены" in result.reply and "не забронировано" in result.reply
    a.handle(s, "отмени бронь")
    assert s.state.order and s.state.pending == "cancel"
    a.handle(s, "нет")
    assert s.state.order and s.state.pending is None
    a.handle(s, "отмени бронь")
    a.handle(s, "да, отменить")
    assert s.state.order is None


def test_bare_answers_fill_missing_slots_without_becoming_a_selection():
    a = agent()
    s = a.new_session()
    assert "когда" in a.handle(s, "хочу в Сочи").reply.lower()
    assert "ноч" in a.handle(s, "ноябрь").reply.lower()
    assert "город" in a.handle(s, "3").reply.lower()
    assert "взросл" in a.handle(s, "Москва").reply.lower()
    result = a.handle(s, "2")
    assert result.payload["kind"] == "packages"
    assert s.state.dest_id == "sochi" and s.state.origin == "Москва" and s.state.nights == 3 and s.state.adults == 2


def test_unspecified_number_of_children_is_asked_not_assumed():
    a = agent()
    s = a.new_session()
    step = a.handle(s, "в Сочи из Москвы с 5 по 12 декабря двое взрослых с детьми")
    assert step.payload["kind"] == "question" and "сколько детей" in step.reply.lower()
    assert s.state.children is None and s.state.children_unknown
    step = a.handle(s, "3")
    assert step.payload["kind"] == "packages" and s.state.children == 3 and not s.state.children_unknown
