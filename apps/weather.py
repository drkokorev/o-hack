"""Small cached forecast adapter. Historical averages are never called forecasts."""
from datetime import date, timedelta
from functools import lru_cache
import httpx

@lru_cache(maxsize=128)
def _fetch(lat, lon, start, end, hour):
    response = httpx.get('https://api.open-meteo.com/v1/forecast', params={
        'latitude':lat,'longitude':lon,'daily':'temperature_2m_max,temperature_2m_min',
        'start_date':start,'end_date':end,'timezone':'auto'}, timeout=5)
    response.raise_for_status()
    return response.json().get('daily', {})

def forecast(destination, start: date, end: date, today: date):
    import time
    if start < today or end <= start:
        return {'status':'unavailable'}
    if start > today + timedelta(days=15):
        return {'status':'later'}
    last=min(end-timedelta(days=1),today+timedelta(days=15))
    try:
        data=_fetch(destination.lat,destination.lon,start.isoformat(),last.isoformat(),int(time.time()//3600))
        expected=[(start+timedelta(days=n)).isoformat() for n in range((last-start).days+1)]
        highs,lows=data.get('temperature_2m_max',[]),data.get('temperature_2m_min',[])
        if data.get('time')!=expected or len(highs)!=len(expected) or len(lows)!=len(expected) or any(not isinstance(v,(int,float)) for v in highs+lows):
            return {'status':'unavailable'}
        return {'status':'forecast','day':round(sum(highs)/len(highs)),'night':round(sum(lows)/len(lows)),
                'start':start.isoformat(),'end':last.isoformat(),'partial':last<end-timedelta(days=1),'source':'Open-Meteo','url':'https://open-meteo.com/'}
    except (httpx.HTTPError,ValueError,TypeError,KeyError):
        return {'status':'unavailable'}
