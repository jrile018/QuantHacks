"""Prepare an explicit small SEC document batch without outcome-based selection."""
import argparse
import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.document_manifest import SecFetcher, SECBlocked, inventory_from_submission, atomic_json
from scripts.analyze_8k_documents import store_source, is_analysis_document


def select_filings(catalog, tickers, start, end):
    selected = {}
    with Path(catalog).open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            if row.get('form') != '8-K' or not start <= row['filing_date'] < end:
                continue
            listed = {t.strip() for t in row.get('tickers', '').replace(',', ';').replace('|', ';').split(';')}
            for ticker in set(tickers) & listed:
                if ticker not in selected or (row['filing_date'], row['accession']) < (selected[ticker]['filing_date'], selected[ticker]['accession']):
                    selected[ticker] = row
    return [dict(selected[ticker], pilot_ticker=ticker) for ticker in tickers if ticker in selected]


def cache_coverage(directory):
    shapes, count, total = collections.Counter(), 0, 0
    for path in Path(directory).glob('*.json'):
        count += 1
        total += path.stat().st_size
        if path.stat().st_size > 10_000_000:
            shapes['not_inspected_size_limit'] += 1
            continue
        payload = json.loads(path.read_text(encoding='utf-8'))
        results = payload.get('results') if isinstance(payload, dict) else None
        if isinstance(results, list) and results and isinstance(results[0], dict):
            shapes['|'.join(sorted(results[0]))] += 1
    return {'cache_files': count, 'cache_bytes': total, 'sample_record_shapes': dict(shapes),
            'limitation': 'Metadata inventory only; cached daily bars are not historical bid/ask training labels.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', default=str(ROOT / 'data/processed/sec_8k_urls/filings.csv'))
    parser.add_argument('--tickers', nargs='+', default=['AAPL', 'MSFT', 'GD'])
    parser.add_argument('--start', default='2024-01-01')
    parser.add_argument('--end', default='2025-01-01')
    parser.add_argument('--output-dir', default=str(ROOT / 'data/processed/document_pilot'))
    parser.add_argument('--raw-dir', default=str(ROOT / 'data/raw/8k_documents'))
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    if len(args.tickers) > 10:
        parser.error('Pilot limited to ten explicitly named tickers')
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    selected = select_filings(args.catalog, args.tickers, args.start, args.end)
    ledger = {'schema_version': '1.0', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'selection_rule': 'First ordinary 8-K by filing date/accession within fixed interval, per named ticker; no outcome filter.',
              'requested_tickers': args.tickers, 'filings': selected, 'documents': [], 'failures': [], 'status': 'selected'}
    atomic_json(output / 'selection.json', ledger)
    atomic_json(output / 'market_cache_coverage.json', cache_coverage(ROOT / '.massive_cache'))
    if args.fetch:
        fetcher = SecFetcher(args.raw_dir, os.environ.get('SEC_CONTACT_EMAIL'))
        for row in selected:
            try:
                fetched = fetcher.fetch(row['complete_text_url'], row['cik'], row['accession'])
                raw = Path(fetched['path']).read_bytes()
                row['submission_path'] = str(store_source(args.raw_dir, raw, '.submission.txt'))
                row['submission_sha256'] = fetched['source_sha256']
                for record in inventory_from_submission(row, raw):
                    content = record.pop('content_bytes')
                    record.pop('content', None)
                    if not is_analysis_document(record):
                        continue
                    if content is None:
                        ledger['failures'].append({'document_id': record['document_id'], 'reason': record['inventory_status']})
                        continue
                    suffix = Path(record['filename'] or 'document.txt').suffix
                    record['source_path'] = str(store_source(args.raw_dir, content, suffix))
                    record['receipt_at_utc'] = fetched['receipt_at_utc']
                    record['container_sha256'] = fetched['source_sha256']
                    ledger['documents'].append(record)
            except Exception as error:
                ledger['failures'].append({'accession': row['accession'], 'reason': type(error).__name__, 'detail': str(error)})
                if isinstance(error, SECBlocked):
                    ledger['status'] = 'sec_blocked'
                    break
            finally:
                atomic_json(output / 'selection.json', ledger)
        if ledger['status'] != 'sec_blocked':
            ledger['status'] = 'completed_with_gaps' if ledger['failures'] else 'completed'
        atomic_json(output / 'selection.json', ledger)
        manifest = output / 'documents.jsonl'
        manifest.write_text(''.join(json.dumps(record) + '\n' for record in ledger['documents']), encoding='utf-8')
    print(json.dumps({'selection': str((output / 'selection.json').resolve()), 'filings': len(selected),
                      'documents': len(ledger['documents']), 'status': ledger['status'], 'failures': ledger['failures']}, indent=2))
    return 1 if ledger['status'] == 'sec_blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
