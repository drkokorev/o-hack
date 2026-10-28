"""Check the integrated application over HTTP; all requests use synthetic data."""
import argparse
import json
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8080')
    parser.add_argument('--voice', choices=('gigaam', 'browser'), default='gigaam')
    args = parser.parse_args()
    base = args.url.rstrip('/')

    def get(path):
        with urlopen(base + path, timeout=20) as response:
            return json.load(response), response.headers

    def chat(text, session=None):
        body = json.dumps({'text': text, 'session_id': session}, ensure_ascii=False).encode('utf-8')
        request = Request(base + '/api/chat', data=body, headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=20) as response:
            return json.load(response), response.headers

    catalog, _ = get('/api/map/catalog')
    destinations, _ = get('/api/map/destinations')
    clusters, _ = get('/api/map/clusters?kind=all&zoom=3')
    country, country_headers = get('/api/visitor-country')
    voice, _ = get('/api/voice')
    first, headers = chat('Хочу в Казань')
    second, _ = chat('На 7 дней', first['session_id'])
    changed, _ = chat('Передумал, хочу в Дубай', first['session_id'])
    checks = {
        'catalog_counts': catalog['counts'] == {'airport': 48101, 'beach': 7866, 'camping': 8, 'city': 161662, 'hotel': 65924},
        'catalog_destinations_and_clusters': len(destinations['items']) == 75 and sum(x['count'] for x in clusters['items']) == 283561,
        'visitor_country_no_cache_or_ip': country_headers.get('Cache-Control') == 'no-store' and 'ip' not in country,
        'voice_backend': voice == {'backend': args.voice, 'status': 'ready' if args.voice == 'gigaam' else 'off', 'max_seconds': 20},
        'chat_no_cache': headers.get('Cache-Control') == 'no-store',
        'duration_and_changed_destination': second['trip_summary']['destination'] == 'Казань' and
            changed['trip_summary']['destination'] == 'Дубай' and 'поездка: 7 дней' in changed['understood'],
    }
    with urlopen(base + '/', timeout=20) as response:
        html = response.read().decode('utf-8')
    with urlopen(base + '/static/reply-text.js', timeout=20) as response:
        script = response.read().decode('utf-8')
    checks['complete_reply_script_shipped'] = '/static/reply-text.js' in html and 'renderTravelReply' in script
    print(json.dumps(checks, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
