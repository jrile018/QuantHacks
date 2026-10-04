"""Parameterized, read-only queries against a verified REIT snapshot."""
from __future__ import annotations

import argparse
from datetime import date as parse_date
import json
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.reit_dataset import TABLES, verify_snapshot

ROOT = Path(__file__).resolve().parents[1]


def query_snapshot(snapshot_dir, *, table='financial_histories', issuer_cik=None, evidence=None, date=None, source_root=None):
    if table not in TABLES:
        raise ValueError('unknown export table')
    filters, values = [], []
    if issuer_cik is not None:
        text = str(issuer_cik)
        if not text.isdigit() or len(text) > 10 or int(text) <= 0:
            raise ValueError('invalid issuer CIK')
        filters.append('issuer_cik = ?')
        values.append(text.zfill(10))
    if date is not None:
        parse_date.fromisoformat(date)
        filters.append('substr(effective_at, 1, 10) = ?')
        values.append(date)
    if evidence is not None:
        filters.append('instr(evidence_json, ?) > 0')
        values.append(str(evidence))
    verified = verify_snapshot(snapshot_dir, source_root=source_root)
    if not verified['valid']:
        raise ValueError('snapshot verification failed: ' + '; '.join(verified['errors']))
    uri = (Path(snapshot_dir) / 'dataset.sqlite').resolve().as_uri() + '?mode=ro'
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute('PRAGMA query_only = ON')
        where = ' WHERE ' + ' AND '.join(filters) if filters else ''
        return [json.loads(row[0]) for row in connection.execute(f'SELECT row_json FROM "{table}"' + where + ' ORDER BY row_number', values)]
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot_dir')
    parser.add_argument('--table', choices=TABLES, default='financial_histories')
    parser.add_argument('--issuer-cik')
    parser.add_argument('--evidence')
    parser.add_argument('--date')
    parser.add_argument('--source-root', type=Path, default=ROOT, help='Project root for portable retained-source references (default: repository root)')
    parser.add_argument('--export', type=Path, help='Optional JSONL result file outside the immutable snapshot')
    args = parser.parse_args(argv)
    rows = query_snapshot(args.snapshot_dir, table=args.table, issuer_cik=args.issuer_cik, evidence=args.evidence, date=args.date, source_root=args.source_root)
    output = ''.join(json.dumps(row, sort_keys=True, ensure_ascii=False) + '\n' for row in rows)
    if args.export:
        target = args.export.resolve()
        snapshot = Path(args.snapshot_dir).resolve()
        if target == snapshot or snapshot in target.parents:
            parser.error('export must be outside the immutable snapshot')
        with target.open('x', encoding='utf-8') as stream:
            stream.write(output)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
