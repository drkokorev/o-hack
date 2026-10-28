"""Разбор реплики путешественника правилами: страхует LLM и работает без неё (у жюри может не быть ключа)."""

from __future__ import annotations

import re
from datetime import date, timedelta

from .geo import BY_ID, DESTINATIONS, ORIGINS
from .state import TripState, TripUpdate
from .temperature import temperature_preferences
from .textparse import (MONTH_RE, NUM, month_of, negated, norm, num_word, parse_budget_scopes, parse_dates, parse_guests,
                        parse_stars)
from .world_places import COUNTRY_NAMES, find_world_places

TRIP_TYPE_WORDS = [
    ("sea", r"\bмор[еяюи]\b|морск|\bна море|побереж|океан"),
    ("beach", r"пляж|купат|позагорать|загорать"),
    ("warm", r"т[её]пл|жар[кау]|солнц|солнеч|лето зимой|погреться|вайб лета|летн\w* (?:настроен|вайб)"),
    ("mountains", r"\bгор[ыа]?\b|\bв горы|горн(?!олыж)"),
    ("ski", r"лыж|сноуборд|горнолыж|покатат"),
    ("city", r"город|прогуля|погулять по"),
    ("culture", r"музе|истори|культур|экскурс|архитектур|театр"),
    ("nature", r"природ|поход|трек|озер|вулкан|лес|северное сияние"),
    ("surf", r"(?<![а-яё])с[её]рф"),
    ("food", r"гастро|кухн|поесть|вкусн|ресторан|вино|\bед[ауы]\b|шашлык|\bшашлы\b"),
    ("spa", r"санатор|оздоров|минеральн|лечени|термальн"),
    ("exotic", r"экзоти|необычн|тропик"),
]
WISH_WORDS = {
    "pool": r"бассейн", "kids_club": r"детск\w* клуб|аниматор|детская комната", "spa": r"\bспа\b|spa|сауна",
    "gym": r"фитнес|спортзал|тренаж", "parking": r"парковк|на машине|на авто", "beach_line": r"перв\w* линия|перв\w* линии",
    "kitchen": r"кухн\w* в номере|с кухней|апартамент",
    "wifi": r"\bwi[- ]?fi\b|вай[- ]?фай|вайфай",
}
MEAL_WORDS = [("all_inclusive", r"вс[её] включено|all inclusive|олл? инклюзив|ультра"),
              ("half_board", r"полупансион"), ("breakfast", r"завтрак"),
              ("meal_included", r"(?:с|и|нужн\w*)\s+питани\w*|питани\w*\s+(?:включ|нужн)")]
# Согласие на необратимое действие должно быть явным: «давай подумаем», «да нет», «ок, а что с визой?» — не согласие
CONFIRM_NO = r"^(нет|неа|не надо|не нужно|не стоит|отмена|стоп|не хочу|да нет)\b|передума"
HESITATE = r"подума|подожд|погоди|не уверен|не готов|позже реш|не сейчас|пока нет|сомнева|посоветуюсь"
QUESTION_TOPICS = [("travel", r"время (?:в )?пути|сколько (?:ехать|лететь|в пути)|долго ли (?:ехать|лететь)"),
                   ("location", r"адрес|где (?:находится|расположен)|местоположен"),
                   ("visa", r"виз|паспорт|границ"), ("cancellation", r"отмен|вернуть деньги|возврат"),
                   ("meal", r"завтрак|питан|полупансион|все включено|all inclusive"),
                   ("baggage", r"багаж|чемодан|ручн\w* клад"), ("weather", r"погод|температур|тепло ли|холодно|дожд|мор[еяю] .*тепл|вода"),
                   ("transfer", r"трансфер|как добрат|до отеля|такси"), ("pets", r"собак|кошк|животн|питом"),
                   # вопросы о месте — отвечаем по путеводителю (RAG)
                   ("sights", r"что (?:\w+ )?(?:посмотреть|интересного|посетить)|достопримечательн|куда (?:\w+ )?сходить|"
                              r"чем (?:\w+ )?заняться|что (?:там )?делать"),
                   ("areas", r"какой район|в каком районе|где (?:\w+ )?(?:жить|остановиться|поселиться)"),
                   ("food", r"где (?:\w+ )?(?:поесть|покушать|пообедать|поужинать)|что (?:\w+ )?попробовать|местн\w* кухн|"
                            r"ресторан|кафе"),
                   ("safety", r"безопасн|опасно|не опасно"),
                   ("local_transport", r"как (?:там )?передвигаться|общественн\w* транспорт|метро|автобус")]
_PLACE_QUESTIONS = frozenset({"sights", "areas", "food", "safety", "local_transport"})
CONFIRM_STRONG = (r"^(да\b(?!\s*нет)|оформля|оформи|бронир|оплачива|оплати|покупа|купи|куплю|подтвержда|согласн|верно|"
                  r"всё верно|все верно|бер[уё]м?\b|давай оформ|давай брон|давай бер|давай куп|давайте оформ|"
                  r"хочу (купить|оформить|забронировать)|можно оформ)")
_LONG_TRAVEL = r"(?:долго|далеко|подолгу|много\s+час\w*|по\s+\d+\s+час\w*)\s+(?:лететь|летать|ехать|добираться)"
# «Всё отлично, бронируй», «Нормально уже, оформляйте» — одобрение перед глаголом оформления
_CONFIRM_LEAD = r"^(?:(?:всё|все|ну|да|хорошо|отлично|нормально|супер|окей|ок|ладно|прекрасно|класс|уже|тогда|так|в общем|вс[её] устраивает|подходит)[\s,.!—-]*)+"
CONFIRM_SHORT = r"^(ок|окей|ага|угу|конечно|давай|давайте|го|поехали|отлично|супер)[.!]*$"
ORDINALS = {"перв": 1, "втор": 2, "трет": 3, "четв": 4, "пят": 5}
_OFFSET_WORDS = {"день": 1, "дня": 1, "дней": 1, "сутки": 1, "неделю": 7, "недели": 7}


_NEG_BEFORE = re.compile(r"(\bне|\bбез|\bвместо|\bкроме|\bпередумал(?:а|и)?\s+(?:насчет|про)|"
                         r"\bотказал(?:ся|ась)\s+от)\s+(\w+\s+)?$")
_NEG_AFTER = re.compile(r"^\W*(?:\w+\W+)?(не надо|не хочу|не интересует|не нуж(?:н\w*|ен)|не подходит|отпадает|не вариант)")
# Слова с заглавной буквы после «в», которые не города
_NOT_PLACES = {"январе", "феврале", "марте", "апреле", "мае", "июне", "июле", "августе", "сентябре", "октябре",
               "ноябре", "декабре", "россии", "европу", "европе", "азию", "азии", "горы", "море", "отпуск", "субботу",
               "воскресенье", "пятницу", "понедельник", "отеле", "отель", "город", "одиночку", "общем", "целом",
               "пути", "дороге", "перелете", "полете"}
_TIME_NOT_PLACE = re.compile(
    r"(?:(?:следующ|будущ|прошл|текущ)[а-я]*|эт(?:от|а|о|и|ом|ого|ому|у|ой|им|ими|их))"
    r"(?:\s+(?:месяц|недел|год|выходн|дн)[а-я]*)?"
    r"|(?:месяц|недел|выходн|сут|ноч|день|дня|дней|год|завтра|послезавтра|сегодня)[а-я]*"
)


def time_expression_not_place(value: str) -> bool:
    """Reject time words even when the model repeats them as a destination."""
    return bool(_TIME_NOT_PLACE.fullmatch(norm(value).strip()))


_COUNTRY_STEMS = [(country, re.sub(r"[аия]$", "", norm(country))) for country in COUNTRY_NAMES | {d.country for d in DESTINATIONS}]
_COUNTRY_PATTERNS = [(country, stem, re.compile(rf"(?<![а-яё]){re.escape(stem)}[а-яё]{{0,3}}(?![а-яё])"))
                     for country, stem in _COUNTRY_STEMS]


def _question_clause(text: str, start: int, end: int) -> bool:
    """A question about a feature is not, by itself, a request to require it."""
    left = max((text.rfind(mark, 0, start) for mark in ".!?;,"), default=-1) + 1
    stops = [pos for mark in ".!?;," if (pos := text.find(mark, end)) >= 0]
    right = min(stops) if stops else len(text)
    clause = text[left:right]
    if re.fullmatch(r"\s*(?:отель\s+)?все включено\s*", clause) and not (right < len(text) and text[right] == "?"):
        return False
    explicit_wish = re.search(r"\b(?:хочу|нуж(?:ен|на|но|ны)|ищу|важ(?:ен|на|но|ны))\b", clause)
    if explicit_wish and not (right < len(text) and text[right] == "?") and not re.search(
            r"\b(?:можно ли|есть ли|нуж(?:ен|на|но|ны) ли)\b", clause):
        return False
    return ((right < len(text) and text[right] == "?") or
            bool(re.search(r"\b(?:можно ли|есть ли|нуж(?:ен|на|но|ны) ли|какой|какая|какое|какие|где|сколько)\b", clause)) or
            bool(re.search(r"\b(?:есть|включен[ао]?|входит)\s*$", clause)))


def _negated_at(t: str, start: int, end: int) -> bool:
    return bool(_NEG_BEFORE.search(t[max(0, start - 30):start]) or _NEG_AFTER.search(t[end:end + 25]))


def _fuzzy_destination(word: str) -> str | None:
    """Опечатки: «Стамбу», «Калининрад» — похожее на название направления с высокой схожестью."""
    from difflib import SequenceMatcher

    w = norm(word)
    if (len(w) < 4 or w in _NOT_PLACES or time_expression_not_place(w)
            or any(re.search(pattern, w) for _, pattern in TRIP_TYPE_WORDS) or find_world_places(w)):
        return None
    scores = {}
    for d in DESTINATIONS:
        for alias in (*d.aliases, norm(d.name)):
            r = SequenceMatcher(None, w, alias[: len(w) + 2]).ratio()
            scores[d.id] = max(scores.get(d.id, 0), r)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return None
    best, score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    threshold, margin = (0.75, 0.15) if len(w) == 4 else (0.82, 0.05)
    return best if score >= threshold and score - runner_up >= margin else None


def _unknown_place(text: str) -> str | None:
    """Город или страна вне каталога: «в Париж», «в Лиссабоне» — чтобы честно сказать, а не подменить молча."""
    not_place_stems = re.compile(r"^(?:недел|выходн|дн|отпуск|путешеств|поездк|начал|середин|конц|следующ|"
                                 r"этот|этом|друг|тепл|холод|город|страна|росси|самолет|поезд|машин|палат|кемпинг|отел)")
    for m in re.finditer(r"\b(?:в|во)\s+([а-яё]{3,}(?:-[а-яё]+)?)", text, re.IGNORECASE):
        word = m.group(1)
        if re.search(r"игра(?:ю|ем|ешь|ете|ет|ют|ть|л|ла|ли)\s+$", norm(text[:m.start()])):
            continue  # «играет в шахматы» не обозначает направление
        if (norm(word) in _NOT_PLACES or time_expression_not_place(word) or not_place_stems.match(norm(word)) or _mentioned_countries(norm(word)) or find_destination(norm(word))
                or _fuzzy_destination(word)):
            continue
        if len(word) > 5 and word.endswith(("е", "у", "ю")):
            base = word[:-1]
            candidates = [value for value in (base, base + "а", base + "я") if find_world_places(value)]
            return candidates[0] if len(candidates) == 1 else base
        return word
    return None


def _mentioned_countries(t: str) -> set[str]:
    """Страны из справочника, названные в запросе и не отрицаемые пользователем."""
    hits = []
    for country, stem, pattern in _COUNTRY_PATTERNS:
        for match in pattern.finditer(t):
            prefix = t[max(0, match.start() - 12):match.start()]
            explicit_context = bool(re.search(r"(?:\bв|\bво|\bпо|\bиз|страна)\s+$", prefix))
            if (len(stem) <= 3 and match.group() != norm(country) and not explicit_context):
                continue  # "мало денег" — не упоминание страны Мали
            if not _negated_at(t, match.start(), match.end()):
                hits.append((len(stem), match.start(), match.end(), country))
    found, occupied = set(), []
    for _, start, end, country in sorted(hits, key=lambda item: (-item[0], item[1], item[3])):
        if not any(start < right and left < end for left, right in occupied):
            found.add(country)
            occupied.append((start, end))
    return found


def _excluded_countries(t: str) -> set[str]:
    """Only explicit negative country mentions; choose the longest overlapping name."""
    hits = []
    for country, stem, pattern in _COUNTRY_PATTERNS:
        for match in pattern.finditer(t):
            prefix = t[max(0, match.start() - 12):match.start()]
            explicit_context = bool(re.search(r"(?:\bв|\bво|\bпо|\bиз|страна)\s+$", prefix))
            if len(stem) <= 3 and match.group() != norm(country) and not explicit_context:
                continue
            if _negated_at(t, match.start(), match.end()):
                hits.append((len(stem), match.start(), match.end(), country))
    found, occupied = set(), []
    for _, start, end, country in sorted(hits, key=lambda item: (-item[0], item[1], item[3])):
        if not any(start < right and left < end for left, right in occupied):
            found.add(country)
            occupied.append((start, end))
    return found


def _find_origin(t: str) -> str | None:
    m = re.search(r"(?:\bиз|вылет\w* из|выезжа\w* из|еду из|едем из|летим из|лечу из|живу в|нахожусь в)\s+([а-яё\- ]{3,30})", t)
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
    for m in re.finditer(r"(?<![а-яё])дубаи(?![а-яё])", t):
        hits.append((m.start(), "dubai", _negated_at(t, m.start(), m.end())))
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
    if state.showing == "real_hotels" and state.real_hotels_shown:
        # A bare number or an exact visible name selects a record, not a new
        # destination. Do not guess when the same name is listed twice.
        numeric = re.fullmatch(r"\s*(\d+)\s*[.!)]?\s*", t)
        if numeric and 1 <= int(numeric.group(1)) <= len(state.real_hotels_shown):
            return TripUpdate(pick=int(numeric.group(1)))
        label = re.sub(r"^\s*(?:выбери|выбираю|беру|хочу|отель)\s+", "", t).strip(" .!\t")
        matches = [i for i, item in enumerate(state.real_hotels_shown, 1)
                   if norm(item.get("name", "")).strip() == label]
        if len(matches) == 1:
            return TripUpdate(pick=matches[0])
    if state.pending_trip_candidate:
        if re.fullmatch(r"\s*(?:новая поездка|новый поиск|новый запрос|начать заново|заново|сначала)\s*[.!]?\s*", t):
            return TripUpdate(resolve_trip_choice="new")
        if re.fullmatch(r"\s*(?:изменить текущую|изменить поездку|текущая поездка|продолжить текущую|сохранить условия)\s*[.!]?\s*", t):
            return TripUpdate(resolve_trip_choice="edit")
    origin_reply = _find_origin(f"из {t}") if state.pending_question == "origin" else None

    if re.search(r"заново|сначала|новый поиск|другой запрос", t):
        data["new_search"] = True
    excluded = _excluded_countries(t)
    explicitly_allowed = _mentioned_countries(t)
    previous_excluded = set() if data.get("new_search") else set(state.excluded_countries or [])
    if excluded or previous_excluded.intersection(explicitly_allowed):
        data["excluded_countries"] = sorted((previous_excluded | excluded) - explicitly_allowed)
    if re.search(r"\bбез\s+виз\w*|\bбезвизов\w*", t):
        data["visa_free_requested"] = True
    elif re.search(r"\bвиз\w*\s+(?:не важно|не важна|подойдет|подходит|можно)", t):
        data["visa_free_requested"] = False
    if (origin := _find_origin(t) or origin_reply):
        data["origin"] = origin
    elif (m := re.search(r"(?:\bиз|вылет\w* из|живу в|я из)\s+([а-яё]+(?:-[а-яё]+)?)", text, re.IGNORECASE)):
        if norm(m.group(1)) not in _NOT_PLACES and not re.match(r"люб|каког|город|ближайш|своег|моег", norm(m.group(1))):
            data["unknown_origin"] = m.group(1)
    dest_text = re.sub(r"(?:\bиз|вылет\w* из|едем из|летим из|лечу из|живу в)\s+[а-яё\-]+", " ", t)
    if origin_reply and not re.search(r"\b(?:в|во|на)\s+[а-яё]", dest_text):
        dest_text = ""  # bare answer to "откуда?" is not a new destination
    dest = find_destination(dest_text)
    unknown_candidate = _unknown_place(re.sub(r"(?:\bиз|живу в)\s+\S+", " ", text))
    if dest and unknown_candidate and find_world_places(unknown_candidate):
        # A known country name must not replace the explicitly named city
        # ("Рейкьявик в Италии" must not silently become Rome).
        name_stem = norm(BY_ID[dest].name).split()[0][:-1]
        if name_stem not in dest_text:
            dest = None
    if dest:
        selected = BY_ID[dest]
        countries = _mentioned_countries(dest_text)
        country_stem = re.sub(r"[аия]$", "", norm(selected.country))
        city_aliases = [alias for alias in (*selected.aliases, norm(selected.name))
                        if not norm(alias).startswith(country_stem) and len(norm(alias)) >= 3]
        city_named = any(re.search(rf"(?<![а-яё]){re.escape(re.sub(r'[аеиоуыья]$', '', norm(alias)))}[а-яё]{{0,3}}(?![а-яё])", dest_text)
                         for alias in city_aliases)
        if (selected.country in countries and not city_named and
                norm(selected.name) != norm(selected.country)):
            data["country"], dest = selected.country, None
    if not dest and not data.get("country") and not (unknown_candidate and find_world_places(unknown_candidate)):
        for word in re.findall(r"\b(?:в|во|на)\s+([а-яё]{4,})", dest_text):
            if _mentioned_countries(word):
                continue
            if (dest := _fuzzy_destination(word)):
                data["corrected_place"] = word
                break
    if dest and (dest != state.dest_id or state.country_conflict):
        data["destination"] = dest
    elif not dest and (place := unknown_candidate):
        data["unknown_place"] = place
    unknown = data.get("unknown_place") or (state.destination if not state.dest_id else None)
    if unknown and not dest:
        matches = find_world_places(unknown)
        countries = _mentioned_countries(dest_text)
        if matches and len(countries) == 1:
            country = next(iter(countries))
            data["place_country"] = country
            if not any(place.country == country for place in matches):
                data["country_conflict"] = country
    if dest:
        conflicting = _mentioned_countries(dest_text) - {BY_ID[dest].country}
        if conflicting:
            data["country_conflict"] = sorted(conflicting)[0]
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
    overridden_shift = False
    known_in = None if data.get("new_search") else state.date_from
    d_in, d_out = parse_dates(text, today, known_in)
    if shift is not None and not (d_in and d_out):
        d_in, d_out = None, None
    elif shift is not None:
        shift = None  # «на два дня позже, с 12 по 17» — названные даты точнее сдвига
        overridden_shift = True
    if d_in:
        data["date_from"] = d_in
    if d_out:
        data["date_to"] = d_out
    m = re.search(rf"\bв\s+{MONTH_RE}|на\s+{MONTH_RE}\b(?!\s*\d)|{MONTH_RE}\s*$|"
                  rf"(?:начал\w*|середин\w*|конц\w*|конец|первой половин\w*|второй половин\w*)\s+{MONTH_RE}", t)
    if m and not d_in:
        data["month"] = month_of(next(g for g in m.groups() if g))
        year_match = re.match(r"\s+(20\d{2})\b", t[m.end():])
        if year_match:
            data["year"] = int(year_match.group(1))
    part = re.search(r"(в )?(начал\w*|первой половин\w*|середин\w*|конц\w*|конец|второй половин\w*)\s+(месяц|" + MONTH_RE[1:-1] + ")", t)
    if part and not d_in:
        word = part.group(2)
        data["month_part"] = "early" if word.startswith(("начал", "перв")) else "mid" if word.startswith("середин") else "late"
    if not d_in and re.search(r"\b(?:следующ(?:ем|ий|его|им)|будущ(?:ем|ий|его))\s+месяц(?:е|а|у|ем)?\b", t):
        data["month"] = today.month % 12 + 1
        data["year"] = today.year + (today.month == 12)
    if "month" not in data and not d_in:
        season = None
        # A summer mood describes the desired atmosphere, not a travel date.
        season_text = re.sub(r"вайб\s+лета|летн\w*\s+(?:вайб|настроен\w*)", " ", t)
        if re.search(r"\bзим(ой|у|ние|них)\b|на зиму", season_text):
            season = "winter"
        elif re.search(r"\bлет(ом|о)\b|летн", season_text):
            season = "summer"
        elif re.search(r"\bвесн(ой|а)\b", season_text):
            season = "spring"
        elif re.search(r"\bосен(ью|ь)\b", season_text):
            season = "autumn"
        if season:
            data["season"] = season
    if re.search(r"недорог|недораг|бюджетн|подешевле|дешев|эконом|не дорого|подешёвк|мало денег|немного\s+денег|"
                 r"(?:денег|деньги)\s+(?:мало|не\s*много|в\s+обрез)|бюджет\s+(?:маленьк|небольш|низк)|"
                 r"(?:маленьк\w*|небольш\w*)\s+бюджет", t) and not state.last_plan:
        data["economy"] = True
    if re.search(r"отдох|поехать|съездить|отпуск|путешеств|куда|поездк|\bтур\b|развеяться|выбраться|посоветуй|идеи", t):
        data["wants_ideas"] = True
    if re.search(r"майски", t) and not d_in:
        data["month"] = 5  # праздники указывают месяц, но не конкретные даты или длительность
    m = re.search(rf"на\s+{NUM}\s+(ноч|сут)", t) or re.search(rf"\b{NUM}\s+ноч", t) or re.search(rf"ноч\w*\s+на\s+{NUM}", t)
    weeks = re.search(r"(?:на\s+)?(\d|две|два|три|четыре|пару)\s+недел", t)
    day_range = re.search(r"(?<!\d)(\d{1,3})\s*(?:-|–|—|до|по)\s*(\d{1,3})\s*(?:дней|дня|день|дей)\b", t)
    days = re.search(rf"(?:\bна\s+|^){NUM}\s+(?:дней|дня|день|дей)\b", t)
    short_refused = re.search(r"\bне\s+(?:хочу\s+)?(?:пару|два|две|2)\s+(?:дней|дня|день|дей|ночи|ночей)\b", t)
    if shift is not None:
        pass
    elif m:
        data["nights"] = num_word(m.group(1))
    elif weeks and not re.search(r"через", t[: weeks.start() + 1][-8:]):
        n = {"две": 2, "два": 2, "три": 3, "четыре": 4, "пару": 2}.get(weeks.group(1)) or int(weeks.group(1))
        data["nights"] = 7 * n
    elif re.search(r"на неделю|неделю отдыха|на недельку", t):
        data["nights"] = 7
    elif day_range and not _negated_at(t, day_range.start(), day_range.end()):
        low, high = int(day_range.group(1)), int(day_range.group(2))
        if 1 <= low <= high <= 365:
            data["trip_days_min"], data["trip_days_max"] = low, high
    elif days and not _negated_at(t, days.start(), days.end()):
        n = num_word(days.group(1))
        if n and n <= 365:
            data["trip_days_min"] = data["trip_days_max"] = n
    elif (pair := re.search(r"(?:на\s+)?пару\s+дней\b", t)) and not _negated_at(t, pair.start(), pair.end()):
        data["trip_days_min"] = data["trip_days_max"] = 2
    elif re.search(r"на выходные", t) and not d_in:
        data["nights"] = 2
    if short_refused:
        data["clear_duration"] = True

    # Состав
    m = re.search(rf"{NUM}\s+взросл", t)
    if m:
        data["adults"] = num_word(m.group(1))
    elif (inflected := re.search(r"\b(?:на\s+)?(двоих|троих|четверых)\s+взросл", t)):
        data["adults"] = {"двоих": 2, "троих": 3, "четверых": 4}[inflected.group(1)]
    elif (mm := re.search(rf"(?:не\s+\w+,?\s+а|а)\s+(двое|трое|четверо|пятеро|{NUM})\b(?!{_UNITS})", t)) and re.search(r"\bне\s+(двое|трое|один|одна|четверо)", t):
        data["party_size"] = num_word(mm.group(1))  # «не двое, а трое»
    elif (n := parse_guests(text)) is not None and re.search(r"человек|чел\b|персон|нас\b|вчетвером|втроём|втроем|на двоих|на троих|на четверых|\bтрое\b|\bчетверо\b", t):
        data["party_size"] = n
    elif re.search(r"\bвдво[её]м\b|(?:на|для) двоих", t):
        data["party_size"] = 2
    elif re.search(r"\bвтро[её]м\b|(?:на|для) троих", t):
        data["party_size"] = 3
    elif re.search(r"\bвчетвером\b|(?:на|для) четверых", t):
        data["party_size"] = 4
    elif (friends := re.search(rf"\bя\s+и\s+{NUM}\s+(?:друг|друз|подруг)\w*", t)):
        if (count := num_word(friends.group(1))) is not None:
            data["party_size"] = count + 1
    elif re.search(r"\bя\s+и\s+(?:(?:мой|моя)\s+)?(?:друг|подруга)\b", t):
        data["party_size"] = 2
    elif ((companion := re.search(r"\bс\s+(?:(?:моей|моим|своей|своим|любимой|любимым)\s+)?"
                                  r"(?:другом|дргуом|друагом|подругой|подругай|женой|жиной|мужем|"
                                  r"девушкой|евушкой|парнем|молодым\s+человеком)\b", t))
          and not _negated_at(t, companion.start(), companion.end())
          and not re.search(r"\bдет(?:и|ей|ям|ьми)|реб[её]н|сын|доч|компан|друзьями", t)):
        data["party_size"] = 2
    if re.search(r"добав\w* (ещ[её] )?(одного )?взросл|ещ[её] (один|одна|одного) (взросл|человек)|\+\s*1", t):
        data["add_adults"] = 1
    kids = (re.search(rf"(?:с|и)\s+(?:{NUM}|(одним|одной|двумя|тремя))\s+(?:детьми|дет|реб[её]н)", t) or
            re.search(rf"\b{NUM}\s+(?:детей|ребенка|ребенок|дети)\b", t))
    if kids:
        word = kids.group(1) or (kids.group(2) if kids.lastindex and kids.lastindex >= 2 else "")
        data["children"] = {"двумя": 2, "тремя": 3}.get(word, num_word(word))
    elif re.search(r"с реб[её]нк|с дочк|с сыном|с малыш|с ребенк|и реб[её]н|и дочк|и сын\b|и сыном|"
                   r"[,;]\s*(?:и\s+)?(?:ребенок|дочка|сын|малыш)\b", t):
        data["children"] = 1
    elif re.search(r"с детьми|и дети\b", t):
        data["children_unknown"] = True
    if re.search(r"без (реб[её]нк|детей)|детей не будет|реб[её]нок не едет|дети не едут", t):
        data["children"] = 0
        data["children_unknown"] = False
    # Accept only explicit ages in years. Months, future birthdays and dates
    # cannot establish the age at check-in or a carrier's tariff category.
    single_age = re.search(r"(?:ребенку|ребенка|сыну|дочке|дочери|малышу)\s+(\d{1,2})\s+(?:год|года|лет)\b", t)
    pair_ages = re.search(r"дет(?:ям|ей|и|ьми)\s+(\d{1,2})\s*(?:и|,)\s*(\d{1,2})\s+(?:года|лет)\b", t)
    ages = ([int(pair_ages.group(1)), int(pair_ages.group(2))] if pair_ages else
            [int(single_age.group(1))] if single_age else None)
    if ages and all(0 <= age <= 17 for age in ages) and data.get("children") != 0:
        data["children_ages"] = ages
        if data.get("children") is None and state.children is None:
            if pair_ages or data.get("children_unknown"):
                data["children_unknown"] = True  # two named ages need not describe every child
            else:
                data["children"] = 1
    room_match = re.search(rf"\b{NUM}\s+(?:отдельн\w*\s+)?номер(?:а|ов)?\b", t)
    if room_match and (number := num_word(room_match.group(1))) is not None and 1 <= number <= 20:
        data["rooms"] = number
    if data.get("party_size") and data.get("children") is not None and not data.get("children_unknown") and "adults" not in data:
        remaining = data["party_size"] - data["children"]
        if remaining > 0:
            data["adults"] = remaining
    if "adults" not in data and not data.get("party_size") and re.search(r"\b(одна|один|одному|одной)\b(?!\s*(ноч|день|раз|номер|комнат|отел))|в одиночку", t):
        data["party_size"] = 1
    if re.search(r"(мы|я) с (мужем|женой) и (реб|дет|сын|доч)", t):
        data["adults"] = 2
    pet_mention = re.search(r"с собак|с кош|с питомц|с животн|с собачк|с котом|с псом|со щенк|"
                            r"\bи (?:с\s+)?(?:собак|кошк|питомец|кот\b|пес\b|щен)", t)
    pet_question = re.search(r"(?:можно|разреш\w*|принима\w*|пуст\w*)\s+(?:ли\s+)?"
                             r"(?:(?:ехать|останавливат\w*|засел\w*|поселиться)\s+)?"
                             r"(?:с|со)\s+(?:собак|кош|питомц|животн|кот|пс|щен)", t)
    if pet_mention and not (pet_question and pet_question.start() <= pet_mention.start() < pet_question.end()):
        data["pets"] = True
    elif re.search(r"без (собак|животн|питомц)", t):
        data["pets"] = False
    tent_refused = re.search(r"\b(?:без|не|не хочу|не хотим|не нужна|не нужен)\s+(?:своей\s+)?палатк", t)
    if tent_refused:
        if re.search(r"отел|гостиниц", t) and not re.search(r"без\s+(?:отел|гостиниц)", t):
            data["lodging"] = "hotel"
        else:
            data.setdefault("clear", []).append("lodging")
    elif re.search(r"палатк|кемпинг|без отеля|сво[её] жиль[её]|жиль[её] не нуж", t):
        data["lodging"] = "tent"
    elif re.search(r"нужен отель|отель нужен|жить в отеле", t) or (state.pending_question == "lodging" and re.fullmatch(r"\s*отель\s*[.!]?\s*", t)):
        data["lodging"] = "hotel"

    # Деньги
    data.update(temperature_preferences(text))
    if re.search(r"температур\w*.*(?:не важн|не нужн|без разниц)|(?:не важн|не нужн).*температур", t):
        if re.search(r"вод[аые]|мор[ея]", t):
            data.setdefault("clear", []).extend(["sea_min_temp", "sea_max_temp"])
        elif re.search(r"воздух|днем", t):
            data.setdefault("clear", []).extend(["air_min_temp", "air_max_temp"])
        else:
            data.setdefault("clear", []).extend(["air_min_temp", "air_max_temp", "sea_min_temp", "sea_max_temp"])
    total_budget, nightly_budget = parse_budget_scopes(text)
    if total_budget is not None:
        if re.search(r"\bна\s+(?:(?:одного|каждого)\s+)?(?:человека|чел\w*|персону)|\bна\s+каждого\b|\bс\s+человека\b|/\s*чел", t):
            data["budget_per_person"] = total_budget
        else:
            data["budget_total"] = total_budget
    if nightly_budget is not None:
        data["budget_night"] = nightly_budget
    if re.search(r"бюджет\w*\s+не\s+важ|убери\w*\s+(?:ограничени\w*\s+)?бюджет|без\s+ограничени\w*\s+по\s+бюджету", t):
        data.setdefault("clear", []).extend(["budget_total", "budget_per_person"])
    if re.search(r"бюджет\w* (меньше|поменьше|ниже)|дешевле|подешевле|дороговато|дорого", t) and state.last_plan:
        data["cheaper"] = True

    # Дорога
    m = re.search(r"(?:не (?:больше|более|дольше)|до|максимум)\s+(\d+)\s*(?:час|ч\b)", t)
    if m:
        data["max_travel_hours"] = float(m.group(1))
    elif re.search(r"без долг\w+ (перел[её]т|дорог)|недалеко|не очень далеко|близко лететь|недолго лететь|"
                   + _LONG_TRAVEL + r"\s+не\s+(?:хоч|хот|готов|буд|люб)|не\s+(?:\w+\s+)?" + _LONG_TRAVEL, t):
        data["prefer_short_travel"] = True
    if re.search(r"время\s+в\s+пути\s+не\s+важ|дорога\s+не\s+важ|убери\w*\s+ограничени\w*\s+(?:по\s+)?времени", t):
        data.setdefault("clear", []).extend(["max_travel_hours", "prefer_short_travel"])
    # «долго лететь не хотим» — про длительность, а не отказ от самолёта
    no_plane = re.search(r"\bбез\s+(?:самол[её]т|перел[её]т|авиаперел[её]т)|"
                         r"\bне\s+(?:(?:хочу|буду|готов\w*)\s+)?(?:лететь|летать|полететь|самол[её]том)|"
                         r"\b(?:лететь|летать|полететь)\s+не\s+(?:буду|будем|хочу|хотим|могу|можем)|"
                         r"\b(?:самол[её]т|перел[её]т)\w*\s+не\s+(?:подходит|нужен|хочу)", re.sub(_LONG_TRAVEL, "", t))
    no_train = re.search(r"\bбез\s+поезд(?!к)|\bне\s+поезд(?!к)", t)
    fear_flying = re.search(r"(?:боюсь|боимся|страшно|опасаюсь)\s+(?:летать|лететь|полет(?:а|е)ть|перел[её]т\w*)", t)
    if fear_flying and not no_plane:
        data["flight_concern"] = True
    elif state.flight_concern and (no_plane or re.search(r"самол[её]т|перел[её]т|лететь|летать|поезд(?!к)", t)):
        data["flight_concern"] = False
    other_transport = re.search(r"\bна\s+(?:машин|авто|автомобил|автобус)", t)
    train = re.search(r"\bпоезд(?!к)|\bж/?д\b|по железной|сапсан|ласточк", t) and not no_train
    if no_plane and (no_train or (other_transport and not train)):
        data["transport"] = "none"  # другие виды транспорта прототип пока не моделирует
    elif no_plane:
        # В прототипе доступны самолёт и поезд: при отказе от перелёта показываем только поезд.
        data["transport"] = "train"
    elif train:
        data["transport"] = "train"
    elif re.search(r"самол[её]т|перел[её]т|лететь|полет", t) and not re.search(r"без (долг|перел)|не лететь", t):
        if re.search(r"самол[её]т|перел[её]т|полет", t):
            data["transport"] = "plane"
    if re.search(r"без пересад|\bпрям(ой|ые|ым|ыми|ого)\b", t):
        data["direct_only"] = True
    elif re.search(r"можно\s+с\s+пересад|пересадк\w*\s+(?:подходят|допускаются|нормально)", t):
        data["direct_only"] = False
    if ((mm := re.search(r"(?:с|и) багаж|багаж нуж|нужен багаж|чемодан", t)) and
            not negated(t, mm.start()) and not _question_clause(t, mm.start(), mm.end())):
        data["baggage"] = True
    elif re.search(r"без багаж|багаж\w*\s+не\s+(?:нужен|нужен будет|нужен мне|нужен нам)", t):
        data["baggage"] = False

    # Отель
    for code, pattern in MEAL_WORDS:
        mm = re.search(pattern, t)
        if mm and not _negated_at(t, mm.start(), mm.end()) and not _question_clause(t, mm.start(), mm.end()):
            data["meal"] = code
            break
    if state.meal and not data.get("meal"):
        for code, pattern in MEAL_WORDS:
            mm = re.search(pattern, t)
            if code == state.meal and mm and _negated_at(t, mm.start(), mm.end()):
                data.setdefault("clear", []).append("meal")
                break
    if ((mm := re.search(r"бесплатн\w* отмен|можно отменить|без предоплат|с возвратом", t)) and
            not _question_clause(t, mm.start(), mm.end()) and not _negated_at(t, mm.start(), mm.end())):
        data["free_cancellation"] = True
    if (stars := parse_stars(text)) is not None:
        data["stars_min"] = stars
    wishes = [code for code, pattern in WISH_WORDS.items()
              if (mm := re.search(pattern, t)) and not _negated_at(t, mm.start(), mm.end())
              and not _question_clause(t, mm.start(), mm.end())]
    if wishes:
        data["hotel_wishes"] = wishes
    removed_wishes = [code for code, pattern in WISH_WORDS.items()
                      if (mm := re.search(pattern, t)) and _negated_at(t, mm.start(), mm.end())
                      and not _question_clause(t, mm.start(), mm.end())]
    if removed_wishes:
        data["remove_hotel_wishes"] = removed_wishes
    if re.search(r"за границ|за рубеж|заграниц", t):
        data["abroad"] = True
    elif re.search(r"по росси|в росси|без загран|без визы и загран|"
                   r"\b(?:только|лишь|исключительно)\s+(?:(?:по|в)\s+)?(?:росси\w*|рф)\b", t):
        data["abroad"] = False

    # Действия
    if state.stage == "payment":
        if re.search(r"\bсбп\b|qr|куар|кьюар", t):
            data["payment_method"] = "sbp"
        elif re.search(r"карт", t):
            data["payment_method"] = "card"
    if re.search(r"не знаю|не определил|пока не решил|без понятия|пока не выбрал", t):
        data["unsure"] = True
    if re.search(r"не (?:говорил|указывал|называл|писал).{0,35}(?:ноч|дн|срок|длитель)", t):
        data["duration_not_given"] = True
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
                                                       or re.search(CONFIRM_STRONG, re.sub(_CONFIRM_LEAD, "", stripped))
                                                       or re.fullmatch(CONFIRM_SHORT, stripped)):
        data["confirm"] = True
    if shift is not None:
        data["shift_days"] = shift
    if overridden_shift:  # «два дня» в «на два дня позже» — не длительность поездки
        data.pop("trip_days_min", None)
        data.pop("trip_days_max", None)
    if re.search(r"друг\w* отел|ещ[её] отел|покажи отел|другой вариант жиль|все отели|сменить отель", t):
        data["show_hotels"] = True
    hotel_search = re.fullmatch(r"\s*(?:(?:найди|поищи|ищу|покажи)\s+)?(?:отель|гостиницу|гостиница)\s+(.{3,100}?)\s*[.!]?\s*", text, re.I)
    if hotel_search and not re.match(r"(?:с|без|где|котор|рядом|нужен|любой|недорог)\b", norm(hotel_search.group(1))):
        data["search_real_hotels"] = hotel_search.group(1).strip()
        data.pop("show_hotels", None)
    if (re.search(r"реальн\w*|настоящ\w*|без демо|без выдум|открыт\w* данн", t)
            and re.search(r"отел|гостиниц|жиль", t)):
        data["show_real_hotels"] = True
    asking = "?" in text or re.search(r"\b(можно ли|если|а что если|какие условия|условия отмены)\b", t)
    if "?" in text or re.search(r"\bможно ли\b|\bадрес\b|где (?:находится|расположен)|"
                                r"^(а |какая |какие |какой |какое |нуж(?:ен|на|но|ны) ли|есть ли|сколько )|"
                                r"\b(?:есть|включен[ао]?|входит)\s*$", t):
        questions = []
        for topic, pattern in QUESTION_TOPICS:
            # «что посмотреть», «где поесть» — вопрос и без знака «?»
            if (topic == "location" and re.search(r"\bадрес\b", t) or
                    topic in _PLACE_QUESTIONS and re.search(pattern, t) or
                    any(_question_clause(t, mm.start(), mm.end()) for mm in re.finditer(pattern, t))):
                questions.append(topic)
        asked_wishes = [code for code, pattern in WISH_WORDS.items()
                        if (mm := re.search(pattern, t)) and _question_clause(t, mm.start(), mm.end())]
        if asked_wishes:
            questions.append("amenities:" + ",".join(asked_wishes))
        if questions:
            data["question"] = "|".join(questions)
            if set(questions) <= _PLACE_QUESTIONS:
                # «где поесть?», «что попробовать из еды?» — вопрос о месте, а не новые условия поездки
                data.pop("trip_types", None)
                data.pop("unknown_origin", None)
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
    if state.pending_question in ("duration", "people", "children"):
        answer = re.fullmatch(r"\s*(\d+|один|одна|двое|два|две|трое|три|четверо|четыре|пятеро|пять)"
                              r"(?:\s+(?:ноч(?:ей|и|ь)?|взросл\w*|дет(?:ей|и)|реб[её]н\w*))?\s*[.!]?\s*", t)
        if answer and (number := num_word(answer.group(1))) is not None:
            if state.pending_question == "duration" and number > 0:
                data["nights"] = number
            elif state.pending_question == "people" and number > 0:
                data["adults"] = number
            elif state.pending_question == "children":
                data["children"], data["children_unknown"] = number, False
            data.pop("pick", None)
    # Preserve explicitly tentative choices as ideas, not confirmed inputs to
    # a price calculation. Only local qualifiers are used, not a broad guess
    # that the whole message is uncertain.
    maybe = r"\b(?:может(?:\s+быть)?|возможно|наверное|вероятно|скорее\s+всего)\s*,?\s*"
    possible = []
    if re.search(maybe + r"(?:(?:поеду|поедем|полетим|поехать)\s+)?с\s+"
                 r"(?:(?:моей|моим|своей|своим)\s+)?"
                 r"(?:другом|дргуом|друагом|подругой|подругай|девушкой|евушкой|парнем|женой|жиной|мужем|молодым\s+человеком)\b", t):
        possible.append("party_size")
    if re.search(maybe + r"(?:(?:жить|ночевать|останавливаться)\s+)?(?:в\s+)?палатк", t):
        possible.append("lodging")
    if re.search(maybe + r"(?:(?:на|лететь|ехать)\s+)?(?:самолет|перелет|поезд(?!к))", t):
        possible.append("transport")
    if re.search(maybe + r"(?:(?:поехать|ехать)\s+)?(?:в\s+)?гор[ыа]\b", t):
        possible.append("trip_types")
    if possible:
        data["tentative_fields"] = possible
    # A fresh, incompatible request may be either a new trip or an edit. Do not
    # silently carry a prior pet, weekend or party into it; ask what the person means.
    fresh_request = re.match(r"\s*(?:хочу|мне хочется|планирую|ищу|подбери|помоги подобрать)\b", t)
    explicit_edit = re.search(r"\b(?:лучше|вместо|тогда|измени|поменяй|скорректируй)\b", t)
    if state.dest_id and fresh_request and not explicit_edit and not data.get("new_search"):
        requested = set(data.get("trip_types") or []) - {"warm", "food"}
        destination_changed = data.get("destination") and data["destination"] != state.dest_id
        category_changed = requested and not requested.intersection(BY_ID[state.dest_id].tags)
        if destination_changed or category_changed:
            data["needs_trip_choice"] = True
    return TripUpdate(**data)
