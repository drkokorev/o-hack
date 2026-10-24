"""Проверка доступа к LLM из .env: один запрос на извлечение, время ответа и разобранный результат.

    .venv/bin/python -m tools.llm_check
    .venv/bin/python -m tools.llm_check "Казань на выходные до 6000 с завтраком"
"""

from __future__ import annotations

import sys
import time
from datetime import date

from core.config import get_settings
from core.llm import build_llm, extract
from domains.trips.domain import TripsDomain
from domains.trips.state import TripState, TripUpdate


def main() -> int:
    settings = get_settings()
    print(f"Провайдер: {settings.llm_base_url}\nМодель:    {settings.llm_model}")
    if not settings.llm_enabled:
        print("LLM_API_KEY не задан в .env — агент работает только на правилах.")
        return 1
    llm = build_llm(settings)
    assert llm is not None
    started = time.perf_counter()
    try:
        raw = llm.complete([{"role": "user", "content": "Ответь одним словом: да"}])
    except Exception as err:
        print(f"Ошибка запроса: {type(err).__name__}: {err}")
        return 1
    print(f"Связь есть: «{raw.strip()[:40]}», {(time.perf_counter() - started) * 1000:.0f} мс")

    text = " ".join(sys.argv[1:]) or "Хочу к тёплому морю в ноябре, недорого, с ребёнком"
    messages = TripsDomain().extraction_messages(TripState(), [], text, date.today())
    started = time.perf_counter()
    update = extract(llm, TripUpdate, messages)
    ms = (time.perf_counter() - started) * 1000
    print(f"Извлечение за {ms:.0f} мс: {update.model_dump_json(exclude_none=True)}")
    if not update.model_dump(exclude_none=True):
        print("Модель ничего не извлекла — попробуйте LLM_JSON_MODE=0 или другую модель.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
