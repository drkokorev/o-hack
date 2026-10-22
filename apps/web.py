"""Веб-демо: чат с агентом, карточки отелей и панель «что я понял».

Запуск: .venv/bin/python -m apps.web  (порт 8000, можно задать PORT)
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.agent import Agent, Session, Step
from core.config import get_settings
from core.llm import OpenAICompatLLM
from core.ru import fmt_date, fmt_money, plural
from domains.hotels.catalog import AMENITIES, TRIP_PURPOSES
from domains.hotels.domain import HotelsDomain
from domains.hotels.search import SearchResult
from domains.hotels.state import PARAM_FIELDS, HotelState, HotelUpdate

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
MAX_SESSIONS = 500

EXAMPLES = [
    "Питер на выходные до 8 тысяч за ночь, с завтраком, поближе к центру",
    "Сочи у моря с детьми, с бассейном, на неделю с 3 ноября",
    "Командировка в Москву завтра на 2 ночи, нужен фитнес",
    "Казань, 5 звёзд со спа, до 3000 за ночь",
]


class ChatIn(BaseModel):
    text: str
    session_id: str | None = None


class ClearIn(BaseModel):
    session_id: str
    field: str


class ResetIn(BaseModel):
    session_id: str


class Sessions:
    """Сессии в памяти процесса (ADR 006) с вытеснением самых старых."""

    def __init__(self, agent: Agent, limit: int = MAX_SESSIONS):
        self.agent = agent
        self.limit = limit
        self._items: OrderedDict[str, Session] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, session_id: str | None) -> tuple[str, Session]:
        if session_id and session_id in self._items:
            self._items.move_to_end(session_id)
            return session_id, self._items[session_id]
        session_id = uuid.uuid4().hex
        self._items[session_id] = self.agent.new_session()
        while len(self._items) > self.limit:
            self._items.popitem(last=False)
        return session_id, self._items[session_id]

    def drop(self, session_id: str) -> None:
        self._items.pop(session_id, None)


def state_chips(state: HotelState) -> list[dict]:
    """Понятые параметры в виде «плашек»; у каждой — поле, которое можно сбросить."""
    chips = []
    if state.city:
        chips.append({"field": "city", "label": state.city, "removable": False})
    if state.check_in:
        label = f"с {fmt_date(state.check_in)}"
        if state.check_out:
            nights = (state.check_out - state.check_in).days
            label += f" по {fmt_date(state.check_out)} · {nights} {plural(nights, 'ночь', 'ночи', 'ночей')}"
        chips.append({"field": "check_in", "label": label, "removable": True})
    if state.guests:
        chips.append({"field": "guests", "label": f"{state.guests} {plural(state.guests, 'гость', 'гостя', 'гостей')}",
                      "removable": True})
    if state.budget_max:
        chips.append({"field": "budget_max", "label": f"до {fmt_money(state.budget_max)}/ночь", "removable": True})
    if state.stars_min:
        chips.append({"field": "stars_min", "label": f"от {state.stars_min}★", "removable": True})
    for code in state.amenities or []:
        chips.append({"field": f"amenity:{code}", "label": AMENITIES.get(code, code), "removable": True})
    if state.near_center:
        chips.append({"field": "near_center", "label": "ближе к центру", "removable": True})
    if state.near_sea:
        chips.append({"field": "near_sea", "label": "ближе к морю", "removable": True})
    if state.district:
        chips.append({"field": "district", "label": f"район {state.district}", "removable": True})
    if state.trip_purpose:
        chips.append({"field": "trip_purpose", "label": TRIP_PURPOSES.get(state.trip_purpose, state.trip_purpose),
                      "removable": True})
    return chips


def hotel_cards(state: HotelState, result: SearchResult | None) -> list[dict]:
    if not isinstance(result, SearchResult):
        return []
    nights = None
    if state.check_in and state.check_out and state.check_out > state.check_in:
        nights = (state.check_out - state.check_in).days
    cards = []
    for m in result.matches:
        h = m.hotel
        cards.append({
            "id": h.id, "name": h.name, "stars": h.stars, "district": h.district,
            "distance_center_km": h.distance_center_km, "distance_sea_km": h.distance_sea_km,
            "price_per_night": fmt_money(h.price_per_night),
            "price_total": fmt_money(h.price_per_night * nights) if nights else None,
            "nights": nights, "rating": h.rating, "reviews_count": h.reviews_count,
            "reasons": m.reasons, "highlights": h.review_highlights[:2],
            "amenities": [AMENITIES[a] for a in h.amenities if a in AMENITIES],
        })
    return cards


def summary(step: Step) -> str:
    """Короткая реплика для чата: сами варианты показаны карточками рядом."""
    if not isinstance(step.payload, SearchResult) or not step.payload.matches:
        return step.reply
    lines = [ln for ln in step.reply.splitlines() if ln.strip()]
    head = lines[0].rstrip(":") + "."
    if step.payload.relaxed:
        head += " " + lines[1]
    tail = [ln for ln in lines if ln.startswith(("Укажите", "Могу уточнить"))]
    return "\n".join([head, *tail])


def build_app(agent: Agent | None = None) -> FastAPI:
    settings = get_settings()
    if agent is None:
        llm = OpenAICompatLLM(settings) if settings.llm_enabled else None
        agent = Agent(HotelsDomain(), llm, nlg=settings.llm_nlg)
    domain: HotelsDomain = agent.domain  # type: ignore[assignment]
    sessions = Sessions(agent)
    app = FastAPI(title="Подбор отелей", docs_url="/api/docs")

    def respond(session_id: str, session: Session, step: Step, started: float) -> dict:
        return {
            "session_id": session_id,
            "reply": step.reply,
            "summary": summary(step),
            "hotels": hotel_cards(session.state, step.payload),
            "relaxed": step.payload.relaxed if isinstance(step.payload, SearchResult) else [],
            "total": step.payload.total if isinstance(step.payload, SearchResult) else 0,
            "chips": state_chips(session.state),
            "nlu": session.last_nlu,
            "ms": round((time.perf_counter() - started) * 1000),
        }

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "llm": settings.llm_model if agent.llm is not None else None,
            "hotels": len(domain.hotels),
            "cities": domain.cities,
            "examples": EXAMPLES,
        }

    @app.post("/api/chat")
    def chat(body: ChatIn) -> dict:
        started = time.perf_counter()
        with sessions.lock:
            session_id, session = sessions.get(body.session_id)
        step = agent.handle(session, body.text)
        return respond(session_id, session, step, started)

    @app.post("/api/clear")
    def clear(body: ClearIn) -> dict:
        """Сбросить один параметр по клику на плашку — без LLM."""
        started = time.perf_counter()
        with sessions.lock:
            session_id, session = sessions.get(body.session_id)
        if body.field.startswith("amenity:"):
            code = body.field.split(":", 1)[1]
            amenities = [a for a in session.state.amenities or [] if a != code]
            session.state = session.state.model_copy(update={"amenities": amenities or None})
        elif body.field in PARAM_FIELDS and body.field != "city":
            session.state = domain.merge(session.state, HotelUpdate(clear=[body.field]))
        else:
            raise HTTPException(400, "Этот параметр нельзя сбросить")
        step = domain.step(session.state)
        session.last = step
        session.last_nlu = "ui"
        return respond(session_id, session, step, started)

    @app.post("/api/reset")
    def reset(body: ResetIn) -> dict:
        with sessions.lock:
            sessions.drop(body.session_id)
        return {"ok": True}

    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(build_app(), host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
