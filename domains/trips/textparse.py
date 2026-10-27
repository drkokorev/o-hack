"""Общие разборщики русского текста: даты, бюджет, число гостей, звёзды, отрицания.

Правила намеренно консервативные: лучше не извлечь параметр, чем извлечь неверный.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
MONTH_RE = r"(январ[ьяе]|феврал[ьяе]|март[ае]?|апрел[ьяе]|ма[йяе]|июн[ьяе]|июл[ьяе]|август[ае]?|сентябр[ьяе]|октябр[ьяе]|ноябр[ьяе]|декабр[ьяе])"
NUM_WORDS = {
    "одн": 1, "один": 1, "две": 2, "два": 2, "двое": 2, "три": 3, "трое": 3, "четыре": 4, "четверо": 4,
    "пять": 5, "пятеро": 5, "шесть": 6, "семь": 7, "неделю": 7, "десять": 10,
}
NUM = r"(\d{1,2}|одн[уа]|один|две|два|двое|три|трое|четыре|четверо|пять|пятеро|шесть|семь|десять)"

# Common nominative and genitive forms used in written budgets. The parser
# accepts only an unambiguous descending sequence before an explicit "тысяч".
_MONEY_WORDS = {
    "сто": 100, "ста": 100, "двести": 200, "двухсот": 200, "триста": 300, "трехсот": 300,
    "четыреста": 400, "четырехсот": 400, "пятьсот": 500, "пятисот": 500,
    "шестьсот": 600, "шестисот": 600, "семьсот": 700, "семисот": 700,
    "восемьсот": 800, "восьмисот": 800, "девятьсот": 900, "девятисот": 900,
    "двадцать": 20, "двадцати": 20, "тридцать": 30, "тридцати": 30, "сорок": 40, "сорока": 40,
    "пятьдесят": 50, "пятидесяти": 50, "шестьдесят": 60, "шестидесяти": 60,
    "семьдесят": 70, "семидесяти": 70, "восемьдесят": 80, "восьмидесяти": 80,
    "девяносто": 90, "девяноста": 90, "десять": 10, "десяти": 10, "одиннадцать": 11,
    "одиннадцати": 11, "двенадцать": 12, "двенадцати": 12, "тринадцать": 13,
    "тринадцати": 13, "четырнадцать": 14, "четырнадцати": 14, "пятнадцать": 15,
    "пятнадцати": 15, "шестнадцать": 16, "шестнадцати": 16, "семнадцать": 17,
    "семнадцати": 17, "восемнадцать": 18, "восемнадцати": 18, "девятнадцать": 19,
    "девятнадцати": 19, "один": 1, "одна": 1, "одной": 1, "одного": 1,
    "два": 2, "две": 2, "двух": 2, "три": 3, "трех": 3, "четыре": 4, "четырех": 4,
    "пять": 5, "пяти": 5, "шесть": 6, "шести": 6, "семь": 7, "семи": 7,
    "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9,
}

_NEGATION = r"(без|не нужн\w*|не надо|не обязательно|необязательно|не хочу|не хотим|не будем|не стоит|не требуется|не интересует)\s+(\w+\s+){0,2}$"


def norm(text: str) -> str:
    return text.lower().replace("ё", "е")


def num_word(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    for k, v in NUM_WORDS.items():
        if word.startswith(k):
            return v
    return None


def month_of(word: str) -> int:
    word = norm(word)
    if word.startswith("ма") and not word.startswith("март"):
        return 5
    for stem, m in MONTHS.items():
        if word.startswith(stem):
            return m
    raise ValueError(word)


def future_date(day: int, month: int, today: date) -> date | None:
    # Включаем ближайший високосный год для 29 февраля; несуществующие даты не вызывают исключение.
    for year in range(today.year, today.year + 9):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate >= today:
            return candidate
    return None


def _nearest_weekend(today: date, next_week: bool) -> tuple[date, date]:
    """Ближайшие выходные, на которые ещё можно собраться: в субботу и воскресенье — уже следующие."""
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    if today.weekday() >= 4:
        friday = today + timedelta(days=(4 - today.weekday()) % 7 or 7)
    if next_week:
        friday += timedelta(days=7)
    return friday, friday + timedelta(days=2)


def _date_with_year(day: int, month: int, year: str | int | None, today: date) -> date | None:
    """При явно указанном годе не подменять его ближайшей датой."""
    if not year:
        return future_date(day, month, today)
    year = int(year)
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_dates(text: str, today: date, known_in: date | None = None) -> tuple[date | None, date | None]:
    t = norm(text)
    check_in = check_out = None

    # «7–9 ноября 2027», «28 декабря 2027 — 4 января 2028»
    month_pattern = MONTH_RE[1:-1]
    m = re.search(rf"(?P<day_in>\d{{1,2}})\s*(?:(?P<month_in>{month_pattern})\s*"
                  rf"(?:(?P<year_in>20\d{{2}})\s*)?)?(?:-|–|—|по|до)\s*"
                  rf"(?P<day_out>\d{{1,2}})\s+(?P<month_out>{month_pattern})"
                  rf"(?:\s+(?P<year_out>20\d{{2}}))?", t)
    if m:
        month_out = month_of(m.group("month_out"))
        month_in = month_of(m.group("month_in")) if m.group("month_in") else month_out
        year_in, year_out = m.group("year_in"), m.group("year_out")
        if year_out and not year_in:
            year_in = int(year_out) - (month_in > month_out)
        elif year_in and not year_out:
            year_out = int(year_in) + (month_out < month_in)
        check_in = _date_with_year(int(m.group("day_in")), month_in, year_in, today)
        check_out = _date_with_year(int(m.group("day_out")), month_out, year_out, today)
        if not (year_in or year_out) and check_in and check_out and check_out <= check_in:
            check_out = check_out.replace(year=check_out.year + 1)
        return check_in, check_out

    # «5-12.12», «5–12.12.2026»
    m = re.search(r"\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b", t)
    if m and 1 <= int(m.group(3)) <= 12:
        check_in = _date_with_year(int(m.group(1)), int(m.group(3)), m.group(4), today)
        check_out = _date_with_year(int(m.group(2)), int(m.group(3)), m.group(4), today)
        if check_in and check_out and check_out > check_in:
            return check_in, check_out

    # «7.11 — 9.11», «07.11.2026»
    dots = re.findall(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b", t)
    parsed = [_date_with_year(int(d), int(mo), year, today) for d, mo, year in dots if 1 <= int(mo) <= 12]
    parsed = [d for d in parsed if d]
    if len(parsed) >= 2:
        return parsed[0], parsed[1]
    if parsed:
        check_in = parsed[0]

    if check_in is None:
        m = re.search(rf"(?:с|со|на|заезд\w*)?\s*(\d{{1,2}})(?:-?го)?\s+{MONTH_RE}(?:\s+(20\d{{2}}))?", t)
        if m:
            check_in = _date_with_year(int(m.group(1)), month_of(m.group(2)), m.group(3), today)
    if check_in is None:
        m = re.search(r"\bс (\d{1,2})(?:-?го)?\b(?!\s*(?:до|ноч|звезд|человек|гост|\d))", t)
        if m:
            day = int(m.group(1))
            if 1 <= day <= 31:
                month = today.month if day >= today.day else today.month % 12 + 1
                check_in = future_date(day, month, today)
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
    m = (re.search(rf"на\s+{NUM}\s+(ноч|сут|дн|день)", t) or re.search(r"на\s+(неделю)", t)
         or re.search(rf"(?<!за )\b{NUM}\s+(ноч|сут)", t))
    nights = num_word(m.group(1)) if m else None
    if m and nights and m.group(0).endswith(("дн", "день")) and nights > 1:
        nights -= 1  # «на 3 дня» — две ночи
    if re.search(r"\bна (одну )?ночь\b", t):
        nights = 1
    if base and nights:
        check_out = base + timedelta(days=nights)
    return check_in, check_out


def parse_budget(text: str) -> tuple[int | None, bool]:
    """Возвращает (сумма, за весь период?)."""
    t = norm(text).replace("\u00a0", " ")
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
    for unit in re.finditer(r"\bтысяч\w*\b|\bтыс\w*\b", t):
        prefix, suffix = t[:unit.start()], t[unit.end():unit.end() + 35]
        if not (re.search(r"бюджет|денег|потрат|предел|не дороже|не больше|не более|максимум|\bдо\b", prefix[-100:])
                or re.match(r"\s*(?:руб\w*|₽)", suffix)):
            continue
        words = re.findall(r"[а-я]+", prefix)[-3:]
        values = []
        for word in reversed(words):
            if word not in _MONEY_WORDS:
                break
            values.insert(0, _MONEY_WORDS[word])
        if values and values == sorted(values, reverse=True) and sum(values) < 1000:
            groups = [100 if value >= 100 else 10 if value >= 10 else 1 for value in values]
            if len(groups) == len(set(groups)):
                return sum(values) * 1000, False
    return None, False


def parse_guests(text: str) -> int | None:
    t = norm(text)
    m = (re.search(rf"{NUM}\s+(взросл|человек|гост|чел\b|персон)", t)
         or re.search(rf"\bнас\s+(?:будет\s+)?{NUM}\b", t)
         or re.search(rf"на\s+{NUM}\b(?!\s*(ноч|сут|дн|звезд|\d))", t))
    if m:
        n = num_word(m.group(1))
        if n and 1 <= n <= 10:
            return n
    for pattern, n in [(r"\bвдво[её]м\b|на двоих|с женой|с мужем|с девушк|с парнем|с другом|с подругой", 2),
                       (r"\bвтро[её]м\b|на троих", 3), (r"\bвчетвером\b|на четверых", 4),
                       (r"\bодн[аи]\b|\bодин\b(?!\s*(ноч|день|раз))|в одиночку", 1)]:
        if re.search(pattern, t):
            return n
    return None


def parse_stars(text: str) -> int | None:
    t = norm(text)
    m = re.search(r"(\d)\s*(\*|★|зв)", t)
    if m:
        return int(m.group(1))
    for word, n in [("пятизвезд", 5), ("пять звезд", 5), ("пятерк", 5), ("четырехзвезд", 4),
                    ("четыре звезд", 4), ("трехзвезд", 3), ("три звезд", 3), ("люкс", 5)]:
        if word in t:
            return n
    return None


def negated(t: str, start: int) -> bool:
    return bool(re.search(_NEGATION, t[max(0, start - 30):start]))
