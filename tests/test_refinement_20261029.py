from datetime import date
from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.web import build_app
from apps.weather import forecast
from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.geo import BY_ID
from domains.trips.dialogue import ideas
from domains.trips.state import TripState

TODAY=date(2026,10,29)
def client():
    return TestClient(build_app(Agent(TripsDomain(today=lambda:TODAY),None,today=lambda:TODAY)))

def test_range_preserves_trip_and_invalid_range_is_not_applied():
    with client() as c:
        first=c.post('/api/chat',json={'text':'В Казань из Москвы с 15 по 22 ноября 2026, двое взрослых, бюджет 150000 рублей, поездом'}).json()
        old=first['trip_summary']
        changed=c.post('/api/chat',json={'session_id':first['session_id'],'text':'Меняю даты','date_range':{'start':'2026-12-05','end':'2026-12-12'}})
        assert changed.status_code==200
        after=changed.json()['trip_summary']
        assert after['date_from']=='2026-12-05' and after['date_to']=='2026-12-12' and after['nights']==7
        for key in ['origin','destination','adults','children','budget_total','transport']:
            assert after[key]==old[key],key
        for dates in [{'start':'2026-12-12','end':'2026-12-05'},{'start':'2020-01-01','end':'2020-01-02'},{'start':'111111-11-11','end':'2026-12-12'}]:
            assert c.post('/api/chat',json={'session_id':first['session_id'],'text':'Меняю даты','date_range':dates}).status_code==422
            assert c.post('/api/session',json={'session_id':first['session_id']}).json()['trip_summary']==after
        budget=c.post('/api/chat',json={'session_id':first['session_id'],'text':'Бюджет 170000 рублей'}).json()['trip_summary']
        assert budget['date_from']==after['date_from'] and budget['date_to']==after['date_to']
        assert budget['destination']==after['destination'] and budget['adults']==after['adults']

def test_browser_preferences_filter_and_prioritize_without_overriding_requirements():
    baseline=ideas(TripState()).payload['items']
    favorite=baseline[2]['id'];hidden=baseline[0]['id']
    result=ideas(TripState(ui_preferences={'saved':[favorite],'hidden':[hidden]})).payload['items']
    assert result[0]['id']==favorite and hidden not in {v['id'] for v in result}
    constrained=ideas(TripState(country='Россия',ui_preferences={'saved':['paris'],'hidden':[]})).payload['items']
    assert all(v['country']=='Россия' for v in constrained)

def test_hidden_hotels_are_not_returned_on_next_recommendation():
    with client() as c:
        body={'text':'В Казань из Москвы с 15 по 22 ноября 2026, двое взрослых, бюджет 150000 рублей, поездом'}
        first=c.post('/api/chat',json=body).json()
        assert first['payload']['kind']=='packages'
        hidden=first['payload']['items'][0]['hotel']['id']
        body['preferences']={'saved':[],'hidden':['hotel:'+hidden]}
        second=c.post('/api/chat',json=body).json()
        assert second['payload']['kind']=='packages'
        assert all(v['hotel']['id']!=hidden for v in second['payload']['items'])

def test_forecast_horizon_and_validation():
    dest=next(iter(BY_ID.values()))
    with patch('apps.weather._fetch') as fetch:
        assert forecast(dest,date(2027,6,1),date(2027,6,8),TODAY)=={'status':'later'}
        fetch.assert_not_called()
    data={'time':['2026-10-30','2026-10-31'],'temperature_2m_max':[10,12],'temperature_2m_min':[3,5]}
    with patch('apps.weather._fetch',return_value=data):
        result=forecast(dest,date(2026,10,30),date(2026,11,1),TODAY)
        assert result['status']=='forecast' and result['day']==11 and result['night']==4
    with patch('apps.weather._fetch',return_value={**data,'time':['2020-01-01']}):
        assert forecast(dest,date(2026,10,30),date(2026,11,1),TODAY)['status']=='unavailable'

def test_origin_hint_remains_internal():
    with client() as c:
        data=c.post('/api/chat',json={'text':'Хочу в Казань','detected_city':'Moscow'}).json()
        assert data['trip_summary']['origin']=='Москва'
        assert data['trip_summary']['origin_inferred'] is True
        assert 'по IP' not in ' '.join(data['understood'])
