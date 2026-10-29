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
        assert any('период события:' in chip for chip in first['understood'])
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


def test_short_event_populates_city_and_dates_in_one_action():
    with client_at() as client:
        result = client.post('/api/chat', json={'text':'Хочу на событие','event_id':'f2-abu-dhabi-2026'}).json()
        summary = result['trip_summary']
        assert summary['destination'] == 'Абу-Даби'
        assert summary['date_from'] == '2026-12-04'
        assert summary['date_to'] == '2026-12-07'
        assert summary['nights'] == 3
        assert 'следующий день' in result['reply']
        assert 'На какие дни' not in result['reply']
        restored = client.post('/api/session', json={'session_id':result['session_id']}).json()
        assert restored['trip_summary'] == summary


def test_event_dates_can_be_edited_and_undone_without_losing_event():
    with client_at() as client:
        first = client.post('/api/chat', json={'text':'Событие','event_id':'f2-abu-dhabi-2026'}).json()
        edited = client.post('/api/chat', json={'session_id':first['session_id'],'text':'Даты поездки',
                            'date_range':{'start':'2026-12-03','end':'2026-12-08'}}).json()
        assert edited['trip_summary']['date_from'] == '2026-12-03'
        assert edited['trip_summary']['selected_event']['id'] == 'f2-abu-dhabi-2026'
        restored = client.post('/api/chat/undo', json={'session_id':first['session_id'],
                                                     'revision':edited['revision']}).json()
        assert restored['trip_summary'] == first['trip_summary']


def test_ongoing_short_event_does_not_fill_past_arrival():
    with client_at(date(2026,12,5)) as client:
        result = client.post('/api/chat', json={'text':'Событие','event_id':'f2-abu-dhabi-2026'}).json()
        assert result['trip_summary']['date_from'] == '2026-12-05'
        assert result['trip_summary']['date_to'] == '2026-12-07'


def test_one_day_event_has_a_valid_overnight_range():
    with client_at() as client:
        result = client.post('/api/chat', json={'text':'Событие','event_id':'marathon-dubai'}).json()
        assert result['trip_summary']['destination'] == 'Дубай'
        assert result['trip_summary']['date_from'] == '2027-01-17'
        assert result['trip_summary']['date_to'] == '2027-01-18'
        assert result['trip_summary']['nights'] == 1


def test_discontinuous_programme_keeps_event_period_without_claiming_a_full_stay():
    with client_at() as client:
        result = client.post('/api/chat', json={'text':'Событие','event_id':'venice-street-show-2027'}).json()
        assert result['trip_summary']['destination'] == 'Венеция'
        assert result['trip_summary']['date_from'] is None
        assert result['trip_summary']['date_to'] is None
        assert result['payload']['field'] == 'when'
        assert result['reply'].count('?') == 1
