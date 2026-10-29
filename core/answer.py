"""Ответ пользователю пишет LLM — по фактам шага и найденным фрагментам (RAG), на замаскированных данных.

Цепочка (по образцу Einstein Trust Layer, Presidio, LLM Guard):
    маскирование ([имя_1]) → контекст: факты шага + фрагменты базы знаний → LLM пишет ответ
    → проверка ответа по контексту → метки снова в имена → пользователю.

Факты (цены, рейсы, отели, даты) считает код домена — модель их только пересказывает. Проверка не пропускает
ответ с числом, которого нет в контексте, со ссылкой, контактом, чужой меткой или обещанием брони; тогда
пользователь видит черновик-шаблон, он всегда верен. Модель не видит исходных личных данных и таблицы меток.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .llm import LLM, Message, strip_think

log = logging.getLogger(__name__)

ANSWER_SYSTEM = """Ты — консультант сервиса поездок «О!дин запрос». Напиши ответ пользователю на русском: тепло, живо и по делу.

Правила:
1. Пиши только то, что есть в блоках «Факты» и «Источники». Не добавляй цены, даты, время, сроки, названия отелей, рейсов, мест и условий, которых там нет.
2. Числа, даты, время, суммы и названия переписывай точно как в фактах.
3. Если в фактах пронумерованы варианты — сохрани все варианты и их номера.
4. Метки вроде [имя_1] и [телефон_1] — скрытые личные данные. Оставь их как есть, не угадывай и не запрашивай их.
5. Если в фактах есть вопрос к пользователю или предложение следующего шага — закончи ответ им.
6. Сведения из источников подавай как сведения путеводителя, не как свои проверенные данные.
7. Не обещай бронь, оплату или звонок, если этого нет в фактах. Не давай ссылок и контактов.
8. Если ответа нет ни в фактах, ни в источниках — так и скажи и предложи следующий шаг.
9. Условия поездки (даты, город, состав) считай принятыми, только если они есть в фактах. Если пользователь назвал что-то, чего в фактах нет, не подтверждай это.
10. О себе пиши в мужском роде, как в фактах («учёл», «подобрал»), без восторгов и комплиментов выбору пользователя.
11. Если в фактах сказано, что данные демонстрационные или смоделированные, сохрани эту пометку: не выдавай их за реальные рейсы, цены и наличие.
12. Пиши обычным текстом без разметки: без звёздочек, решёток и таблиц. Списки — строками «1. …».
Объём — не длиннее фактов плюс пара фраз. Без приветствий и подписи."""

_NUMBER = re.compile(r"\d+(?:[   ]\d{3})*(?:[.,:]\d+)?")
_LINK = re.compile(r"https?://|www\.|\b[\w-]+\.(?:ru|com|org|net|рф)\b", re.IGNORECASE)
_CONTACT = re.compile(r"@|\+\d|\b\d{3}[ -]\d{2}[ -]\d{2}\b")
_GUSH = re.compile(r"^\W*(?:замечательн|отличн\w* выбор|прекрасн|великолепн|здорово|чудесн|рад[аы]?,? что)", re.IGNORECASE)
_TOKEN = re.compile(r"\[[а-яё ]+(?:_\d+)?\]")
_PRICE = re.compile(r"\d+(?:[ \u00a0\u202f]\d{3})*\s?₽")
_OPTION = re.compile(r"(?m)^\s*(\d)[.)]\s")
_PROMISE = re.compile(r"забронирова|оплачен|оплатил|подтвердил[аи]? бронь|перезвон|свяжемся|отправил[аи]? (?:письмо|смс)",
                      re.IGNORECASE)


@dataclass
class Composed:
    text: str
    by: str                      # llm — текст модели прошёл проверку; template — показан черновик
    problems: list[str] = field(default_factory=list)


def _numbers(text: str) -> set[str]:
    out = set()
    for raw in _NUMBER.findall(text):
        value = re.sub(r"[   ]", "", raw).replace(",", ".")
        out.add(value)
        if re.fullmatch(r"\d+\.0+", value):
            out.add(value.split(".")[0])
    return out


def context_text(facts: str, sources: list[dict]) -> str:
    return facts + "\n" + "\n".join(s.get("text", "") for s in sources)


def verify(answer: str, context: str, user_text: str, known_tokens: set[str], facts: str = "") -> list[str]:
    """Что в ответе модели не подтверждается контекстом или потеряно из фактов. Пустой список — можно показывать."""
    problems = []
    # Полнота: цены, номера вариантов и вопрос к пользователю из фактов должны дойти до пользователя
    lost = [p for p in dict.fromkeys(_PRICE.findall(facts))
            if re.sub(r"\D", "", p) not in {re.sub(r"\D", "", a) for a in _PRICE.findall(answer)}]
    if lost:
        problems.append("потеряны цены: " + ", ".join(lost[:3]))
    options = set(_OPTION.findall(facts))
    if len(options) > 1 and not options <= set(re.findall(r"(?<!\d)(\d)[.)]\s", answer)):
        problems.append("потеряны варианты")
    if facts.rstrip().endswith("?") and "?" not in answer:
        problems.append("потерян вопрос к пользователю")
    if (re.search(r"демонстрац|смоделир", facts, re.IGNORECASE)
            and not re.search(r"демо|смоделир|модельн|условн", answer, re.IGNORECASE)):
        problems.append("потеряна пометка, что данные демонстрационные")
    if "путеводителя могут устареть" in facts.lower() and "устар" not in answer.lower():
        problems.append("потеряна оговорка об актуальности путеводителя")
    if "по данным языковой модели" in facts and "модел" not in answer.lower():
        problems.append("потеряна пометка, что место определила модель")
    if _GUSH.search(answer):
        problems.append("восторги вместо фактов")
    source_text = (context + " " + user_text).lower()
    invented = [q for q in re.findall(r"[«\"]([^»\"]{3,40})[»\"]", answer) if q.lower()[:6] not in source_text]
    if invented:  # «фундуковую гору» — название, которого не было ни в фактах, ни в реплике
        problems.append("названия не из фактов: " + ", ".join(invented[:3]))
    allowed = _numbers(context)  # число только из реплики пользователя система могла не принять («с 7 по 13»)
    extra = sorted(n for n in _numbers(answer) if n not in allowed and not (n.isdigit() and int(n) <= 3))
    if extra:
        problems.append("числа не из фактов: " + ", ".join(extra[:5]))
    if _LINK.search(answer) and not _LINK.search(context):
        problems.append("ссылка")
    if _CONTACT.search(answer) and not _CONTACT.search(context):
        problems.append("контакт")
    unknown = [t for t in _TOKEN.findall(answer) if t not in known_tokens and t not in context and t not in user_text]
    if unknown:
        problems.append("неизвестные метки: " + ", ".join(unknown[:3]))
    if _PROMISE.search(answer) and not _PROMISE.search(context):
        problems.append("обещание, которого нет в фактах")
    letters = re.findall(r"[a-zа-яё]", answer.casefold())
    if letters and sum(1 for ch in letters if "а" <= ch <= "я" or ch == "ё") / len(letters) < 0.6:
        problems.append("не по-русски")
    if not answer.strip():
        problems.append("пустой ответ")
    elif len(answer) > max(900, 2 * len(context)):
        problems.append("слишком длинно")
    return problems


def plain(text: str) -> str:
    """Чат показывает обычный текст: «**Перелёты**» → «Перелёты», «### Итог» → «Итог»."""
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^(\s*)[*•]\s+", r"\1— ", text)
    return text.replace("`", "")


def messages(user_text: str, facts: str, sources: list[dict]) -> list[Message]:
    blocks = [f"Сообщение пользователя: «{user_text}»", "Факты (посчитаны системой, верны):\n" + facts.strip()]
    if sources:
        blocks.append("Источники (путеводитель):\n" + "\n".join(
            f"[{i}] {s.get('cite', '')}: {s.get('text', '')}" for i, s in enumerate(sources, 1)))
    return [{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": "\n\n".join(blocks)}]


def compose(llm: LLM | None, user_text: str, facts: str, draft: str, sources: list[dict],
            known_tokens: set[str]) -> Composed:
    """Ответ модели, если он прошёл проверку; иначе черновик. Одна повторная попытка при ошибке проверки."""
    if llm is None or not facts.strip():
        return Composed(draft, "template")
    context = context_text(facts, sources)
    problems: list[str] = []
    for attempt in range(2):
        prompt = messages(user_text, facts, sources)
        if attempt and problems:
            prompt[-1]["content"] += ("\n\nПредыдущий вариант отклонён: " + "; ".join(problems)
                                      + ". Перепиши строго по фактам.")
        try:
            answer = strip_think(llm.complete(prompt)).strip()
        except Exception as err:  # недоступна, таймаут, предохранитель — показываем черновик
            log.info("Генерация ответа недоступна (%s), показан шаблон", type(err).__name__)
            return Composed(draft, "template", [type(err).__name__])
        answer = plain(answer)
        if facts.rstrip().endswith("?") and "?" not in answer:
            # модель часто теряет финальный вопрос — дописываем его из фактов, а не отказываемся от ответа
            answer = answer.rstrip() + "\n\n" + facts.rstrip().splitlines()[-1].strip()
        problems = verify(answer, context, user_text, known_tokens, facts)
        if not problems:
            return Composed(answer, "llm")
    log.info("Ответ модели не прошёл проверку (%s), показан шаблон", "; ".join(problems))
    return Composed(draft, "template", problems)
