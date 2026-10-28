"""One-step navigation for planning only; never rewinds checkout or orders.

Keeps one structured snapshot under the session's existing lock and TTL.
No raw user utterances are added to server history.
"""
from copy import deepcopy

from core.agent import Session, Step

PLANNING_STAGES = {"start", "destination", "plan", "hotel_search", "flight_search", "transfer_search"}


def can_snapshot(session: Session) -> bool:
    state = session.state
    return (getattr(state, "stage", None) in PLANNING_STAGES
            and not getattr(state, "order", None)
            and not getattr(state, "past_orders", None))


def snapshot(session: Session):
    if not can_snapshot(session):
        return None
    return (session.state.model_copy(deep=True), deepcopy(session.last),
            session.last_nlu, list(session.last_notes))


def complete_turn(session: Session, previous) -> None:
    session.ui_previous = previous if can_snapshot(session) else None
    session.ui_revision += 1


def candidate(session: Session) -> Session:
    state, last, nlu, notes = session.ui_previous
    return Session(state=state.model_copy(deep=True), last=deepcopy(last),
                   last_nlu=nlu, last_notes=list(notes))


def undo(session: Session) -> Step:
    old = candidate(session)
    session.state, session.last = old.state, old.last
    session.last_nlu, session.last_notes = old.last_nlu, old.last_notes
    session.history = []
    session.ui_previous = None
    session.ui_revision += 1
    if session.last is None:
        session.last = Step("Куда хочется? Расскажите о месте, настроении или всей поездке сразу.",
                            payload={"kind": "greeting"})
    return session.last
