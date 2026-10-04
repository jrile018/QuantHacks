#!/usr/bin/env python3
"""Export a bounded retained-evidence history packet without acquisition."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.reit_instrument_history import build_instrument_history_packet

DEFAULT_SNAPSHOT = PROJECT_ROOT / 'data/processed/reit_build/20261003/integrated/snapshots/snapshot-419fe98b772e4b3116b6e29535e434dce97afcf6e4137aba75c8aaa0a0dc1f04'
DEFAULT_OUTPUT = PROJECT_ROOT / 'data/processed/reit_build/20261004-continuation/histories/v3'
INPUT_TABLES = ('instrument_financial_histories', 'instruments', 'role_edges', 'entities')
MAX_INPUT_BYTES = 2_000_000
BXMT_QUARANTINE_URLS = (
    'https://www.sec.gov/Archives/edgar/data/1061630/000106163026000009/exhibit10504q25.htm',
    'https://www.sec.gov/Archives/edgar/data/1061630/000106163026000009/exhibit10664q25.htm',
)


def _read_bounded(path):
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError('Input exceeds bounded size limit: ' + path.name)
    return path.read_bytes()


def _encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def write_history_packet(snapshot, output, *, as_of=None):
    snapshot, output = Path(snapshot), Path(output)
    if output.resolve().is_relative_to(snapshot.resolve()):
        raise ValueError('Output must not modify the immutable source snapshot or its descendants')
    if output.exists():
        raise ValueError('Output directory already exists; select a fresh packet version directory')
    published_raw = _read_bounded(snapshot / 'manifest.json')
    published = json.loads(published_raw.decode('utf-8-sig'))
    rows, input_receipts = {}, {}
    # Validate every selected input before creating the output directory.
    for name in INPUT_TABLES:
        filename = name + '.jsonl'
        raw = _read_bounded(snapshot / filename)
        digest = sha256(raw).hexdigest()
        expected = published['artifacts'][filename]
        if digest != expected['sha256'] or len(raw) != expected['bytes']:
            raise ValueError('Published input hash/size mismatch: ' + filename)
        rows[name] = [json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
        if len(rows[name]) != published['counts'][name]:
            raise ValueError('Published input row-count mismatch: ' + filename)
        input_receipts[filename] = {'sha256': digest, 'bytes': len(raw), 'rows': len(rows[name])}
    packet = build_instrument_history_packet(rows['instrument_financial_histories'], rows['instruments'], rows['role_edges'], rows['entities'], as_of=as_of)
    packet['source_snapshot_fingerprint'] = published['fingerprint']
    packet['source_quarantine'] = [{'source_url': url, 'source_eligible': False,
                                  'status': 'conflicting_bxmt_exhibit_source_claim',
                                  'used_in_history_packet': False,
                                  'declaration_path': 'data/processed/reit_build/20261003/integrated/source_adjudication_v2.json',
                                  'declaration_sha256': '437afc3d89db0acdef2daf2336e347b2c698c38f6d72973b705705c6c1c85f51',
                                  'resolution': 'Reconcile source URL/issuer identity and retained-byte provenance before admitting either exhibit.'}
                                 for url in BXMT_QUARANTINE_URLS]
    for claim in packet['source_quarantine']:
        packet['missing_evidence_queue'].append({'queue_id': 'history-review:' + sha256(claim['source_url'].encode()).hexdigest(),
            'status': 'source_quarantined', 'instrument_id': None, 'assertion_id': None,
            'source_url': claim['source_url'], 'source_eligible': False,
            'request': claim['resolution'], 'evidence': None})
    tables = {name + '.jsonl': ''.join(json.dumps(row, sort_keys=True, ensure_ascii=False) + '\n' for row in packet[name]).encode('utf-8')
              for name in ('events', 'components', 'instrument_links', 'role_assertions', 'entities', 'canonical_instruments', 'missing_evidence_queue')}
    artifacts = {'packet.json': _encode(packet), 'views.json': _encode(packet['views']),
                 'retained_inputs.json': _encode(rows), **tables}
    output.mkdir(parents=True, exist_ok=False)
    for name, raw in artifacts.items():
        (output / name).write_bytes(raw)
    receipt = {'schema_version': 'reit-instrument-history-packet-receipt-1',
               'source_snapshot_fingerprint': published['fingerprint'],
               'source_snapshot_manifest_sha256': sha256(published_raw).hexdigest(),
               'inputs': input_receipts, 'input_artifacts_verified': True,
               'raw_sources_revalidated': False, 'acquisition_calls': 0,
               'canonical_schema_modified': False, 'as_of': as_of,
               'source_eligibility_interpretation': 'Inherited published assertions; cached/raw source bytes were not re-extracted or re-adjudicated.',
               'counts': {name: len(packet[name]) for name in ('events', 'components', 'instrument_links', 'role_assertions', 'entities', 'canonical_instruments', 'missing_evidence_queue', 'source_quarantine')},
               'view_counts': {name: len(packet['views'][name]) for name in ('original', 'latest', 'nonoverlapping_flow', 'information_time_unordered')},
               'role_eligibility_counts': {'eligible': sum(r['eligibility']['eligible'] for r in packet['role_assertions']),
                                           'review_or_ineligible': sum(not r['eligibility']['eligible'] for r in packet['role_assertions'])},
               'implementation_sha256': {str(path.relative_to(PROJECT_ROOT)).replace('\\', '/'): sha256(path.read_bytes()).hexdigest()
                                          for path in (Path(__file__), PROJECT_ROOT / 'src/reit_instrument_history.py')},
               'artifacts': {name: {'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in artifacts.items()},
               'limitations': packet['limits']}
    (output / 'manifest.json').write_bytes(_encode(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--as-of', help='Optional timezone-aware information cutoff')
    args = parser.parse_args()
    receipt = write_history_packet(args.snapshot, args.output, as_of=args.as_of)
    print(json.dumps({'output': str(args.output), 'counts': receipt['counts'],
                      'view_counts': receipt['view_counts'],
                      'packet_sha256': receipt['artifacts']['packet.json']['sha256']}, sort_keys=True))


if __name__ == '__main__':
    main()
