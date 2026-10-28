"""Очистка пользовательского ввода и простая эвристика против промпт-инъекций."""

import re
import unicodedata

MAX_INPUT_CHARS = 1000

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SPACES = re.compile(r"[ \t]+")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[a-z0-9.-]+\.[a-z]{2,}(?!\w)", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+7|8)[\s().-]*(?:\d[\s().-]*){10}(?!\d)")
_INTERNATIONAL_PHONE = re.compile(r"(?<!\d)\+\d(?:[\s().-]*\d){8,14}(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)")
_PASSPORT = re.compile(
    r"(?:загран)?паспорт\w*\s*[:#№-]?\s*(?:(?:№|номер|серия)\s*[:#№-]?\s*)?"
    r"\d(?:[\s-]?\d){1,3}\s*(?:(?:номер|№)\s*[:#№-]?\s*)?\d(?:[\s-]?\d){5,7}(?!\d)",
    re.IGNORECASE,
)
_DOCUMENT = re.compile(
    r"\b(?:снилс|инн)\s*[:#№-]?\s*\d(?:[\s-]?\d){9,11}(?!\d)", re.IGNORECASE
)
_BIRTH_DATE = re.compile(
    r"\b(?:дата\s+рождения|родил(?:ся|ась))\s*[:#]?\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
    re.IGNORECASE,
)
_NAME = re.compile(
    r"(?:\bменя\s+зовут|\b(?:фио|фамилия|имя\s+гостя))\s*[:—-]?\s*[а-яёa-z][а-яёa-z-]+",
    re.IGNORECASE,
)
_SECRET = re.compile(
    r"\b(?:пароль|password|api[\s_-]?(?:key|ключ)|ключ\s+api|токен|token|cvv|cvc)\s*[:=]\s*\S{3,}"
    r"|\bauthorization\s*:\s*bearer\s+\S+",
    re.IGNORECASE,
)
_HOME_ADDRESS = re.compile(r"\b(?:мой|наш|домашний|почтовый)\s+адрес\s*[:=]\s*\S+", re.IGNORECASE)
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
    """Эвристика для явно лишних данных, не полное распознавание ПДн."""
    # Remove invisible formatting characters only for inspection; otherwise a
    # zero-width character can hide a phone or e-mail from the filter.
    inspected = "".join(ch for ch in unicodedata.normalize("NFKC", text)
                        if unicodedata.category(ch) != "Cf")
    patterns = (_EMAIL, _PHONE, _INTERNATIONAL_PHONE, _CARD, _PASSPORT, _DOCUMENT, _BIRTH_DATE, _NAME,
                _SECRET, _HOME_ADDRESS)
    return any(pattern.search(inspected) for pattern in patterns)
