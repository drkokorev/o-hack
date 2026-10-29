"""Reproduce the owner's anonymous clarification loop through the model-enabled HTTP chat."""
import argparse
import json
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:18763')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    texts = ['Хочу в горы, красивый вид и спокойные прогулки. Предложи направления.',
             'предложи сам', 'предложи сам']
    records, session = [], None
    for text in texts:
        if records:
            time.sleep(3)
        payload = json.dumps({'text': text, 'session_id': session}, ensure_ascii=False).encode('utf-8')
        request = Request(args.url.rstrip('/') + '/api/chat', data=payload,
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
                        'count': len((data.get('payload') or {}).get('items', [])),
                        'trip_summary': data['trip_summary']})
        if len(records) == 1 and data['nlu'] not in {'llm', 'llm+rules'}:
            break  # an unavailable model is not a successful live-model check
    checks = {
        'model_processed_first_turn': bool(records and records[0].get('nlu') in {'llm', 'llm+rules'}),
        'asks_about_time': bool(records and records[0].get('kind') == 'question'),
        'delegation_returns_ideas': bool(len(records) >= 2 and records[1].get('kind') == 'ideas' and records[1].get('count')),
        'repeated_reply_does_not_loop': bool(len(records) >= 3 and records[2].get('kind') == 'ideas' and
                                             'не понял' not in records[2].get('reply', '').lower()),
        'no_invented_dates_or_prices': bool(len(records) >= 2 and not records[1]['trip_summary']['date_from'] and
                                             not records[1]['trip_summary']['date_to'] and
                                             not records[1]['trip_summary']['budget_total']),
    }
    report = {'status': 'complete' if len(records) == 3 else 'incomplete', 'checks': checks, 'records': records}
    with open(args.output, 'w', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps({'status': report['status'], 'checks': checks}, ensure_ascii=False))
    return 0 if report['status'] == 'complete' and all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
