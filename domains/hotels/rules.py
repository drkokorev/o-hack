"""Разбор запроса правилами: запасной путь, когда LLM нет, она упала или что-то пропустила.

Правила намеренно консервативные: лучше не извлечь параметр, чем извлечь неверный.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .catalog import CITY_ALIASES
from .state import HotelState, HotelUpdate

MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
_MONTH_RE = r"(январ[ья]|феврал[ья]|марта?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|августа?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])"
_NUM_WORDS = {
    "одн": 1, "один": 1, "две": 2, "два": 2, "двое": 2, "три": 3, "трое": 3, "четыре": 4, "четверо": 4,
    "пять": 5, "пятеро": 5, "шесть": 6, "семь": 7, "неделю": 7, "десять": 10,
}
_NUM = r"(\d{1,2}|одн[уа]|один|две|два|двое|три|трое|четыре|четверо|пять|пятеро|шесть|семь|десять)"

# Слово-маркер → код удобства. Отрицание («без завтрака») проверяется отдельно.
AMENITY_WORDS = {
    "breakfast": r"завтрак",
    "pool": r"бассейн",
    "parking": r"парковк|паркинг|на машине|на авто",
    "spa": r"\bспа\b|spa|сауна|хаммам",
    "gym": r"фитнес|спортзал|тренажёрн|тренажерн|\bзал\b",
    "pets": r"с собак|с кош|с питомц|с животн|с собачк|pet",
    "kids": r"детск\w* комнат|аниматор",
    "wifi": r"wi-?fi|вай-?фай|интернет",
    "transfer": r"трансфер",
}
PURPOSE_WORDS = [
    ("business", r"командиров|по работе|деловую? поездк|на конференц|рабоч\w+ поездк"),
    ("family", r"с детьми|с ребён|с ребен|с дочк|с сын|семь[её]й|всей семь|с малыш"),
    ("romantic", r"романтич|годовщин|медов\w+ месяц|с девушк|с любим|с парнем|для пары|вдвоём с (женой|мужем)"),
    ("budget", r"подешевле|недорог|бюджетн|эконом|подешевле|дёшев|дешев"),
]
CLEAR_WORDS = [
    ("budget_max", r"(бюджет|цена|стоимость)\w* (не важ|не имеет|любая|без разниц)|любой бюджет|без ограничени\w* по (цене|бюджету)"),
    ("stars_min", r"(звёзд|звезд)\w* (не важ|без разниц|любая|не имеет)|любая звёздность|любая звездность"),
    ("amenities", r"удобства не важ|без (особых )?требований"),
    ("near_center", r"(не обязательно|необязательно) (в |у |ближе к )?центр|центр не важ"),
    ("district", r"район не важ|любой район"),
]
_NEGATION = r"(без|не нужн\w*|не надо|не обязательно|необязательно)\s+(\w+\s+){0,2}$"


def _norm(text: str) -> str:
    return text.lower().replace("ё", "е")


def _num(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    for k, v in _NUM_WORDS.items():
        if word.startswith(k):
            return v
    return None


def _month(word: str) -> int:
    word = _norm(word)
    if word.startswith("ма") and not word.startswith("март"):
        return 5
    for stem, m in MONTHS.items():
        if word.startswith(stem):
            return m
    raise ValueError(word)


def _future(day: int, month: int, today: date) -> date | None:
    try:
        d = date(today.year, month, day)
    except ValueError:
        return None
    return d if d >= today else d.replace(year=today.year + 1)


def _nearest_weekend(today: date, next_week: bool) -> tuple[date, date]:
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    if today.weekday() >= 5:  # уже суббота или воскресенье — эти выходные
        friday = today - timedelta(days=today.weekday() - 4)
        friday = max(friday, today)
    if next_week:
        friday += timedelta(days=7)
    return friday, friday + timedelta(days=2)


def parse_dates(text: str, today: date, known_in: date | None = None) -> tuple[date | None, date | None]:
    t = _norm(text)
    check_in = check_out = None

    # «с 7 по 9 ноября», «7-9 ноября», «с 7 ноября по 9 ноября»
    m = re.search(rf"(\d{{1,2}})\s*(?:{_MONTH_RE}\s*)?(?:-|–|—|по|до)\s*(\d{{1,2}})\s+{_MONTH_RE}", t)
    if m:
        month_out = _month(m.group(4))
        month_in = _month(m.group(2)) if m.group(2) else month_out
        check_in = _future(int(m.group(1)), month_in, today)
        check_out = _future(int(m.group(3)), month_out, today)
        if check_in and check_out and check_out <= check_in:
            check_out = check_out.replace(year=check_out.year + 1)
        return check_in, check_out

    # «7.11 — 9.11», «07.11.2026»
    dots = re.findall(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b", t)
    parsed = [_future(int(d), int(mo), today) for d, mo, _ in dots if 1 <= int(mo) <= 12]
    parsed = [d for d in parsed if d]
    if len(parsed) >= 2:
        return parsed[0], parsed[1]
    if parsed:
        check_in = parsed[0]

    if check_in is None:
        m = re.search(rf"(?:с|со|на|заезд\w*)?\s*(\d{{1,2}})(?:-?го)?\s+{_MONTH_RE}", t)
        if m:
            check_in = _future(int(m.group(1)), _month(m.group(2)), today)
    if check_in is None:
        m = re.search(r"\bс (\d{1,2})(?:-?го)?\b(?!\s*(?:до|ноч|звезд|человек|гост|\d))", t)
        if m:
            day = int(m.group(1))
            if 1 <= day <= 31:
                month = today.month if day >= today.day else today.month % 12 + 1
                check_in = _future(day, month, today)
    if check_in is None:
        if re.search(r"\bпослезавтра\b", t):
            check_in = today + timedelta(days=2)
        elif re.search(r"\bзавтра\b", t):
            check_in = today + timedelta(days=1)
        elif re.search(r"\bсегодня\b", t):
            check_in = today
    if check_in is None and re.search(r"выходн", t):
        return _nearest_weekend(today, bool(re.search(r"следующ", t)))

    base = check_in or known_in
    m = (re.search(rf"на\s+{_NUM}\s+(ноч|сут|дн|день)", t) or re.search(r"на\s+(неделю)", t)
         or re.search(rf"(?<!за )\b{_NUM}\s+(ноч|сут)", t))
    nights = _num(m.group(1)) if m else None
    if m and nights and m.group(0).endswith(("дн", "день")) and nights > 1:
        nights -= 1  # «на 3 дня» — две ночи
    if re.search(r"\bна (одну )?ночь\b", t):
        nights = 1
    if base and nights:
        check_out = base + timedelta(days=nights)
    return check_in, check_out


def parse_budget(text: str) -> tuple[int | None, bool]:
    """Возвращает (сумма, за весь период?)."""
    t = _norm(text).replace("\u00a0", " ")
    pattern = (
        r"(?:до|не дороже|не больше|максимум|бюджет\w*|в пределах|за|около|примерно|по|тысяч\w* на)\s*"
        r"(\d[\d\s]*(?:[.,]\d+)?)\s*(к\b|тыс\w*|т\.р|тр\b)?"
    )
    for m in re.finditer(pattern, t):
        raw = m.group(1).strip().replace(" ", "").replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            continue
        unit = m.group(2) or ""
        if unit:
            value *= 1000
        tail = t[m.end(): m.end() + 40]
        if value < 500 or re.match(r"\s*(звезд|ноч|сут|дн|человек|гост|км|минут|\.|январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)", tail):
            continue  # «за 2 ночи», «по 9 ноября», «4 звезды» — это не деньги
        total = bool(re.match(
            r"\s*(руб\w*|₽|р\.?)?\s*(за (все|всю|весь|поездк|отпуск)|на (все|всю|весь|поездк|отпуск)|в сумме|итого)", tail))
        return int(round(value)), total
    return None, False


def parse_guests(text: str) -> int | None:
    t = _norm(text)
    m = (re.search(rf"{_NUM}\s+(взросл|человек|гост|чел\b|персон)", t)
         or re.search(rf"\bнас\s+(?:будет\s+)?{_NUM}\b", t)
         or re.search(rf"на\s+{_NUM}\b(?!\s*(ноч|сут|дн|звезд|\d))", t))
    if m:
        n = _num(m.group(1))
        if n and 1 <= n <= 10:
            return n
    for pattern, n in [(r"\bвдво[её]м\b|на двоих|с женой|с мужем|с девушк|с парнем|с другом|с подругой", 2),
                       (r"\bвтро[её]м\b|на троих", 3), (r"\bвчетвером\b|на четверых", 4),
                       (r"\bодн[аи]\b|\bодин\b(?!\s*(ноч|день|раз))|в одиночку", 1)]:
        if re.search(pattern, t):
            return n
    return None


def parse_stars(text: str) -> int | None:
    t = _norm(text)
    m = re.search(r"(\d)\s*(\*|★|зв)", t)
    if m:
        return int(m.group(1))
    for word, n in [("пятизвезд", 5), ("пять звезд", 5), ("пятерк", 5), ("четырехзвезд", 4),
                    ("четыре звезд", 4), ("трехзвезд", 3), ("три звезд", 3), ("люкс", 5)]:
        if word in t:
            return n
    return None


def _negated(t: str, start: int) -> bool:
    return bool(re.search(_NEGATION, t[max(0, start - 30):start]))


def parse_amenities(text: str) -> list[str]:
    t = _norm(text)
    found = []
    for code, pattern in AMENITY_WORDS.items():
        m = re.search(pattern, t)
        if m and not _negated(t, m.start()):
            found.append(code)
    return found


class CityMatcher:
    """Находит город каталога в любом падеже по основе («в Казани», «Питер», «из Москвы»)."""

    def __init__(self, cities: list[str]):
        self.patterns: list[tuple[re.Pattern, str]] = []
        for alias, city in CITY_ALIASES.items():
            self.patterns.append((re.compile(rf"\b{re.escape(alias)}\w*"), city))
        for city in cities:
            words = _norm(city).split("-")
            stem = "-".join(words[:-1] + [re.sub(r"[аеиоуыьяй]$", "", words[-1])])
            self.patterns.append((re.compile(rf"\b{re.escape(stem)}\w{{0,3}}\b"), city))

    def find(self, text: str) -> str | None:
        t = _norm(text)
        hits = [(m.start(), city) for p, city in self.patterns if (m := p.search(t))]
        return min(hits)[1] if hits else None


def guess_unknown_city(text: str) -> str | None:
    """Город не из каталога: «в Мурманск», «в Мурманске» → «Мурманск» (чтобы честно сказать, что его нет)."""
    m = re.search(r"\b(?:в|во|до|город)\s+([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)", text)
    if not m:
        return None
    word = m.group(1)
    if word.endswith("е") and len(word) > 4:
        word = word[:-1]
    return word


def rule_extract(state: HotelState, text: str, today: date, cities: list[str], districts: list[str]) -> HotelUpdate:
    t = _norm(text)
    data: dict = {}

    if re.search(r"заново|сначала|новый поиск|другой запрос|сброс", t):
        data["new_search"] = True
    city = CityMatcher(cities).find(text) or guess_unknown_city(text)
    if city and city != state.city:
        data["city"] = city

    known_in = None if data.get("new_search") else state.check_in
    check_in, check_out = parse_dates(text, today, known_in)
    if check_in:
        data["check_in"] = check_in
    if check_out:
        data["check_out"] = check_out

    budget, total = parse_budget(text)
    if budget:
        cin = check_in or known_in
        cout = check_out or (None if data.get("new_search") else state.check_out)
        if total and cin and cout and cout > cin:
            budget = budget // (cout - cin).days
        data["budget_max"] = budget

    if (guests := parse_guests(text)) is not None:
        data["guests"] = guests
    if (stars := parse_stars(text)) is not None:
        data["stars_min"] = stars
    if amenities := parse_amenities(text):
        data["amenities"] = amenities

    if re.search(r"центр|в шаговой доступности|пешком до", t) and not _negated(t, t.find("центр")):
        data["near_center"] = True
    if re.search(r"(у|к|на|до|рядом с|возле|около) мор|пляж|первая линия|первой линии", t):
        data["near_sea"] = True
    for district in districts:
        stem = re.sub(r"(ий|ый|ая|ое|а|я)$", "", _norm(district))
        if len(stem) >= 4 and re.search(rf"\b{re.escape(stem)}", t):
            data["district"] = district
            break

    for purpose, pattern in PURPOSE_WORDS:
        if re.search(pattern, t):
            data["trip_purpose"] = purpose
            break
    if re.search(r"(подешевле|дешевле|бюджетнее|не так дорого|дороговато|дорого)", t) and state.shown_prices:
        data["cheaper"] = True
        data.pop("trip_purpose", None)

    clear = [field for field, pattern in CLEAR_WORDS if re.search(pattern, t)]
    if clear:
        data["clear"] = clear
        for field in clear:
            data.pop(field, None)
    return HotelUpdate(**data)
