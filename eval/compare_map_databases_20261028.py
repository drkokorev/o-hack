"""Compare the design snapshot with the rebuilt integrated index, without changing either."""
import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--design-db', type=Path, required=True)
    parser.add_argument('--combined-db', type=Path, required=True)
    args = parser.parse_args()
    connect = lambda path: sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    with connect(args.design_db) as old, connect(args.combined_db) as new:
        integrity = [db.execute('PRAGMA quick_check').fetchone()[0] for db in (old, new)]
        metadata = [dict(db.execute('SELECT key,value FROM metadata')) for db in (old, new)]
        counts = [json.loads(row['counts']) for row in metadata]
        sources_match = list(old.execute('SELECT * FROM sources ORDER BY id')) == list(new.execute('SELECT * FROM sources ORDER BY id'))
        columns = [[row[1] for row in db.execute('PRAGMA table_info(point)')] for db in (old, new)]
        if columns[0] != columns[1]:
            raise SystemExit('Different point schemas')
        differences, checked, expected_corrections = Counter(), 0, 0
        for before, after in itertools.zip_longest(old.execute('SELECT * FROM point ORDER BY id'),
                                                   new.execute('SELECT * FROM point ORDER BY id')):
            if before is None or after is None:
                raise SystemExit('Different point counts')
            changed = tuple(name for i, name in enumerate(columns[0]) if before[i] != after[i])
            if changed:
                differences[','.join(changed)] += 1
                old_fields, new_fields = dict(zip(columns[0], before)), dict(zip(columns[0], after))
                if (changed == ('country_name', 'country_code') and old_fields['country_name'] == 'XK' and
                    old_fields['country_code'] is None and new_fields['country_name'] == 'Косово' and
                    new_fields['country_code'] == 'XK'):
                    expected_corrections += 1
            checked += 1
        report = {'integrity': integrity, 'counts_match': counts[0] == counts[1], 'sources_match': sources_match,
                  'old_digest': json.loads(metadata[0]['source_digest']), 'new_digest': json.loads(metadata[1]['source_digest']),
                  'records_compared': checked, 'differences': dict(differences), 'expected_country_corrections': expected_corrections}
        print(json.dumps(report, ensure_ascii=False))
        return 0 if (integrity == ['ok', 'ok'] and counts[0] == counts[1] and sources_match and checked == 283561 and
                     differences == Counter({'country_name,country_code': 58}) and expected_corrections == 58) else 1


if __name__ == '__main__':
    raise SystemExit(main())
