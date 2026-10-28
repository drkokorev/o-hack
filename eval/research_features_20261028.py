"""Synthetic dialogue cases based on newly inspected requirements, no personal data."""
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

TODAY = date(2026, 10, 28)
CASES = [
    ("person_budget_plain", "Четверо из Екатеринбурга, 70 тысяч на человека, только прямой рейс", "budget"),
    ("person_budget_fillers", "Ну, эм, так, нас четверо, из Екатеринбурга, где-то 70 тысяч на каждого, только прямой рейс", "budget"),
    ("excluded_visa", "Не Египет, хочу зимой на море без визы", "excluded"),
    ("fear_flight", "К морю с собакой вдвоём, боюсь летать", "fear"),
    ("days_plain", "Хочу в Сочи на 7 дней", "days"),
    ("days_fillers", "Ну эм, я, наверное, в Сочи на семь дней хочу", "days"),
    ("typos", "Хачу на мори в дикабре с жиной недорага", "typos"),
]


def assess(kind, state, step):
    if kind == "budget":
        return state.party_size == 4 and state.budget_per_person == 70000 and state.budget_total == 280000 and state.direct_only is True
    if kind == "excluded":
        return ("Египет" in (state.excluded_countries or []) and state.visa_free_requested is True
                and state.dest_id is None and "не проверял" in step.reply and "не фильтровал" in step.reply
                and all(item.get("country") != "Египет" for item in step.payload.get("items", [])))
    if kind == "fear":
        return state.pets is True and state.party_size == 2 and state.flight_concern is True and state.transport is None
    if kind == "days":
        return (state.trip_days_min == state.trip_days_max == 7 and state.date_from is None and state.nights is None
                and ("когда" in step.reply.lower() or "числа" in step.reply.lower()))
    return (state.month == 12 and state.destination is None and state.party_size == 2
            and state.economy is True and state.budget_total is None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--pace-seconds", type=float, default=0)
    args = parser.parse_args()
    settings = get_settings()
    if args.model and not settings.llm_enabled:
        raise RuntimeError("Не настроен разрешённый доступ к модели")
    agent = Agent(TripsDomain(today=lambda: TODAY), build_llm(settings) if args.model else None, today=lambda: TODAY)
    results = []
    for ident, text, kind in CASES:
        session = agent.new_session()
        start = time.monotonic()
        step = agent.handle(session, text)
        available = not args.model or session.last_nlu in {"llm", "llm+rules"}
        passed = assess(kind, session.state, step)
        status = "INCOMPLETE" if not available else "PASS" if passed else "FAIL"
        results.append({"id": ident, "status": status, "nlu": session.last_nlu,
                        "seconds": round(time.monotonic() - start, 3),
                        "state": session.state.params().model_dump(mode="json", exclude_none=True),
                        "reply": step.reply})
        print(ident, status, flush=True)
        if not available:
            break
        if args.pace_seconds:
            time.sleep(args.pace_seconds)
    report = {"mode": "model+rules" if args.model else "rules", "planned": len(CASES),
              "completed": len(results), "passed": sum(r["status"] == "PASS" for r in results), "results": results}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['passed']}/{report['completed']} PASS, planned {report['planned']}")
    return 0 if report["completed"] == report["planned"] and report["passed"] == report["planned"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
