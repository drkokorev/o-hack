"""Synthetic HTTP replay of the reported flow against a model-enabled server."""
import argparse
import json
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:18763')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    texts = [
        'Хочу в горы, красивый вид и спокойные прогулки. Предложи направления.',
        'предложи сам', 'с 11.11.2027 по 11.12.2027',
        'Хочу в Байкал (Иркутск)', '2 взрослых',
    ]
    records, session = [], None
    for index, text in enumerate(texts):
        if index:
            time.sleep(3)
        body = {'text': text, 'session_id': session}
        if not index:
            body['detected_city'] = 'Москва'  # synthetic, disclosed IP-city approximation
        request = Request(args.url.rstrip('/') + '/api/chat',
                          data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=90) as response:
                data = json.load(response)
        except Exception as exc:
            records.append({'input': text, 'error': type(exc).__name__})
            break
        session = data['session_id']
        records.append({'input': text, 'nlu': data['nlu'], 'reply': data['reply'],
                        'kind': (data.get('payload') or {}).get('kind'),
                        'understood': data['understood'], 'trip_summary': data['trip_summary']})
        if data['nlu'] not in {'llm', 'llm+rules'}:
            break  # distinguish an unavailable model from a passed model check
    checks = {
        'five_model_turns': len(records) == 5 and all(x.get('nlu') in {'llm', 'llm+rules'} for x in records),
        'both_wishes_preserved': bool(records and all(any(label in item for item in records[0].get('understood', []))
            for label in ('красивые виды', 'спокойные прогулки'))),
        'delegation_shows_ideas': bool(len(records) >= 2 and records[1].get('kind') == 'ideas'),
        'dates_preserved': bool(len(records) >= 3 and records[2].get('trip_summary', {}).get('date_from') == '2027-11-11'
                                and records[2]['trip_summary'].get('date_to') == '2027-12-11'),
        'prices_explained': bool(len(records) >= 5 and records[4].get('kind') == 'packages' and
                                 'самый недорогой' in records[4].get('reply', '').lower() and
                                 'демо' in records[4].get('reply', '').lower() and
                                 'примерно по ip' in records[4].get('reply', '').lower()),
    }
    report = {'status': 'complete' if len(records) == len(texts) else 'incomplete', 'checks': checks, 'records': records}
    with open(args.output, 'w', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps({'status': report['status'], 'checks': checks}, ensure_ascii=False))
    return 0 if report['status'] == 'complete' and all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
