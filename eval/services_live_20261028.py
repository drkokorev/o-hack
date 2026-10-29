"""Synthetic end-to-end checks with the configured LLM, without saving prompts or personal data."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from core.agent import Agent
from core.config import get_settings
from core.llm import build_llm
from domains.trips.domain import TripsDomain


class CountingLLM:
    def __init__(self, inner):
        self.inner, self.calls = inner, 0
        self.breaker = getattr(inner, "breaker", None)

    def complete(self, messages, **kwargs):
        self.calls += 1
        return self.inner.complete(messages, **kwargs)


def main():
    settings = get_settings()
    llm = build_llm(settings)
    if llm is None:
        raise SystemExit("Модель недоступна или не настроена")
    llm = CountingLLM(llm)
    today = date(2026, 10, 28)
    agent = Agent(TripsDomain(today=lambda: today), llm, nlg=True, today=lambda: today)
    cases = [
        ("transfer", ["Нужен трансфер в Сочи из аэропорта в отель завтра в 14:30, 2 человека в одну сторону"],
         lambda s, r: s.search_scope == "transfer_only" and "не заказ" in r and "14:30" in r),
        ("multiroom", ["Только отель в Казани с 10 по 15 декабря 2026, 3 взрослых и ребенок, 2 номера",
                       "номер 1: 2 взрослых, ребёнок 7 лет; номер 2: 1 взрослый"],
         lambda s, r: len(s.room_allocations or []) == 2 and "за все номера" in r),
        ("two_hotels", ["Хочу два отеля в Сочи", "по очереди",
                        "1: Казань 10.12.2026–12.12.2026; 2: Сочи 12.12.2026–15.12.2026",
                        "2 взрослых", "1"],
         lambda s, r: len(s.split_stays or []) == 2 and "Выбрана пара" in r),
        ("flight_class", ["Только перелёт из Москвы в Казань 10 декабря 2026 в одну сторону бизнес-класс"],
         lambda s, r: s.seat_class == "бизнес" and "нет перелётов" in r),
        ("train_only", ["Только билет на поезд из Москвы в Казань 10 декабря 2026 в одну сторону без отеля"],
         lambda s, r: s.search_scope == "train_only" and s.lodging is None and "Демонстрационные поезда" in r),
        ("child_fare", ["Ребёнку 7 лет билет бесплатный?"],
         lambda s, r: s.children is None and "со скидкой или по полному" in r),
        ("relative_time", ["Хочу куда-нибудь поехать", "не завтра, а в следующем месяце"],
         lambda s, r: s.month == 11 and s.year == 2026 and s.date_from is None),
        ("guide_synonym", ["Хочу в Казань", "где перекусить недорого?"],
         lambda s, r: s.dest_id == "kazan" and "Wikivoyage" in r),
    ]
    results = []
    for name, turns, predicate in cases:
        session = agent.new_session()
        before = llm.calls
        errors = []
        sources = []
        reply = ""
        for turn in turns:
            try:
                reply = agent.handle(session, turn).reply
                sources.append(session.last_nlu)
            except Exception as exc:
                errors.append(type(exc).__name__)
                break
        model_calls = llm.calls - before
        passed = not errors and model_calls > 0 and predicate(session.state, reply)
        results.append({"case": name, "pass": passed, "model_calls": model_calls, "nlu_by_turn": sources, "errors": errors})
        print(f"{name}: {'PASS' if passed else 'FAIL'}; model_calls={model_calls}", flush=True)
    report = {"model": settings.llm_model, "synthetic": True, "total": len(results),
              "passed": sum(r["pass"] for r in results), "calls": llm.calls, "cases": results}
    Path(sys.argv[1]).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
