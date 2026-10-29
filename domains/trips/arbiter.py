"""Сверка ответа LLM с текстом реплики и разбором правилами — защита от типовых сбоев модели.

Типовые сбои (опыт прошлого проекта, docs/04_decisions.md ADR 020–023):
- «да» на мусоре или на вопросе → ложное оформление; поэтому согласие принимаем, только если его видят правила;
- повтор действий и параметров из контекста («на два дня позже» второй раз) → действие без опоры в тексте отбрасываем;
- галлюцинация параметра («с собакой», бюджет), которого в реплике нет → поле без опоры в тексте отбрасываем;
- неточные числа и даты → там, где правила нашли значение, верим правилам (они не додумывают).

Где правила ничего не поняли («11 дн», «из пинзы», «2 взр + реб»), главная — модель (ADR 028): значение
принимаем, если её дословная ссылка на реплику (`evidence`) есть в тексте и подтверждает значение (`_backed`);
без ссылки — если число стоит в реплике со своей единицей (`_grounded`). Действия — только с правилами.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .geo import BY_ID
from .dialogue import QUESTION_INPUT_FIELDS
from .rules import DEFERABLE_QUESTIONS, PLACE_QUESTIONS, find_destination, match_origin, time_expression_not_place
from .state import TripState, TripUpdate
from .textparse import MONTH_RE, month_of, norm

# Поля, где правила точнее модели: если правила что-то нашли, берём их значение
RULES_WIN = {"date_from", "date_to", "nights", "month", "season", "year", "budget_total", "budget_night", "adults", "children", "pets", "trip_types", "scenic_views", "relaxed_walks", "transport", "lodging",
             "meal", "hotel_wishes", "abroad", "economy", "direct_only", "baggage",
             "max_travel_hours", "stars_min", "shift_days", "pick", "confirm", "after_sale", "origin", "question"}

_NUM = r"\d|один|одна|дв|три|четыр|пят|шест|сем|восем|девят|десят|пар"
_MONTHS = r"январ|феврал|март|апрел|ма[йяе]|июн|июл|август|сентябр|октябр|ноябр|декабр"
# Признаки в тексте, без которых значение поля от модели не принимаем (защита от повторов и выдумок)
CUES = {
    "origin": r"\bиз\b|вылет|отправ|живу|выезжа",
    "month": _MONTHS + r"|майск|нов\w+ год|лет[оа]м?|летн|зим|весн|осен",
    "year": r"\b20\d{2}\b",
    "date_from": _NUM + "|" + _MONTHS + r"|выходн|недел|завтра|сегодня|майск|год|числ",
    "date_to": _NUM + "|" + _MONTHS + r"|выходн|недел|завтра|майск|год|числ",
    "nights": _NUM + r"|недел|выходн|ноч|сут|дн",
    "adults": _NUM + r"|взросл|вдво|втро|вчетв|нас\b|муж|жен|один|одна|сам\b|друз|компан|семь|пар[аео]",
    "children": r"реб|дет|сын|доч|малыш|школьн|подрост|семь",
    "pets": r"соба|кош|кот|пит[оеё]м|живот|п[её]с|щен",
    "lodging": r"палат|кемпинг|отел|жиль",
    "budget_total": _NUM + r"|тыс|к\b|млн|миллион|бюджет|руб|₽|дешев|недорог",
    "budget_night": _NUM + r"|тыс|к\b|ноч|сутк",
    "max_travel_hours": _NUM + r"|час|долг|далек|близк|недалек",
    "transport": r"\bпоезд(?!к)|самол|перел[её]т|лет[еая]|\bж/?д\b|электрич|сапсан|машин|авто",
    "direct_only": r"пересад|прям",
    "meal": r"завтрак|включ|пансион|питан|еда|корм|inclusive|ужин",
    "free_cancellation": r"отмен|возврат|предоплат",
    "stars_min": r"зв[её]зд|\*|★|люкс|пят[её]р|четв[её]р",
    "abroad": r"границ|рубеж|росси|виз|стран",
    "economy": r"дешев|дорог|бюджет|эконом|недорог",
    "pick": _NUM + r"|перв|втор|трет|вариант|этот|эту|эта|его|её|ее|беру|берём|берем|выбира|давай|хочу",
    "shift_days": r"позже|раньше|сдвин|перенес|перенест",
    "cheaper": r"дешев|дорог|бюджет|сэконом|подешев|поменьше",
    "show_hotels": r"отел|гостиниц|жиль|вариант",
    "new_search": r"заново|сначала|нов\w+ (поиск|поездк)|друг\w+ поездк",
    "after_sale": r"заезд|выезд|отмен|перенес|перенест|дат",
    "month_part": r"начал|середин|конц|конец|половин",
    "baggage": r"багаж|чемодан",
    "more": r"ещ[её]|друг|покажи|что ещ",
    "back": r"верн|назад",
    "add_adults": r"добав|ещ[её]|\+",
    "wants_ideas": r"отдох|поех|съезд|отпуск|путешеств|куда|поездк|тур|посовет|иде",
    "hesitate": r"подума|подожд|погоди|уверен|готов|позже|сейчас|сомнева|посовет",
    "question": r"\?|виз|паспорт|отмен|багаж|погод|трансфер|животн|собак|адрес|расположен|местоположен",
    "clear": r"не важ|без разниц|люб[оа]|убери|не нужн|друг\w* направлен|не учитыва|неважн",
}


_WORD_NUMBERS = {"один": 1, "одна": 1, "одного": 1, "одну": 1, "два": 2, "две": 2, "двое": 2, "двоих": 2, "пару": 2,
                 "три": 3, "трое": 3, "троих": 3, "четыре": 4, "четверо": 4, "пять": 5, "пятеро": 5, "шесть": 6,
                 "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11, "двенадцать": 12,
                 "четырнадцать": 14, "пятнадцать": 15, "двадцать": 20}
_NUMBER = r"(\d+(?:[.,]\d+)?|" + "|".join(_WORD_NUMBERS) + r")"
# Число засчитывается только рядом со своей единицей: «11 дн», «2 взр», «150к», «5 часов»
_UNITS = {
    "nights": r"\s*(?:ноч\w*|н\b|сут\w*|дн\w*|д\b|день|дня)",
    "adults": r"\s*(?:взр\w*|чел\w*)",
    "children": r"\s*(?:дет\w*|реб\w*|малыш\w*)",
    "budget_total": r"\s*(?:тыс\w*|т\.?р\.?|к\b|k\b|млн|миллион\w*|руб\w*|₽|р\b)",
    "budget_night": r"\s*(?:тыс\w*|т\.?р\.?|к\b|k\b|руб\w*|₽|р\b)",
    "max_travel_hours": r"\s*(?:час\w*|ч\b)",
}
# Поле, о котором агент только что спросил: голое число в коротком ответе — ответ на вопрос
_PENDING = {"duration": "nights", "people": "adults", "children": "children", "budget": "budget_total"}


def _value(raw: str, unit: str) -> set[int]:
    number = float(raw.replace(",", ".")) if raw[0].isdigit() else _WORD_NUMBERS[raw]
    scale = 1_000_000 if unit.startswith(("млн", "миллион")) else 1000 if re.match(r"тыс|т\.?р|к|k", unit) else 1
    return {int(number), int(number * scale)}


# ---------- значения модели со ссылкой на реплику (evidence) ----------
# Модель главная в понимании: значение принимаем, если её дословная ссылка есть в реплике (с опечатками)
# и подтверждает значение. Действия (оформить, оплатить, отменить, выбрать) — по-прежнему только с правилами.
# Требования к отелю и дороге (питание, удобства, животные, багаж, «без пересадок») — только через правила:
# «завтрак и бассейн есть?» — вопрос, а не требование, правила это различают
_EVIDENCE_FIELDS = {"destination", "origin", "month", "date_from", "date_to", "nights", "adults", "children",
                    "budget_total", "budget_night", "max_travel_hours", "trip_types", "transport", "lodging",
                    "abroad", "economy", "stars_min", "party_size", "scenic_views", "relaxed_walks", "question"}
# «С женой», «вдвоём», «с друзьями» возраст не подтверждают — агент уточнит про детей (решение команды)
_ADULT_WORDS = r"взр|один|одна|\bсам\b|\bсама\b"


def _quote_in(quote: str, t: str) -> bool:
    """Фрагмент модели действительно есть в реплике — дословно или с мелкими расхождениями («стамбл»)."""
    q = norm(quote).strip(" .,!?:;«»\"'")
    if len(q) < 1:
        return False
    if q in t:
        return True
    if len(q) < 4:
        return False
    return any(SequenceMatcher(None, q, t[i:i + len(q)]).ratio() >= 0.85 for i in range(0, max(1, len(t) - len(q) + 1)))


_WEEKS = r"(?:(\d|две|два|три|пару)\s*)?\bнед(?:ел\w*|\b)"


def _quote_numbers(q: str) -> set[int]:
    """Числа во фрагменте: цифры («150к» = 150 000), слова, «вдвоём», недели («полторы недели» — 10–11 ночей)."""
    found: set[int] = set()
    for m in re.finditer(rf"(?<![а-яё\d]){_NUMBER}\s*(тыс\w*|т\.?р\.?|к\b|k\b|млн|миллион\w*)?", q):
        found |= _value(m.group(1), (m.group(2) or "").strip())
    found |= {n for stem, n in (("вдво", 2), ("двоих", 2), ("втро", 3), ("троих", 3), ("вчетв", 4), ("четверых", 4),
                                ("впят", 5)) if stem in q}
    for m in re.finditer(_WEEKS, q):
        found.add(7 * ({"две": 2, "два": 2, "три": 3, "пару": 2}.get(m.group(1) or "") or int(m.group(1) or 1)))
    if re.search(r"полтор\w* недел", q):
        found |= {10, 11}
    return found


def _backed(field: str, value, quote: str | None, t: str) -> bool:
    """Ссылка модели есть в реплике и согласуется со значением поля."""
    if field not in _EVIDENCE_FIELDS or not quote or value is None or not _quote_in(quote, t):
        return False
    q = norm(quote)
    if field == "question":
        topics = set(str(value).split("|")) - {""}
        return len(q.strip()) >= 4 and bool(topics) and topics <= PLACE_QUESTIONS
    if field == "destination":
        dest_id = find_destination(norm(str(value)))
        return norm(str(value))[:4] in q or (dest_id is not None and find_destination(q) == dest_id)
    if field == "origin":
        return norm(str(value))[:4] in q or match_origin(q) == value
    if field == "month":
        return any(month_of(m.group(0)) == value for m in re.finditer(MONTH_RE, q))
    if field in ("date_from", "date_to"):
        # A day number alone cannot prove the month or year supplied by the model.
        # Rules resolve partial and relative dates against today's date instead.
        if not hasattr(value, "day"):
            return False
        for match in re.finditer(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})(?!\d)", q):
            if (int(match.group(1)), int(match.group(2)), int(match.group(3))) == (value.day, value.month, value.year):
                return True
        return False
    if field in ("nights", "adults", "children", "budget_total", "budget_night", "max_travel_hours", "party_size"):
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        numbers = _quote_numbers(q)
        if field == "nights":
            return value in numbers or value + 1 in numbers  # «11 дней» — 10 ночей
        if field == "adults":
            return value in numbers and bool(re.search(_ADULT_WORDS, q))
        if field == "children":
            return value in numbers or (value == 1 and bool(re.search(r"реб|сын|доч|малыш", q)))
        return value in numbers
    return True  # тип отдыха, транспорт, питание, удобства — смысл понимает модель, ссылка подтверждена


def _grounded(field: str, value, t: str, state: TripState, rules: TripUpdate) -> bool:
    """Модель не дала ссылку: ищем в реплике сами куски, где число стоит со своей единицей («11 дн», «2 взр»,
    «150к»), и проверяем их как ссылку. Голое число засчитываем только коротким ответом на заданный вопрос."""
    if not isinstance(value, int) or isinstance(value, bool) or (field == "nights" and rules.trip_days_min):
        return False  # «11 дней» правила уже поняли как дни
    if (_PENDING.get(state.pending_question or "") == field and len(t.split()) <= 3
            and not re.search(r"через|позже|раньше", t) and value in _quote_numbers(t)):
        return True
    spans = [m.group(0) for m in re.finditer(rf"(?<![а-яё\d]){_NUMBER}{_UNITS[field]}", t)
             if not re.search(r"(?:через|спустя|за)\s+$", t[:m.start()])]  # «через 3 дня» — дата, а не длительность
    if field == "nights":
        spans += [m.group(0) for m in re.finditer(_WEEKS + r"|полтор\w* недел\w*", t)]
    return any(_backed(field, value, span, t) for span in spans)


def _same(a, b) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    return a == b


def arbitrate(state: TripState, text: str, llm: TripUpdate, rules: TripUpdate) -> tuple[TripUpdate, list[str]]:
    t = norm(text)
    data = llm.model_dump()
    rule_data = rules.model_dump()
    notes: list[str] = []
    quotes = llm.evidence or {}
    backed = {field for field, value in data.items() if _backed(field, value, quotes.get(field), t)}
    data.pop("evidence", None)

    service_fields = ("split_stays", "split_choice", "room_allocations", "search_scope", "flight_direction", "transfer_from", "transfer_to", "transfer_time", "transfer_date", "transfer_direction", "seat_class", "unknown_place", "unknown_origin", "country_conflict", "place_country", "country", "excluded_countries", "visa_free_requested", "budget_per_person", "flight_concern", "corrected_place", "unsure", "without_dates", "duration_not_given", "clear_duration", "payment_method", "season", "children_unknown", "children_ages", "rooms", "tentative_fields", "trip_days_min", "trip_days_max", "needs_trip_choice", "resolve_trip_choice", "prefer_short_travel", "party_size", "remove_hotel_wishes", "accessibility_needs", "remove_accessibility_needs", "show_real_hotels", "search_real_hotels", "air_min_temp", "air_max_temp", "sea_min_temp", "sea_max_temp")
    for field in service_fields:  # служебные поля — только из правил
        data[field] = rule_data.get(field)
    if data.get("clear") and not (rules.clear and "accessibility_needs" in rules.clear):
        data["clear"] = [field for field in data["clear"] if field != "accessibility_needs"] or None
    # A model can recognise an unfamiliar way to defer a clarification, but
    # only with a verbatim quote from this turn and no concrete answer or
    # competing action. Deferral never chooses an option or authorises a
    # transaction; required service details stay unknown and are requested.
    quote = norm(quotes.get("unsure", "")).strip()
    answer_fields = QUESTION_INPUT_FIELDS.get(state.pending_question or "", set())
    explicit_answer = any(rule_data.get(field) is not None or
                          (getattr(llm, field, None) is not None and
                           _backed(field, getattr(llm, field), quotes.get(field), t))
                          for field in answer_fields)
    if (rules.unsure is None and llm.unsure is True and state.pending_question in DEFERABLE_QUESTIONS
            and 4 <= len(quote) <= 120 and quote in t and not explicit_answer
            and not rules.question and not llm.question and rules.pick is None and rules.confirm is None
            and not llm.confirm and not rules.after_sale and not rules.resolve_trip_choice):
        data["unsure"] = True
    if llm.question and not rules.question:
        # Semantic fallback only for read-only destination questions with a
        # quoted user phrase. It cannot trigger purchases or discard a service.
        if (not state.dest_id or "question" not in backed or rules.confirm is not None or
                rules.pick is not None or rules.after_sale or rules.new_search or rules.search_scope):
            data["question"] = None
    if state.showing == "real_hotels":
        # A model may guess a number for a duplicate or partial name. Only an
        # exact, unambiguous visible record or a stated number can select it.
        if data.get("pick") and rules.pick is None:
            notes.append("pick: выбор из открытого каталога не подтверждён номером или точным названием")
        data["pick"] = rules.pick
        data["pick_name"] = None
    for field, value in list(data.items()):
        if value is None or field in service_fields:
            continue
        ruled = rule_data.get(field)
        if field in RULES_WIN and ruled is not None:
            if not _same(ruled, value):
                notes.append(f"{field}: правила {ruled!r} вместо LLM {value!r}")
            data[field] = ruled
            continue
        if field in TripState.model_fields and not isinstance(value, bool) and _same(getattr(state, field, None), value):
            data[field] = None  # повтор уже известного — не изменение
            continue
        cue = CUES.get(field)
        if cue and not re.search(cue, t) and field not in backed:
            notes.append(f"{field}={value!r}: нет опоры в тексте")
            data[field] = None

    for field in ("scenic_views", "relaxed_walks"):
        if (rule_data.get(field) is None and data.get(field) is not None and
                (field not in backed or "?" in text)):
            data[field] = None  # a question is not a confirmed wish

    if (rules.month is not None and rules.date_from is None and (data.get("date_from") or data.get("date_to"))
            and "date_from" not in backed):
        notes.append("модель указала точные даты, хотя правила нашли только месяц")
        data["date_from"] = data["date_to"] = None

    if rules.season and not rules.month and not rules.date_from:
        # A season is a range, not an invented month or exact departure date.
        data["month"] = data["date_from"] = data["date_to"] = None
    if re.search(r"вайб\s+лета|летн\w*\s+(?:настроен|вайб)", t) and not rules.month and not rules.season:
        data["month"] = data["date_from"] = data["date_to"] = None
    if rules.duration_not_given:
        data["nights"] = None
        if not rules.date_from:
            data["date_from"] = data["date_to"] = None

    if data.get("landmark"):
        words = [w for w in re.findall(r"[а-яёa-z]{3,}", norm(data["landmark"]))]
        if not words or not any(w[:4] in t for w in words):
            notes.append(f"landmark={data['landmark']!r}: нет в тексте")
            data["landmark"] = None
        elif data.get("destination") and not rules.destination and norm(data["destination"])[:4] not in t:
            data["destination"] = None  # город по достопримечательности определяем отдельно и с проверкой

    if data.get("pick_name") and norm(data["pick_name"])[:4] not in t:
        notes.append(f"pick_name={data['pick_name']!r}: нет в тексте")
        data["pick_name"] = None

    if (data.get("origin") and not rules.origin and norm(data["origin"])[:4] not in t and
            match_origin(t) != data["origin"] and "origin" not in backed):  # «пинза» — опечатка в названии, модель поняла верно
        notes.append("origin: в реплике нет указанного моделью города отправления")
        data["origin"] = None

    if data.get("meal") and not rules.meal:
        # Mentioning food in general is not a request for a hotel meal plan.
        notes.append("meal: конкретный тип питания пользователь не назвал")
        data["meal"] = None

    question_topics = set((rules.question or "").split("|"))
    asked = set((data.get("question") or rules.question or "").split("|")) - {""}
    if asked and asked <= PLACE_QUESTIONS:
        # «где вкусно поесть?» — вопрос о месте: ответ по путеводителю, условия поездки не меняем,
        # даже если модель нашла в нём «еду» со ссылкой на текст
        for field in TripState.model_fields:
            if field in data and field not in ("question",) and rule_data.get(field) is None:
                data[field] = None
    if "pets" in question_topics and rules.pets is None and data.get("pets") is not None:
        notes.append("pets: вопрос об условиях для животных не подтверждает их участие в поездке")
        data["pets"] = None
    if "child_fare" in question_topics and rules.children is None and data.get("children") is not None:
        notes.append("children: вопрос о детском тарифе не подтверждает состав поездки")
        data["children"] = None
    for topic, field in (("baggage", "baggage"), ("cancellation", "free_cancellation")):
        if topic in question_topics and rule_data.get(field) is None and data.get(field) is not None:
            notes.append(f"{field}: вопрос об условиях не задаёт требование")
            data[field] = None
    if rules.remove_hotel_wishes and data.get("clear") and "hotel_wishes" in data["clear"]:
        data["clear"] = [field for field in data["clear"] if field != "hotel_wishes"] or None
    if rules.clear:
        data["clear"] = list(dict.fromkeys([*(data.get("clear") or []), *rules.clear]))
    if rules.clear and "lodging" in rules.clear and not rules.lodging:
        data["lodging"] = None
    if rules.flight_concern and rules.transport is None:
        data["transport"] = None  # fear is not a final choice or a hard ban

    for field in ("budget_total", "budget_night", "adults", "children", "nights", "max_travel_hours", "hotel_wishes"):
        if data.get(field) is not None and rule_data.get(field) is None:
            if field in backed or (field != "hotel_wishes" and _grounded(field, data[field], t, state, rules)):
                continue  # «11 дн», «полторы недели», «бюджет 150к» — правила не разобрали, а число в реплике есть
            notes.append(f"{field}: точное значение в реплике не подтверждено")
            data[field] = None

    if not rules.date_from and "date_from" not in backed:
        data["date_from"] = None
    if not rules.date_to and data.get("date_to") and "date_to" not in backed:
        notes.append("date_to: дата окончания поездки явно не подтверждена")
        data["date_to"] = None
    if (rules.search_scope or state.search_scope) == "transfer_only":
        # Transfer pickup is a separate date; an LLM must not rewrite the stay.
        data["date_from"] = data["date_to"] = None

    # Направление: правила знают каталог точно; без упоминания в тексте модель часто повторяет контекст
    if data.get("destination"):
        dest = data["destination"]
        dest_id = find_destination(norm(dest))
        excluded = set(rules.excluded_countries or [])
        if (not rules.destination and excluded and
                (norm(dest) in {norm(country) for country in excluded} or
                 (dest_id and BY_ID[dest_id].country in excluded))):
            notes.append("destination: страна была исключена, а не выбрана")
            data["destination"] = None
        elif "travel" in question_topics and not rules.destination and not rules.unknown_place:
            notes.append("destination: вопрос о времени пути не называет направление")
            data["destination"] = None
        elif rule_data.get("country") and not rule_data.get("destination"):
            data["destination"] = None
        elif rule_data.get("destination") and rule_data["destination"] != find_destination(norm(dest)):
            notes.append(f"destination: правила {rule_data['destination']} вместо LLM {dest}")
            data["destination"] = rule_data["destination"]
        elif rule_data.get("unknown_place") and "destination" not in backed:
            data["destination"] = rule_data["unknown_place"]
        elif not rule_data.get("destination") and "destination" not in backed:
            # Do not turn generic tags ("mountains") or an origin city into
            # a destination merely because the model produced a valid string.
            destination_text = re.sub(r"(?:\bиз|вылет\w* из|едем из|летим из|живу в)\s+[а-яё\-]+", " ", t)
            if time_expression_not_place(dest) or not re.search(
                    rf"(?<![а-яёa-z0-9]){re.escape(norm(dest))}(?![а-яёa-z0-9])", destination_text):
                notes.append("destination: в реплике нет указанного моделью места")
                data["destination"] = None
        elif find_destination(norm(dest)) == state.dest_id and state.dest_id:
            data["destination"] = None

    # Согласие на оформление и отмену — только если правила видят явное «да» (а не вопрос и не «давай подумаем»)
    if llm.confirm is True and rules.confirm is not True:
        notes.append("confirm=true от LLM без явного согласия в тексте — отклонено")
        data["confirm"] = rules.confirm
    if llm.after_sale == "cancel" and rules.after_sale != "cancel":
        notes.append("after_sale=cancel от LLM без явной просьбы — отклонено")
        data["after_sale"] = rules.after_sale

    # Пробелы модели заполняем правилами
    for field, value in rule_data.items():
        if value is not None and data.get(field) is None and field not in ("confirm", "after_sale"):
            data[field] = value
    if data.get("confirm") is None and rules.confirm is not None:
        data["confirm"] = rules.confirm
    if data.get("after_sale") is None and rules.after_sale is not None:
        data["after_sale"] = rules.after_sale
    return TripUpdate.model_validate(data), notes
