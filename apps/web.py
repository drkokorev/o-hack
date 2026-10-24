"""Веб-приложение: чат с агентом поездки и визуальный план (направления, варианты, корзина, заказ).

Запуск: .venv/bin/python -m apps.web  (порт 8080, можно задать APP_PORT)
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.agent import Agent, Session
from core.config import get_settings
from core.llm import OpenAICompatLLM
from core.ru import MONTHS_GEN, fmt_money, plural
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID, DESTINATIONS, ORIGINS, TAG_NAMES
from domains.trips.offers import AMENITIES, MEALS
from domains.trips.state import TripState

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
MAX_SESSIONS = 1000
MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
              "ноябрь", "декабрь"]
STAGES = [("start", "Запрос"), ("destination", "Направление"), ("plan", "Варианты"),
          ("cart", "Корзина"), ("booked", "Покупка")]

EXAMPLES = [
    "Хочу к тёплому морю в ноябре, недорого, с ребёнком, без долгих перелётов",
    "Казань из Питера на выходные с собакой",
    "Горы и природа в июле на неделю, вдвоём, до 200 тысяч",
    "Новый год на море, всё включено, 4 звезды",
]


class ChatIn(BaseModel):
    text: str
    session_id: str | None = None


class ResetIn(BaseModel):
    session_id: str


class Sessions:
    """Сессии в памяти процесса с вытеснением самых старых."""

    def __init__(self, agent: Agent, limit: int = MAX_SESSIONS):
        self.agent = agent
        self.limit = limit
        self._items: OrderedDict[str, Session] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, session_id: str | None) -> tuple[str, Session]:
        with self.lock:
            if session_id and session_id in self._items:
                self._items.move_to_end(session_id)
                return session_id, self._items[session_id]
            session_id = uuid.uuid4().hex
            self._items[session_id] = self.agent.new_session()
            while len(self._items) > self.limit:
                self._items.popitem(last=False)
            return session_id, self._items[session_id]

    def drop(self, session_id: str) -> None:
        with self.lock:
            self._items.pop(session_id, None)


def understood(state: TripState) -> list[str]:
    """Что агент понял из разговора — короткими плашками."""
    chips = []
    if state.origin:
        chips.append(f"из: {state.origin}")
    if state.dest_id:
        chips.append(BY_ID[state.dest_id].name)
    elif state.destination:
        chips.append(state.destination)
    for t in state.trip_types or []:
        chips.append(TAG_NAMES.get(t, t))
    if state.date_from and state.date_to:
        chips.append(f"{state.date_from.day} {MONTHS_GEN[state.date_from.month - 1]} — "
                     f"{state.date_to.day} {MONTHS_GEN[state.date_to.month - 1]}")
    elif state.month:
        chips.append(MONTHS_NOM[state.month - 1])
    if state.adults:
        chips.append(f"{state.adults} {plural(state.adults, 'взрослый', 'взрослых', 'взрослых')}")
    if state.children:
        chips.append(f"{state.children} {plural(state.children, 'ребёнок', 'ребёнка', 'детей')}")
    if state.pets:
        chips.append("с питомцем")
    if state.budget_total:
        chips.append(f"бюджет {fmt_money(state.budget_total)}")
    if state.budget_night:
        chips.append(f"до {fmt_money(state.budget_night)}/ночь")
    if state.max_travel_hours:
        chips.append(f"в пути до {state.max_travel_hours:g} ч")
    if state.transport:
        chips.append("поезд" if state.transport == "train" else "самолёт")
    if state.direct_only:
        chips.append("без пересадок")
    if state.meal:
        chips.append(MEALS.get(state.meal, state.meal))
    if state.free_cancellation:
        chips.append("бесплатная отмена")
    if state.stars_min:
        chips.append(f"от {state.stars_min}★")
    chips += [AMENITIES.get(w, w) for w in state.hotel_wishes or []]
    if state.abroad is not None:
        chips.append("за границу" if state.abroad else "по России")
    return chips


def build_app(agent: Agent | None = None) -> FastAPI:
    settings = get_settings()
    if agent is None:
        llm = OpenAICompatLLM(settings) if settings.llm_enabled else None
        agent = Agent(TripsDomain(), llm, nlg=settings.llm_nlg)
    sessions = Sessions(agent)
    app = FastAPI(title="О!дин запрос — агент поездки", docs_url="/api/docs")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/info")
    def info() -> dict:
        return {"llm": settings.llm_model if agent.llm is not None else None, "destinations": len(DESTINATIONS),
                "places": [{"id": d.id, "name": d.name, "lat": d.lat, "lon": d.lon} for d in DESTINATIONS],
                "origins": [{"name": o.name, "lat": o.lat, "lon": o.lon} for o in ORIGINS],
                "examples": EXAMPLES, "stages": [{"key": k, "title": t} for k, t in STAGES]}

    @app.post("/api/chat")
    def chat(body: ChatIn) -> dict:
        started = time.perf_counter()
        session_id, session = sessions.get(body.session_id)
        step = agent.handle(session, body.text)
        state: TripState = session.state  # type: ignore[assignment]
        return {
            "session_id": session_id, "reply": step.reply, "payload": step.payload, "stage": state.stage,
            "understood": understood(state), "assumptions": state.assumptions, "nlu": session.last_nlu,
            "ms": round((time.perf_counter() - started) * 1000),
        }

    @app.post("/api/reset")
    def reset(body: ResetIn) -> dict:
        sessions.drop(body.session_id)
        return {"ok": True}

    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(build_app(), host=os.getenv("APP_HOST", "127.0.0.1"), port=int(os.getenv("APP_PORT", "8080")))


if __name__ == "__main__":
    main()
