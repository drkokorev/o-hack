"""Массовый замер понимания: сотни разговорных реплик с известным правильным ответом.

    .venv/bin/python -m eval.stress_live --generate 150   # модель пишет реплики → eval/stress_cases.json
    .venv/bin/python -m eval.stress_live                  # только правила
    .venv/bin/python -m eval.stress_live --model          # модель из .env + правила

Параметры поездки задаёт код (направление, иногда через достопримечательность; город отправления; месяц или даты;
ночи; состав; иногда бюджет), а модель только пересказывает их одной репликой в заданном стиле: с опечатками,
сокращениями, как голосовое без знаков, очень коротко. Правильный ответ известен заранее, поэтому видно точность
по каждому полю и типовые ошибки. Реплики сохраняются, чтобы сравнивать версии на одних и тех же данных.
Отчёт: eval/stress_report.md.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from core.agent import Agent
from core.ru import MONTHS_GEN
from domains.trips.domain import TripsDomain
from domains.trips.geo import DESTINATIONS, ORIGINS

TODAY = date(2026, 10, 28)
HERE = Path(__file__).parent
CASES = HERE / "stress_cases.json"
STYLES = ["с 2–3 опечатками, как пишут в спешке с телефона", "с сокращениями (мск, спб, нед, дн, взр, к вместо тысяч)",
          "как расшифровка голосового: без знаков препинания и заглавных", "очень коротко, телеграфным стилем",
          "разговорно, с лишними словами и эмоциями", "вежливо и подробно"]
LANDMARKS = {"paris": "Эйфелева башня", "rome": "Колизей", "newyork": "Статуя Свободы", "dubai": "Бурдж-Халифа",
             "moscow": "Красная площадь", "spb": "Эрмитаж", "istanbul": "Айя-София", "barcelona": "Саграда Фамилия",
             "kazan": "Казанский кремль"}
MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
              "ноябрь", "декабрь"]

GENERATE_PROMPT = """Ты пишешь одну реплику человека в чат сервиса поездок. Стиль: {style}.
Реплика должна содержать ровно эти сведения и ничего лишнего:
{facts}
Не добавляй других городов, дат и чисел. Ответь только текстом реплики."""


def _facts(rng: random.Random) -> tuple[dict, list[str]]:
    expected, facts = {}, []
    dest = rng.choice(DESTINATIONS)
    if dest.id in LANDMARKS and rng.random() < 0.5:
        facts.append(f"хочет к достопримечательности: {LANDMARKS[dest.id]} (город не называет)")
    else:
        facts.append(f"куда: {dest.name}")
    expected["dest_id"] = dest.id
    origin = rng.choice(ORIGINS[:60])
    if origin.name != dest.name:
        facts.append(f"откуда: {origin.name}")
        expected["origin"] = origin.name
    month = rng.randint(1, 12)
    year = TODAY.year + (month <= TODAY.month)
    if rng.random() < 0.5:
        facts.append(f"когда: месяц {MONTHS_NOM[month - 1]}, точные даты не знает")
        expected["month"] = month
        nights = rng.choice([3, 5, 7, 10, 14])
        facts.append(rng.choice([f"на {nights} ночей", f"на {nights + 1} дней"]) if nights != 7 else
                     "на неделю")
        expected["nights"] = nights
    else:
        day = rng.randint(1, 20)
        nights = rng.choice([3, 5, 7, 10])
        facts.append(f"даты: с {day} по {day + nights} {MONTHS_GEN[month - 1]}")
        expected["date_from"] = date(year, month, day).isoformat()
        expected["nights"] = nights
    adults, children = rng.choice([(1, 0), (2, 0), (2, 0), (2, 1), (2, 2), (3, 0), (4, 0)])
    who = {(1, 0): "едет один взрослый", (2, 0): "двое взрослых (например, с женой или мужем)",
           (3, 0): "трое взрослых", (4, 0): "четверо взрослых друзей"}.get((adults, children))
    facts.append(who or f"{adults} взрослых и {children} {'ребёнок' if children == 1 else 'детей'}"
                        f" ({', '.join(str(rng.randint(3, 14)) for _ in range(children))} лет)")
    expected["adults"], expected["children"] = adults, children
    if rng.random() < 0.3:
        budget = rng.choice([80, 150, 200, 300, 500]) * 1000
        facts.append(f"бюджет на всю поездку до {budget // 1000} тысяч рублей")
        expected["budget_total"] = budget
    return expected, facts


def generate(count: int) -> None:
    from core.config import get_settings
    from core.llm import build_llm, strip_think

    llm = build_llm(get_settings())
    if llm is None:
        raise SystemExit("Для генерации нужна модель в .env")
    rng = random.Random(20261028)
    cases = []
    for i in range(count):
        expected, facts = _facts(rng)
        style = rng.choice(STYLES)
        prompt = GENERATE_PROMPT.format(style=style, facts="\n".join(f"- {f}" for f in facts))
        try:
            text = strip_think(llm.complete([{"role": "user", "content": prompt}])).strip().strip("«»\"")
        except Exception as err:
            print("сбой генерации:", type(err).__name__)
            continue
        cases.append({"text": text, "style": style, "facts": facts, "expected": expected})
        print(f"{i + 1}/{count}  {text[:90]}")
    CASES.write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _actual(state, field):
    if field == "date_from":
        return state.date_from.isoformat() if state.date_from else None
    if field == "nights":
        if state.nights:
            return state.nights
        if state.date_from and state.date_to:
            return (state.date_to - state.date_from).days
        return state.trip_days_min - 1 if state.trip_days_min else None
    if field == "children":
        return state.children or 0 if state.adults is not None or state.children is not None else None
    return getattr(state, field)


def run(use_model: bool) -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    llm = None
    if use_model:
        from core.config import get_settings
        from core.llm import build_llm
        llm = build_llm(get_settings())
    agent = Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY, nlg=False)
    right, total, misses = Counter(), Counter(), defaultdict(list)
    perfect = 0
    started = time.perf_counter()
    for i, case in enumerate(cases, 1):
        session = agent.new_session()
        agent.handle(session, case["text"])
        ok_all = True
        for field, want in case["expected"].items():
            have = _actual(session.state, field)
            total[field] += 1
            if have == want:
                right[field] += 1
            else:
                ok_all = False
                misses[field].append(f"«{case['text'][:110]}» → {have!r}, ждали {want!r}")
        perfect += ok_all
        if i % 25 == 0:
            print(f"{i}/{len(cases)}  {time.perf_counter() - started:.0f} с")
    mode = "модель + правила" if llm else "правила"
    lines = [f"# Массовый замер понимания ({mode})", "", f"{len(cases)} реплик; поняты полностью: {perfect} "
             f"({100 * perfect // max(len(cases), 1)}%).", "", "| Поле | Верно |", "| :--- | ---: |"]
    lines += [f"| {f} | {right[f]}/{total[f]} ({100 * right[f] // total[f]}%) |" for f in total]
    for field, items in misses.items():
        lines += ["", f"## {field}: ошибки", *[f"- {m}" for m in items[:25]]]
    suffix = "model" if llm else "rules"
    (HERE / f"stress_report_{suffix}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:4 + len(total) + 2]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", type=int)
    parser.add_argument("--model", action="store_true")
    args = parser.parse_args()
    if args.generate:
        generate(args.generate)
    else:
        run(args.model)


if __name__ == "__main__":
    main()
