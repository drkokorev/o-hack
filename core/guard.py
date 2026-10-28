"""Очистка пользовательского ввода и простая эвристика против промпт-инъекций."""

import re
import unicodedata

from .privacy import PlacePredicate, Vault, mask_names

MAX_INPUT_CHARS = 1000

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SPACES = re.compile(r"[ \t]+")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[a-z0-9.-]+\.[a-z]{2,}(?!\w)", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+7|8)[\s().-]*(?:\d[\s().-]*){10}(?!\d)")
_INTERNATIONAL_PHONE = re.compile(r"(?<!\d)\+\d(?:[\s().-]*\d){8,14}(?!\d)")
_LOCAL_PHONE = re.compile(
    r"\b(?:тел(?:ефон)?\.?|мобильный(?:\s+номер)?|номер(?:\s+телефона|\s+связи)?|"
    r"позвоните|контакт|связь|whatsapp|ватсапп?|вацап)\s*[:#№-]?\s*"
    r"9(?:[\s().-]*\d){9}(?!\d)", re.IGNORECASE
)
_SPOKEN_PHONE = re.compile(
    r"\b(?:(?:мой|наш)\s+)?(?:телефон|номер\s+телефона|номер\s+связи|номер\s+для\s+связи)\s*[:=]?\s*"
    r"(?:(?:\d{1,3}|ноль|один|одна|два|две|три|четыре|пять|шесть|семь|восемь|девять|"
    r"десять|одиннадцать|двенадцать|тринадцать|четырнадцать|пятнадцать|"
    r"шестнадцать|семнадцать|восемнадцать|девятнадцать|двадцать|тридцать|"
    r"сорок|пятьдесят|шестьдесят|семьдесят|восемьдесят|девяносто|сто|"
    r"двести|триста|четыреста|пятьсот|шестьсот|семьсот|восемьсот|девятьсот)"
    r"(?:[\s-]+|(?=[,.;!?]|$))){4,}", re.IGNORECASE
)
_SPOKEN_EMAIL = re.compile(
    r"\b(?:(?:моя|наш(?:а)?)\s+)?(?:почта|email|e-mail)\s*[:=]?\s*"
    r"[\w.+-]+\s*(?:собака|at|\(собака\)|\(at\)|\[at\]|\{at\})\s*[\w-]+"
    r"(?:(?:\s+(?:точка|dot)\s+[\w-]+)|(?:\.[\w-]+))+",
    re.IGNORECASE,
)
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)")
_PASSPORT = re.compile(
    r"(?:загран)?паспорт\w*\s*[:#№-]?\s*(?:(?:№|номер|серия)\s*[:#№-]?\s*)?"
    r"\d(?:[\s-]?\d){1,3}\s*(?:(?:номер|№)\s*[:#№-]?\s*)?\d(?:[\s-]?\d){5,7}(?!\d)",
    re.IGNORECASE,
)
_PASSPORT_ALT = re.compile(
    r"\bсерия\s+паспорта\s*[:№#=]?\s*\d{2}[ -]?\d{2}"
    r"\s*[,;]?\s*(?:и\s+)?номер\s*[:№#=]?\s*\d{6}(?!\d)", re.IGNORECASE
)
_PASSPORT_FOREIGN = re.compile(
    r"\b(?:загран)?паспорт\w*\s*[:#№-]?\s*[a-zа-яё]{1,2}\s*\d{6,9}\b", re.IGNORECASE
)
_DOCUMENT = re.compile(
    r"\b(?:снилс|инн)\s*[:#№-]?\s*\d(?:[\s-]?\d){9,11}(?!\d)", re.IGNORECASE
)
_BIRTH_DATE = re.compile(
    r"\b(?:дата\s+рождения|день\s+рождения|родил(?:ся|ась))\s*[:#]?\s*"
    r"(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}\s+(?:января|февраля|марта|апреля|мая|"
    r"июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4}(?:\s+года)?|"
    r"в\s+\d{4}\s+году|в\s+(?:январе|феврале|марте|апреле|мае|июне|июле|августе|"
    r"сентябре|октябре|ноябре|декабре)\s+\d{4}\s+года)\b",
    re.IGNORECASE,
)
_BIRTH_YEAR = re.compile(r"\b(?:я\s+)?\d{4}\s+года\s+рождения\b|"
                         r"\bя\s+\d{4}-го\s+года\b", re.IGNORECASE)
_NAME = re.compile(
    r"(?:\bменя\s+зовут|\b(?:фио|фамилия|имя\s+гостя|"
    r"имя(?!\s+(?:отеля|гостиницы|города|страны|рейса))))\s*[:—-]?\s*"
    r"[а-яёa-z][а-яёa-z-]+(?:\s+(?!(?:хочу|планирую|едем|еду|лечу|"
    r"поедем|нужно|нужен|нужна|нужны|бюджет|телефон|адрес|паспорт|на|в|из)\b)"
    r"[а-яёa-z][а-яёa-z-]+){0,2}",
    re.IGNORECASE,
)
_INTRODUCED_NAME = re.compile(r"\b(?i:я)\s+(?-i:[А-ЯЁ][а-яё-]{1,40})(?:\s+(?-i:[А-ЯЁ][а-яё-]{1,40})){0,2}")
_LATIN_NAME = re.compile(
    r"\b(?i:my name is|traveler|traveller|guest)\s+(?-i:[A-Z][a-z-]{1,40})"
    r"(?:\s+(?-i:[A-Z][a-z-]{1,40})){0,2}"
)
_SECRET = re.compile(
    r"\b(?:пароль|password|логин|username|api[\s_-]?(?:key|ключ)|ключ\s+api|токен|token|cvv|cvc|пин|pin)\s*[:=]\s*\S{3,}"
    r"|\bauthorization\s*:\s*bearer\s+\S+",
    re.IGNORECASE,
)
_ONE_TIME_CODE = re.compile(
    r"\b(?:код\s+(?:подтверждения|из\s+sms|из\s+смс)|одноразовый\s+код|sms\s+code)"
    r"\s*[:=]?\s*\d{4,8}\b", re.IGNORECASE
)
_BARE_LOGIN = re.compile(r"\b(?:мой\s+)?(?:логин|username)\s+[\w.-]{3,}\b", re.IGNORECASE)
_STREET_ADDRESS = re.compile(
    r"\b(?:улица|ул\.?|проспект|пр-т|пр\.|переулок|пер\.?|бульвар|шоссе)\s+"
    r"[а-яёa-z0-9-]+(?:\s+(?!дом\b|д\b|кв\b)[а-яёa-z0-9-]+){0,2}"
    r"\s*,?\s*(?:(?:дом|д\.?)\s*)?\d{1,4}[а-яё]?"
    r"(?:\s*,?\s*(?:квартира|кв\.?)\s*\d{1,4})?",
    re.IGNORECASE,
)
_HOME_ADDRESS = re.compile(
    r"\b(?:(?:мой|наш|домашний|почтовый)\s+адрес|адрес\s+проживания|"
    r"жив(?:у|ем|ём)\s+по\s+адресу)\s*[:=]?\s*[^;.!?\n]{1,100}"
    r"?(?=,\s*(?:хочу|планирую|подберите|ищу|еду|едем|поездка)\b|[;.!?\n]|$)",
    re.IGNORECASE,
)
_ADDRESS_NEAR = re.compile(
    r"\bжив(?:у|ем|ём)\s+(?:возле|около|рядом|у)\s+[^,;.!?\n]{1,80}?"
    r"\b(?:дом(?:е|а)?|д\.?)\s*\d{1,4}[а-яё]?", re.IGNORECASE
)
_HOME_ROAD = re.compile(
    r"\bжив(?:у|ем|ём)\s+на\s+[^,;.!?\n]{1,60}?\b(?:проспекте|улице|бульваре|шоссе)"
    r"\s*,?\s*(?:дом(?:е|а)?|д\.?)\s*\d{1,4}[а-яё]?", re.IGNORECASE
)
_HOME_IN_HOUSE = re.compile(
    r"\b(?:я\s+)?жив(?:у|ем|ём)\s+в\s+дом(?:е|а)?\s+[^,;.!?\n]{1,80}?"
    r"(?=,|[;.!?\n]|\s+(?:хочу|ищу|еду|едем|планирую)\b|$)", re.IGNORECASE
)
_SNILS = re.compile(r"(?<!\d)\d{3}-\d{3}-\d{3}\s+\d{2}(?!\d)")
_CUSTOMER_ID = re.compile(
    r"\b(?:номер|id|идентификатор)\s+(?:клиента|пользователя|заказа)\s*[:№#=]?\s*\d{6,}\b",
    re.IGNORECASE,
)
_BANK_ACCOUNT = re.compile(
    r"\b(?:расч[её]тный\s+сч[её]т|сч[её]т|р/с)\s*[:№#=]?\s*\d{20}\b", re.IGNORECASE
)
_SOCIAL_HANDLE = re.compile(
    r"\b(?:телеграм|telegram|tg|ник|username|instagram|инстаграм)\s*[:=]?\s*@[\w.]{3,}\b", re.IGNORECASE
)
_BARE_HANDLE = re.compile(r"(?<![\w.])@[a-zа-яё_][\w.]{2,}\b", re.IGNORECASE)
_BOOKING_ID = re.compile(
    r"\b(?:номер\s+(?:брони|заказа)|код\s+(?:бронирования|от\s+брони)|booking\s+reference)\s*[:№#=]?\s*"
    r"(?=[a-z0-9-]{4,}\b)(?=[a-z0-9-]*\d)[a-z0-9-]+\b", re.IGNORECASE
)
_HEALTH_INFO = re.compile(
    r"\b(?:у\s+меня|у\s+реб[её]нка|у\s+сына|у\s+дочери|у\s+мамы|у\s+отца|у\s+жены|у\s+мужа|"
    r"у\s+моего\s+друга|у\s+моей\s+подруги)\s+"
    r"(?:диагноз\s*[:=]?\s*)?(?:диабет|астма|гипертония|целиакия|эпилепсия|онкология|беременность|"
    r"вич|психиатрическ\w*\s+диагноз)\b", re.IGNORECASE
)
_MEDICATION = re.compile(r"\b(?:я\s+)?принимаю\s+(?:инсулин|лекарств\w*|препарат\w*)\b", re.IGNORECASE)
_HEALTH_DIAGNOSIS = re.compile(
    r"\b(?:у\s+меня|у\s+реб[её]нка|у\s+сына|у\s+дочери|у\s+мамы|у\s+отца|у\s+жены|у\s+мужа)\s+"
    r"диагноз\s*[:=]?\s*[а-яёa-z-]{3,}(?:\s+(?!(?:хочу|планирую|еду|едем|нужно|нужен|нужна)\b)"
    r"[а-яёa-z-]{3,}){0,2}", re.IGNORECASE
)
_FOOD_ALLERGY = re.compile(
    r"\b(?:у\s+меня|у\s+реб[её]нка|у\s+сына|у\s+дочери)\s+"
    r"(?:(?:сильная|тяж[её]лая|пищевая)\s+)?аллергия\s+на\s+"
    r"(?P<food>орехи|арахис|молоко|лактозу|глютен|морепродукты|рыбу|яйца)\b", re.IGNORECASE
)
_FOOD_INTOLERANCE = re.compile(
    r"\b(?:у\s+меня|у\s+реб[её]нка|у\s+сына|у\s+дочери)\s+непереносимость\s+"
    r"(?P<food>глютена|лактозы|молока|арахиса|орехов)\b", re.IGNORECASE
)
_FOODS = {food: food for food in ("орехи", "арахис", "молоко", "лактозу", "глютен", "морепродукты", "рыбу", "яйца")}
_INTOLERANCE_FOODS = {"глютена": "глютен", "лактозы": "лактозу", "молока": "молоко", "арахиса": "арахис", "орехов": "орехи"}
_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
                   r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b")
_SENSITIVE_PATTERNS = (
    (_SPOKEN_EMAIL, "[почта]"), (_EMAIL, "[почта]"), (_PHONE, "[телефон]"),
    (_INTERNATIONAL_PHONE, "[телефон]"), (_LOCAL_PHONE, "[телефон]"), (_SPOKEN_PHONE, "[телефон]"),
    (_CARD, "[номер карты]"), (_BANK_ACCOUNT, "[счёт]"), (_PASSPORT_ALT, "[паспорт]"),
    (_PASSPORT_FOREIGN, "[паспорт]"), (_PASSPORT, "[паспорт]"), (_DOCUMENT, "[документ]"),
    (_SNILS, "[документ]"), (_BIRTH_DATE, "[дата рождения]"), (_BIRTH_YEAR, "[дата рождения]"), (_NAME, "[имя]"),
    (_INTRODUCED_NAME, "[имя]"), (_LATIN_NAME, "[имя]"), (_ONE_TIME_CODE, "[секрет]"),
    (_SECRET, "[секрет]"), (_BARE_LOGIN, "[секрет]"),
    (_HOME_ADDRESS, "[адрес]"), (_ADDRESS_NEAR, "[адрес]"), (_HOME_ROAD, "[адрес]"),
    (_HOME_IN_HOUSE, "[адрес]"), (_STREET_ADDRESS, "[адрес]"),
    (_CUSTOMER_ID, "[номер клиента]"), (_BOOKING_ID, "[номер брони]"), (_SOCIAL_HANDLE, "[контакт]"),
    (_BARE_HANDLE, "[контакт]"), (_HEALTH_DIAGNOSIS, "[сведения о здоровье]"),
    (_HEALTH_INFO, "[сведения о здоровье]"), (_MEDICATION, "[сведения о здоровье]"), (_IPV4, "[адрес сети]"),
)
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
_UNRESOLVED_HINTS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\b(?:звони(?:те)?(?:\s+мне)?|номер\s+для\s+связи|телефон|мобильный)\b"
    r"[^,;.!?\n]{0,80}\b(?:\d{3,}|ноль|один|два|три|четыре|пять|шесть|семь|восемь|девять|девятсот)\b",
    r"\b(?:зовите\s+меня|меня\s+называют)\s+[а-яёa-z-]{2,}",
    r"\b\d{4}\s*г\.?\s*р\.?\b",
    r"\b(?:загран)?паспорт\w*\s*[:#№-]?\s*[a-zа-яё]{1,3}[- ]*\d{4,}\b",
    r"\b(?:t\.me|telegram\.me|vk\.com|wa\.me|instagram\.com)/[\w.-]+",
    r"\b[\w.+-]+\s+(?:это|собака|через|at|\{at\})\s+[\w-]+\s+(?:точка|dot)\s+[\w-]+",
    r"\b(?:инсулин\w*|лекарств\w*|диагноз\w*|артрит\w*)\b",
    r"\bродил(?:ся|ась)\s+в\s+(?:тысяча|девятнадцать|двадцать)\b",
    r"\b(?:моя\s+квартира|(?:я\s+)?живу\s+(?:у|в|на))\b[^;.!?\n]{0,100}\b(?:дом\w*|дом)\b",
))
_REDACTED_MARKER = re.compile(
    r"\[(?:имя|почта|телефон|контакт|номер карты|счёт|паспорт|документ|дата рождения|"
    r"секрет|адрес|адрес сети|номер клиента|номер брони|сведения о здоровье)(?:_\d+)?\]"
)


def sanitize(text: str) -> str:
    text = _CONTROL.sub("", text)
    text = _SPACES.sub(" ", text).strip()
    return text[:MAX_INPUT_CHARS]


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION.search(text))


_NAME_INTRO = re.compile(r"(?is)^(.*?\b(?:зовут|фио|фамилия|имя\s+гостя|имя|я|my name is|traveler|traveller|guest)"
                         r"\s*[:—-]?\s*)(\S.*)$")


def _reversible(vault: Vault, label: str, value: str) -> str:
    """Для имени метка заменяет только само имя: «меня зовут [имя_1]», вступление остаётся в тексте."""
    if label == "имя" and (intro := _NAME_INTRO.match(value)):
        return intro.group(1) + vault.token(label, intro.group(2))
    return vault.token(label, value)


def mask_basic_data(text: str, vault: Vault | None = None) -> tuple[str, bool]:
    """Маскирует форматные данные, не отправляя текст во внешнюю службу."""
    inspected = "".join(ch for ch in unicodedata.normalize("NFKC", text)
                        if unicodedata.category(ch) != "Cf")
    # Retain the practical food requirement for the travel request without
    # forwarding the explicitly stated health condition.
    inspected, food_count = _FOOD_ALLERGY.subn(
        lambda match: "[условие питания: исключить " + _FOODS[match.group("food").casefold()] + "]", inspected)
    inspected, intolerance_count = _FOOD_INTOLERANCE.subn(
        lambda match: "[условие питания: исключить " + _INTOLERANCE_FOODS[match.group("food").casefold()] + "]", inspected)
    masked = food_count > 0 or intolerance_count > 0
    for pattern, replacement in _SENSITIVE_PATTERNS:
        if vault is None:
            inspected, count = pattern.subn(replacement, inspected)
        else:  # обратимо: «[телефон_1]», значение остаётся только в хранилище сессии
            label = replacement.strip("[]")
            inspected, count = pattern.subn(lambda m, label=label: _reversible(vault, label, m.group(0)), inspected)
        masked = masked or count > 0
    return _SPACES.sub(" ", _CONTROL.sub("", inspected)).strip(), masked


def mask_sensitive_data(text: str, preserve_place: PlacePredicate | None = None,
                        vault: Vault | None = None) -> tuple[str, bool]:
    """Локально скрывает обнаруженные данные, но не гарантирует распознавание всех ПДн.

    Проверяем и обрабатываем одну и ту же нормализованную строку, иначе невидимые
    символы могли бы обойти замену. Исходные значения не сохраняем для восстановления.
    """
    inspected, masked = mask_basic_data(text, vault)
    inspected, names_masked = mask_names(inspected, preserve_place, vault)
    return inspected, masked or names_masked


def contains_unresolved_sensitive_data(text: str) -> bool:
    """Признаки, при которых оставшийся текст безопаснее не отправлять модели."""
    # Do not discard arbitrary bracketed user content: it could itself contain
    # a contact or another unresolved sensitive value.
    without_placeholders = _REDACTED_MARKER.sub(" ", text)
    return any(pattern.search(without_placeholders) for pattern in _UNRESOLVED_HINTS)
