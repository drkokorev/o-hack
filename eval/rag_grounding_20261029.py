"""Compare old generic-prefix RAG with grounded retrieval on synthetic cases.

This small development set tests passage relevance and abstention, not the
truth, completeness or freshness of Wikivoyage or LLM-generated answers.
"""
import argparse
import json
from pathlib import Path

from domains.trips import guides
from domains.trips.domain import GUIDE_QUERY


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    cases = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
    results = []
    for case in cases:
        old = guides.search(GUIDE_QUERY[case['topic']] + ' ' + case['query'],
                            case['dest'], case['topic'], k=4)
        new = guides.search_grounded(case['query'], case['dest'], case['topic'], k=4)

        def passes(found):
            if case['expect'] == 'none':
                return not found
            if case['expect'] == 'any':
                return bool(found)
            return bool(found and case['term'] in found[0].text.lower())

        results.append({'id': case['id'], 'expect': case['expect'],
                        'old_pass': passes(old), 'new_pass': passes(new),
                        'old_top': old[0].section if old else None,
                        'new_top': new[0].section if new else None})
    report = {'mode': guides.mode(), 'total': len(results),
              'old_passed': sum(x['old_pass'] for x in results),
              'new_passed': sum(x['new_pass'] for x in results), 'results': results}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return int(report['new_passed'] != report['total'])


if __name__ == '__main__':
    raise SystemExit(main())
