from datetime import date
import ipaddress
from fastapi.testclient import TestClient
from apps import location
from apps.web import build_app
from core.agent import Agent
from domains.trips.domain import TripsDomain

def test_bundled_index_boundaries_and_missing_ranges():
    index=location.OriginIndex({'cities':['Москва','Казань'],'ipv4':[[100,110,0],[120,140,1]],'ipv6':[[2**64,2**64+8,1]]})
    for value,city in [(99,None),(100,'Москва'),(110,'Москва'),(111,None),(119,None),(120,'Казань'),(140,'Казань'),(141,None)]:
        record=index.get(str(ipaddress.IPv4Address(value)))
        assert (record['city']['names']['ru'] if record else None)==city
    assert index.get(str(ipaddress.IPv6Address(2**64)))['city']['names']['ru']=='Казань'

def test_departure_is_automatic_from_bundled_ip_data_and_manual_change_wins(monkeypatch):
    import urllib.request
    monkeypatch.delenv('ODIN_CITY_DATABASE',raising=False)
    location._city_reader.cache_clear()
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**k: (_ for _ in ()).throw(AssertionError('No network lookup')))
    reader=location._bundled_city_reader()
    assert reader is not None
    row=next(row for row in reader.ranges[4] if reader.cities[row[2]]=='Москва' and ipaddress.IPv4Address(row[0]).is_global)
    host=str(ipaddress.IPv4Address(row[0]))
    assert location.visitor_city(host)['origin']=='Москва'
    fixed=lambda:date(2026,10,29)
    with TestClient(build_app(Agent(TripsDomain(today=fixed),None,today=fixed)),client=(host,12345)) as c:
        first=c.post('/api/chat',json={'text':'Хочу в Казань с 5 по 12 декабря 2026, 2 взрослых'}).json()
        assert first['trip_summary']['origin']=='Москва' and first['trip_summary']['origin_inferred']
        assert 'по IP' not in ' '.join(first['understood']) and host not in str(first)
        corrected=c.post('/api/chat',json={'session_id':first['session_id'],'text':'Выезжаю из Самары'}).json()
        assert corrected['trip_summary']['origin']=='Самара'
    location._city_reader.cache_clear()
