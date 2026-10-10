"""Русское форматирование дат, денег и числительных."""

from datetime import date

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
WEEKDAYS_DAT_PL = ["понедельникам", "вторникам", "средам", "четвергам", "пятницам", "субботам", "воскресеньям"]
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def fmt_date(d: date) -> str:
    return f"{WEEKDAYS_SHORT[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"


def fmt_date_long(d: date) -> str:
    """Для голоса: синтезатор плохо читает сокращения «вт», «пн»."""
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"


def fmt_money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def join_and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " и " + items[-1]
