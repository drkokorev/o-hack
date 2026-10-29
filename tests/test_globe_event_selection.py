"""Map actions preserve trip intent and reject stale or conflicting events."""
from datetime import date
from fastapi.testclient import TestClient
from apps.web import build_app
from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.state import TripState


def client_at(day=date(2026, 10, 29)):
    return TestClient(build_app(Agent(TripsDomain(today=lambda: day), None, today=lambda: day)))


def test_event_does_not_invent_stay_dates_and_resumes_exact_context():
    with client_at() as client:
        response = client.post('/api/chat', json={'text':'хочу на событие','event_id':'global-village','detected_city':'Moscow'})
        assert response.status_code == 200
        first = response.json()
        summary = first['trip_summary']
        assert summary['destination'] == 'Дубай'
        assert summary['selected_event']['id'] == 'global-village'
        assert summary['date_from'] is None and summary['date_to'] is None
        assert 'Билеты на событие не включены' in first['reply']
        restored = client.post('/api/session', json={'session_id':first['session_id']}).json()
        assert restored['trip_summary'] == summary
        assert restored['revision'] == first['revision']


def test_event_preserves_existing_dates_and_budget():
    with client_at() as client:
        first = client.post('/api/chat', json={'text':'В Дубай из Москвы с 1 по 8 июня 2027, двое взрослых, бюджет 200 тысяч рублей'}).json()
        after = client.post('/api/chat', json={'session_id':first['session_id'],'text':'на событие','event_id':'global-village'}).json()
        for key in ('date_from','date_to','budget_total','origin','adults'):
            assert after['trip_summary'][key] == first['trip_summary'][key]
        assert 'не совпадают' in after['reply']


def test_changing_destination_clears_event_context():
    with client_at() as client:
        first = client.post('/api/chat', json={'text':'событие','event_id':'global-village'}).json()
        after = client.post('/api/chat', json={'session_id':first['session_id'],'text':'город','destination_id':'kazan'}).json()
        assert after['trip_summary']['destination'] == 'Казань'
        assert after['trip_summary']['selected_event'] is None


def test_invalid_or_expired_event_does_not_change_existing_trip():
    with client_at(date(2028, 1, 1)) as client:
        first = client.post('/api/chat', json={'text':'Хочу в Казань'}).json()
        for event_id in ('missing-event','global-village'):
            response = client.post('/api/chat', json={'session_id':first['session_id'],'text':'событие','event_id':event_id})
            assert response.status_code == 422
            restored = client.post('/api/session', json={'session_id':first['session_id']}).json()
            assert restored['trip_summary'] == first['trip_summary']
            assert restored['revision'] == first['revision']


def test_ambiguous_map_action_is_rejected():
    with client_at() as client:
        response = client.post('/api/chat', json={'text':'выбрать','event_id':'global-village','destination_id':'kazan'})
        assert response.status_code == 422


def test_suggest_for_me_is_an_explicit_delegation_without_invented_dates():
    update = rule_extract(TripState(), 'Предложи сам', date(2026, 10, 29))
    assert update.unsure is True
    assert update.date_from is None and update.nights is None
