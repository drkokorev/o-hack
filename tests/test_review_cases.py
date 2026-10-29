"""Случаи из независимого ревью (25 окт): каждый — реальная реплика, на которой агент ошибался."""

from datetime import date

import pytest

from core.agent import Agent
from domains.trips.domain import TripsDomain

T = date(2026, 10, 25)


def run(*messages):
    a = Agent(TripsDomain(today=lambda: T), None, today=lambda: T)
    s = a.new_session()
    # These regression cases exercise the planning engine with a known starting
    # city and group size, while the guided-dialogue tests cover missing fields.
    s.state.origin, s.state.adults = "Москва", 2
    step = None
    for m in messages:
        step = a.handle(s, m)
    return s.state, step


def test_own_hint_is_understood():
    st, step = run("Сочи", "в начале декабря на неделю")
    assert st.stage == "plan" and st.date_from.day <= 10 and st.nights == 7


@pytest.mark.parametrize("text, key", [("беру 2", "budget"), ("давай 3", "comfort"), ("2-й", "budget"),
                                       ("хочу комфорт", "comfort"), ("оформляй 3", "comfort")])
def test_picking_by_number_or_name(text, key):
    st, _ = run("Сочи с 5 по 12 декабря вдвоём", text)
    assert st.stage == "cart" and st.package == key


def test_acknowledgement_keeps_destination_list():
    st, step = run("Хочу к морю в ноябре", "спасибо")
    first = st.suggested
    assert "Пожалуйста" in step.reply
    st2, _ = run("Хочу к морю в ноябре", "спасибо", "давай 2")
    assert st2.dest_id == first[1]


@pytest.mark.parametrize("text, dest", [("нет, не Сочи, а Казань", "kazan"), ("вместо Сочи давай Казань", "kazan"),
                                        ("Сочи не надо, давай Стамбул", "istanbul")])
def test_corrections(text, dest):
    st, _ = run("Сочи с 5 по 12 декабря", text)
    assert st.dest_id == dest


def test_sea_to_mountains_changes_direction():
    st, step = run("Сочи с 5 по 12 декабря", "не на море, а в горы")
    assert st.dest_id is None and st.trip_types == ["mountains"] and st.stage == "destination"


def test_first_line_is_a_wish_not_a_pick():
    st, _ = run("Сочи с 5 по 12 декабря", "первая линия")
    assert st.stage == "plan" and "beach_line" in st.hotel_wishes


def test_all_inclusive_goes_where_it_exists():
    st, step = run("Новый год на море, всё включено, 4 звезды, на неделю")
    assert set(st.suggested) <= {"antalya", "hurghada", "sharm", "sanya", "dubai"}


def test_buy_words_book():
    st, _ = run("Сочи с 5 по 12 декабря", "беру 1 вариант", "хочу купить", "оплата картой", "да")
    assert st.stage == "booked"


def test_unreachable_budget_is_explained():
    st, step = run("Дубай на неделю с 1 декабря, бюджет 100к")
    assert "не уложиться" in step.reply and step.payload["notice"]


def test_date_change_after_purchase_needs_confirmation_and_can_be_declined():
    st, step = run("Сочи с 10 по 15 ноября", "беру 1 вариант", "да", "оплата картой", "да", "перенеси на 20 ноября")
    assert st.pending == "change" and st.order["date_in"] == "2026-11-10"
    st, step = run("Сочи с 10 по 15 ноября", "беру 1 вариант", "да", "оплата картой", "да", "перенеси на 20 ноября", "нет")
    assert st.stage == "booked" and st.date_from == date(2026, 11, 10)
    st, step = run("Сочи с 10 по 15 ноября", "беру 1 вариант", "да", "оплата картой", "да", "на 2 дня позже", "да")
    assert st.stage == "booked" and st.order["date_in"] == "2026-11-12"


def test_new_trip_after_purchase_keeps_old_order():
    st, _ = run("Сочи с 10 по 15 ноября", "беру 1 вариант", "да", "оплата картой", "да", "а ещё хочу в Казань на выходные")
    assert st.dest_id == "kazan" and st.past_orders and st.nights == 2


@pytest.mark.parametrize("text, adults, children, total", [("нас 4 человека", None, None, 4), ("трое взрослых и ребёнок", 3, 1, None)])
def test_group_size(text, adults, children, total):
    st, _ = run("Сочи с 5 по 12 декабря", text)
    assert st.adults == adults and st.children == children and st.party_size == total


def test_durations_and_unknown_places():
    st, _ = run("Таиланд на 2 недели в январе")
    assert st.nights == 14
    st, step = run("хочу в Рейкьявик в декабре")
    assert "Рейкьявик" in step.reply and st.dest_id is None
    st, step = run("вылет из Краснодара в Сочи с 5 по 12 декабря")
    assert "Краснодара" in step.reply
    st, step = run("хочу в Москву на выходные")
    assert "Откуда поедете" in step.reply


def test_back_and_more():
    st, step = run("Хочу к морю в ноябре", "давай 2", "вернись к направлениям")
    assert st.stage == "destination" and step.payload["kind"] in ("ideas", "destinations")
    first, _ = run("Хочу к морю в ноябре")
    st, _ = run("Хочу к морю в ноябре", "покажи ещё")
    assert not set(st.suggested) & set(first.suggested)
