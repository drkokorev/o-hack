"""Сверка ответа LLM с текстом реплики и разбором правилами — защита от типовых сбоев модели.

Типовые сбои (опыт прошлого проекта, docs/04_decisions.md ADR 020–023):
- «да» на мусоре или на вопросе → ложное оформление; поэтому согласие принимаем, только если его видят правила;
- повтор действий и параметров из контекста («на два дня позже» второй раз) → действие без опоры в тексте отбрасываем;
- галлюцинация параметра («с собакой», бюджет), которого в реплике нет → поле без опоры в тексте отбрасываем;
- неточные числа и даты → там, где правила нашли значение, верим правилам (они не додумывают).
"""

from __future__ import annotations

import re

from .geo import BY_ID
from .rules import find_destination
from .state import TripState, TripUpdate
from .textparse import norm

# Поля, где правила точнее модели: если правила что-то нашли, берём их значение
RULES_WIN = {"date_from", "date_to", "nights", "month", "season", "year", "budget_total", "budget_night", "adults", "children", "pets", "trip_types", "transport", "lodging",
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


def _same(a, b) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    return a == b


def arbitrate(state: TripState, text: str, llm: TripUpdate, rules: TripUpdate) -> tuple[TripUpdate, list[str]]:
    t = norm(text)
    data = llm.model_dump()
    rule_data = rules.model_dump()
    notes: list[str] = []

    service_fields = ("unknown_place", "unknown_origin", "country_conflict", "place_country", "country", "excluded_countries", "visa_free_requested", "budget_per_person", "flight_concern", "corrected_place", "unsure", "duration_not_given", "clear_duration", "payment_method", "season", "children_unknown", "children_ages", "rooms", "tentative_fields", "trip_days_min", "trip_days_max", "needs_trip_choice", "resolve_trip_choice", "prefer_short_travel", "party_size", "remove_hotel_wishes", "show_real_hotels", "air_min_temp", "air_max_temp", "sea_min_temp", "sea_max_temp")
    for field in service_fields:  # служебные поля — только из правил
        data[field] = rule_data.get(field)
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
        if cue and not re.search(cue, t):
            notes.append(f"{field}={value!r}: нет опоры в тексте")
            data[field] = None

    if rules.month is not None and rules.date_from is None and (data.get("date_from") or data.get("date_to")):
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

    if data.get("pick_name") and norm(data["pick_name"])[:4] not in t:
        notes.append(f"pick_name={data['pick_name']!r}: нет в тексте")
        data["pick_name"] = None

    if data.get("origin") and not rules.origin and norm(data["origin"])[:4] not in t:
        notes.append("origin: в реплике нет указанного моделью города отправления")
        data["origin"] = None

    if data.get("meal") and not rules.meal:
        # Mentioning food in general is not a request for a hotel meal plan.
        notes.append("meal: конкретный тип питания пользователь не назвал")
        data["meal"] = None

    if rules.question == "pets" and rules.pets is None and data.get("pets") is not None:
        notes.append("pets: вопрос об условиях для животных не подтверждает их участие в поездке")
        data["pets"] = None
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
            notes.append(f"{field}: точное значение в реплике не подтверждено")
            data[field] = None

    explicit_day = re.search(r"\b\d{1,2}\s*[./]\s*\d{1,2}|\b\d{1,2}\s*(?:–|-|по\b|"
                             r"январ|феврал|март|апрел|ма[йяе]|июн|июл|август|сентябр|октябр|ноябр|декабр)|"
                             r"\b(?:завтра|послезавтра|сегодня)\b", t)
    if not rules.date_from and not explicit_day:
        data["date_from"] = data["date_to"] = None
    elif not rules.date_to and data.get("date_to"):
        notes.append("date_to: дата окончания поездки явно не подтверждена")
        data["date_to"] = None

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
        elif rules.question == "travel" and not rules.destination and not rules.unknown_place:
            notes.append("destination: вопрос о времени пути не называет направление")
            data["destination"] = None
        elif rule_data.get("country") and not rule_data.get("destination"):
            data["destination"] = None
        elif rule_data.get("destination") and rule_data["destination"] != find_destination(norm(dest)):
            notes.append(f"destination: правила {rule_data['destination']} вместо LLM {dest}")
            data["destination"] = rule_data["destination"]
        elif rule_data.get("unknown_place"):
            data["destination"] = rule_data["unknown_place"]
        elif not rule_data.get("destination"):
            # Do not turn generic tags ("mountains") or an origin city into
            # a destination merely because the model produced a valid string.
            destination_text = re.sub(r"(?:\bиз|вылет\w* из|едем из|летим из|живу в)\s+[а-яё\-]+", " ", t)
            if norm(dest) not in destination_text:
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
