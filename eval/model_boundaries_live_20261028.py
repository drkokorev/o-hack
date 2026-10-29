"""Небольшая проверка реальной модели на вымышленных репликах; секреты и запросы провайдеру не сохраняются."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from core.agent import Agent
from core.config import get_settings
from core.llm import build_llm
from domains.trips.domain import TripsDomain


class Recorder:
    def __init__(self, inner):
        self.inner = inner
        self.breaker = getattr(inner, "breaker", None)
        self.calls = 0
        self.leaked = False

    def complete(self, messages, **kwargs):
        self.calls += 1
        content = " ".join(m["content"] for m in messages).casefold()
        self.leaked |= (any(x in content for x in ("иван", "петров", "test-traveller@example.com"))
                        or "9991234567" in "".join(ch for ch in content if ch.isdigit()))
        return self.inner.complete(messages, **kwargs)


def main():
    llm = build_llm(get_settings())
    if llm is None:
        raise SystemExit("Нет доступа к модели")
    recorder = Recorder(llm)
    today = date(2026, 10, 28)
    agent = Agent(TripsDomain(today=lambda: today), recorder, nlg=True, today=lambda: today)
    cases = [
        ("flight", "Только перелёт из Москвы в Казань 10 декабря 2026 в одну сторону", "flight_results"),
        ("tour", "Подбери пакетный тур в Турцию", "question"),
        ("privacy", "Меня зовут Иван Петров, телефон +7 999 123-45-67, почта test-traveller@example.com. Хочу в Казань", "question"),
        ("package", "Из Москвы в Казань с 10 по 15 декабря 2026 двое взрослых", "packages"),
    ]
    rows = []
    for label, text, expected in cases:
        session = agent.new_session()
        before = recorder.calls
        step = agent.handle(session, text)
        kind = (step.payload or {}).get("kind")
        model_used = session.last_nlu in {"llm", "llm+rules"} and recorder.calls > before
        rows.append({"case": label, "kind": kind, "expected_kind": expected, "nlu": session.last_nlu,
                     "answer_by": session.last_answer_by, "model_used": model_used,
                     "pass": kind == expected and model_used})
    result = {"model": get_settings().llm_model, "cases": rows, "calls": recorder.calls,
              "test_values_in_requests": recorder.leaked}
    Path(sys.argv[1]).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if all(row["pass"] for row in rows) and not recorder.leaked else 1


if __name__ == "__main__":
    raise SystemExit(main())
