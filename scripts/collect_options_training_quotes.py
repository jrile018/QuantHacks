"""Collect only a finite explicit historical quote-request manifest."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.market_quote_collector import collect_request
from src.document_manifest import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--raw-dir', type=Path, default=ROOT / 'data/raw/option_quotes')
    parser.add_argument('--max-pages', type=int, default=4)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    requests = [json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
    if not 1 <= len(requests) <= 50:
        parser.error('Each manifest must contain 1–50 explicit requests')
    if not args.fetch:
        print(json.dumps({'status': 'dry_run', 'requests': len(requests), 'maximum_pages': len(requests) * args.max_pages}, indent=2))
        return 0
    from src.data import _session
    session = _session()
    ledger = {'schema_version': '1.0', 'results': [], 'limitation': 'Raw quotes need dated mappings, as-of synchronization, entry/exit coverage and feature provenance before fitting.'}
    for request in requests:
        result = collect_request(request, session, args.raw_dir, args.max_pages)
        ledger['results'].append(result)
        atomic_json(args.output, ledger)
        if result['status'] in ('access_blocked', 'request_failed'):
            break
    print(json.dumps({'output': str(args.output.resolve()), 'statuses': [r['status'] for r in ledger['results']],
                      'quote_records': sum(len(r['quotes']) for r in ledger['results'])}, indent=2))
    return 0 if all(r['complete'] for r in ledger['results']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
