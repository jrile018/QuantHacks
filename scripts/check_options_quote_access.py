"""Check a bounded historical quote request without printing credentials."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data import _session
from src.document_manifest import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract')
    parser.add_argument('--date')
    parser.add_argument('--output', default=str(ROOT / 'data/processed/document_pilot/quote_access.json'))
    args = parser.parse_args()
    contract, day = args.contract, args.date
    if not contract:
        for path in sorted((ROOT / '.massive_cache').glob('*.json')):
            payload = json.loads(path.read_text())
            ticker = payload.get('ticker', '')
            rows = payload.get('results', [])
            if ticker.startswith('O:') and rows and 't' in rows[0]:
                contract = ticker
                day = datetime.fromtimestamp(rows[0]['t'] / 1000, timezone.utc).date().isoformat()
                break
    if not contract or not day:
        raise ValueError('Supply an explicit contract/date; no cached option bars identify a probe')
    if not contract.startswith('O:') or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:.' for c in contract):
        raise ValueError('Invalid option contract ticker')
    datetime.strptime(day, '%Y-%m-%d')
    url = 'https://api.massive.com/v3/quotes/' + contract
    result = {'schema_version': '1.0', 'provider': 'Massive', 'contract': contract, 'date': day,
              'purpose': 'bounded entitlement and response-shape check; not a training sample',
              'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'requested_limit': 2}
    try:
        response = _session().get(url, params={'timestamp': day, 'limit': 2, 'order': 'asc', 'sort': 'timestamp'}, timeout=20)
        result['http_status'] = response.status_code
        if response.status_code == 200:
            payload = response.json()
            rows = payload.get('results', [])
            result.update(status='quotes_available' if rows else 'no_quotes_in_probe', records=len(rows),
                          record_fields=sorted(rows[0]) if rows else [], has_more=bool(payload.get('next_url')))
            raw = response.content
            target = ROOT / 'data/raw/option_quotes' / (hashlib.sha256(raw).hexdigest() + '.json')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            result['raw_path'] = str(target.resolve())
            result['source_sha256'] = hashlib.sha256(raw).hexdigest()
        else:
            result['status'] = 'access_denied' if response.status_code in (401, 403) else 'request_failed'
    except Exception as error:
        result.update(status='request_failed', error_type=type(error).__name__)
    atomic_json(args.output, result)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'quotes_available' else 1


if __name__ == '__main__':
    raise SystemExit(main())
