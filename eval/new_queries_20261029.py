"""Reproducible fixed-date rule-extraction checks; inputs are synthetic."""
import argparse
import json
from datetime import date
from pathlib import Path

from domains.trips.rules import rule_extract
from domains.trips.state import TripState


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    cases = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
    results = []
    for case in cases:
        actual = rule_extract(TripState(), case['text'], date(2026, 10, 27)).model_dump(mode='json')
        failures = []
        for field, expected in case.get('expected', {}).items():
            if actual.get(field) != expected:
                failures.append(f'{field}: expected {expected!r}, got {actual.get(field)!r}')
        for field, expected in case.get('expected_contains', {}).items():
            actual_values = set((actual.get(field) or '').split('|'))
            if not set(expected) <= actual_values:
                failures.append(f'{field}: expected {expected!r}, got {actual.get(field)!r}')
        results.append({'id': case['id'], 'pass': not failures, 'failures': failures})
    report = {'today': '2026-10-27', 'passed': sum(x['pass'] for x in results),
              'total': len(results), 'results': results}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return int(report['passed'] != report['total'])


if __name__ == '__main__':
    raise SystemExit(main())
