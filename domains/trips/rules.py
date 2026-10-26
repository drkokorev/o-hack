"""Разбор реплики путешественника правилами: страхует LLM и работает без неё (у жюри может не быть ключа)."""

from __future__ import annotations

import re
from datetime import date, timedelta

from .geo import DESTINATIONS, ORIGINS
from .state import TripState, TripUpdate
from .textparse import (MONTH_RE, NUM, month_of, negated, norm, num_word, parse_budget, parse_dates, parse_guests,
                        parse_stars)

TRIP_TYPE_WORDS = [
    ("sea", r"\bмор[еяюи]\b|морск|\bна море|побереж|океан"),
    ("beach", r"пляж|купат|позагорать|загорать"),
    ("warm", r"т[её]пл|жар[кау]|солнц|лето зимой|погреться"),
    ("mountains", r"\bгор[ыа]?\b|\bв горы|горн(?!олыж)"),
    ("ski", r"лыж|сноуборд|горнолыж|покатат"),
    ("city", r"город|прогуля|погулять по"),
    ("culture", r"музе|истори|культур|экскурс|архитектур|театр"),
    ("nature", r"природ|поход|трек|озер|вулкан|лес|северное сияние"),
    ("food", r"гастро|кухн|поесть|вкусн|ресторан|вино"),
    ("spa", r"санатор|оздоров|минеральн|лечени|термальн"),
    ("exotic", r"экзоти|необычн|тропик"),
]
WISH_WORDS = {
    "pool": r"бассейн", "kids_club": r"детск\w* клуб|аниматор|детская комната", "spa": r"\bспа\b|spa|сауна",
    "gym": r"фитнес|спортзал|тренаж", "parking": r"парковк|на машине|на авто", "beach_line": r"перв\w* линия|перв\w* линии",
    "kitchen": r"кухн\w* в номере|с кухней|апартамент",
}
MEAL_WORDS = [("all_inclusive", r"вс[её] включено|all inclusive|олл? инклюзив|ультра"),
              ("half_board", r"полупансион"), ("breakfast", r"завтрак")]
# Согласие на необратимое действие должно быть явным: «давай подумаем», «да нет», «ок, а что с визой?» — не согласие
CONFIRM_NO = r"^(нет|неа|не надо|не нужно|не стоит|отмена|стоп|не хочу|да нет)\b|передума"
HESITATE = r"подума|подожд|погоди|не уверен|не готов|позже реш|не сейчас|пока нет|сомнева|посоветуюсь"
QUESTION_TOPICS = [("visa", r"виз|паспорт|границ"), ("cancellation", r"отмен|вернуть деньги|возврат"),
                   ("baggage", r"багаж|чемодан|ручн\w* клад"), ("weather", r"погод|температур|тепло ли|холодно|дожд|мор[еяю] .*тепл|вода"),
                   ("transfer", r"трансфер|как добрат|до отеля|такси"), ("pets", r"собак|кошк|животн|питом")]
CONFIRM_STRONG = (r"^(да\b(?!\s*нет)|оформля|оформи|бронир|оплачива|оплати|покупа|купи|куплю|подтвержда|согласн|верно|"
                  r"всё верно|все верно|бер[уё]м?\b|давай оформ|давай брон|давай бер|давай куп|давайте оформ|"
                  r"хочу (купить|оформить|забронировать)|можно оформ)")
CONFIRM_SHORT = r"^(ок|окей|ага|угу|конечно|давай|давайте|го|поехали|отлично|супер)[.!]*$"
ORDINALS = {"перв": 1, "втор": 2, "трет": 3, "четв": 4, "пят": 5}
_OFFSET_WORDS = {"день": 1, "дня": 1, "дней": 1, "сутки": 1, "неделю": 7, "недели": 7}


_NEG_BEFORE = re.compile(r"(\bне|\bбез|\bвместо|\bкроме)\s+(\w+\s+)?$")
_NEG_AFTER = re.compile(r"^\W*\w*\W+(не надо|не хочу|не нужн\w*|не подходит|отпадает|не вариант)")
# Слова с заглавной буквы после «в», которые не города
_NOT_PLACES = {"январе", "феврале", "марте", "апреле", "мае", "июне", "июле", "августе", "сентябре", "октябре",
               "ноябре", "декабре", "россии", "европу", "европе", "азию", "азии", "горы", "отпуск", "субботу",
               "воскресенье", "пятницу", "понедельник", "отеле", "отель", "город", "одиночку", "общем", "целом"}


def _negated_at(t: str, start: int, end: int) -> bool:
    return bool(_NEG_BEFORE.search(t[max(0, start - 30):start]) or _NEG_AFTER.search(t[end:end + 25]))


def _fuzzy_destination(word: str) -> str | None:
    """Опечатки: «Стамбу», «Калининрад» — похожее на название направления с высокой схожестью."""
    from difflib import SequenceMatcher

    w = norm(word)
    if len(w) < 5:
        return None
    best, score = None, 0.0
    for d in DESTINATIONS:
        for alias in (*d.aliases, norm(d.name)):
            r = SequenceMatcher(None, w, alias[: len(w) + 2]).ratio()
            if r > score:
                best, score = d.id, r
    return best if score >= 0.82 else None


def _unknown_place(text: str) -> str | None:
    """Город или страна вне каталога: «в Париж», «в Лиссабоне» — чтобы честно сказать, а не подменить молча."""
    for m in re.finditer(r"\b(?:в|во|на|до)\s+([А-ЯЁ][а-яё]{2,}(?:[- ][А-ЯЁ][а-яё]+)?)", text):
        word = m.group(1)
        if norm(word) in _NOT_PLACES or find_destination(norm(word)) or _fuzzy_destination(word):
            continue
        return re.sub(r"(е|у|ю)$", "", word) if len(word) > 5 and word.endswith(("е", "у", "ю")) else word
    return None


def _find_origin(t: str) -> str | None:
    m = re.search(r"(?:из|вылет\w* из|выезжа\w* из|еду из|едем из|летим из|лечу из)\s+([а-яё\- ]{3,30})", t)
    if not m:
        return None
    tail = m.group(1)
    for o in ORIGINS:
        stem = norm(o.name)[:-1] if len(o.name) > 5 else norm(o.name)
        if tail.startswith(stem) or tail.startswith(norm(o.name)[:5]):
            return o.name
    aliases = {"питер": "Санкт-Петербург", "спб": "Санкт-Петербург", "мск": "Москва", "екб": "Екатеринбург",
               "нижн": "Нижний Новгород", "новосиб": "Новосибирск"}
    for k, v in aliases.items():
        if tail.startswith(k):
            return v
    return None


def find_destination(t: str) -> str | None:
    """Направление каталога в тексте в любом падеже; при «не Сочи, а Казань» — то, что не отрицается. Возвращает id."""
    hits: list[tuple[int, str, bool]] = []
    for d in DESTINATIONS:
        for alias in (*d.aliases, norm(d.name)):
            stem = alias if len(alias) <= 4 else re.sub(r"[аеиоуыья]$", "", alias)
            for m in re.finditer(rf"(?<![а-яё]){re.escape(stem)}[а-яё]{{0,3}}(?![а-яё])", t):
                hits.append((m.start(), d.id, _negated_at(t, m.start(), m.end())))
    positive = sorted(h for h in hits if not h[2])
    if positive:
        return positive[-1][1] if any(h[2] for h in hits) else positive[0][1]
    return None


def negated_destination(t: str) -> str | None:
    """Направление, от которого отказываются: «не Сочи», «Сочи не надо»."""
    for d in DESTINATIONS:
        for alias in (*d.aliases, norm(d.name)):
            stem = alias if len(alias) <= 4 else re.sub(r"[аеиоуыья]$", "", alias)
            for m in re.finditer(rf"(?<![а-яё]){re.escape(stem)}[а-яё]{{0,3}}(?![а-яё])", t):
                if _negated_at(t, m.start(), m.end()):
                    return d.id
    return None


_UNITS = (r"\s*(ноч|сут|дн|день|дня|недел|зв[её]зд|\*|человек|взросл|гост|тыс|к\b|руб|₽|час|ч\b|числ|лет|год|"
          r"январ|феврал|март|апрел|ма[йяе]|июн|июл|август|сентябр|октябр|ноябр|декабр|\.\d|[-–]\s*\d)")
_PICK_VERBS = r"беру|берём|берем|давай|давайте|оформ\w*|хочу|выбира\w*|возьм\w*|покупа\w*|купи\w*|бронир\w*|остановимся на"


def _pick(t: str) -> int | None:
    t = re.sub(r"перв\w* (лини\w*|раз\w*|очеред\w*)", " ", t)
    m = (re.search(r"(?:вариант\w*|номер|№)\s*(\d)\b", t)
         or re.search(r"\b(\d)\s*(?:-?(?:й|ой|ий|ый|ая|ое))?\s*(?:вариант|пожалуйста|давай|подходит|беру)", t)
         or re.search(rf"(?:{_PICK_VERBS})\s+(\d)\b(?!{_UNITS})", t)
         or re.fullmatch(r"\s*(\d)\s*(?:-?(?:й|ой|ий|ый))?\s*[.!)]?\s*", t))
    if m and 1 <= int(m.group(1)) <= 5:
        return int(m.group(1))
    m = re.search(r"\b(перв|втор|трет|четв|пят)(ый|ой|ий|ая|ое|ую|ого|ом)?\b", t)
    if m and re.search(rf"вариант|{_PICK_VERBS}|этот|\b(перв|втор|трет)\w*\s*[.!]?\s*$|^\s*(перв|втор|трет)", t):
        return ORDINALS[m.group(1)]
    return None


def _pick_name(t: str) -> str | None:
    for pattern, name in ((r"эконом", "Экономный"), (r"комфорт", "Комфорт"), (r"оптимал", "Оптимальный")):
        if re.search(pattern, t):
            return name
    return None


def _shift(t: str) -> int | None:
    m = re.search(rf"на\s+({NUM}|пару)?\s*(день|дня|дней|сутки|неделю|недели)\s+(позже|раньше)", t)
    if not m:
        m2 = re.search(r"(позже|раньше)\s+на\s+(\d+|один|два|три|пару|неделю)\s*(день|дня|дней)?", t)
        if not m2:
            return None
        n = 2 if m2.group(2) == "пару" else (7 if m2.group(2) == "неделю" else (num_word(m2.group(2)) or 1))
        return n if m2.group(1) == "позже" else -n
    count, unit, way = m.group(1), m.group(3), m.group(4)
    n = 2 if count == "пару" else (num_word(count) if count else 1) or 1
    n *= _OFFSET_WORDS.get(unit, 1)
    return n if way == "позже" else -n


def rule_extract(state: TripState, text: str, today: date) -> TripUpdate:
    t = norm(text)
    data: dict = {}

    if re.search(r"заново|сначала|новый поиск|другой запрос", t):
        data["new_search"] = True
    if (origin := _find_origin(t)):
        data["origin"] = origin
    elif (m := re.search(r"(?:\bиз|вылет\w* из|живу в|я из)\s+([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)", text)):
        if norm(m.group(1)) not in _NOT_PLACES and not find_destination(norm(m.group(1))):
            data["unknown_origin"] = m.group(1)
    dest_text = re.sub(r"(?:\bиз|вылет\w* из|едем из|летим из|лечу из|живу в)\s+[а-яё\-]+", " ", t)
    dest = find_destination(dest_text)
    if not dest:
        for word in re.findall(r"\b(?:в|во|на)\s+([а-яё]{5,})", dest_text):
            if (dest := _fuzzy_destination(word)):
                break
    if dest and dest != state.dest_id:
        data["destination"] = dest
    elif not dest and (place := _unknown_place(re.sub(r"(?:\bиз|живу в)\s+\S+", " ", text))):
        data["unknown_place"] = place
    rejected = negated_destination(dest_text)
    if re.search(r"друг\w* направлени|куда-нибудь ещ[её]|не туда", t) or (rejected and rejected == state.dest_id and not dest):
        data["clear"] = ["destination"]
    if re.search(r"вернись|верни\w* к направлен|назад к направлен|к выбору направлен|покажи направлен", t):
        data["back"] = True
    if re.search(r"друг\w* (вариант|идеи|направлени)|ещ[её] (вариант|идеи|направлени)|покажи ещ[её]|что ещ[её] есть|другие места", t) \
            or re.fullmatch(r"(а |и |давай |можно )?ещ[её]\W*", t.strip()):
        data["more"] = True

    types = [code for code, pattern in TRIP_TYPE_WORDS
             if (mm := re.search(pattern, t)) and not _negated_at(t, mm.start(), mm.end())]
    if types:
        data["trip_types"] = types
        if any(re.search(pattern, t) for code, pattern in TRIP_TYPE_WORDS if code not in types):
            data.setdefault("clear", []).append("destination")  # «не на море, а в горы» — прежнее направление не подходит

    shift = _shift(t)
    known_in = None if data.get("new_search") else state.date_from
    d_in, d_out = (None, None) if shift is not None else parse_dates(text, today, known_in)
    if d_in:
        data["date_from"] = d_in
    if d_out:
        data["date_to"] = d_out
    m = re.search(rf"\bв\s+{MONTH_RE}|на\s+{MONTH_RE}\b(?!\s*\d)|{MONTH_RE}\s*$|"
                  rf"(?:начал\w*|середин\w*|конц\w*|конец|первой половин\w*|второй половин\w*)\s+{MONTH_RE}", t)
    if m and not d_in:
        data["month"] = month_of(next(g for g in m.groups() if g))
    part = re.search(r"(в )?(начал\w*|первой половин\w*|середин\w*|конц\w*|конец|второй половин\w*)\s+(месяц|" + MONTH_RE[1:-1] + ")", t)
    if part and not d_in:
        word = part.group(2)
        data["month_part"] = "early" if word.startswith(("начал", "перв")) else "mid" if word.startswith("середин") else "late"
    if re.search(r"через месяц", t) and not d_in:
        data["date_from"] = today + timedelta(days=30)
    elif (mm := re.search(r"через (\d+|две|три|пару) недел", t)) and not d_in:
        data["date_from"] = today + timedelta(days=7 * ({"две": 2, "три": 3, "пару": 2}.get(mm.group(1)) or int(mm.group(1))))
    if "month" not in data and not d_in:
        season = None
        if re.search(r"\bзим(ой|у|ние|них)\b|на зиму", t):
            season = next(m for m in (today.month + i for i in range(1, 13)) if (m - 1) % 12 + 1 in (12, 1, 2))
        elif re.search(r"\bлет(ом|о)\b|летн", t):
            season = 7
        elif re.search(r"\bвесн(ой|а)\b", t):
            season = 4
        elif re.search(r"\bосен(ью|ь)\b", t):
            season = 9
        if season:
            data["month"] = (season - 1) % 12 + 1
    if re.search(r"недорог|бюджетн|подешевле|дешев|эконом|не дорого|подешёвк", t) and not state.last_plan:
        data["economy"] = True
    if re.search(r"отдох|поехать|съездить|отпуск|путешеств|куда|поездк|\bтур\b|развеяться|выбраться|посоветуй|идеи", t):
        data["wants_ideas"] = True
    if re.search(r"майски", t):
        data["month"] = 5
        data.setdefault("date_from", date(today.year + (today.month > 5), 5, 1))
        data.setdefault("date_to", data["date_from"].replace(day=4))
    if re.search(r"нов\w+ год", t) and not d_in:
        year = today.year if today.month < 12 or today.day < 29 else today.year + 1
        data["date_from"], data["date_to"] = date(year, 12, 30), date(year + 1, 1, 6)
    m = re.search(rf"на\s+{NUM}\s+(ноч|сут)", t) or re.search(rf"\b{NUM}\s+ноч", t) or re.search(rf"ноч\w*\s+на\s+{NUM}", t)
    weeks = re.search(r"(?:на\s+)?(\d|две|два|три|четыре|пару)\s+недел", t)
    days = re.search(rf"на\s+{NUM}\s+(дн|день|дня)", t) or re.search(rf"(?:дн\w*|сут\w*)\s+на\s+{NUM}", t)
    if shift is not None:
        pass
    elif m:
        data["nights"] = num_word(m.group(1))
    elif weeks and not re.search(r"через", t[: weeks.start() + 1][-8:]):
        n = {"две": 2, "два": 2, "три": 3, "четыре": 4, "пару": 2}.get(weeks.group(1)) or int(weeks.group(1))
        data["nights"] = 7 * n
    elif re.search(r"на неделю|неделю отдыха|на недельку", t):
        data["nights"] = 7
    elif days:
        n = num_word(days.group(1))
        data["nights"] = max(1, (n or 2) - 1)
    elif re.search(r"на пару дней|пару дней", t):
        data["nights"] = 2
    elif re.search(r"на выходные", t) and not d_in:
        data["nights"] = 2

    # Состав
    m = re.search(rf"{NUM}\s+взросл", t)
    if m:
        data["adults"] = num_word(m.group(1))
    elif (mm := re.search(rf"(?:не\s+\w+,?\s+а|а)\s+(двое|трое|четверо|пятеро|{NUM})\b(?!{_UNITS})", t)) and re.search(r"\bне\s+(двое|трое|один|одна|четверо)", t):
        data["adults"] = num_word(mm.group(1))  # «не двое, а трое»
    elif (n := parse_guests(text)) is not None and re.search(r"человек|чел\b|персон|нас\b|вчетвером|втроём|втроем|на двоих|на троих|на четверых", t):
        data["adults"] = n  # «4 человека», «на 3 человек»; детей вычтем ниже
    if re.search(r"добав\w* (ещ[её] )?(одного )?взросл|ещ[её] (один|одна|одного) (взросл|человек)|\+\s*1", t):
        data["add_adults"] = 1
    kids = re.search(rf"(?:с|и)\s+(?:{NUM}|двумя|тремя)\s+(?:детьми|дет|реб[её]н)", t)
    if kids:
        word = kids.group(1) or ""
        data["children"] = {"двумя": 2, "тремя": 3}.get(word, num_word(word) if word else 2)
    elif re.search(r"с реб[её]нк|с дочк|с сыном|с малыш|с ребенк|и реб[её]н|и дочк|и сын\b|и сыном", t):
        data["children"] = 1
    elif re.search(r"с детьми|и дети\b", t):
        data["children"] = 2
    if re.search(r"без (реб[её]нк|детей)|детей не будет|реб[её]нок не едет|дети не едут", t):
        data["children"] = 0
    if "adults" in data and data.get("children") and re.search(r"человек|чел\b|нас\b", t) and not re.search(r"взросл", t):
        data["adults"] = max(1, data["adults"] - data["children"])
    if "adults" in data:
        pass
    elif re.search(r"\bвдво[её]м\b|с женой|с мужем|с девушк|с парнем|на двоих", t):
        data["adults"] = 2
    elif re.search(r"\bвтро[её]м\b|на троих", t):
        data.setdefault("adults", 3)
    elif re.search(r"\b(одна|один|одному|одной)\b(?!\s*(ноч|день|раз))|в одиночку", t):
        data["adults"] = 1
    m = re.search(rf"\bнас\s+(?:будет\s+)?{NUM}\b", t)
    if m:
        total = num_word(m.group(1)) or 2
        data["adults"] = max(1, total - data.get("children", state.children or 0))
    if re.search(r"(мы|я) с (мужем|женой) и (реб|дет|сын|доч)", t):
        data["adults"] = 2
    if re.search(r"с собак|с кош|с питомц|с животн|с собачк|с котом|с псом", t):
        data["pets"] = True
    elif re.search(r"без (собак|животн|питомц)", t):
        data["pets"] = False

    # Деньги
    budget, _total = parse_budget(text)
    if budget:
        if re.search(r"за ночь|в сутки|ночь\b|/ночь", t):
            data["budget_night"] = budget
        else:
            data["budget_total"] = budget
    if re.search(r"бюджет\w* (меньше|поменьше|ниже)|дешевле|подешевле|дороговато|дорого", t) and state.last_plan:
        data["cheaper"] = True

    # Дорога
    m = re.search(r"(?:не (?:больше|более|дольше)|до|максимум)\s+(\d+)\s*(?:час|ч\b)", t)
    if m:
        data["max_travel_hours"] = float(m.group(1))
    elif re.search(r"без долг\w+ (перел[её]т|дорог)|недалеко|не очень далеко|близко лететь|недолго лететь", t):
        data["max_travel_hours"] = 5.0
    if re.search(r"поезд|\bж/?д\b|по железной|сапсан|ласточк", t) and not re.search(r"без поезд|не поезд", t):
        data["transport"] = "train"
    elif re.search(r"самол[её]т|перел[её]т|лететь|полет", t) and not re.search(r"без (долг|перел)|не лететь", t):
        if re.search(r"самол[её]т|только перел", t):
            data["transport"] = "plane"
    if re.search(r"без пересад|\bпрям(ой|ые|ым|ыми|ого)\b", t):
        data["direct_only"] = True
    if (mm := re.search(r"с багаж|багаж нуж|нужен багаж|чемодан", t)) and not negated(t, mm.start()):
        data["baggage"] = True

    # Отель
    for code, pattern in MEAL_WORDS:
        mm = re.search(pattern, t)
        if mm and not negated(t, mm.start()):
            data["meal"] = code
            break
    if re.search(r"бесплатн\w* отмен|можно отменить|без предоплат|с возвратом", t):
        data["free_cancellation"] = True
    if (stars := parse_stars(text)) is not None:
        data["stars_min"] = stars
    wishes = [code for code, pattern in WISH_WORDS.items()
              if (mm := re.search(pattern, t)) and not negated(t, mm.start())]
    if wishes:
        data["hotel_wishes"] = wishes
    if re.search(r"за границ|за рубеж|заграниц", t):
        data["abroad"] = True
    elif re.search(r"по росси|в росси|без загран|без визы и загран", t):
        data["abroad"] = False

    # Действия
    if (pick := _pick(t)) is not None:
        data["pick"] = pick
    elif state.showing == "packages" and (name := _pick_name(t)):
        data["pick_name"] = name
        data.pop("economy", None)
    stripped = t.strip()
    if re.search(HESITATE, stripped):
        data["hesitate"] = True
    elif re.search(CONFIRM_NO, stripped):
        data["confirm"] = False
    elif "?" not in text and not data.get("pick") and (re.search(CONFIRM_STRONG, stripped)
                                                       or re.fullmatch(CONFIRM_SHORT, stripped)):
        data["confirm"] = True
    if shift is not None:
        data["shift_days"] = shift
    if re.search(r"друг\w* отел|ещ[её] отел|покажи отел|другой вариант жиль|все отели|сменить отель", t):
        data["show_hotels"] = True
    asking = "?" in text or re.search(r"\b(можно ли|если|а что если|какие условия|условия отмены)\b", t)
    if "?" in text or re.search(r"^(а |какая |какие |какой |нужн\w+ ли|есть ли|сколько )", t):
        for topic, pattern in QUESTION_TOPICS:
            if re.search(pattern, t) and not (topic == "pets" and data.get("pets")):
                data["question"] = topic
                break
    if (mm := re.search(r"ранн\w* заезд|заселит\w* раньше|заселиться пораньше", t)) and not negated(t, mm.start()):
        data["after_sale"] = "early_checkin"
    elif (mm := re.search(r"поздн\w* выезд|выехать позже", t)) and not negated(t, mm.start()):
        data["after_sale"] = "late_checkout"
    elif re.search(r"отмен\w*\s+(\w+\s+)?(брон\w*|заказ\w*|поездк\w*)|отмена (брони|заказа)", t) or (
            state.stage == "booked" and re.search(r"^\W*(отмени\w*|отмена)\W*$", t)):
        data["after_sale"] = "cancel_info" if asking else "cancel"
    elif state.stage == "booked" and re.search(r"напомн|напоминан", t):
        data["after_sale"] = "reminder"
    elif state.stage == "booked" and re.search(r"трансфер|такси|встрет", t) and "?" not in text:
        data["after_sale"] = "transfer"
    elif state.stage == "booked" and (shift is not None or d_in or re.search(r"перенес|перенест|сдвин|помен\w* дат", t)):
        data["after_sale"] = "change_dates"
    return TripUpdate(**data)
