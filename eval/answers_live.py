"""Живой прогон ответов через LLM: доля ответов модели, причины отказа проверки, задержка и утечки личных данных.

    .venv/bin/python -m eval.answers_live            # нужен ключ модели в .env (GigaChat или OpenAI-совместимая)

Каждый запрос к модели перехватывается: если в нём встретилось исходное личное значение из диалога
(имя, телефон, почта, номер карты), это утечка — скрипт её считает и печатает. Отчёт: eval/answers_report.md.
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import median

from core.agent import Agent
from core.config import get_settings
from core.llm import build_llm
from domains.trips.domain import TripsDomain

DIALOGUES = [
    ("Семья с ребёнком", ["Меня зовут Анна, хочу с мужем и сыном 7 лет к тёплому морю в феврале",
                          "давай первое", "из Москвы, на 10 ночей", "беру первый вариант"]),
    ("Пара в Будву", ["Из Москвы в Будву с 10 по 17 июля 2027 вдвоём", "что там посмотреть?",
                      "где лучше поесть?", "беру второй"]),
    ("Стамбул на выходные", ["Стамбул на выходные в мае, нас двое, из Казани", "безопасно ли там?",
                             "как там передвигаться?"]),
    ("Контакты в тексте", ["Я Иван Петров, мой телефон +7 916 123-45-67, почта ivan.p@mail.ru. Хочу в Сочи в июне",
                           "на неделю, вдвоём, из Москвы", "а что посмотреть в Сочи?"]),
    ("Размытый запрос", ["Хочу куда-нибудь отдохнуть осенью недорого", "покажи другие направления", "давай второе"]),
    ("Токио весной", ["Токио в апреле на 10 ночей из Москвы, двое взрослых", "нужна ли виза?",
                      "что посмотреть в Токио?", "дешевле"]),
    ("Карта в тексте", ["Оплачу картой 4276 1600 1234 5678, хочу в Анталью всё включено в сентябре"]),
]
PRIVATE = ["Анна", "Иван", "Петров", "916 123-45-67", "ivan.p@mail.ru", "4276 1600 1234 5678"]


class Recorder:
    """Обёртка над моделью: запоминает всё, что ушло наружу, и время ответа."""

    def __init__(self, inner):
        self.inner, self.sent, self.latency = inner, [], []
        self.breaker = getattr(inner, "breaker", None)

    def complete(self, messages, **kwargs):
        self.sent.append(" ".join(m["content"] for m in messages))
        started = time.perf_counter()
        try:
            return self.inner.complete(messages, **kwargs)
        finally:
            self.latency.append(time.perf_counter() - started)


def main() -> None:
    settings = get_settings()
    llm = build_llm(settings)
    if llm is None:
        raise SystemExit("Модель не настроена: впишите ключ в .env (GIGACHAT_AUTH_KEY или LLM_API_KEY)")
    recorder = Recorder(llm)
    agent = Agent(TripsDomain(today=date.today), recorder, nlg=True)
    by, problems, turn_times, rows = Counter(), Counter(), [], []
    for title, turns in DIALOGUES:
        session = agent.new_session()
        rows.append(f"\n### {title}\n")
        for text in turns:
            started = time.perf_counter()
            step = agent.handle(session, text)
            turn_times.append(time.perf_counter() - started)
            by[session.last_answer_by or "template"] += 1
            for note in session.last_notes:
                if note.startswith("ответ:"):
                    for item in note.removeprefix("ответ:").split(";"):
                        problems[item.strip().split(":")[0]] += 1
            rows.append(f"**Пользователь:** {text}  \n**Агент ({session.last_answer_by}):** "
                        + step.reply.replace("\n", "  \n") + "\n")
            print(f"[{session.last_answer_by:8}] {turn_times[-1]:4.1f} с  {text[:60]}")
    leaks = sorted({value for value in PRIVATE for sent in recorder.sent if value in sent})
    total = sum(by.values())
    turn_times.sort()
    summary = [
        "# Живой прогон ответов через LLM",
        f"\nМодель: {settings.llm_provider} / {settings.llm_model}. Дата: {date.today():%d.%m.%Y}.",
        f"\n- Реплик: {total}; ответ написала модель (прошёл проверку): {by['llm']} "
        f"({100 * by['llm'] // max(total, 1)}%), шаблон: {by['template']}",
        f"- Причины, по которым проверка не пропустила ответ модели: "
        + (", ".join(f"{k} — {v}" for k, v in problems.most_common()) or "нет"),
        f"- Время ответа на реплику: медиана {median(turn_times):.1f} с, "
        f"90-й перцентиль {turn_times[int(len(turn_times) * 0.9) - 1]:.1f} с; запросов к модели: {len(recorder.sent)}",
        f"- Утечки личных данных в запросы к модели: {', '.join(leaks) if leaks else 'нет'}",
        "\n## Диалоги",
    ]
    Path(__file__).with_name("answers_report.md").write_text("\n".join(summary + rows) + "\n", encoding="utf-8")
    print("\n".join(summary[2:6]))
    if leaks:
        raise SystemExit("Найдены утечки личных данных в запросах к модели")


if __name__ == "__main__":
    main()
