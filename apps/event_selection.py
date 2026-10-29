"""An event selection is server-owned context, never client-supplied travel dates."""
import json
from datetime import date
from pathlib import Path

from fastapi import HTTPException
from core.agent import Step
from domains.trips.geo import DESTINATIONS
from domains.trips.state import TripUpdate


def choose_event(agent, session, event_id):
    data = json.loads((Path(__file__).parent / 'static/events.json').read_text(encoding='utf-8'))
    event = next((item for item in data['events'] if item['id'] == event_id), None)
    if not event or date.fromisoformat(event['end']) < agent.today():
        raise HTTPException(status_code=422, detail='Событие не найдено или уже завершилось')
    state = session.state
    if state.order or state.pending_trip_candidate or state.stage in {'payment', 'booked'}:
        raise HTTPException(status_code=409, detail='Начните новую поездку, чтобы выбрать событие.')
    # Exact city identity; never choose the closest unrelated destination.
    matches = [dest for dest in DESTINATIONS if dest.name == event['city'] and dest.country == event['country']]
    dest = matches[0] if len(matches) == 1 else None
    if not dest or event.get('destination_id') != dest.id:
        raise HTTPException(status_code=422, detail='Для этого события пока нет подбора поездки. Выберите другое событие.')
    candidate = agent.domain.merge(state.model_copy(deep=True), TripUpdate(destination=dest.id))
    state = candidate
    if state.pending_trip_candidate:
        raise HTTPException(status_code=409, detail='Сначала завершите изменение текущей поездки.')
    state.selected_event = {key: event[key] for key in ('id', 'name', 'city', 'country', 'start', 'end', 'dates', 'url')}
    # Event dates are not check-in/check-out dates. Existing dates remain intact.
    step = agent.domain.step(state)
    intro = f"Повод для поездки: {event['name']}, {event['city']} — {event['dates']}. Билеты на событие не включены."
    if state.date_from and state.date_to:
        if state.date_to < date.fromisoformat(event['start']) or state.date_from > date.fromisoformat(event['end']):
            intro += ' Текущие даты поездки не совпадают с событием. На какие дни перенесём поездку?'
        else:
            intro += ' Ваши даты поездки сохранены.'
    else:
        intro += ' На какие дни хотите поехать? Даты события не подставляю как даты проживания.'
    step.reply = intro + '\n\n' + step.reply
    session.state = state
    session.last, session.last_nlu, session.last_notes = step, 'action', []
    return step, {'id':event_id, 'name':event['name'], 'accepted':True}
