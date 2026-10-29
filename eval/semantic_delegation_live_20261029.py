"""Check a delegation phrase that is not in the deterministic phrase patterns."""
import argparse
import json
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:18763')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    records, session = [], None
    for text in ('Хочу в горы, предложи направления', 'ориентируйся на свой опыт'):
        if records:
            time.sleep(3)
        request = Request(args.url.rstrip('/') + '/api/chat',
                          data=json.dumps({'text': text, 'session_id': session}, ensure_ascii=False).encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=90) as response:
                data = json.load(response)
        except Exception as exc:
            records.append({'input': text, 'error': type(exc).__name__})
            break
        session = data['session_id']
        records.append({'input': text, 'nlu': data['nlu'], 'reply': data['reply'],
                        'kind': (data.get('payload') or {}).get('kind'), 'trip_summary': data['trip_summary']})
        if data['nlu'] not in {'llm', 'llm+rules'}:
            break
    checks = {
        'model_processed_both_turns': len(records) == 2 and all(r.get('nlu') in {'llm', 'llm+rules'} for r in records),
        'new_formulation_gives_ideas': len(records) == 2 and records[1].get('kind') == 'ideas',
        'dates_not_invented': len(records) == 2 and not records[1]['trip_summary']['date_from'],
    }
    report = {'status': 'complete' if len(records) == 2 else 'incomplete', 'checks': checks, 'records': records}
    with open(args.output, 'w', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps({'status': report['status'], 'checks': checks}, ensure_ascii=False))
    return 0 if report['status'] == 'complete' and all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
