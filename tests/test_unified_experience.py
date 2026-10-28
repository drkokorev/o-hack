"""Cross-branch contracts: exact map selections, source hotels and chat history."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from apps.web import build_app
from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.map_catalog import hotels_in_destination
from tests.conftest import FakeLLM


@pytest.fixture
def client():
    today = lambda: date(2026, 10, 28)
    with TestClient(build_app(Agent(TripsDomain(today=today), None, today=today))) as client:
        yield client


def post(client, text, previous=None, **extra):
    response = client.post('/api/chat', json={
        'text': text, 'session_id': previous and previous['session_id'], **extra})
    assert response.status_code == 200
    return response.json()


def undo(client, result):
    response = client.post('/api/chat/undo', json={
        'session_id': result['session_id'], 'revision': result['revision']})
    assert response.status_code == 200
    return response.json()


def test_map_hotel_replaces_source_selection_and_undo_restores_it(client):
    first = post(client, 'В Ярославль, покажи реальные отели')
    records = first['payload']['items']
    selected = post(client, '1', first)
    assert 'отель: ' + records[0]['name'] in selected['understood']
    mapped = post(client, 'Выбираю отель на карте', selected, map_point_id=records[1]['id'])
    assert mapped['map_selection']['accepted'] is True
    assert 'отель: ' + records[1]['name'] in mapped['understood']
    assert 'отель: ' + records[0]['name'] not in mapped['understood']
    restored = undo(client, mapped)
    assert restored['understood'] == selected['understood']
    planned = post(client, 'Из Москвы с 10 по 14 июля 2027, двое взрослых, поездом', restored)
    expected = 'yaroslavl-h' + records[0]['id'].removeprefix('overture:')
    assert planned['payload']['kind'] == 'packages'
    assert all(item['hotel']['id'] == expected for item in planned['payload']['items'])


def test_followup_keeps_map_hotel_identity_and_summary(client):
    record = hotels_in_destination('yaroslavl')[1]
    mapped = post(client, 'Выбираю отель', map_point_id=record['id'])
    planned = post(client, 'Из Москвы с 10 по 14 июля 2027, двое взрослых, поездом', mapped)
    assert 'отель: ' + record['name'] in planned['understood']
    assert planned['trip_summary']['destination'] == 'Ярославль'
    expected = 'yaroslavl-h' + record['id'].removeprefix('overture:')
    assert all(item['hotel']['id'] == expected for item in planned['payload']['items'])


def test_undo_exact_city_and_edit_previous_text(client):
    first = post(client, 'Из Москвы')
    mapped = post(client, 'Выбираю город', first, map_city_id='geonames:3514674')
    assert mapped['payload']['place']['id'] == 'geonames:3514674'
    restored = undo(client, mapped)
    assert restored['trip_summary'] == first['trip_summary']
    next_turn = post(client, 'В Казань', restored)
    edited = client.post('/api/chat/edit', json={
        'session_id': next_turn['session_id'], 'revision': next_turn['revision'], 'text': 'В Сочи'})
    assert edited.status_code == 200
    assert edited.json()['trip_summary']['destination'] == 'Сочи'
    assert edited.json()['trip_summary']['origin'] == 'Москва'


def test_edited_message_is_masked_at_model_boundary():
    today = lambda: date(2026, 10, 28)
    llm = FakeLLM({}, {}, {})
    agent = Agent(TripsDomain(today=today), llm, today=today)
    with TestClient(build_app(agent)) as client:
        first = post(client, 'Хочу в Казань')
        second = post(client, 'Из Москвы', first)
        edited = client.post('/api/chat/edit', json={
            'session_id': second['session_id'], 'revision': second['revision'],
            'text': 'Из Санкт-Петербурга, почта synthetic.person@example.com'})
        assert edited.status_code == 200
        assert edited.json()['trip_summary']['origin'] == 'Санкт-Петербург'
        assert llm.calls
        assert 'synthetic.person@example.com' not in str(llm.calls)
