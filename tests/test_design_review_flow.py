"""Regression coverage for exact UI actions, safe resume and transfer changes."""
from fastapi.testclient import TestClient
import pytest

from apps.web import build_app
from core import agent as agent_module


@pytest.fixture
def client():
    with TestClient(build_app()) as client:
        yield client


def start(client):
    response = client.post('/api/chat', json={'text': 'Хочу на море из Москвы на 7 ночей с 15 июня 2027, двое взрослых, бюджет 180 тысяч рублей на всю поездку, без визы.'})
    assert response.status_code == 200
    return response.json()


def select(client, data):
    dest = next(p for p in client.get('/api/info').json()['places'] if p['name'] == 'Анталья')
    response = client.post('/api/chat', json={'session_id': data['session_id'], 'text': 'Хочу в Анталья', 'destination_id': dest['id']})
    assert response.status_code == 200
    return response.json()


def basket(client):
    chosen = select(client, start(client))
    assert chosen['payload']['kind'] == 'packages'
    response = client.post('/api/chat', json={'session_id': chosen['session_id'], 'text': 'беру 1 вариант'})
    assert response.status_code == 200
    result = response.json()
    assert result['payload']['kind'] == 'cart'
    return result


def test_exact_destination_does_not_depend_on_name_recognition(client, monkeypatch):
    before = start(client)
    monkeypatch.setattr(agent_module, 'mask_sensitive_data', lambda *a, **k: (_ for _ in ()).throw(AssertionError('NLU must not parse a catalog selection')))
    after = select(client, before)
    assert after['map_selection']['accepted'] is True
    assert after['trip_summary']['destination'] == 'Анталья'
    for field in ['date_from','date_to','nights','adults','budget_total','origin']:
        assert after['trip_summary'][field] == before['trip_summary'][field]
    assert 'личные данные' not in after['reply']


def test_invalid_selection_and_reset_cannot_restore(client):
    first = start(client)
    response = client.post('/api/chat', json={'session_id':first['session_id'],'text':'город','destination_id':'missing'})
    assert response.status_code == 422
    response = client.post('/api/chat', json={'session_id':first['session_id'],'text':'город','destination_id':'antalya','map_country_code':'TR'})
    assert response.status_code == 422
    assert client.post('/api/session', json={'session_id':'missing'}).status_code == 404
    client.post('/api/reset', json={'session_id':first['session_id']})
    assert client.post('/api/session', json={'session_id':first['session_id']}).status_code == 404


def test_resume_reads_basket_without_advancing_or_checkout(client):
    before = basket(client)
    for _ in range(2):
        response = client.post('/api/session', json={'session_id':before['session_id']})
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        after = response.json()
        assert after['revision'] == before['revision']
        assert after['stage'] == 'cart'
        assert after['payload'] == before['payload']
        assert after['trip_summary'] == before['trip_summary']


def test_transfer_choice_preserves_trip_and_recalculates(client):
    before = basket(client)
    previous = before['payload']['package']
    response = client.post('/api/trip/transfer', json={'session_id':before['session_id'],'revision':before['revision'],'kind':'shuttle'})
    assert response.status_code == 200
    after = response.json()
    assert after['payload']['kind'] == 'cart'
    current = after['payload']['package']
    assert current['hotel']['id'] == previous['hotel']['id']
    assert current['out'] == previous['out']
    assert current['back'] == previous['back']
    assert after['trip_summary'] == before['trip_summary']
    assert current['transfer']['in']['kind'] == 'shuttle'
    assert current['transfer']['out']['kind'] == 'shuttle'
    old_ground = sum(previous['transfer'][key]['price_rub'] for key in ('in','out'))
    new_ground = sum(current['transfer'][key]['price_rub'] for key in ('in','out'))
    assert current['total_rub'] - previous['total_rub'] == new_ground - old_ground
    assert current['timeline'] != previous['timeline']
    assert client.post('/api/trip/transfer', json={'session_id':before['session_id'],'revision':before['revision'],'kind':'taxi'}).status_code == 409
    resumed = client.post('/api/session', json={'session_id':before['session_id']}).json()
    assert resumed['payload'] == after['payload']


def test_transfer_cannot_change_payment_state(client):
    before = basket(client)
    payment = client.post('/api/chat', json={'session_id':before['session_id'],'text':'да, оформляй'}).json()
    assert payment['stage'] == 'payment'
    assert client.post('/api/trip/transfer', json={'session_id':payment['session_id'],'revision':payment['revision'],'kind':'taxi'}).status_code == 409
    restored = client.post('/api/session', json={'session_id':payment['session_id']}).json()
    assert restored['stage'] == 'payment'
    assert restored['revision'] == payment['revision']
