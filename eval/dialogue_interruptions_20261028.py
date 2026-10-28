"""Synthetic multi-turn evaluation; uses configured model only when --model is supplied."""
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


class CountingLLM:
    def __init__(self, inner):
        self.inner = inner
        self.breaker = getattr(inner, "breaker", None)
        self.calls = 0
        self.errors = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        try:
            return self.inner.complete(messages, **kwargs)
        except Exception:
            self.errors += 1
            raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="store_true")
    parser.add_argument("--pause", type=float, default=0)
    parser.add_argument("--case", help="Run one named scenario")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    settings = get_settings()
    configured = build_llm(settings) if args.model else None
    llm = CountingLLM(configured) if configured else None
    if args.model and llm is None:
        raise SystemExit("Model is not configured; evaluation not started")
    agent = Agent(TripsDomain(today=lambda: TODAY), llm, today=lambda: TODAY)
    scenarios = [
        {
            "id": "interrupted_question",
            "turns": [
                ("Хочу в Казань", lambda s, r: s.pending_question == "when"),
                ("Можно ли будет отменить бронь?", lambda s, r: "отмен" in r.lower() and s.pending_question == "when" and s.free_cancellation is None),
                ("из Москвы", lambda s, r: s.origin == "Москва" and s.pending_question == "when" and "when" not in s.skipped_questions),
                ("в июне", lambda s, r: s.month == 6 and s.pending_question == "duration"),
            ],
        },
        {
            "id": "known_total_with_child",
            "turns": [
                ("Из Москвы в Казань с 10 по 15 июня 2027 на двоих", lambda s, r: s.party_size == 2 and s.adults is None),
                ("с одним ребёнком", lambda s, r: s.adults == 1 and s.children == 1 and s.stage == "plan"),
            ],
        },
        {
            "id": "question_after_plan",
            "turns": [
                ("Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых", lambda s, r: s.stage == "plan"),
                ("Сколько ехать?", lambda s, r: "в пути" in r.lower() and "животн" not in r.lower()),
            ],
        },
        {
            "id": "hotel_questions",
            "turns": [
                ("Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых", lambda s, r: s.stage == "plan"),
                ("Завтрак и бассейн есть?", lambda s, r: "питан" in r.lower() and "бассейн" in r.lower() and s.meal is None and not s.hotel_wishes),
                ("Нужен завтрак, а парковка есть?", lambda s, r: s.meal == "breakfast" and "parking" not in (s.hotel_wishes or []) and "парковк" in r.lower()),
            ],
        },
        {
            "id": "baggage_requirement",
            "turns": [
                ("Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых, самолётом, нужен багаж",
                 lambda s, r: s.baggage is True and s.stage == "plan" and "без багажа" not in r.lower()),
                ("Багаж не нужен", lambda s, r: s.baggage is False and s.stage == "plan"),
            ],
        },
        {
            "id": "all_inclusive",
            "turns": [
                ("Новый год на море, всё включено, 4 звезды",
                 lambda s, r: s.meal == "all_inclusive" and s.stars_min == 4 and "sea" in (s.trip_types or [])),
            ],
        },
        {
            "id": "nightly_limit",
            "turns": [
                ("Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых, отель до 6000 рублей за ночь",
                 lambda s, r: s.budget_night == 6000 and s.stage == "plan"),
            ],
        },
    ]
    if args.case:
        scenarios = [scenario for scenario in scenarios if scenario["id"] == args.case]
        if not scenarios:
            raise SystemExit("Unknown scenario")
    result = {"mode": "model+rules" if llm else "rules", "provider": settings.llm_provider if llm else None,
              "model": settings.llm_model if llm else None, "cases": []}
    calls = 0
    for scenario in scenarios:
        session = agent.new_session()
        turns = []
        for text, check in scenario["turns"]:
            if calls and args.pause:
                time.sleep(args.pause)
            before = llm.calls if llm else 0
            start = time.perf_counter()
            step = agent.handle(session, text)
            calls += 1
            turns.append({"text": text, "reply": step.reply, "nlu": session.last_nlu,
                          "model_calls": llm.calls - before if llm else 0,
                          "milliseconds": round((time.perf_counter() - start) * 1000),
                          "pass": bool(check(session.state, step.reply))})
        result["cases"].append({"id": scenario["id"], "pass": all(t["pass"] for t in turns), "turns": turns})
    result["passed"] = sum(c["pass"] for c in result["cases"])
    result["total"] = len(result["cases"])
    result["turns"] = calls
    result["model_turns"] = sum(t["model_calls"] > 0 for c in result["cases"] for t in c["turns"])
    result["model_calls"] = llm.calls if llm else 0
    result["model_errors"] = llm.errors if llm else 0
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("mode", "passed", "total", "turns", "model_turns", "model_calls", "model_errors")}, ensure_ascii=False))
    return 0 if result["passed"] == result["total"] and (not args.model or (result["model_turns"] == calls and not llm.errors)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
