"""Small, synthetic HTTP chat check; run only against an explicitly permitted model server."""
import argparse
import json
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:18763')
    parser.add_argument('--output', required=True)
    parser.add_argument('--pause', type=float, default=3)
    args = parser.parse_args()
    records = []

    def send(case, text, session=None):
        if records:
            time.sleep(args.pause)
        body = json.dumps({'text': text, 'session_id': session}, ensure_ascii=False).encode('utf-8')
        request = Request(args.url.rstrip('/') + '/api/chat', data=body,
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=90) as response:
                data = json.load(response)
            records.append({'case': case, 'input': text, 'nlu': data.get('nlu'),
                            'reply': data.get('reply'), 'trip_summary': data.get('trip_summary'),
                            'kind': (data.get('payload') or {}).get('kind'),
                            'field': (data.get('payload') or {}).get('field')})
            return data
        except Exception as exc:
            records.append({'case': case, 'error': type(exc).__name__})
            return None

    checks = {}
    first = send('hotel', 'Только отель в Сочи с 12 по 18 ноября для двух взрослых и ребёнка 5 лет, с завтраком, до 90 тысяч на всех')
    if first:
        summary = first['trip_summary']
        checks['hotel_parameters'] = (summary['destination'] == 'Сочи' and summary['adults'] == 2 and
            summary['children'] == 1 and summary['children_ages'] == [5] and
            summary['budget_total'] == 90000 and summary['date_from'] == '2026-11-12' and
            summary['date_to'] == '2026-11-18' and (first.get('payload') or {}).get('kind') == 'service_results')
        checks['hotel_marks_demo'] = 'демо' in first['reply'].lower()
    if first and first['nlu'] in {'llm', 'llm+rules'}:
        second = send('guide_question', 'Где поесть?', first['session_id'])
        if second:
            checks['question_keeps_trip'] = (second['trip_summary'] == first['trip_summary'] and
                                             'Wikivoyage' in second['reply'])
    else:
        second = None
    if second and second['nlu'] in {'llm', 'llm+rules'}:
        third = send('unsupported_detail', 'В ресторанах есть меню на клингонском?', first['session_id'])
        if third:
            checks['no_invented_detail'] = ('ответа не нашёл' in third['reply'].lower() and
                                             third['trip_summary']['destination'] == 'Сочи')
    else:
        third = None
    if third and third['nlu'] in {'llm', 'llm+rules'}:
        transfer = send('transfer', 'Нужен трансфер в Сочи из аэропорта в отель завтра в 14:30, двое взрослых в одну сторону')
        if transfer:
            checks['transfer'] = ((transfer.get('payload') or {}).get('kind') == 'service_results' and
                                  '14:30' in transfer['reply'] and 'заказ' in transfer['reply'].lower())
    model_turns = sum(r.get('nlu') in {'llm', 'llm+rules'} for r in records)
    report = {'status': 'complete' if len(records) == 4 and len(checks) == 5 and model_turns == 4 else 'incomplete',
              'passed': sum(checks.values()), 'total_checks': len(checks), 'model_turns': model_turns,
              'checks': checks, 'records': records}
    with open(args.output, 'w', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ('status', 'passed', 'total_checks', 'model_turns', 'checks')}, ensure_ascii=False))
    return 0 if report['status'] == 'complete' and all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
