"""Three synthetic end-to-end temperature examples using explicitly configured model access."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import time

from core.agent import Agent
from core.config import get_settings
from core.llm import build_llm
from domains.trips.domain import TripsDomain

TODAY = date(2026, 10, 27)
CASES = [
    ("air_and_sea", "Хочу в Сочи в июле, воздух не ниже +25 градусов и вода от 22 градусов"),
    ("historical_mismatch", "Из Москвы в Ярославль с 10 по 14 июля 2027 двое взрослых, воздух от 30 градусов"),
    ("question_not_preference", "Хочу в Сочи, какая температура воздуха будет 25 градусов?"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--pace-seconds", type=float, default=0)
    args = parser.parse_args()
    settings = get_settings()
    if not settings.llm_enabled:
        raise RuntimeError("Нет разрешённого настроенного доступа к модели")
    agent = Agent(TripsDomain(today=lambda: TODAY), build_llm(settings), today=lambda: TODAY)
    results = []
    for ident, text in CASES:
        session = agent.new_session()
        step = agent.handle(session, text)
        if session.last_nlu not in ("llm", "llm+rules"):
            results.append({"id": ident, "status": "INCOMPLETE", "nlu": session.last_nlu})
            break
        if ident == "air_and_sea":
            ok = session.state.air_min_temp == 25 and session.state.sea_min_temp == 22
        elif ident == "historical_mismatch":
            ok = session.state.air_min_temp == 30 and "не соответствуют указанному порогу" in step.reply and "не прогноз" in step.reply
        else:
            ok = session.state.air_min_temp is None and session.state.air_max_temp is None
        results.append({"id": ident, "status": "PASS" if ok else "FAIL", "nlu": session.last_nlu,
                        "reply": step.reply, "state": session.state.params().model_dump(mode="json", exclude_none=True)})
        print(ident, results[-1]["status"], flush=True)
        if args.pace_seconds:
            time.sleep(args.pace_seconds)
    report = {"mode": "configured model + rules", "fixed_today": TODAY.isoformat(), "planned": len(CASES),
              "completed": len(results), "passed": sum(r["status"] == "PASS" for r in results), "results": results}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['passed']}/{report['completed']} PASS, planned {report['planned']}")
    return 0 if report["passed"] == report["planned"] and report["completed"] == report["planned"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
