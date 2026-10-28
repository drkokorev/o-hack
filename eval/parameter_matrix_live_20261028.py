"""Run synthetic parameter cases through the configured language model and arbiter."""
from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

from core.agent import Agent
from core.config import get_settings
from core.llm import build_llm
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID
from domains.trips.rules import find_destination
from domains.trips.textparse import norm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--pause", type=float, default=3.0)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.llm_enabled:
        raise SystemExit("Нет настроенного доступа к языковой модели")
    llm = build_llm(settings)
    today = date(2026, 10, 28)
    agent = Agent(TripsDomain(today=lambda: today), llm, today=lambda: today)
    fixture = json.loads(Path(__file__).with_name("parameter_matrix_20261028.json").read_text(encoding="utf-8"))
    chosen = fixture["new_phrases"] + [case for case in fixture["development"]
        if case["id"] in {"user", "month", "relative week", "pet", "nightly budget", "unsure"}]
    results = []
    for case in chosen:
        if args.pause:
            time.sleep(args.pause)
        session = agent.new_session()
        started = time.perf_counter()
        update, nlu = agent._understand(session, case["text"])
        values = update.model_dump(mode="json", exclude_none=True)
        compared = dict(values)
        destination = compared.get("destination")
        if destination and destination not in BY_ID:
            compared["destination"] = find_destination(norm(destination)) or destination
        errors = {field: {"expected": expected, "actual": compared.get(field)}
                  for field, expected in case["expected"].items() if compared.get(field) != expected}
        model_used = nlu in {"llm", "llm+rules"}
        results.append({"id": case["id"], "text": case["text"], "expected": case["expected"],
                        "actual": values, "differences": errors, "nlu": nlu,
                        "passed": not errors and model_used,
                        "ms": round((time.perf_counter() - started) * 1000)})
        status = 'PASS' if results[-1]['passed'] else 'FAIL'
        print(f"{len(results)}/{len(chosen)} {case['id']}: {status} ({nlu}) {errors or ''}", flush=True)
        interim = {"model": settings.llm_model, "fixed_today": today.isoformat(), "complete": False,
                   "passed": sum(item["passed"] for item in results), "total": len(chosen), "results": results}
        Path(args.output).write_text(json.dumps(interim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    passed = sum(item["passed"] for item in results)
    report = {"model": settings.llm_model, "fixed_today": today.isoformat(), "complete": True, "passed": passed,
              "total": len(results), "results": results}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
