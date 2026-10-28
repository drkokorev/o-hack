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
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from core.agent import Agent, Session, Step
from core.config import get_settings
from core.llm import build_llm
from core.ru import MONTHS_GEN, fmt_money, plural
from apps.location import city_hint, visitor_city, visitor_country
from apps import chat_navigation
from apps.event_selection import choose_event
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID, DESTINATIONS, ORIGINS, TAG_NAMES
from domains.trips.offers import AMENITIES, MEALS, hotel_count, _real
from domains.trips import map_catalog
from domains.trips.state import TripState, TripUpdate
from domains.trips.world_places import find_world_places
from apps.voice import LocalVoice, MAX_AUDIO_BYTES

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
    map_point_id: str | None = Field(default=None, max_length=200)
    map_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    map_city_id: str | None = Field(default=None, max_length=200)
    destination_id: str | None = Field(default=None, max_length=100)
    event_id: str | None = Field(default=None, max_length=160)
    detected_city: str | None = None  # untrusted browser hint; never an exact location


class ResetIn(BaseModel):
    session_id: str


class NavigateIn(BaseModel):
    session_id: str
    revision: int


class EditIn(NavigateIn):
    text: str


class TransferIn(NavigateIn):
    kind: Literal["auto", "taxi", "shuttle"]


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

    def existing(self, session_id: str) -> Session:
        with self.lock:
            now = self.clock()
            self._prune_locked(now)
            item = self._items.get(session_id)
            if item is None:
                raise HTTPException(status_code=404, detail="Диалог уже завершён. Начните новую поездку.")
            session, _ = item
            self._items[session_id] = (session, now)
            self._items.move_to_end(session_id)
            return session

    def drop(self, session_id: str) -> None:
        with self.lock:
            self._items.pop(session_id, None)


def understood(state: TripState) -> list[str]:
    """Что агент понял из разговора — короткими плашками."""
    chips = []
    if state.origin:
        suffix = " (примерно по IP)" if state.origin_inferred else ""
        chips.append(f"из: {state.origin}{suffix}")
    if state.dest_id:
        chips.append(BY_ID[state.dest_id].name)
    elif state.destination:
        chips.append(state.destination)
    elif state.country:
        chips.append(state.country)
    if state.selected_real_hotel:
        chips.append("отель: " + state.selected_real_hotel["name"])
    if state.excluded_countries:
        chips.append("исключены: " + ", ".join(state.excluded_countries))
    if state.visa_free_requested:
        chips.append("безвизовый въезд: не проверен")
    for t in state.trip_types or []:
        chips.append(TAG_NAMES.get(t, t))
    if state.date_from and state.date_to:
        start_year = f" {state.date_from.year}" if state.date_from.year != state.date_to.year else ""
        chips.append(f"{state.date_from.day} {MONTHS_GEN[state.date_from.month - 1]}{start_year} — "
                     f"{state.date_to.day} {MONTHS_GEN[state.date_to.month - 1]} {state.date_to.year}")
    elif state.date_from:
        chips.append(f"начало: {state.date_from.day} {MONTHS_GEN[state.date_from.month - 1]} {state.date_from.year}")
    elif state.month:
        chips.append(MONTHS_NOM[state.month - 1] + (f" {state.year}" if state.year else ""))
    if state.trip_days_min:
        days = (str(state.trip_days_min) if state.trip_days_min == state.trip_days_max else
                f"{state.trip_days_min}–{state.trip_days_max}")
        chips.append(f"поездка: {days} дней")
    if state.nights:
        chips.append(f"{state.nights} {plural(state.nights, 'ночь', 'ночи', 'ночей')}")
    if state.adults:
        chips.append(f"{state.adults} {plural(state.adults, 'взрослый', 'взрослых', 'взрослых')}")
    elif state.party_size:
        prefix = "возможно: " if "party_size" in (state.tentative_fields or []) else ""
        chips.append(f"{prefix}{state.party_size} {plural(state.party_size, 'путешественник', 'путешественника', 'путешественников')}")
    if state.children:
        chips.append(f"{state.children} {plural(state.children, 'ребёнок', 'ребёнка', 'детей')}")
    if state.children_ages:
        chips.append("возраст детей: " + ", ".join(map(str, state.children_ages)) + " лет")
    if state.rooms:
        chips.append(f"номеров: {state.rooms}")
    if state.lodging:
        prefix = "возможно: " if "lodging" in (state.tentative_fields or []) else ""
        chips.append(prefix + {"tent": "палатка", "hotel": "отель"}.get(state.lodging, state.lodging))
    if state.pets:
        chips.append("с питомцем")
    if state.budget_total:
        chips.append(f"бюджет {fmt_money(state.budget_total)}")
    if state.economy:
        chips.append("недорого")
    if state.budget_per_person:
        chips.append(f"до {fmt_money(state.budget_per_person)} на человека")
    if state.budget_night:
        chips.append(f"до {fmt_money(state.budget_night)}/ночь")
    if state.max_travel_hours:
        chips.append(f"в пути до {state.max_travel_hours:g} ч")
    if state.prefer_short_travel:
        chips.append("желательно недолго в пути")
    for label, value in (("воздух от", state.air_min_temp), ("воздух до", state.air_max_temp),
                         ("море от", state.sea_min_temp), ("море до", state.sea_max_temp)):
        if value is not None:
            chips.append(f"{label} {value:g} °C")
    if state.transport:
        prefix = "возможно: " if "transport" in (state.tentative_fields or []) else ""
        chips.append(prefix + {"train": "поезд", "plane": "самолёт", "none": "нет подходящего транспорта"}.get(state.transport, state.transport))
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


def contextual_suggestions(state: TripState, step) -> list[str]:
    """Only offer actions supported by the current result, not by stage alone."""
    payload = step.payload if isinstance(step.payload, dict) else {}
    if state.pending_trip_candidate:
        return ["новая поездка", "изменить текущую"]
    if isinstance(payload.get("suggestions"), list):
        return payload["suggestions"]
    kind = payload.get("kind")
    if kind == "greeting":
        return EXAMPLES
    if kind == "question":
        return ["пока не знаю"] if payload.get("field") in ("when", "duration", "origin", "people", "children") else []
    if kind == "real_hotels":
        return [str(i) for i in range(1, len(payload.get("items") or []) + 1)]
    if kind == "real_hotel_selected":
        return ["можно с пересадкой", "покажи реальные отели"] if state.direct_only else ["покажи реальные отели"]
    if kind in ("ideas", "destinations"):
        choices = ["покажи ещё"]
        if state.abroad is None and not state.country:
            choices.append("только по России")
        return choices
    if kind == "packages":
        choices = ["подешевле", "покажи другие отели"]
        if state.date_from:
            choices.append("а если на два дня позже?")
        if not state.direct_only and any(item.get(leg, {}).get("stops", 0) for item in payload.get("items", [])
                                         for leg in ("out", "back")):
            choices.append("только без пересадок")
        return choices + ["другое направление"]
    if kind in ("cart", "tent_cart"):
        return ["да, оформляй", "нет, вернуться к вариантам"]
    if kind == "payment":
        return ["оплата картой", "оплата СБП", "нет"]
    if kind in ("order", "tent_order"):
        return ["запроси ранний заезд", "поздний выезд", "перенеси на 2 дня позже", "отмени бронь"]
    return []


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
    mode = (os.getenv("ODIN_MODE") or "models").lower()
    if mode not in {"models", "rules"}:
        raise RuntimeError("ODIN_MODE должен быть models или rules")
    require_models = mode == "models"
    voice_dir = os.getenv("VOICE_MODEL_DIR") or (str(Path(__file__).resolve().parents[2] / "models" / "gigaam-v3-int8")
                                                  if require_models else None)
    if require_models and ((agent is None and not settings.llm_enabled) or
                           (agent is not None and agent.llm is None)):
        raise RuntimeError("Не задан доступ к языковой модели. Укажите GIGACHAT_AUTH_KEY или ODIN_SECRET_ENV_FILE.")
    if require_models and (not voice_dir or not Path(voice_dir).is_dir()):
        raise RuntimeError("Не найдена локальная GigaAM. Укажите существующую папку в VOICE_MODEL_DIR.")
    if agent is None:
        llm = build_llm(settings) if require_models else None
        agent = Agent(TripsDomain(), llm, nlg=settings.llm_nlg)
    sessions = Sessions(agent, ttl_seconds=float(os.getenv("SESSION_TTL_SECONDS") or "3600"))
    images = Images()
    voice = LocalVoice(voice_dir)

    @asynccontextmanager
    async def lifespan(_app):
        stopped = threading.Event()

        def cleanup() -> None:
            while not stopped.wait(min(60, sessions.ttl_seconds)):
                sessions.prune()

        worker = threading.Thread(target=cleanup, name="session-cleanup", daemon=True)
        worker.start()
        if voice.model_dir:
            threading.Thread(target=voice.load, name="local-voice-load", daemon=True).start()
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
        if require_models and voice.status != "ready":
            raise HTTPException(status_code=503, detail="Локальная модель голоса ещё не готова")
        return {"status": "ok"}

    @app.get("/api/visitor-country")
    def country_from_ip(request: Request) -> JSONResponse:
        return JSONResponse(visitor_country(request.client.host if request.client else None),
                            headers={"Cache-Control": "no-store"})

    def city_for_request(request: Request) -> dict:
        local_preview = (os.getenv("ODIN_LOCAL_PREVIEW_IP") == "1" and
                         request.url.hostname in {"127.0.0.1", "localhost", "::1"})
        return visitor_city(request.client.host if request.client else None, local_preview=local_preview)

    @app.get("/api/visitor-city")
    def city_info(request: Request) -> JSONResponse:
        return JSONResponse(city_for_request(request), headers={"Cache-Control": "no-store"})

    @app.get("/api/map/catalog")
    def map_info() -> dict:
        try:
            return map_catalog.catalogue()
        except (FileNotFoundError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Каталог карты недоступен") from exc

    @app.get("/api/map/countries")
    def map_countries() -> dict:
        try:
            return map_catalog.countries()
        except (FileNotFoundError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Каталог карты недоступен") from exc

    @app.get("/api/map/destinations")
    def map_destinations() -> dict:
        try:
            return map_catalog.destinations()
        except (FileNotFoundError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Каталог карты недоступен") from exc

    @app.get("/api/map/points")
    def map_points(kind: Literal["hotel", "airport", "beach", "city", "camping", "all"] = "hotel",
                   west: float = -180, south: float = -90, east: float = 180, north: float = 90,
                   cursor: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=1000),
                   country_code: str | None = None, destination_id: str | None = None) -> dict:
        try:
            return map_catalog.points(kind, west, south, east, north, cursor, limit,
                                      country_code=country_code, destination_id=destination_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (FileNotFoundError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Каталог карты недоступен") from exc

    @app.get("/api/map/point/{point_id}")
    def map_point(point_id: str) -> dict:
        try:
            point = map_catalog.lookup(point_id)
        except (FileNotFoundError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Каталог карты недоступен") from exc
        if point is None:
            raise HTTPException(status_code=404, detail="Точка отсутствует в каталоге")
        return point

    @app.get("/api/map/clusters")
    def map_clusters(kind: Literal["hotel", "airport", "beach", "city", "camping", "all"] = "hotel",
                     west: float = -180, south: float = -90, east: float = 180, north: float = 90,
                     zoom: int = Query(3, ge=0, le=8), country_code: str | None = None,
                     destination_id: str | None = None) -> dict:
        try:
            return map_catalog.clusters(kind, west, south, east, north, zoom,
                                        country_code=country_code, destination_id=destination_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (FileNotFoundError, OSError) as exc:
            raise HTTPException(status_code=503, detail="Каталог карты недоступен") from exc

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

    @app.get("/api/voice")
    def voice_info(response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return {"backend": "gigaam" if voice.model_dir else "browser", "status": voice.status,
                "max_seconds": 20}

    @app.post("/api/voice/transcribe")
    async def transcribe_voice(request: Request, response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
        if voice.status != "ready":
            raise HTTPException(status_code=503, detail="Локальное распознавание пока недоступно")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_AUDIO_BYTES:
                raise HTTPException(status_code=413, detail="Аудио слишком длинное")
        try:
            transcript = await run_in_threadpool(voice.transcribe, bytes(raw))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log.warning("Speech recognition failed: %s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Распознавание не удалось") from exc
        return {"text": transcript, "backend": "gigaam"}

    def present(session_id, session, step, started):
        state = session.state
        breaker = getattr(agent.llm, "breaker", None)
        reply = step.reply
        if session.last_nlu in {"rules", "none"} and breaker and breaker.state in {"degraded", "down"}:
            reply += "\n\nЯзыковая модель временно недоступна; ответ подготовлен по правилам."
        summary = state.model_dump(mode="json", include={"origin", "origin_inferred", "date_from", "date_to", "nights",
            "adults", "children", "children_ages", "budget_total", "transport", "trip_types", "selected_event"})
        summary["destination"] = BY_ID[state.dest_id].name if state.dest_id else state.destination or state.country
        return {"session_id": session_id, "reply": reply, "payload": images.decorate(step.payload),
            "stage": state.stage, "understood": understood(state), "assumptions": state.assumptions,
            "nlu": session.last_nlu, "suggestions": contextual_suggestions(state, step),
            "trip_summary": summary, "revision": session.ui_revision,
            "can_undo": bool(session.ui_previous) and chat_navigation.can_snapshot(session),
            "checked": ["Неподтверждённый параметр отклонён или исправлен."] * len(session.last_notes),
            "ms": round((time.perf_counter() - started) * 1000)}

    def check_navigation(session, revision):
        if revision != session.ui_revision or not session.ui_previous or not chat_navigation.can_snapshot(session):
            raise HTTPException(status_code=409, detail="Этот шаг уже нельзя изменить. Уточните условия в чате.")

    @app.post("/api/session")
    def resume_session(body: ResetIn, response: Response):
        """Read current state; never replay a message, checkout or payment."""
        response.headers["Cache-Control"] = "no-store"
        session = sessions.existing(body.session_id)
        with session.lock:
            step = session.last or Step("Расскажите о поездке.", payload={"kind": "greeting"})
            return present(body.session_id, session, step, time.perf_counter())

    @app.post("/api/trip/transfer")
    def change_transfer(body: TransferIn, response: Response):
        response.headers["Cache-Control"] = "no-store"
        session = sessions.existing(body.session_id)
        with session.lock:
            state = session.state
            if (session.ui_revision != body.revision or state.stage != "cart" or
                    state.order or state.pending_trip_candidate or not session.last or
                    not isinstance(session.last.payload, dict) or session.last.payload.get("kind") != "cart"):
                raise HTTPException(status_code=409, detail="Откройте выбранную поездку ещё раз, чтобы изменить трансфер.")
            # Preserve the chosen hotel; change only the ground-transport preference.
            state.hotel_id = session.last.payload["package"]["hotel"]["id"]
            state.transfer_kind = None if body.kind == "auto" else body.kind
            state.params_changed = True
            state.act = {}
            session.last = agent.domain.step(state)
            session.last_nlu, session.last_notes = "action", []
            chat_navigation.complete_turn(session, None)
            return present(body.session_id, session, session.last, time.perf_counter())

    @app.post("/api/chat/undo")
    def undo_chat(body: NavigateIn, response: Response):
        started = time.perf_counter()
        response.headers["Cache-Control"] = "no-store"
        session = sessions.existing(body.session_id)
        with session.lock:
            check_navigation(session, body.revision)
            step = chat_navigation.undo(session)
            return present(body.session_id, session, step, started)

    @app.post("/api/chat/edit")
    def edit_chat(body: EditIn, response: Response):
        started = time.perf_counter()
        response.headers["Cache-Control"] = "no-store"
        session = sessions.existing(body.session_id)
        with session.lock:
            check_navigation(session, body.revision)
            proposed = chat_navigation.candidate(session)
            step = agent.handle(proposed, body.text)
            if proposed.last_nlu == "none":
                raise HTTPException(status_code=422, detail="Проверьте текст сообщения и попробуйте снова.")
            previous = session.ui_previous
            session.state, session.last = proposed.state, proposed.last
            session.last_nlu, session.last_notes = proposed.last_nlu, proposed.last_notes
            session.history = []
            chat_navigation.complete_turn(session, previous)
            return present(body.session_id, session, step, started)

    @app.post("/api/chat")
    def chat(body: ChatIn, response: Response, request: Request) -> dict:
        started = time.perf_counter()
        session_id, session = sessions.get(body.session_id)
        response.headers["Cache-Control"] = "no-store"
        with session.lock:
            guessed_origin = None
            if not session.location_checked:
                session.location_checked = True
                location = city_hint(body.detected_city) if body.detected_city else city_for_request(request)
                if location.get("origin"):
                    guessed_origin = location["origin"]
                    session.state.origin = guessed_origin
                    session.state.origin_inferred = True
                elif location.get("city_name"):
                    session.state.ip_city_hint = location["city_name"]
            previous = chat_navigation.snapshot(session)
            selected = None
            if sum(bool(value) for value in (body.map_point_id, body.map_country_code, body.map_city_id, body.destination_id, body.event_id)) > 1:
                raise HTTPException(status_code=422, detail="Выберите один объект карты")
            if body.event_id:
                step, selected = choose_event(agent, session, body.event_id)
            elif body.destination_id:
                dest = BY_ID.get(body.destination_id)
                if dest is None:
                    raise HTTPException(status_code=422, detail="Направление отсутствует в каталоге")
                if session.state.order or session.state.pending_trip_candidate or session.state.stage in {"payment", "booked"}:
                    raise HTTPException(status_code=409, detail="Начните новую поездку, чтобы выбрать другое направление.")
                # A catalog ID is a structured action, not a natural-language
                # utterance. Free-form messages still use the full privacy path.
                session.state = agent.domain.merge(session.state, TripUpdate(destination=dest.id))
                step = agent.domain.step(session.state)
                session.last, session.last_nlu, session.last_notes = step, "action", []
                selected = {"id": dest.id, "name": dest.name, "accepted": session.state.dest_id == dest.id}
            elif body.map_point_id:
                point = map_catalog.lookup(body.map_point_id)
                if not point or point["kind"] != "hotel" or not body.map_point_id.startswith("overture:"):
                    raise HTTPException(status_code=422, detail="Не найден выбранный отель")
                dest_id = point.get("destination_id")
                record_id = body.map_point_id.removeprefix("overture:")
                record = next((item for item in _real().get("hotels", {}).get(dest_id, [])
                               if item.get("id") == record_id), None)
                if (dest_id not in BY_ID or not record or
                    abs(record["lat"] - point["lat"]) > 1e-6 or abs(record["lon"] - point["lon"]) > 1e-6):
                    raise HTTPException(status_code=422, detail="Отель отсутствует в каталоге подбора")
                state = session.state
                selected = {"id": body.map_point_id, "name": point["name"], "accepted": False}
                if state.order or state.pending_trip_candidate or (state.dest_id and state.dest_id != dest_id):
                    step = Step("У вас уже есть другая поездка или открытый заказ. Начните новую поездку, "
                                "затем выберите этот отель на карте.")
                else:
                    def pin_hotel(merged: BaseModel) -> None:
                        if merged.dest_id == dest_id and not merged.act.get("ask_trip_choice"):
                            merged.hotel_id = f"{dest_id}-h{record_id}"
                            merged.selected_real_hotel = {
                                "id": point["id"], "name": point["name"],
                                "address": point.get("address"), "destination_id": dest_id,
                                "lat": point["lat"], "lon": point["lon"],
                            }
                            merged.showing, merged.real_hotels_shown = None, []
                            merged.lodging = "hotel"
                            merged.package = None
                            merged.params_changed = True
                            selected["accepted"] = True
                    # Only the server's known destination enters NLU. The map
                    # record's name is display data, not an instruction.
                    step = agent.handle(session, f"Хочу в {BY_ID[dest_id].name}", after_merge=pin_hotel)
                    selected["accepted"] = selected["accepted"] and session.state.hotel_id == f"{dest_id}-h{record_id}"
                    if selected["accepted"]:
                        step.reply = f"Выбран отель «{point['name']}». Наличие и цена не проверены.\n\n" + step.reply
                    else:
                        step.reply = "Не удалось закрепить отель. Уточните направление и выберите его ещё раз.\n\n" + step.reply
            elif body.map_city_id:
                point = map_catalog.lookup(body.map_city_id)
                if not point or point["kind"] != "city" or not point["source_id"]:
                    raise HTTPException(status_code=422, detail="Город не найден")
                # Match a demo destination only when its geographic alias is
                # the same GeoNames record, not merely a similar name.
                matches = [dest for dest in DESTINATIONS
                           if map_catalog._destination_country(dest) == point["country_code"]
                           and any(str(place.id) == point["source_id"] for place in find_world_places(dest.name))]
                dest = matches[0] if len(matches) == 1 else None
                state = session.state
                selected = {"id": body.map_city_id, "name": point["name"], "accepted": False}
                if (state.order or state.pending_trip_candidate or
                    (state.dest_id and (dest is None or state.dest_id != dest.id)) or
                    (state.destination and not state.dest_id and state.destination != point["name"]) or
                    (state.country and state.country != point["country_name"])):
                    step = Step("У вас уже есть другая поездка или открытый заказ. Начните новую поездку, "
                                "затем выберите этот город на карте.")
                elif dest:
                    step = agent.handle(session, f"Хочу в {dest.name}")
                    selected["accepted"] = session.state.dest_id == dest.id
                    if selected["accepted"]:
                        step.reply = f"Выбран город: {point['name']}, {point['country_name']}.\n\n" + step.reply
                    else:
                        step.reply = "Не удалось выбрать город. Попробуйте ещё раз.\n\n" + step.reply
                else:
                    def choose_city(merged: BaseModel) -> None:
                        if not merged.act.get("ask_trip_choice"):
                            merged.dest_id = merged.hotel_id = merged.package = None
                            merged.selected_real_hotel, merged.real_hotels_shown = None, []
                            merged.destination = point["name"]
                            merged.country = point["country_name"]
                            merged.place_country = point["country_name"]
                            merged.map_place = {"id": point["id"], "name": point["name"],
                                                "country": point["country_name"], "lat": point["lat"], "lon": point["lon"]}
                            merged.params_changed = True
                            selected["accepted"] = True
                    step = agent.handle(session, "Хочу поехать", after_merge=choose_city)
                    selected["accepted"] = selected["accepted"] and session.state.map_place is not None
                    if selected["accepted"] and (not isinstance(step.payload, dict) or step.payload.get("kind") != "place_info"):
                        step.reply = f"Выбран город: {point['name']}, {point['country_name']}.\n\n" + step.reply
                    elif not selected["accepted"]:
                        step.reply = "Не удалось выбрать город. Попробуйте ещё раз.\n\n" + step.reply
            elif body.map_country_code:
                code = body.map_country_code.upper()
                country = map_catalog._countries().get(code)
                if not country:
                    raise HTTPException(status_code=422, detail="Страна не найдена")
                state = session.state
                selected = {"code": code, "name": country, "accepted": False}
                if (state.order or state.pending_trip_candidate or (state.destination and not state.dest_id) or
                    (state.dest_id and BY_ID[state.dest_id].country != country)):
                    step = Step("У вас уже есть другая поездка или открытый заказ. Начните новую поездку, "
                                "затем выберите эту страну на карте.")
                else:
                    def choose_country(merged: BaseModel) -> None:
                        if not merged.act.get("ask_trip_choice"):
                            merged.country = country
                            merged.country_conflict = None
                            merged.excluded_countries = [item for item in (merged.excluded_countries or []) if item != country]
                            merged.params_changed = True
                            selected["accepted"] = True
                    step = agent.handle(session, "Хочу поехать", after_merge=choose_country)
                    selected["accepted"] = selected["accepted"] and session.state.country == country
                    if selected["accepted"]:
                        step.reply = f"Выбрана страна: {country}.\n\n" + step.reply
                    else:
                        step.reply = "Не удалось выбрать страну. Попробуйте ещё раз.\n\n" + step.reply
            else:
                step = agent.handle(session, body.text)
            # The approximate origin is already exposed as an editable chip.
            # Avoid repeating the geolocation notice in the conversation.
            chat_navigation.complete_turn(session, previous)
            result = present(session_id, session, step, started)
            result["map_selection"] = selected
            return result

    @app.post("/api/reset")
    def reset(body: ResetIn, response: Response) -> dict:
        response.headers["Cache-Control"] = "no-store"
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
