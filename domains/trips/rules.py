"""Разбор реплики путешественника правилами: страхует LLM и работает без неё (у жюри может не быть ключа)."""

from __future__ import annotations

import re
from datetime import date

from .geo import DESTINATIONS, ORIGINS
from .state import TripState, TripUpdate
from .textparse import NUM, MONTH_RE, month_of, negated, norm, num_word, parse_budget, parse_dates, parse_stars

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
CONFIRM_STRONG = r"^(да\b(?!\s*нет)|оформля|оформи|бронир|оплачива|оплати|покупаю|подтвержда|согласн|верно|всё верно|все верно|бер[уё]м?\b|давай оформ|давай брон|давай бер|давайте оформ)"
CONFIRM_SHORT = r"^(ок|окей|ага|угу|конечно|давай|давайте|го|поехали|отлично|супер)[.!]*$"
ORDINALS = {"перв": 1, "втор": 2, "трет": 3, "четв": 4, "пят": 5}
_OFFSET_WORDS = {"день": 1, "дня": 1, "дней": 1, "сутки": 1, "неделю": 7, "недели": 7}


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
    """Ищет направление каталога в тексте в любом падеже; возвращает id."""
    best: tuple[int, str] | None = None
    for d in DESTINATIONS:
        for alias in (*d.aliases, norm(d.name)):
            stem = alias if len(alias) <= 4 else re.sub(r"[аеиоуыья]$", "", alias)
            m = re.search(rf"(?<![а-яё]){re.escape(stem)}[а-яё]{{0,3}}(?![а-яё])", t)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), d.id)
    return best[1] if best else None


def _pick(t: str) -> int | None:
    m = (re.search(r"(?:вариант|номер|№)\s*(\d)\b", t) or re.search(r"\b(\d)\s*(?:-?(?:й|ой|ий))?\s*вариант", t)
         or re.fullmatch(r"\s*(\d)\s*[.!)]?\s*", t))
    if m:
        return int(m.group(1))
    m = re.search(r"\b(перв|втор|трет|четв|пят)\w*", t)
    if m and re.search(r"вариант|давай|беру|берём|берем|выбира|хочу|этот|\b(перв|втор|трет)\w*\s*$|^\s*(перв|втор|трет)", t):
        return ORDINALS[m.group(1)]
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
    dest_text = re.sub(r"(?:из|вылет\w* из|едем из|летим из|лечу из)\s+[а-яё\-]+", " ", t)
    if (dest := find_destination(dest_text)) and dest != state.dest_id:
        data["destination"] = dest
    if re.search(r"друг\w* направлени|куда-нибудь ещ[её]|не туда|другие варианты направлен", t):
        data["clear"] = ["destination"]

    types = [code for code, pattern in TRIP_TYPE_WORDS if re.search(pattern, t)]
    if types:
        data["trip_types"] = types

    shift = _shift(t)
    known_in = None if data.get("new_search") else state.date_from
    d_in, d_out = (None, None) if shift is not None else parse_dates(text, today, known_in)
    if d_in:
        data["date_from"] = d_in
    if d_out:
        data["date_to"] = d_out
    m = re.search(rf"\bв\s+{MONTH_RE}|на\s+{MONTH_RE}\b(?!\s*\d)|{MONTH_RE}\s*$", t)
    if m and not d_in:
        data["month"] = month_of(next(g for g in m.groups() if g))
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
    m = re.search(rf"на\s+{NUM}\s+(ноч|сут)", t) or re.search(rf"\b{NUM}\s+ноч", t)
    if shift is not None:
        pass
    elif m:
        data["nights"] = num_word(m.group(1))
    elif re.search(r"на неделю", t):
        data["nights"] = 7
    elif (m := re.search(rf"на\s+{NUM}\s+(дн|день|дня)", t)):
        n = num_word(m.group(1))
        data["nights"] = max(1, (n or 2) - 1)
    elif re.search(r"на две недели", t):
        data["nights"] = 14
    elif re.search(r"на выходные", t) and not d_in:
        data["nights"] = 2

    # Состав
    m = re.search(rf"{NUM}\s+взросл", t)
    if m:
        data["adults"] = num_word(m.group(1))
    kids = re.search(rf"(?:с|и)\s+(?:{NUM}|двумя|тремя)\s+(?:детьми|дет|реб[её]н)", t)
    if kids:
        word = kids.group(1) or ""
        data["children"] = {"двумя": 2, "тремя": 3}.get(word, num_word(word) if word else 2)
    elif re.search(r"с реб[её]нк|с дочк|с сыном|с малыш|с ребенк", t):
        data["children"] = 1
    elif re.search(r"с детьми", t):
        data["children"] = 2
    if re.search(r"\bвдво[её]м\b|с женой|с мужем|с девушк|с парнем|на двоих", t):
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
    if re.search(r"без пересад|прям\w+ рейс|прямой", t):
        data["direct_only"] = True

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
    elif re.search(r"отмен\w*\s+(\w+\s+)?(брон\w*|заказ\w*|поездк\w*)|отмена (брони|заказа)", t):
        data["after_sale"] = "cancel_info" if asking else "cancel"
    elif state.stage == "booked" and (shift is not None or d_in):
        data["after_sale"] = "change_dates"
    return TripUpdate(**data)
