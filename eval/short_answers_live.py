"""Короткие ответы на вопросы агента: сокращения, опечатки, разговорные формы («11 дн», «пинза», «2+1»).

    .venv/bin/python -m eval.short_answers_live            # только правила
    .venv/bin/python -m eval.short_answers_live --model    # модель из .env + правила

Для каждого вопроса агент сначала доводится до него (pending_question), затем получает один короткий ответ.
Проверяется состояние поездки после ответа. Отчёт: eval/short_answers_report.md.
"""

from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

from core.agent import Agent
from domains.trips.domain import TripsDomain

TODAY = date(2026, 10, 28)

# вопрос: (реплика, после которой агент его задаёт; [(ответ, ожидаемое состояние)])
CASES = {
    "when": ("хочу на море", [
        ("нояюрь", {"month": 11}), ("в декабре", {"month": 12}), ("декабрь", {"month": 12}),
        ("в янв", {"month": 1}), ("летом", {"season": "summer"}), ("с 7 по 13", {"date_from": date(2026, 11, 7)}),
        ("7-13 дек", {"date_from": date(2026, 12, 7)}), ("на новый год", {"month": 12}),
        ("в след месяце", {"month": 11}), ("сентябр", {"month": 9}),
    ]),
    "duration": ("хочу в Гоа в декабре", [
        ("11 дн", {"nights": (10, 11)}), ("11", {"nights": 11}), ("11н", {"nights": 11}), ("неделю", {"nights": 7}),
        ("нед", {"nights": 7}), ("на 2 нед", {"nights": 14}), ("полторы недели", {"nights": (10, 11)}),
        ("10 суток", {"nights": 10}), ("дней 10", {"nights": (9, 10)}), ("около недели", {"nights": 7}),
        ("дней на десять", {"nights": (9, 10)}), ("две недельки", {"nights": 14}), ("5 ночей", {"nights": 5}),
    ]),
    "origin": ("хочу в Гоа с 5 по 15 декабря", [
        ("пенза", {"origin": "Пенза"}), ("из пинзы", {"origin": "Пенза"}), ("мск", {"origin": "Москва"}),
        ("спб", {"origin": "Санкт-Петербург"}), ("питер", {"origin": "Санкт-Петербург"}),
        ("я из екб", {"origin": "Екатеринбург"}), ("краснодар", {"origin": "Краснодар"}),
        ("из Ростова", {"origin": "Ростов-на-Дону"}), ("Нижний", {"origin": "Нижний Новгород"}),
        ("тюмень", {"origin": "Тюмень"}), ("с владика", {"origin": "Владивосток"}),
    ]),
    "people": ("хочу в Гоа из Москвы с 5 по 15 декабря", [
        ("2", {"adults": 2}), ("2 взр", {"adults": 2}), ("двое взрослых", {"adults": 2}), ("я и жена", {"adults": 2}),
        ("2+1", {"adults": 2, "children": 1}), ("я один", {"adults": 1}), ("нас трое взрослых", {"adults": 3}),
        ("4 чел", {"adults": 4}), ("один взрослый", {"adults": 1}), ("я с мужем и дочкой 5 лет", {"adults": 2, "children": 1}),
    ]),
}


def _ok(state, expected: dict) -> list[str]:
    problems = []
    for field, want in expected.items():
        have = getattr(state, field)
        if field == "nights" and have is None and state.trip_days_min:
            have = state.trip_days_min - 1  # «11 дней» хранится как дни; ночей на одну меньше
        good = have in want if isinstance(want, tuple) else have == want
        if not good:
            problems.append(f"{field}: ждали {want}, получили {have}")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="store_true")
    args = parser.parse_args()
    llm = None
    if args.model:
        from core.config import get_settings
        from core.llm import build_llm
        llm = build_llm(get_settings())
        if llm is None:
            raise SystemExit("Модель не настроена в .env")
    agent = Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY, nlg=False)
    rows, passed, total = [], 0, 0
    for question, (opening, answers) in CASES.items():
        for answer, expected in answers:
            session = agent.new_session()
            agent.handle(session, opening)
            asked = session.state.pending_question
            started = time.perf_counter()
            step = agent.handle(session, answer)
            problems = ([] if asked == question else [f"агент спросил «{asked}», а не «{question}»"])
            problems += _ok(session.state, expected)
            total += 1
            passed += not problems
            mark = "ok" if not problems else "FAIL"
            print(f"[{mark:4}] {question:8} «{answer}» {'; '.join(problems)}  ({time.perf_counter() - started:.1f} с)")
            if problems:
                rows.append(f"- {question}: «{answer}» — {'; '.join(problems)}. Ответ: "
                            + step.reply.replace("\n", " ")[:160])
    mode = "модель + правила" if llm else "правила"
    report = [f"# Короткие ответы на вопросы агента ({mode})", "", f"Прошло {passed} из {total}.", ""] + rows
    Path(__file__).with_name("short_answers_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"\n{mode}: {passed}/{total}")


if __name__ == "__main__":
    main()
