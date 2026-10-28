"""User-visible history must rewind the server state, not just DOM messages."""
import pytest
from fastapi.testclient import TestClient

from apps.web import build_app
from apps import chat_navigation
from core.agent import Session, Step
from domains.trips.state import TripState


@pytest.fixture
def client():
    with TestClient(build_app()) as test_client:
        yield test_client


def chat(client, text, previous=None):
    response = client.post('/api/chat', json={'text': text, 'session_id': previous and previous['session_id']})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def nav_body(data, **kwargs):
    return {'session_id': data['session_id'], 'revision': data['revision'], **kwargs}


def test_undo_restores_conditions_and_rejects_double_undo(client):
    first = chat(client, 'Хочу в Казань')
    second = chat(client, 'из Москвы', first)
    assert second['trip_summary']['origin'] == 'Москва'
    result = client.post('/api/chat/undo', json=nav_body(second))
    assert result.status_code == 200
    restored = result.json()
    assert restored['trip_summary'] == first['trip_summary']
    assert restored['stage'] == first['stage']
    assert restored['can_undo'] is False
    assert client.post('/api/chat/undo', json=nav_body(second)).status_code == 409
    assert chat(client, 'из Санкт-Петербурга', restored)['trip_summary']['origin'] == 'Санкт-Петербург'


def test_edit_replaces_only_latest_turn(client):
    first = chat(client, 'Хочу в Казань')
    second = chat(client, 'из Москвы', first)
    edited = client.post('/api/chat/edit', json=nav_body(second, text='из Санкт-Петербурга'))
    assert edited.status_code == 200
    result = edited.json()
    assert result['trip_summary']['destination'] == 'Казань'
    assert result['trip_summary']['origin'] == 'Санкт-Петербург'
    assert result['revision'] > second['revision']
    assert client.post('/api/chat/edit', json=nav_body(second, text='из Москвы')).status_code == 409
    undone = client.post('/api/chat/undo', json=nav_body(result)).json()
    assert undone['trip_summary'] == first['trip_summary']


def test_rejected_edit_does_not_erase_valid_turn(client):
    first = chat(client, 'Хочу в Казань')
    second = chat(client, 'из Москвы', first)
    assert client.post('/api/chat/edit', json=nav_body(second, text='')).status_code == 422
    assert client.post('/api/chat/edit', json=nav_body(second, text='x' * 6000)).status_code == 422
    result = client.post('/api/chat/undo', json=nav_body(second))
    assert result.status_code == 200
    assert result.json()['trip_summary'] == first['trip_summary']


def test_new_session_and_reset_have_no_recoverable_history(client):
    first = chat(client, 'Хочу в Казань')
    undone = client.post('/api/chat/undo', json=nav_body(first)).json()
    assert undone['stage'] == 'start'
    assert undone['understood'] == []
    assert undone['payload']['kind'] == 'greeting'
    client.post('/api/reset', json={'session_id':first['session_id']})
    assert client.post('/api/chat/undo', json=nav_body(first)).status_code == 404
    assert client.post('/api/chat/edit', json={'session_id':'missing','revision':1,'text':'из Москвы'}).status_code == 404


@pytest.mark.parametrize('stage', ['cart', 'payment', 'booked'])
def test_checkout_drops_undo_snapshot(stage):
    session = Session(state=TripState(stage='plan', destination='Казань'))
    before = chat_navigation.snapshot(session)
    session.state.stage = stage
    chat_navigation.complete_turn(session, before)
    assert session.ui_previous is None


def test_snapshot_is_independent_and_contains_no_raw_message_history():
    session = Session(state=TripState(destination='Казань'), last=Step('Уточним даты'))
    session.history = [{'role':'user','content':'text only in active session'}]
    before = chat_navigation.snapshot(session)
    session.state.destination = 'Сочи'
    session.last.reply = 'Changed'
    assert before[0].destination == 'Казань'
    assert before[1].reply == 'Уточним даты'
    assert 'text only in active session' not in repr(before)
