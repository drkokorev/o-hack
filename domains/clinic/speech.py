"""Нормализация транскриптов речи до разбора.

Распознавание речи ошибается предсказуемо: пишет слова-паразиты («э», «ну», «как его»),
склеивает предлог со словом («клору» вместо «к лору») и путает буквы в редких словах
(«тирапевту», «Белавой»). Чиним это словарём специальностей и фамилий врачей, без обучения моделей.
"""

from __future__ import annotations

import difflib
import re

_FILLERS = re.compile(
    r"\b(э+(?:-э+)*|эм+|м+|ну|вот|как его|как е[её]|это самое|короче|типа|блин|в общем|значит)\b[,.]?",
    re.IGNORECASE,
)
_SPECIALTY_WORDS = [
    "терапевт", "стоматолог", "дантист", "лор", "отоларинголог", "оториноларинголог",
    "офтальмолог", "окулист", "невролог", "невропатолог", "кардиолог", "дерматолог", "педиатр",
]
_CASE_ENDINGS = ["", "у", "а", "ом", "ам"]
# Фамилию врача исправляем только там, где её и ждём: «к Белавой», «когда принимает Гусив».
# Иначе «голова» превращается в «Орлова», а пациентка Смирнова — во врача Миронову.
_DOCTOR_CONTEXT = {"к", "ко", "у", "доктор", "доктору", "доктора", "врач", "врачу", "врача", "принимает", "принимают"}


def _surname_forms(surname: str) -> list[str]:
    s = surname.lower().replace("ё", "е")
    if s.endswith("а"):  # Белова → Беловой, Белову
        return [s, s[:-1] + "ой", s[:-1] + "у"]
    return [s, s + "у", s + "а", s + "ым"]  # Орлов → Орлову, Орлова, Орловым


def strip_fillers(text: str) -> str:
    text = _FILLERS.sub(" ", text)
    text = re.sub(r"\s+([,.?!])", r"\1", text)
    text = re.sub(r"([,.?!])(?:\s*[,.])+", r"\1", text)
    return re.sub(r"\s+", " ", text).strip(" ,.")


class SpeechNormalizer:
    def __init__(self, doctor_surnames: list[str]):
        self._specialties = sorted({w + e for w in _SPECIALTY_WORDS for e in _CASE_ENDINGS})
        self._surnames = sorted({f for s in doctor_surnames for f in _surname_forms(s)})
        self._known = set(self._specialties) | set(self._surnames)

    def fix(self, text: str) -> str:
        """Текст в нижнем регистре → тот же текст с исправленными словами словаря."""
        pieces, last, prev = [], 0, ""
        for m in re.finditer(r"[а-я]+(?:-[а-я]+)*", text):
            pieces += [text[last:m.start()], self._fix_word(m.group(0), surnames_ok=prev in _DOCTOR_CONTEXT)]
            prev, last = m.group(0), m.end()
        pieces.append(text[last:])
        return "".join(pieces)

    def _fix_word(self, word: str, surnames_ok: bool) -> str:
        if len(word) < 4 or word in self._known:
            return word
        # Склейка с предлогом: «клору» → «к лору», «ктерапевту» → «к терапевту»
        for prefix in ("ко", "к"):
            rest = word[len(prefix):]
            if word.startswith(prefix) and rest in self._known:
                return f"{prefix} {rest}"
        if hit := self._fuzzy(word, surnames_ok):
            return hit
        for prefix in ("ко", "к"):
            rest = word[len(prefix):]
            if word.startswith(prefix) and (hit := self._fuzzy(rest, surnames_ok=True)):
                return f"{prefix} {hit}"
        return word

    def _fuzzy(self, word: str, surnames_ok: bool) -> str | None:
        if len(word) < 5:  # короткие слова исправлять опасно
            return None
        if hits := difflib.get_close_matches(word, self._specialties, n=1, cutoff=0.8):
            return hits[0]
        if surnames_ok:
            hits = difflib.get_close_matches(word, self._surnames, n=3, cutoff=0.8)
            return next((h for h in hits if h[0] == word[0]), None)
        return None
