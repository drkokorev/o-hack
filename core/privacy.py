"""Локальное распознавание имён перед отправкой текста внешней модели.

Модель распознавания работает в процессе приложения и не делает сетевых вызовов.
Её результат является эвристикой и не доказывает отсутствие всех личных данных.
"""
from __future__ import annotations

import threading
import re
from functools import lru_cache
from importlib.resources import files
from typing import Any, Callable


PlacePredicate = Callable[[str, int, int], bool]
_TOKEN = re.compile(r"\[([а-яё ]+)_(\d+)\]")


class Vault:
    """Обратимое маскирование на одну сессию: «[имя_1]» ↔ исходное значение.

    Живёт только в памяти процесса. В модель, логи и историю диалога уходят лишь метки, таблица соответствий —
    никогда. Одно и то же значение в сессии получает одну и ту же метку, чтобы модель понимала связи в тексте.
    Вернуть в ответ можно только безопасные виды (по умолчанию имена): номера карт, паспорта и коды
    пользователю не повторяем.
    """

    RESTORE = frozenset({"имя"})

    def __init__(self) -> None:
        self._by_value: dict[tuple[str, str], str] = {}
        self._by_token: dict[str, str] = {}

    def token(self, label: str, value: str) -> str:
        key = (label, " ".join(value.casefold().split()))
        if key not in self._by_value and label == "имя":
            # «Иван» после «Иван Петров» — тот же человек, а не [имя_2]
            words = set(key[1].split())
            same = next((tok for (kind, known), tok in self._by_value.items()
                         if kind == label and (words <= set(known.split()) or set(known.split()) <= words)), None)
            if same:
                self._by_value[key] = same
        if key not in self._by_value:
            number = sum(1 for tok in self._by_token if tok.startswith(f"[{label}_")) + 1
            token = f"[{label}_{number}]"
            self._by_value[key] = token
            self._by_token[token] = value.strip()
        return self._by_value[key]

    def known(self, token: str) -> bool:
        return token in self._by_token

    def restore(self, text: str, kinds: frozenset[str] = RESTORE) -> str:
        """Метки разрешённых видов → исходные значения; остальные → обезличенная «[телефон]»."""
        def put(match: re.Match) -> str:
            token, label = match.group(0), match.group(1)
            if label in kinds and token in self._by_token:
                return self._by_token[token]
            return f"[{label}]"
        return _TOKEN.sub(put, text)

    def __len__(self) -> int:
        return len(self._by_token)
_LOCK = threading.RLock()
_LOWER_NAME_PAIR = re.compile(r"\b(?:для|с|со)\s+([а-яё]{3,})\s+([а-яё-]{4,})\b")
_LOWER_NAME_SINGLE = re.compile(r"\b(?:для|с|со)\s+([а-яё]{3,})\b")
_SURNAME = re.compile(r"(?:ов|ев|ин)(?:а|ой|у|ым|ыме|ых)?$|(?:ский|ского|скому|ская|ской|"
                      r"цкий|цкая|енко|чук|юк)$")
_TRAVEL_COMMANDS = frozenset({"перенеси", "перенесите", "подбери", "подберите", "покажи", "покажите",
                              "выбери", "выберите", "отмени", "отмените", "оформи", "оформите"})


@lru_cache(maxsize=1)
def _morph():
    import pymorphy2_dicts_ru
    from pymorphy2 import MorphAnalyzer

    return MorphAnalyzer(pymorphy2_dicts_ru.get_path())  # путь явно: поиск словаря требует pkg_resources


def _is_command(span: str) -> bool:
    """NER принимает глагол в начале короткой фразы за имя: «Оформляй оптимальный», «Запросите ранний заезд»."""
    word = span.casefold()
    if word in _TRAVEL_COMMANDS:
        return True
    if " " in word or word in _given_names():
        return False
    return any(p.tag.POS == "VERB" and "impr" in p.tag for p in _morph().parse(word))


@lru_cache(maxsize=1)
def _given_names() -> frozenset[str]:
    data = files("natasha").joinpath("data", "dict", "first.txt").read_text(encoding="utf-8")
    return frozenset(line.strip().casefold() for line in data.splitlines() if line.strip())


def _looks_like_given_name(word: str) -> bool:
    candidates = {word}
    if word.endswith(("ы", "и")):
        candidates.update({word[:-1] + "а", word[:-1] + "я"})
    if word.endswith(("ой", "ей", "ом", "ем")):
        root = word[:-2]
        candidates.update({root, root + "а", root + "я", root + "й"})
    return bool(candidates & _given_names())


@lru_cache(maxsize=1)
def _name_tagger():
    # Natasha ships its weights in the installed package; no runtime download.
    from natasha import NewsEmbedding, NewsNERTagger, Segmenter

    return Segmenter(), NewsNERTagger(NewsEmbedding())


def mask_names(text: str, preserve_place: PlacePredicate | None = None,
               vault: Vault | None = None) -> tuple[str, bool]:
    from natasha import Doc

    # One model is shared by requests, without retaining input texts or spans.
    with _LOCK:
        segmenter, tagger = _name_tagger()
        doc = Doc(text)
        doc.segment(segmenter)
        doc.tag_ner(tagger)
        spans = [(item.start, item.stop) for item in doc.spans if item.type == "PER"
                 and not _is_command(text[item.start:item.stop])]
        for match in _LOWER_NAME_PAIR.finditer(text):
            first, last = match.group(1), match.group(2)
            if _looks_like_given_name(first) and _SURNAME.search(last):
                spans.append((match.start(1), match.end(2)))
        for match in _LOWER_NAME_SINGLE.finditer(text):
            if _looks_like_given_name(match.group(1)):
                spans.append((match.start(1), match.end(1)))
    spans = [(start, end) for start, end in spans
             if not (preserve_place and preserve_place(text, start, end))]
    merged: list[tuple[int, int]] = []
    for start, end in sorted(set(spans)):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    for start, end in reversed(merged):
        text = text[:start] + (vault.token("имя", text[start:end]) if vault else "[имя]") + text[end:]
    return text, bool(merged)


class PrivacyFilteredLLM:
    """Проверяет все сообщения непосредственно перед каждым вызовом модели.

    Включает контекст и повторные попытки. Необрабатываемые форматы и ошибки
    проверки не пересылаются наружу; вызывающий код использует локальные правила.
    """

    def __init__(self, inner: Any, preserve_place: PlacePredicate | None = None):
        self.inner = inner
        self.preserve_place = preserve_place
        self.breaker = getattr(inner, "breaker", None)

    def complete(self, messages, *, json_mode=False, schema=None):
        from .guard import contains_unresolved_sensitive_data, mask_sensitive_data

        checked = []
        for message in messages:
            if (not isinstance(message, dict) or set(message) != {"role", "content"}
                    or message["role"] not in {"system", "user", "assistant"}
                    or not isinstance(message["content"], str)):
                raise ValueError("Неподдерживаемый формат сообщения для проверки данных")
            text, _ = mask_sensitive_data(message["content"], self.preserve_place)
            if message["role"] != "system" and contains_unresolved_sensitive_data(text):
                raise ValueError("Сообщение содержит неразобранные чувствительные сведения")
            checked.append({"role": message["role"], "content": text})
        return self.inner.complete(checked, json_mode=json_mode, schema=schema)
