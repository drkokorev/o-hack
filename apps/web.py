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
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.agent import Agent, Session
from core.config import get_settings
from core.llm import build_llm
from core.ru import MONTHS_GEN, fmt_money, plural
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID, DESTINATIONS, ORIGINS, TAG_NAMES
from domains.trips.offers import AMENITIES, MEALS, hotel_count
from domains.trips.state import TripState

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
MAX_SESSIONS = 1000
MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
              "ноябрь", "декабрь"]
STAGES = [("start", "Запрос"), ("destination", "Направление"), ("plan", "Варианты"),
          ("cart", "Корзина"), ("payment", "Оплата"), ("booked", "Готово")]

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
    """Сессии в памяти процесса с ограничением количества и времени бездействия."""

    def __init__(self, agent: Agent, limit: int = MAX_SESSIONS, ttl_seconds: float = 3600,
                 clock=time.monotonic):
        if limit <= 0 or ttl_seconds <= 0:
            raise ValueError("Лимит сессий и время хранения должны быть положительными")
        self.agent = agent
        self.limit = limit
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._items: OrderedDict[str, tuple[Session, float]] = OrderedDict()
        self.lock = threading.Lock()

    def _prune_locked(self, now: float) -> int:
        removed = 0
        while self._items and now - next(iter(self._items.values()))[1] >= self.ttl_seconds:
            self._items.popitem(last=False)
            removed += 1
        return removed

    def prune(self) -> int:
        with self.lock:
            return self._prune_locked(self.clock())

    def get(self, session_id: str | None) -> tuple[str, Session]:
        with self.lock:
            now = self.clock()
            self._prune_locked(now)
            if session_id and session_id in self._items:
                session, _ = self._items[session_id]
                self._items[session_id] = (session, now)
                self._items.move_to_end(session_id)
                return session_id, session
            session_id = uuid.uuid4().hex
            session = self.agent.new_session()
            self._items[session_id] = (session, now)
            while len(self._items) > self.limit:
                self._items.popitem(last=False)
            return session_id, session

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
        start_year = f" {state.date_from.year}" if state.date_from.year != state.date_to.year else ""
        chips.append(f"{state.date_from.day} {MONTHS_GEN[state.date_from.month - 1]}{start_year} — "
                     f"{state.date_to.day} {MONTHS_GEN[state.date_to.month - 1]} {state.date_to.year}")
    elif state.month:
        chips.append(MONTHS_NOM[state.month - 1] + (f" {state.year}" if state.year else ""))
    if state.adults:
        chips.append(f"{state.adults} {plural(state.adults, 'взрослый', 'взрослых', 'взрослых')}")
    elif state.party_size:
        chips.append(f"{state.party_size} {plural(state.party_size, 'путешественник', 'путешественника', 'путешественников')}")
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
        chips.append({"train": "поезд", "plane": "самолёт", "none": "нет подходящего транспорта"}.get(state.transport, state.transport))
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


class Images:
    """Фото направлений и иллюстрации отелей (Wikimedia Commons, свободные лицензии) — в ответы API по id."""

    HOTEL_KINDS = ("resort", "pool", "city", "room", "mountain", "lobby")

    def __init__(self, root: Path = STATIC / "img"):
        import json

        path = root / "credits.json"
        self.credits: dict[str, dict] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.by_kind = {k: sorted(f for f in self.credits if f.startswith(f"hotel/{k}-")) for k in self.HOTEL_KINDS}

    def _ref(self, key: str | None) -> dict | None:
        if not key or key not in self.credits:
            return None
        c = self.credits[key]
        return {"src": f"/static/img/{key}", "credit": f"{c['author']}, {c['license']}", "page": c.get("page")}

    def dest(self, dest_id: str | None) -> dict | None:
        return self._ref(f"dest/{dest_id}.jpg")

    def gallery(self, dest_id: str | None) -> list[dict]:
        """Главное фото направления и галерея лучших снимков Commons."""
        keys = [f"dest/{dest_id}.jpg"] + sorted(k for k in self.credits if k.startswith(f"gallery/{dest_id}-"))
        return [ref for k in keys if (ref := self._ref(k))]

    def hotel(self, hotel_id: str, dest_id: str, avoid: set[str] | None = None) -> dict | None:
        """Иллюстрация по типу направления; `avoid` — уже показанные рядом, чтобы карточки не повторялись."""
        import zlib

        tags = BY_ID[dest_id].tags if dest_id in BY_ID else ()
        kinds = (["resort", "pool", "room"] if "beach" in tags else ["mountain", "room", "lobby"] if "ski" in tags
                 else ["city", "room", "lobby"])
        pool = [f for k in kinds for f in self.by_kind.get(k, [])] or [f for v in self.by_kind.values() for f in v]
        if not pool:
            return None
        start = zlib.crc32(hotel_id.encode()) % len(pool)
        for i in range(len(pool)):
            key = pool[(start + i) % len(pool)]
            if not avoid or key not in avoid:
                if avoid is not None:
                    avoid.add(key)
                return self._ref(key)
        return self._ref(pool[start])

    def decorate(self, payload: dict | None) -> dict | None:
        if not payload:
            return payload
        kind = payload.get("kind")
        if kind == "destinations":
            for item in payload["items"]:
                item["image"] = self.dest(item["id"])
                item["gallery"] = self.gallery(item["id"])
        if payload.get("trip"):
            payload["trip"]["image"] = self.dest(payload["trip"].get("dest_id"))
            payload["trip"]["gallery"] = self.gallery(payload["trip"].get("dest_id"))
        dest_id = (payload.get("trip") or {}).get("dest_id")
        shown: set[str] = set()
        same: dict[str, dict | None] = {}  # один и тот же отель в разных вариантах — одна картинка
        for item in payload.get("items", []) if kind == "packages" else []:
            hid = item["hotel"]["id"]
            if hid not in same:
                same[hid] = self.hotel(hid, dest_id, shown)
            item["hotel"]["image"] = same[hid]
        if kind == "hotels":
            for item in payload["items"]:
                item["image"] = self.hotel(item["id"], item["id"].rsplit("-h", 1)[0], shown)
        if kind == "cart":
            payload["package"]["hotel"]["image"] = self.hotel(payload["package"]["hotel"]["id"], dest_id)
        if kind == "order":
            payload["order"]["image"] = self.dest(payload["order"].get("dest_id"))
        return payload


def build_app(agent: Agent | None = None) -> FastAPI:
    settings = get_settings()
    if agent is None:
        llm = build_llm(settings)
        agent = Agent(TripsDomain(), llm, nlg=settings.llm_nlg)
    sessions = Sessions(agent, ttl_seconds=float(os.getenv("SESSION_TTL_SECONDS") or "3600"))
    images = Images()

    @asynccontextmanager
    async def lifespan(_app):
        stopped = threading.Event()

        def cleanup() -> None:
            while not stopped.wait(min(60, sessions.ttl_seconds)):
                sessions.prune()

        worker = threading.Thread(target=cleanup, name="session-cleanup", daemon=True)
        worker.start()
        try:
            yield
        finally:
            stopped.set()
            worker.join(timeout=1)

    app = FastAPI(title="О!дин запрос — агент поездки", docs_url="/api/docs", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/info")
    def info() -> dict:
        breaker = getattr(agent.llm, "breaker", None)
        return {"llm": settings.llm_model if agent.llm is not None else None,
                "llm_state": breaker.state if breaker else "off",
                "destinations": len(DESTINATIONS),
                "hotels": hotel_count(),
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
            "session_id": session_id, "reply": step.reply, "payload": images.decorate(step.payload), "stage": state.stage,
            "understood": understood(state), "assumptions": state.assumptions, "nlu": session.last_nlu,
            "checked": session.last_notes,
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
    uvicorn.run(build_app(), host=os.getenv("APP_HOST") or "127.0.0.1", port=int(os.getenv("APP_PORT") or "8080"),
                access_log=False)


if __name__ == "__main__":
    main()
