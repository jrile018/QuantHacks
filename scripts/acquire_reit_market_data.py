"""Quote-first Databento market acquisition with a durable total-spend ledger.

Defaults to quote. Submit is explicit and always re-quotes identical filters.
No paid requests are retried after an ambiguous acknowledgement.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from src.reit_budget import BudgetLedger, legacy_spend
from src.reit_market_data import DatabentoClient, load_api_key, market_readiness, save_json, sanitize


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('mode', nargs='?', default='quote', choices=(
        'quote', 'metadata', 'submit', 'jobs', 'job', 'files', 'download', 'reconcile', 'readiness', 'budget'))
    result.add_argument('--project', type=Path, default=PROJECT)
    result.add_argument('--payload', type=Path, help='Exact request JSON file')
    result.add_argument('--quote-receipt', type=Path, help='Saved quote JSON (required for submit)')
    result.add_argument('--request-id', help='Stable local reservation identity, never a provider idempotency claim')
    result.add_argument('--job-id')
    result.add_argument('--metadata-operation', default='list_datasets', choices=(
        'list_datasets', 'list_schemas', 'get_dataset_range', 'get_dataset_condition', 'list_publishers', 'list_fields'))
    result.add_argument('--dataset')
    result.add_argument('--schema')
    result.add_argument('--start-date')
    result.add_argument('--end-date')
    result.add_argument('--since')
    result.add_argument('--states', default='queued,processing,done,expired')
    result.add_argument('--name-contains')
    result.add_argument('--output', type=Path, help='Write sanitized command result JSON here')
    result.add_argument('--download-dir', type=Path)
    result.add_argument('--ledger', type=Path)
    result.add_argument('--legacy-ledger', type=Path)
    result.add_argument('--manifest', type=Path, help='Evidence manifest for readiness mode')
    return result


def _read(path):
    if path is None:
        raise ValueError('A required input JSON path is missing')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main(argv=None):
    args = parser().parse_args(argv)
    project = args.project.resolve()
    result = None
    key = ''
    try:
        if args.mode == 'readiness':
            result = market_readiness(_read(args.manifest))
        elif args.mode == 'budget':
            ledger = _ledger(args, project)
            result = ledger.summary()
        else:
            key = load_api_key(project)
            client = DatabentoClient(key, project / 'data' / 'processed' / 'reit-market' / 'receipts',
                legacy_ledger=args.legacy_ledger or project / 'data' / 'raw' / 'databento' / 'acquisition_ledger.json')
            if args.mode == 'metadata':
                values = {'dataset': args.dataset, 'schema': args.schema,
                          'start_date': args.start_date, 'end_date': args.end_date}
                if args.metadata_operation == 'list_fields':
                    values['encoding'] = 'csv'
                result = client.metadata(args.metadata_operation,
                                         **{k: v for k, v in values.items() if v is not None})
            elif args.mode == 'quote':
                result = client.quote(_read(args.payload))
            elif args.mode == 'submit':
                if not args.request_id:
                    raise ValueError('--request-id is required for submit')
                result = client.submit(args.request_id, _read(args.payload),
                                       _read(args.quote_receipt), _ledger(args, project))
            elif args.mode == 'jobs':
                values = {'states': args.states}
                if args.since:
                    values['since'] = args.since
                result = client.batch('list_jobs', **values)
            elif args.mode in {'job', 'files', 'download', 'reconcile'}:
                if not args.job_id:
                    raise ValueError('--job-id is required')
                if args.mode in {'job', 'files'}:
                    result = client.batch('get_job_details' if args.mode == 'job' else 'list_files', job_id=args.job_id)
                elif args.mode == 'download':
                    result = client.download(args.job_id, args.download_dir or project / 'data' / 'raw' / 'databento',
                                             name_contains=args.name_contains)
                else:
                    if not args.request_id:
                        raise ValueError('--request-id is required for reconciliation')
                    result = client.reconcile(args.request_id, args.job_id, _ledger(args, project))
        result = sanitize(result, key)
        if args.output:
            save_json(args.output, result)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except Exception as exc:
        # Do not expose requests exception URLs, response bodies, or raw job fields.
        message = sanitize(str(exc), key)
        print(json.dumps({'status': 'blocked', 'error_type': type(exc).__name__, 'message': message}), file=sys.stderr)
        return 2


def _ledger(args, project):
    legacy_path = args.legacy_ledger or project / 'data' / 'raw' / 'databento' / 'acquisition_ledger.json'
    external = max(Decimal('23.14'), legacy_spend(legacy_path))
    ledger = BudgetLedger(args.ledger or project / 'data' / 'processed' / 'reit-market' / 'budget.sqlite',
                          cap='249.99', external_spend=external)
    ledger.refresh_external(external)
    return ledger


if __name__ == '__main__':
    raise SystemExit(main())
