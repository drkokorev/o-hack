"""End-to-end rules topic recognition plus grounded retrieval on the old RAG set.

The section labels only score the result; they are not provided to the parser.
This set is historical/development data, not an independent user evaluation.
"""
import argparse
import json
from datetime import date

from domains.trips import guides
from domains.trips.domain import PLACE_TOPICS
from domains.trips.rules import rule_extract
from domains.trips.state import TripState
from eval.rag_eval import CASES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    results = []
    for dest, text, tags in CASES:
        update = rule_extract(TripState(dest_id=dest), text, date(2026, 10, 27))
        topics = [t for t in (update.question or '').split('|') if t in PLACE_TOPICS]
        found = [s for topic in topics for s in guides.search_grounded(text, dest, topic, k=3)]
        results.append({'dest': dest, 'query': text, 'topics': topics,
                        'top1': bool(found and found[0].tag in tags),
                        'top3': any(s.tag in tags for s in found[:3]),
                        'reason': 'not_recognized' if not topics else 'no_grounded_result' if not found else 'retrieved'})
    report = {'mode': guides.mode(), 'total': len(results),
              'question_recognized': sum(bool(r['topics']) for r in results),
              'top1': sum(r['top1'] for r in results), 'top3': sum(r['top3'] for r in results),
              'results': results}
    with open(args.output, 'w', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in ('mode', 'total', 'question_recognized', 'top1', 'top3')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
