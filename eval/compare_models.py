"""Сравнение систем на фиксированных сценариях. По умолчанию внешние модели не вызываются.

Пример (при наличии разрешённого доступа и квоты):
    python -m eval.compare_models --models rules GigaChat-2-Pro GigaChat-2-Max GigaChat-3-Ultra
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from datetime import date
from pathlib import Path
from statistics import median

from core.agent import Agent
from core.config import get_settings
from core.llm import build_llm
from domains.trips.domain import TripsDomain


TODAY = date(2026, 10, 27)
CASES = Path(__file__).with_name("guided_cases.json")


def assess(case: dict, session, step) -> list[str]:
    failures = []
    state = session.state
    for field, expected in case.get("state", {}).items():
        actual = getattr(state, field, None)
        if isinstance(actual, date):
            actual = actual.isoformat()
        if actual != expected:
            failures.append(f"{field}: ожидалось {expected!r}, получено {actual!r}")
    if "date_year" in case and (not state.date_from or state.date_from.year != case["date_year"]):
        failures.append(f"год начала: ожидался {case['date_year']}")
    if case.get("assumed_dates") and not state.dates_assumed:
        failures.append("выбранные приложением даты не обозначены как предположение")
    if case.get("types_include") and not set(case["types_include"]).issubset(set(state.trip_types or [])):
        failures.append("не сохранены нужные типы отдыха")
    if case.get("types_exclude") and set(case["types_exclude"]).intersection(state.trip_types or []):
        failures.append("сохранён исключённый тип отдыха")
    payload = step.payload or {}
    if case.get("payload") and payload.get("kind") != case["payload"]:
        failures.append(f"экран: ожидался {case['payload']!r}, получен {payload.get('kind')!r}")
    for field, expected in case.get("trip", {}).items():
        if payload.get("trip", {}).get(field) != expected:
            failures.append(f"маршрут {field}: ожидалось {expected!r}")
    if case.get("all_legs"):
        items = payload.get("items", [])
        if not items or any(item[leg]["mode"] != case["all_legs"] for item in items for leg in ("out", "back")):
            failures.append(f"транспорт в вариантах отличается от {case['all_legs']}")
    if case.get("not_booked") and state.order:
        failures.append("заказ оформлен без явного согласия")
    if case.get("has_order") and not state.order:
        failures.append("нет имитированного заказа")
    if case.get("reply_contains") and case["reply_contains"] not in step.reply.lower():
        failures.append(f"в ответе нет ожидаемого текста: {case['reply_contains']!r}")
    return failures


def run_model(name: str, cases: list[dict]) -> dict:
    settings = get_settings()
    if name == "rules":
        llm = None
    else:
        settings = replace(settings, llm_model=name)
        if not settings.llm_enabled:
            raise RuntimeError("Для выбранной модели нет локального ключа или подключения")
        llm = build_llm(settings)
    agent = Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY)
    results, times, llm_turns, total_turns = [], [], 0, 0
    for case in cases:
        session = agent.new_session()
        try:
            for text in case["turns"]:
                start = time.perf_counter()
                step = agent.handle(session, text)
                times.append(round(time.perf_counter() - start, 3))
                total_turns += 1
                llm_turns += session.last_nlu in ("llm", "llm+rules")
            failures = assess(case, session, step)
        except Exception as exc:
            failures = [f"исключение {type(exc).__name__}"]
        results.append({"id": case["id"], "pass": not failures, "failures": failures})
        print(f"{name}: {case['id']}: {'PASS' if not failures else 'FAIL'}", flush=True)
    if llm is not None:
        llm._client.close()
    passed = sum(result["pass"] for result in results)
    ordered = sorted(times)
    return {"model": name, "passed": passed, "total": len(cases), "turns": total_turns,
            "model_turns": llm_turns, "median_seconds": round(median(times), 3) if times else None,
            "p95_seconds": ordered[min(len(ordered) - 1, int(len(ordered) * .95))] if ordered else None,
            "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["rules"])
    parser.add_argument("--output", default="../model_comparison.json")
    args = parser.parse_args()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    report = {"fixed_today": TODAY.isoformat(), "results": [run_model(name, cases) for name in args.models]}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for result in report["results"]:
        print(f"{result['model']}: {result['passed']}/{result['total']}, "
              f"модель участвовала {result['model_turns']}/{result['turns']} реплик, "
              f"медиана {result['median_seconds']} с, p95 {result['p95_seconds']} с")
    return 0 if all(result["passed"] == result["total"] for result in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
