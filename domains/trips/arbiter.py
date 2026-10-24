"""Сверка ответа LLM с текстом реплики и разбором правилами — защита от типовых сбоев модели.

Типовые сбои (опыт прошлого проекта, docs/04_decisions.md ADR 020–023):
- «да» на мусоре или на вопросе → ложное оформление; поэтому согласие принимаем, только если его видят правила;
- повтор действий и параметров из контекста («на два дня позже» второй раз) → действие без опоры в тексте отбрасываем;
- галлюцинация параметра («с собакой», бюджет), которого в реплике нет → поле без опоры в тексте отбрасываем;
- неточные числа и даты → там, где правила нашли значение, верим правилам (они не додумывают).
"""

from __future__ import annotations

import re

from .rules import find_destination
from .state import TripState, TripUpdate
from .textparse import norm

# Поля, где правила точнее модели: если правила что-то нашли, берём их значение
RULES_WIN = {"date_from", "date_to", "nights", "month", "budget_total", "budget_night", "adults", "children",
             "max_travel_hours", "stars_min", "shift_days", "pick", "confirm", "after_sale", "origin"}

_NUM = r"\d|один|одна|дв|три|четыр|пят|шест|сем|восем|девят|десят|пар"
_MONTHS = r"январ|феврал|март|апрел|ма[йяе]|июн|июл|август|сентябр|октябр|ноябр|декабр"
# Признаки в тексте, без которых значение поля от модели не принимаем (защита от повторов и выдумок)
CUES = {
    "origin": r"\bиз\b|вылет|отправ|живу|выезжа",
    "month": _MONTHS + r"|майск|нов\w+ год|лет[оа]м|зим|весн|осен",
    "date_from": _NUM + "|" + _MONTHS + r"|выходн|недел|завтра|сегодня|майск|год|числ",
    "date_to": _NUM + "|" + _MONTHS + r"|выходн|недел|завтра|майск|год|числ",
    "nights": _NUM + r"|недел|выходн|ноч|сут|дн",
    "adults": _NUM + r"|взросл|вдво|втро|вчетв|нас\b|муж|жен|один|одна|сам\b|друз|компан|семь|пар[аео]",
    "children": r"реб|дет|сын|доч|малыш|школьн|подрост|семь",
    "pets": r"соба|кош|кот|пит[оеё]м|живот|п[её]с|щен",
    "budget_total": _NUM + r"|тыс|к\b|млн|миллион|бюджет|руб|₽|дешев|недорог",
    "budget_night": _NUM + r"|тыс|к\b|ноч|сутк",
    "max_travel_hours": _NUM + r"|час|долг|далек|близк|недалек",
    "transport": r"поезд|самол|перел[её]т|лет[еая]|\bж/?д\b|электрич|сапсан|машин|авто",
    "direct_only": r"пересад|прям",
    "meal": r"завтрак|включ|пансион|питан|еда|корм|inclusive|ужин",
    "free_cancellation": r"отмен|возврат|предоплат",
    "stars_min": r"зв[её]зд|\*|★|люкс|пят[её]р|четв[её]р",
    "abroad": r"границ|рубеж|росси|виз|стран",
    "pick": _NUM + r"|перв|втор|трет|вариант|этот|эту|эта|его|её|ее|беру|берём|берем|выбира|давай|хочу",
    "shift_days": r"позже|раньше|сдвин|перенес|перенест",
    "cheaper": r"дешев|дорог|бюджет|сэконом|подешев|поменьше",
    "show_hotels": r"отел|гостиниц|жиль|вариант",
    "new_search": r"заново|сначала|нов\w+ (поиск|поездк)|друг\w+ поездк",
    "after_sale": r"заезд|выезд|отмен|перенес|перенест|дат",
    "hesitate": r"подума|подожд|погоди|уверен|готов|позже|сейчас|сомнева|посовет",
    "question": r"\?|виз|паспорт|отмен|багаж|погод|трансфер|животн|собак",
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

    for field, value in list(data.items()):
        if value is None:
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

    if data.get("pick_name") and norm(data["pick_name"])[:4] not in t:
        notes.append(f"pick_name={data['pick_name']!r}: нет в тексте")
        data["pick_name"] = None

    # Направление: правила знают каталог точно; без упоминания в тексте модель часто повторяет контекст
    if data.get("destination"):
        dest = data["destination"]
        if rule_data.get("destination") and rule_data["destination"] != find_destination(norm(dest)):
            notes.append(f"destination: правила {rule_data['destination']} вместо LLM {dest}")
            data["destination"] = rule_data["destination"]
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
