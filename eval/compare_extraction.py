"""Сравнивает только извлечение модели на фиксированных фразах, чередуя порядок вызовов.

Внешние вызовы делаются только при явном перечислении моделей:
    python -m eval.compare_extraction --models GigaChat-2-Pro GigaChat-2-Max GigaChat-3-Ultra
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from datetime import date
from pathlib import Path
from statistics import median

from core.config import get_settings
from core.llm import build_llm, extract
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID
from domains.trips.rules import find_destination
from domains.trips.state import TripState, TripUpdate
from domains.trips.textparse import norm


TODAY = date(2026, 10, 27)
CASES = Path(__file__).with_name("extraction_cases.json")


def actual_value(field: str, value):
    if isinstance(value, date):
        return value.isoformat()
    if field == "destination" and isinstance(value, str):
        return value if value in BY_ID else find_destination(norm(value)) or value
    return value


def judge(case: dict, update: TripUpdate) -> list[str]:
    failures = []
    for field, expected in case.get("expect", {}).items():
        actual = actual_value(field, getattr(update, field, None))
        if actual != expected:
            failures.append(f"{field}: ожидалось {expected!r}, получено {actual!r}")
    for field, unwanted in case.get("forbid", {}).items():
        if getattr(update, field, None) == unwanted:
            failures.append(f"{field}: запрещено {unwanted!r}")
    for field in case.get("empty", []):
        if getattr(update, field, None) is not None:
            failures.append(f"{field}: модель добавила неуказанное значение")
    for field, value in case.get("contains", {}).items():
        if value not in (getattr(update, field, None) or []):
            failures.append(f"{field}: не найдено {value!r}")
    for field, value in case.get("not_contains", {}).items():
        if value in (getattr(update, field, None) or []):
            failures.append(f"{field}: добавлено исключённое {value!r}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--output", default="../extraction_comparison.json")
    parser.add_argument("--limit", type=int, default=None, help="Ограничить число сценариев для предварительной проверки")
    args = parser.parse_args()
    settings = get_settings()
    if not settings.llm_enabled:
        raise SystemExit("Локальные настройки не содержат доступ к модели")
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.limit is not None:
        cases = cases[:args.limit]
    clients = {name: build_llm(replace(settings, llm_model=name)) for name in args.models}
    outcomes = {name: [] for name in args.models}
    domain = TripsDomain(today=lambda: TODAY)
    for i, case in enumerate(cases):
        order = args.models[i % len(args.models):] + args.models[:i % len(args.models)]
        messages = domain.extraction_messages(TripState(), [], case["text"], TODAY)
        for name in order:
            started = time.perf_counter()
            update = extract(clients[name], TripUpdate, messages)
            elapsed = round(time.perf_counter() - started, 3)
            failures = judge(case, update)
            outcomes[name].append({"id": case["id"], "pass": not failures, "failures": failures,
                                   "seconds": elapsed, "empty": not bool(update.model_dump(exclude_none=True))})
            print(f"{name}: {case['id']}: {'PASS' if not failures else 'FAIL'} ({elapsed:.2f} с)", flush=True)
    results = []
    for name in args.models:
        items = outcomes[name]
        times = sorted(item["seconds"] for item in items)
        results.append({"model": name, "passed": sum(item["pass"] for item in items), "total": len(items),
                        "median_seconds": round(median(times), 3), "max_seconds": max(times),
                        "empty_responses": sum(item["empty"] for item in items), "cases": items})
        client = clients[name]
        if hasattr(client, "_http"):
            client._http.close()
    Path(args.output).write_text(json.dumps({"fixed_today": TODAY.isoformat(), "results": results},
                                            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for result in results:
        print(f"{result['model']}: {result['passed']}/{result['total']}, "
              f"медиана {result['median_seconds']} с, максимум {result['max_seconds']} с")
    return 0 if all(result["passed"] == result["total"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
