"""Веб-макет голосового ассистента клиники (кейс DBI).

Запуск: .venv/bin/uvicorn apps.web.server:app --port 8000
Голос распознаётся и синтезируется в браузере (Web Speech API); сервер работает только с текстом.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.agent import Agent, Session
from core.config import get_settings
from core.llm import OpenAICompatLLM
from domains.clinic.domain import GREETING, ClinicDomain
from domains.clinic.schedule import DEMO_PATIENTS, seed_demo_bookings

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Голосовой ассистент клиники — макет")


def _build() -> tuple[Agent, ClinicDomain]:
    settings = get_settings()
    llm = OpenAICompatLLM(settings) if settings.llm_enabled else None
    domain = ClinicDomain()
    seed_demo_bookings(domain.schedule)
    return Agent(domain, llm, nlg=settings.llm_nlg), domain


agent, domain = _build()
sessions: dict[str, Session] = {}


class MessageIn(BaseModel):
    session_id: str
    text: str


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.post("/api/session")
def new_session() -> dict:
    session_id = uuid.uuid4().hex
    sessions[session_id] = agent.new_session()
    settings = get_settings()
    return {
        "session_id": session_id,
        "greeting": GREETING,
        "nlu": settings.llm_model if agent.llm else "правила (LLM не подключена)",
        "demo_patients": list(DEMO_PATIENTS),
    }


@app.post("/api/message")
def message(body: MessageIn) -> dict:
    session = sessions.get(body.session_id)
    if session is None:
        raise HTTPException(404, "Сессия не найдена — начните новый звонок")
    started = time.perf_counter()
    step = agent.handle(session, body.text)
    return {
        "reply": step.reply,
        "done": step.done,
        "nlu": session.last_nlu,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "state": session.state.model_dump(mode="json", exclude_none=True,
                                          exclude={"offered", "target", "result"}),
    }


@app.get("/api/clinic")
def clinic() -> dict:
    schedule = domain.schedule
    return {
        "today": schedule.today.isoformat(),
        "doctors": [{"name": d.name, "specialty": d.specialty, "branch": d.branch, "schedule": d.describe()}
                    for d in schedule.doctors.values()],
        "bookings": [{"id": b.id, "patient": b.patient_name, "doctor": b.slot.doctor_name,
                      "specialty": b.slot.specialty, "branch": b.slot.branch,
                      "start": b.slot.start.isoformat(timespec="minutes")}
                     for b in sorted(schedule.bookings.values(), key=lambda b: b.slot.start)],
    }


@app.post("/api/reset")
def reset_demo() -> dict:
    """Возвращает расписание и записи к исходному состоянию демо."""
    global agent, domain
    agent, domain = _build()
    sessions.clear()
    return {"ok": True}
