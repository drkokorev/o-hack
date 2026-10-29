"""Select the exact catalog city and apply the configured event-date policy."""
import json
from datetime import date, timedelta
from pathlib import Path

from fastapi import HTTPException
from core.agent import Step
from domains.trips.geo import DESTINATIONS
from domains.trips.state import TripUpdate
from domains.trips.policy_resources import dialogue_policy


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
    start, end = date.fromisoformat(event['start']), date.fromisoformat(event['end'])
    update = TripUpdate(destination=dest.id)
    # A short event is a useful explicit travel choice. Its final day is
    # inclusive; return the following day so a one-day event has a valid stay.
    # Long seasons and discontinuous programmes need actual visiting dates.
    continuous = ';' not in event['dates'] and ' и ' not in event['dates']
    short = continuous and (end - start).days + 1 <= dialogue_policy().event_autofill_max_days
    autofill = short and (not state.date_from or state.dates_assumed)
    if autofill:
        begin, finish = max(start, agent.today()), end + timedelta(days=1)
        update = update.model_copy(update={'date_from':begin, 'date_to':finish, 'nights':(finish-begin).days})
    candidate = agent.domain.merge(state.model_copy(deep=True), update)
    state = candidate
    if state.pending_trip_candidate:
        raise HTTPException(status_code=409, detail='Сначала завершите изменение текущей поездки.')
    state.selected_event = {key: event[key] for key in ('id', 'name', 'city', 'country', 'start', 'end', 'dates', 'url')}
    if autofill:
        state.dates_assumed = False
        state.trip_days_min = state.trip_days_max = None
    intro = f"Повод для поездки: {event['name']}, {event['city']} — {event['dates']}. Билеты на событие не включены."
    if autofill:
        intro += (f' Подставил город и даты поездки: {state.date_from:%d.%m.%Y}–{state.date_to:%d.%m.%Y}. '
                  'Возвращение — на следующий день после события; даты можно изменить в календаре или сообщением.')
        step = agent.domain.step(state)
    elif state.date_from and state.date_to:
        if state.date_to <= start or state.date_from > end:
            state.pending_question = 'when'
            step = Step('Текущие даты поездки не совпадают с событием. На какие дни перенесём поездку?',
                        payload={'kind':'question', 'field':'when'})
        else:
            intro += ' Ваши даты поездки сохранены.'
            step = agent.domain.step(state)
    else:
        state.pending_question = 'when'
        step = Step('Период события сохранён. Какие дни посещения вам подходят? Можно выбрать их в календаре.',
                    payload={'kind':'question', 'field':'when'})
    step.reply = intro + '\n\n' + step.reply
    session.state = state
    session.last, session.last_nlu, session.last_notes = step, 'action', []
    return step, {'id':event_id, 'name':event['name'], 'accepted':True}
