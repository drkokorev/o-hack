"""Same travel intentions with different language styles; synthetic test text only."""
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

TODAY = date(2026, 10, 27)
CASES = Path(__file__).with_name("colloquial_20261028.json")


def assess(case, session, step):
    s = session.state
    failures = []

    def expect(ok, message):
        if not ok:
            failures.append(message)

    if case["family"] == "mountain_tent":
        expect({"mountains", "warm", "food"} <= set(s.trip_types or []), "горы, летнее настроение и еда")
        expect(s.party_size == 2 and s.adults is None, "два человека без выдуманного возраста")
        expect(s.lodging == "tent", "проживание в палатке")
        expect(s.economy is True, "небольшой бюджет")
        expect(s.transport == "plane", "явно указанный перелёт")
        expect(not any((s.month, s.season, s.date_from, s.date_to, s.nights)), "даты и ночи не названы")
        expect((step.payload or {}).get("kind") == "question", "следующий шаг — уточнение")
    else:
        expect(s.dest_id == "kazan" and s.origin == "Москва", "маршрут Москва — Казань")
        expect(s.date_from == date(2027, 6, 10) and s.date_to == date(2027, 6, 14), "указанные даты")
        expect(s.adults == 2 and not s.children_unknown, "двое взрослых")
        expect(s.transport == "train", "поезд")
        expect(s.budget_night == 6000 and s.budget_total is None, "бюджет за ночь, а не на всю поездку")
        expect((step.payload or {}).get("kind") == "packages", "расчёт, если необходимые данные известны")
    if case.get("expected_tentative"):
        expect(set(case["expected_tentative"]) <= set(s.tentative_fields or []),
               "явно возможные пожелания помечены предварительными")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--model", action="store_true")
    parser.add_argument("--pace-seconds", type=float, default=0)
    args = parser.parse_args()
    settings = get_settings()
    if args.model and not settings.llm_enabled:
        raise RuntimeError("Нет разрешённого настроенного доступа к модели")
    llm = build_llm(settings) if args.model else None
    agent = Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY)
    results = []
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    for case in cases:
        session = agent.new_session()
        started = time.perf_counter()
        step = agent.handle(session, case["text"])
        elapsed = round(time.perf_counter() - started, 4)
        failures = assess(case, session, step)
        available = not args.model or session.last_nlu in ("llm", "llm+rules")
        status = "PASS" if not failures and available else ("FAIL" if available else "INCOMPLETE")
        results.append({"id": case["id"], "style": case["style"], "status": status, "failures": failures,
                        "nlu": session.last_nlu, "seconds": elapsed,
                        "state": session.state.params().model_dump(mode="json", exclude_none=True),
                        "reply": step.reply})
        print(f"{case['id']} {status}", flush=True)
        if args.model and not available:
            break  # provider fallback is not an assessment of model quality
        if args.pace_seconds:
            time.sleep(args.pace_seconds)
    report = {"fixed_today": TODAY.isoformat(), "mode": "model+rules" if args.model else "rules",
              "planned": len(cases), "completed": len(results),
              "passed": sum(r["status"] == "PASS" for r in results), "results": results}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['passed']}/{report['completed']} PASS, planned {report['planned']}")
    return 0 if report["completed"] == report["planned"] and report["passed"] == report["planned"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
