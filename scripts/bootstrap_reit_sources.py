"""Acquire official discovery snapshots through the durable REIT broker."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.reit_acquisition import FetchBroker

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ('sec-exchange-map', 'https://www.sec.gov/files/company_tickers_exchange.json', 'discovery_exchange_map'),
    ('nareit-ticker-table', 'https://www.reit.com/data-research/reit-indexes/reits-by-ticker-symbol', 'discovery_REIT_and_REOC'),
    *[('reitwatch-'+code, 'https://www.reit.com/sites/default/files/reitwatch/RW'+code+'.pdf', 'dated_index_constituents')
      for code in ('2312', '2401', '2501', '2601', '2609')],
]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'data/processed/reit_build/20261003')
    parser.add_argument('--broker-root', type=Path, default=ROOT/'data/raw/reit_broker')
    parser.add_argument('--contact', default='john.p.riley00@gmail.com')
    parser.add_argument('--only', choices=[x[0] for x in SOURCES], action='append')
    args = parser.parse_args(argv)
    broker = FetchBroker(args.broker_root, contact_email=args.contact)
    args.output.mkdir(parents=True, exist_ok=True)
    registry_path = args.output/'discovery_source_receipts.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else {'sources': [], 'failures': []}
    for source_id, url, role in SOURCES:
        if args.only and source_id not in args.only:
            continue
        def validate(body):
            if source_id == 'sec-exchange-map':
                payload = json.loads(body)
                if not {'fields', 'data'}.issubset(payload):
                    raise ValueError('SEC exchange response does not have fields/data')
            elif role == 'dated_index_constituents' and not body.startswith(b'%PDF-'):
                raise ValueError('Expected an official REITWatch PDF')
            elif role == 'discovery_REIT_and_REOC' and b'<html' not in body.lower():
                raise ValueError('Expected an official Nareit HTML page')
        try:
            result = broker.fetch(url, validator=validate)
            source = {'source_id': source_id, 'url': url, 'source_role': role,
                      'source_path': result['path'], 'sha256': result['sha256'],
                      'retrieved_at': result['receipt']['retrieved_at'],
                      'content_type': result['receipt']['content_type'], 'receipt': result['receipt'],
                      'first_public_at': None, 'limitation': 'Discovery or index membership does not prove complete dated US listed REIT eligibility.'}
            registry['sources'] = [r for r in registry['sources'] if r['source_id'] != source_id]+[source]
            print(json.dumps({'source': source_id, 'sha256': result['sha256'], 'path': result['path'], 'cached': result['cached']}), flush=True)
        except Exception as exc:
            registry['failures'].append({'source_id': source_id, 'url': url, 'error': type(exc).__name__+': '+str(exc),
                                        'at': datetime.now(timezone.utc).isoformat()})
            print(json.dumps({'source': source_id, 'error': type(exc).__name__+': '+str(exc)}), flush=True)
        finally:
            registry_path.write_text(json.dumps(registry, indent=2)+'\n', encoding='utf-8')
            (args.output/'broker_receipts.json').write_text(json.dumps({'receipts': broker.receipts()}, indent=2)+'\n', encoding='utf-8')
    return 0 if registry['sources'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
