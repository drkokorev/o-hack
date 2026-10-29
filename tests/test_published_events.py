"""Every published point must have a licensed cover and reach actual trip options."""
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from apps.web import build_app
from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID

ROOT = Path(__file__).resolve().parents[1]
EVENTS = json.loads((ROOT/'apps/static/events.json').read_text(encoding='utf-8'))['events']
TODAY = date(2026, 10, 29)


@pytest.mark.parametrize('event', EVENTS, ids=lambda e: e['id'])
def test_published_event_reaches_trip_options(event):
    dest = BY_ID[event['destination_id']]
    assert (dest.name, dest.country) == (event['city'], event['country'])
    photo = event['image']
    assert photo['kind'] == 'theme' and photo['credit'] and photo['page'].startswith('https://commons.wikimedia.org/')
    assert (ROOT/'apps'/photo['src'].lstrip('/')).read_bytes().startswith(b'\xff\xd8')
    assert len(event['description']) > 40
    agent = Agent(TripsDomain(today=lambda:TODAY), None, today=lambda:TODAY)
    with TestClient(build_app(agent)) as client:
        first = client.post('/api/chat', json={'text':'Хочу на событие', 'event_id':event['id']})
        assert first.status_code == 200
        initial = first.json()
        assert initial['trip_summary']['destination'] == event['city']
        assert initial['trip_summary']['date_from'] is None
        origin = 'Санкт-Петербурга' if dest.id == 'moscow' else 'Москвы'
        start = max(TODAY+timedelta(days=15), date.fromisoformat(event['start']))
        end = start+timedelta(days=3)
        answer = client.post('/api/chat', json={'session_id':initial['session_id'],
            'text':f'Из {origin}, двое взрослых, бюджет 1000000 рублей',
            'date_range':{'start':start.isoformat(), 'end':end.isoformat()}})
        # Date actions only amend dates; provide remaining facts as their own turn.
        assert answer.status_code == 200
        complete = client.post('/api/chat', json={'session_id':initial['session_id'],
            'text':f'Из {origin}, двое взрослых, бюджет 1000000 рублей'}).json()
        assert complete['trip_summary']['selected_event']['id'] == event['id']
        assert complete['trip_summary']['date_from'] == start.isoformat()
        assert complete['payload']['kind'] == 'packages', complete['reply']
        assert complete['payload']['items']


def test_unsupported_event_does_not_mutate_trip():
    agent=Agent(TripsDomain(today=lambda:TODAY),None,today=lambda:TODAY)
    with TestClient(build_app(agent)) as client:
        before=client.post('/api/chat',json={'text':'В Казань из Москвы'}).json()
        unsupported=dict(EVENTS[0],city='Неизвестный город',destination_id='missing')
        with patch('apps.event_selection.json.loads',return_value={'events':[unsupported]}):
            # Patch only while executing the action; the request parser uses json.loads too.
            from apps.event_selection import choose_event
            from fastapi import HTTPException
            from types import SimpleNamespace
            from domains.trips.state import TripState
            session=SimpleNamespace(state=TripState(destination='kazan',origin='MOW'))
            snapshot=session.state.model_dump()
            with pytest.raises(HTTPException) as exc:
                choose_event(agent,session,unsupported['id'])
            assert exc.value.status_code == 422
            assert session.state.model_dump() == snapshot
