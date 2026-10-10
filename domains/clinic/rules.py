"""Детерминированный разбор реплик пациента. Fallback для LLM; на нём же работает демо без ключа."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

from core.ru import MONTHS_GEN

from .speech import SpeechNormalizer, strip_fillers

if TYPE_CHECKING:
    from .domain import ClinicState, ClinicUpdate
    from .schedule import Schedule

_INTENTS = [
    ("reschedule", r"перенес|перенест|поменять время|другое время|сдвинуть"),
    ("cancel", r"отмен|не смогу прийти|не приду"),
    ("status", r"статус|(мо|сво)\w* запис|на когда я|когда у меня|провер\w*.{0,12}запис|есть ли у меня запис|узна\w*.{0,15}запис"),
    ("schedule", r"расписан|когда принимает|в какие дни|часы при[её]ма|когда работает|график"),
    ("book", r"запис|запиш|на при[её]м|попасть к|\bко? врачу|к доктору"),
]

# Сначала ищем явно названного специалиста, потом — по жалобам
_EXPLICIT = [
    ("терапевт", r"терапевт"),
    ("стоматолог", r"стоматолог|дантист|зубно\w* врач"),
    ("оториноларинголог", r"\bлор\w{0,2}\b|отоларинголог|оториноларинголог|ухо-горло-нос"),
    ("офтальмолог", r"офтальмолог|окулист|глазно\w* врач"),
    ("невролог", r"невролог|невропатолог"),
    ("кардиолог", r"кардиолог"),
    ("дерматолог", r"дерматолог|кожник"),
    ("педиатр", r"педиатр|детск\w* врач"),
]
_SYMPTOMS = [
    ("стоматолог", r"\bзуб|десн"),
    ("оториноларинголог", r"\bух[оа]\b|\bуш[иа]|насморк|заложен\w* нос"),
    ("офтальмолог", r"глаз|зрени"),
    ("кардиолог", r"сердц|давлени"),
    ("дерматолог", r"\bкож|сыпь|родинк|прыщ|зуд"),
    ("невролог", r"голов\w* бол|бол\w* голов|мигрен|\bспин|поясниц|онемен"),
    ("педиатр", r"ребен|ребён|\bсын|\bдоч"),
    ("терапевт", r"температур|простуд|кашел|кашл|горл|слабост|орви|грипп|больничн|справк|заболел"),
]

_WEEKDAYS = [r"понедельник", r"вторник", r"\bсред[уаы]\b", r"четверг", r"пятниц", r"суббот", r"воскресен"]
_ORDINALS = {
    1: r"\bперв(ый|ого|ому|ым|ая|ую|ое)\b|\bодин\b",
    2: r"\bвтор(ой|ого|ому|ым|ая|ую|ое)\b|\bдва\b",
    3: r"\bтреть?(ий|его|ему|им|ья|ью|е)\b|\bтри\b",
}
_YES = r"\b(да|ага|угу|конечно|давайте|подтверждаю|верно|хорошо|согласен|согласна)\b"
_NO = r"\b(нет|не надо|не нужно|не отменяйте|оставьте)\b"
_NAME = r"(?i:меня зовут|моя фамилия|фамилия|на имя|пациент[а-я]*)\s+([А-ЯЁа-яё-]+(?:\s+[А-ЯЁа-яё-]+){0,2})"
_NOT_NAME = {"и", "я", "а", "хочу", "мне", "на", "к", "запишите", "пожалуйста", "записаться", "нужно", "надо"}


def _first(patterns: list[tuple[str, str]], text: str) -> str | None:
    return next((value for value, pattern in patterns if re.search(pattern, text)), None)


def _parse_day(text: str, today: date) -> date | None:
    if "послезавтра" in text:
        return today + timedelta(days=2)
    if "завтра" in text:
        return today + timedelta(days=1)
    if "сегодня" in text:
        return today
    m = re.search(r"\b(\d{1,2})\s+(" + "|".join(MONTHS_GEN) + r")", text)
    if m:
        d = date(today.year, MONTHS_GEN.index(m.group(2)) + 1, int(m.group(1)))
        return d if d >= today else d.replace(year=today.year + 1)
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})\b", text)
    if m and 1 <= int(m.group(2)) <= 12:
        d = date(today.year, int(m.group(2)), int(m.group(1)))
        return d if d >= today else d.replace(year=today.year + 1)
    for wd, pattern in enumerate(_WEEKDAYS):
        if re.search(pattern, text):
            return today + timedelta(days=(wd - today.weekday()) % 7 or 7)
    return None


def _hm(hour: str, minute: str | None, text_after: str = "") -> time | None:
    h, m = int(hour), int(minute or 0)
    if h < 8 and re.match(r"\s*(час\w*\s*)?(дня|вечера)", text_after):
        h += 12
    return time(h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None


def _parse_exact_time(text: str) -> time | None:
    m = re.search(r"\b(?:в|на)\s+(\d{1,2})[:.](\d{2})\b", text) or re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if m:
        return _hm(m.group(1), m.group(2))
    m = re.search(r"\b(?:в|на)\s+(\d{1,2})\s*(час\w*)?\s*(утра|дня|вечера)?", text)
    if m and (m.group(2) or m.group(3)):
        return _hm(m.group(1), None, text[m.end(1):])
    return None


def _parse_window(text: str) -> tuple[time | None, time | None]:
    if re.search(r"\bутр", text):
        return time(8), time(12)
    if re.search(r"дн[её]м|после обеда|в обед", text):
        return time(13), time(17)
    if re.search(r"вечер", text):
        return time(17), time(21)
    after = re.search(r"после\s+(\d{1,2})(?:[:.](\d{2}))?", text)
    before = re.search(r"\bдо\s+(\d{1,2})(?:[:.](\d{2}))?", text)
    return (_hm(after.group(1), after.group(2)) if after else None,
            _hm(before.group(1), before.group(2)) if before else None)


def _awaits_name(st: "ClinicState") -> bool:
    if st.chosen is not None and not st.patient_name:
        return True
    return st.intent in ("status", "cancel", "reschedule") and st.target is None and not st.booking_id


def rule_extract(
    st: "ClinicState", raw: str, today: date, schedule: "Schedule", speech: SpeechNormalizer | None = None
) -> "ClinicUpdate":
    from .domain import ClinicUpdate

    raw = strip_fillers(raw)
    text = raw.lower().replace("ё", "е")
    if speech is not None:
        text = speech.fix(text)
    upd: dict = {}

    intent = next((name for name, pattern in _INTENTS if re.search(pattern, text)), None)
    if intent:
        upd["intent"] = intent

    m = re.search(_NAME, raw)
    name_words: set[str] = set()
    if m:
        words = []
        for w in m.group(1).split():
            if w.lower() in _NOT_NAME:
                break
            words.append(w.capitalize())
        if words:
            upd["patient_name"] = " ".join(words)
    elif _awaits_name(st) and not intent:
        words = re.findall(r"[А-ЯЁа-яё-]+", raw)
        if 1 <= len(words) <= 3 and not re.search(_YES + "|" + _NO, text):
            upd["patient_name"] = " ".join(w.capitalize() for w in words)
    if "patient_name" in upd:
        name_words = set(upd["patient_name"].lower().split())

    m = re.search(r"\b[Bb]-?0*(\d{1,4})\b", raw) or re.search(r"номер\w*\s+(?:записи\s+)?0*(\d{1,4})\b", text)
    if m:
        upd["booking_id"] = f"B{int(m.group(1)):04d}"

    specialty = _first(_EXPLICIT, text) or _first(_SYMPTOMS, text)
    if specialty:
        upd["specialty"] = specialty
    for word in re.findall(r"[а-я-]{4,}", text):
        if word not in name_words and (doctor := schedule.find_doctor(word)):
            upd["doctor_name"] = doctor.name
            break

    day = _parse_day(text, today)
    exact = _parse_exact_time(text)

    # Пациент выбирает из предложенного: «второй», «давайте в 12:30»
    if st.offered and st.chosen is None:
        choice = next((n for n, pattern in _ORDINALS.items() if re.search(pattern, text)), None)
        if choice is None and re.search(r"последн", text):
            choice = len(st.offered)
        if choice is None and exact:
            hits = [i for i, s in enumerate(st.offered, 1)
                    if s.start.time() == exact and (day is None or s.start.date() == day)]
            if len(hits) == 1:
                choice, day, exact = hits[0], None, None
        if choice is not None and choice <= len(st.offered):
            upd["choice"] = choice

    if day:
        upd["day"] = day
    if exact:
        upd["time_from"] = exact
        upd["time_to"] = (datetime.combine(today, exact) + timedelta(minutes=30)).time()
    else:
        time_from, time_to = _parse_window(text)
        if time_from:
            upd["time_from"] = time_from
        if time_to:
            upd["time_to"] = time_to

    if re.search(_NO, text):
        upd["confirm"] = False
    elif re.search(_YES, text):
        upd["confirm"] = True
    return ClinicUpdate(**upd)
