"""Проверка LLM из .env перед тестами: связь, JSON-режим, строгая схема, задержка и качество понимания.

    .venv/bin/python -m tools.llm_check
"""

from __future__ import annotations

import json
import time
from datetime import date
from statistics import median

from core.config import get_settings
from core.llm import build_llm, extract, strict_schema
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID
from domains.trips.rules import find_destination, rule_extract
from domains.trips.state import TripState, TripUpdate
from domains.trips.textparse import norm

TODAY = date.today()
SAMPLES = [
    ("Хочу к тёплому морю в ноябре, недорого, с ребёнком, без долгих перелётов",
     {"trip_types": "sea", "month": 11, "children": 1}),
    ("Казань из Питера на выходные с собакой, поездом", {"destination": "Казань", "pets": True, "transport": "train"}),
    ("мы с мужем и двумя детьми хотим в Сочи на неделю с 3 ноября до 300 тысяч",
     {"destination": "Сочи", "children": 2, "nights": 7, "budget_total": 300000}),
    ("куда-нибудь в горы летом, природа, походы", {"trip_types": "mountains", "month": {6, 7, 8}}),
    ("а если на два дня позже?", {"shift_days": 2}),
    ("давай подумаем", {"confirm": None}),
    ("Вылет из Екатеринбурга, хочу в Стамбул на майские вдвоём", {"origin": "Екатеринбург", "destination": "Стамбул",
                                                               "adults": 2}),
    ("не на море, а в горы", {"trip_types": "mountains"}),
]


def ok(update: TripUpdate, want: dict) -> bool:
    for key, value in want.items():
        got = getattr(update, key)
        if key == "destination" and isinstance(got, str) and isinstance(value, str):
            actual_id = got if got in BY_ID else find_destination(norm(got))
            expected_id = value if value in BY_ID else find_destination(norm(value))
            if not actual_id or actual_id != expected_id:
                return False
        elif isinstance(value, (set, tuple)):
            if got not in value:
                return False
        elif isinstance(got, list):
            if value not in got:
                return False
        elif isinstance(value, str) and isinstance(got, str):
            if value.lower()[:4] not in got.lower():
                return False
        elif got != value:
            return False
    return True


def main() -> int:
    s = get_settings()
    print(f"Провайдер: {s.llm_provider} · {s.llm_base_url}\nМодель:    {s.llm_model}")
    llm = build_llm(s)
    if llm is None:
        print("Ключ LLM не задан в .env — агент работает только на правилах.")
        return 1
    started = time.perf_counter()
    try:
        raw = llm.complete([{"role": "user", "content": "Ответь одним словом: да"}])
    except Exception as err:
        print(f"Ошибка связи: {type(err).__name__}: {str(err)[:300]}")
        return 1
    print(f"Связь: ок, «{raw.strip()[:30]}», {(time.perf_counter() - started) * 1000:.0f} мс")

    for mode, kwargs in (("json_object", {"json_mode": True}), ("json_schema", {"schema": strict_schema(TripUpdate)})):
        llm._json_mode, llm._schema_mode = mode == "json_object", mode == "json_schema"
        try:
            out = llm.complete([{"role": "user", "content": 'Верни JSON {"pick": 2}'}], **kwargs)
            json.loads(out[out.find("{"): out.rfind("}") + 1])
            supported = llm._json_mode or llm._schema_mode
            print(f"{mode}: {'поддерживается' if supported else 'отвергнут провайдером — агент работает без него'}")
        except Exception as err:
            print(f"{mode}: ошибка {type(err).__name__}")
    llm._json_mode, llm._schema_mode = s.llm_json_mode, s.llm_schema_mode

    domain = TripsDomain()
    times, good = [], 0
    print("\nПонимание (LLM | правила):")
    for text, want in SAMPLES:
        msgs = domain.extraction_messages(TripState(), [], text, TODAY)
        t0 = time.perf_counter()
        update = extract(llm, TripUpdate, msgs)
        times.append((time.perf_counter() - t0) * 1000)
        by_rules = rule_extract(TripState(), text, TODAY)
        llm_ok, rules_ok = ok(update, want), ok(by_rules, want)
        good += llm_ok
        print(f"  {'✓' if llm_ok else '✗'} | {'✓' if rules_ok else '✗'}  {times[-1]:5.0f} мс  {text}")
        if not llm_ok:
            print("        LLM:", update.model_dump_json(exclude_none=True)[:200])
    print(f"\nLLM поняла {good}/{len(SAMPLES)}, задержка p50 {median(times):.0f} мс, макс {max(times):.0f} мс; "
          f"предохранитель: {llm.breaker.state}")
    return 0 if good >= len(SAMPLES) - 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
