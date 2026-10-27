"""Очистка пользовательского ввода и простая эвристика против промпт-инъекций."""

import re

MAX_INPUT_CHARS = 1000

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SPACES = re.compile(r"[ \t]+")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[a-z0-9.-]+\.[a-z]{2,}(?!\w)", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+7|8)[\s().-]*(?:\d[\s().-]*){10}(?!\d)")
_INTERNATIONAL_PHONE = re.compile(r"(?<!\d)\+\d(?:[\s().-]*\d){8,14}(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)")
_PASSPORT = re.compile(r"(?:загран)?паспорт\w*\s*(?:№|номер|серия)?\s*[:#]?\s*\d(?:[\s-]?\d){9,11}(?!\d)", re.IGNORECASE)
_INJECTION = re.compile(
    "|".join(
        [
            r"ignore (all |the )?(previous|above|prior) (instructions|prompts?)",
            r"игнорир\w* (все |всё )?(предыдущ|инструкц|правил)",
            r"забудь\w* (все |всё )?(инструкц|правил|что тебе)",
            r"(system|системн\w*) (prompt|промпт)",
            r"developer mode|режим разработчика",
            r"\bjailbreak\b",
        ]
    ),
    re.IGNORECASE,
)


def sanitize(text: str) -> str:
    text = _CONTROL.sub("", text)
    text = _SPACES.sub(" ", text).strip()
    return text[:MAX_INPUT_CHARS]


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


def contains_sensitive_data(text: str) -> bool:
    """Блокирует некоторые явно лишние для демо данные; не является полным распознаванием ПДн."""
    return any(pattern.search(text) for pattern in (_EMAIL, _PHONE, _INTERNATIONAL_PHONE, _CARD, _PASSPORT))
