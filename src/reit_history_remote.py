"""Portable, evidence-preserving preparation for the frozen REIT history cohort.

This module is offline. Acquisition is an explicit CLI action after preparation.
Original metadata, queues, and broker databases are never rewritten.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import sqlite3
from uuid import uuid4

from src.reit_acquisition import FetchBroker, transaction


FROZEN_HASHES = {
    'universe': '078576300fc1ef4b3b94373bb30241d80aefc5c700dd64ef8bc164875e8513b1',
    'plan': '862a3ba11251b8c98012635acd1e52f67b7ac6069a1510f91b13c529343b8dc3',
}
START_DATE = '2024-01-01'
END_DATE = '2026-10-03'
KNOWN_PREFIXES = ('data/raw/reit_broker', 'data/processed/reit_build/20261003')


def file_hash(path):
    digest = sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    temporary.replace(path)


def map_project_path(value, old_root, new_root):
    """Map only known retained data paths; understand Windows paths on Linux."""
    text = str(value)
    if not text or '\x00' in text:
        raise ValueError('Empty or unsafe retained path')
    windows = bool(PureWindowsPath(str(old_root)).drive)
    constructor = PureWindowsPath if windows else PurePosixPath
    source = constructor(text)
    original_root = constructor(str(old_root))
    if source.is_absolute() or source.drive:
        try:
            relative = source.relative_to(original_root)
        except ValueError as exc:
            raise ValueError('Retained path is outside the explicit old project root') from exc
    else:
        relative = source
    parts = relative.parts
    if not parts or any(part in ('.', '..', '') or ':' in part for part in parts):
        raise ValueError('Unsafe retained path traversal')
    normalized = '/'.join(parts)
    if not any(normalized == prefix or normalized.startswith(prefix+'/') for prefix in KNOWN_PREFIXES):
        raise ValueError('Retained path is outside known REIT data paths')
    root = Path(new_root).resolve()
    mapped = root.joinpath(*parts).resolve()
    if not mapped.is_relative_to(root):
        raise ValueError('Mapped retained path escaped new project root')
    return mapped


def frozen_inputs(universe_path, plan_path, *, expected_hashes=None):
    expected = expected_hashes or FROZEN_HASHES
    paths = {'universe': Path(universe_path), 'plan': Path(plan_path)}
    hashes = {name: file_hash(path) for name, path in paths.items()}
    if hashes != expected:
        raise ValueError('Frozen input hash mismatch; no universe substitution is allowed')
    universe, plan = (load_json(paths[name]) for name in ('universe', 'plan'))
    ciks = sorted({row['cik'] for row in universe['validated']})
    if len(ciks) != 81 or any(not re.fullmatch(r'\d{10}', cik) for cik in ciks):
        raise ValueError('Frozen universe must select exactly 81 explicit issuer CIKs')
    batches = [{'batch_index': row['batch_index'], 'ciks': row['ciks']} for row in plan['batches']]
    if len(batches) != 9:
        raise ValueError('Frozen plan must contain nine batches')
    for number, batch in enumerate(batches, 1):
        if batch != {'batch_index': number, 'ciks': ciks[(number-1)*10:number*10]}:
            raise ValueError('Frozen batch differs from the explicit sorted 81 issuer selection')
    if 'validated_issuer_ciks' in plan and plan['validated_issuer_ciks'] != ciks:
        raise ValueError('Frozen plan issuer list differs from its batches')
    return {'universe': universe, 'batches': batches, 'ciks': ciks, 'input_hashes': hashes}


def checkpoint(output, config):
    output = Path(output).resolve()
    path = output/'checkpoint.json'
    if path.exists():
        value = load_json(path)
        if value.get('schema_version') != 'reit-history-remote-1' or value.get('config') != config:
            raise ValueError('Resume configuration differs from the immutable checkpoint')
        return value
    if output.exists() and any(output.iterdir()):
        raise ValueError('A new resume output directory must be empty')
    value = {'schema_version': 'reit-history-remote-1', 'config': config,
             'completed_batches': [], 'batch_results': {}, 'history_complete': False}
    save_json(path, value)
    return value


def validate_prepared_resume(output, state):
    """Never rebuild a missing mutable broker from an older unblocked snapshot."""
    output = Path(output).resolve()
    migration_path = output/'cache_migration.json'
    if not migration_path.is_file():
        raise ValueError('Prepared resume migration manifest is missing; do not recreate prior broker state')
    if state.get('preparation_status') != 'prepared' or file_hash(migration_path) != state.get('migration_sha256'):
        raise ValueError('Prepared resume migration state is absent or changed')
    database = output/'broker/broker.sqlite'
    if not database.is_file():
        raise ValueError('Prepared resume broker database is missing; prior access blocks cannot be reconstructed')
    migration = load_json(migration_path)
    if Path(migration['destination_root']).resolve() != output/'broker':
        raise ValueError('Prepared resume broker location differs from its migration manifest')
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as db:
        try:
            for entry in migration['verified']:
                row = db.execute('SELECT sha256,receipt FROM cache WHERE url=?', (entry['url'],)).fetchone()
                if row is None or row[0] != entry['sha256'] or json.loads(row[1]).get('receipt_id') != entry['receipt_id']:
                    raise ValueError('Prepared resume broker lost retained cache or receipt identities')
                receipt = db.execute('SELECT payload FROM receipts WHERE receipt_id=?', (entry['receipt_id'],)).fetchone()
                if receipt is None or json.loads(receipt[0]) != json.loads(row[1]):
                    raise ValueError('Prepared resume broker lost its retained receipt records')
            db.execute('SELECT name,last_start,blocked FROM groups').fetchall()
        except sqlite3.DatabaseError as exc:
            raise ValueError('Prepared resume broker database is invalid') from exc
    return migration


def migrate_broker(source_root, destination_root, *, contact, rate, source_database=None):
    """Import verified cache records without inventing a new retrieval receipt."""
    source_root, destination_root = Path(source_root).resolve(), Path(destination_root).resolve()
    if source_root == destination_root or destination_root.is_relative_to(source_root):
        raise ValueError('Derived broker must be separate from the original broker')
    database = Path(source_database).resolve() if source_database else source_root/'broker.sqlite'
    wal = Path(str(database)+'-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('Retained broker has pending WAL changes; use a checkpointed SQLite backup')
    original_hash = file_hash(database)
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1', uri=True)) as source:
        source.row_factory = sqlite3.Row
        candidates = [dict(row) for row in source.execute('SELECT url,sha256,receipt FROM cache ORDER BY url')]
        groups = [tuple(row) for row in source.execute('SELECT name,last_start,blocked FROM groups')]
        receipts = {row['receipt_id']: row['payload'] for row in source.execute('SELECT receipt_id,payload FROM receipts')}
    verified, unavailable = [], []
    for row in candidates:
        digest = row['sha256']
        if not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Invalid retained cache hash')
        receipt = json.loads(row['receipt'])
        if (receipt.get('url') != row['url'] or receipt.get('source_sha256') != digest
                or not re.fullmatch(r'[0-9a-f]{32}', receipt.get('receipt_id', ''))):
            raise ValueError('Retained receipt identity or hash differs from cache')
        obj = source_root/'objects'/digest
        if not obj.is_file():
            unavailable.append({'url': row['url'], 'sha256': digest, 'receipt': receipt, 'reason': 'missing_retained_object'})
            continue
        if file_hash(obj) != digest:
            raise ValueError('Retained cache object hash mismatch: '+digest)
        if not obj.resolve().is_relative_to(source_root):
            raise ValueError('Retained cache object escaped its source broker')
        stored = receipts.get(receipt['receipt_id'])
        if stored is not None and json.loads(stored) != receipt:
            raise ValueError('Original receipt table conflicts with cache receipt')
        verified.append(row)
    if file_hash(database) != original_hash:
        raise ValueError('Original broker database changed during migration')
    broker = FetchBroker(destination_root, contact_email=contact, rate=rate)
    for row in verified:
        broker._check_url(row['url'])
        obj = destination_root/'objects'/row['sha256']
        if obj.exists():
            if file_hash(obj) != row['sha256']:
                raise ValueError('Derived cache object hash mismatch')
        else:
            temporary = obj.with_name(obj.name+'.'+uuid4().hex+'.tmp')
            shutil.copyfile(source_root/'objects'/row['sha256'], temporary)
            if file_hash(temporary) != row['sha256']:
                temporary.unlink()
                raise ValueError('Retained cache hash changed during copy')
            temporary.replace(obj)
        receipt = json.loads(row['receipt'])
        with transaction(broker.db) as db:
            existing = db.execute('SELECT sha256,receipt FROM cache WHERE url=?', (row['url'],)).fetchone()
            if existing and (existing['sha256'] != row['sha256'] or json.loads(existing['receipt']) != receipt):
                raise ValueError('Derived cache conflicts with retained identity')
            db.execute('INSERT OR IGNORE INTO cache VALUES (?,?,?)', (row['url'], row['sha256'], row['receipt']))
            payload = db.execute('SELECT payload FROM receipts WHERE receipt_id=?', (receipt['receipt_id'],)).fetchone()
            if payload and json.loads(payload[0]) != receipt:
                raise ValueError('Derived receipt conflicts with original identity')
            db.execute('INSERT OR IGNORE INTO receipts VALUES (?,?)', (receipt['receipt_id'], row['receipt']))
        sidecar = destination_root/'receipts'/(receipt['receipt_id']+'.json')
        if sidecar.exists() and load_json(sidecar) != receipt:
            raise ValueError('Derived receipt sidecar conflicts with original identity')
        save_json(sidecar, receipt)
    with transaction(broker.db) as db:
        for group in groups:
            db.execute('INSERT OR IGNORE INTO groups VALUES (?,?,?)', group)
    return {'schema_version': 'reit-broker-migration-1', 'source_database_sha256': original_hash,
            'source_root': str(source_root), 'destination_root': str(destination_root),
            'verified_count': len(verified), 'candidate_count': len(candidates),
            'verified': [{'url': row['url'], 'sha256': row['sha256'],
                          'receipt_id': json.loads(row['receipt'])['receipt_id']} for row in verified],
            'unavailable': unavailable, 'originals_modified': False}


def _verify_metadata_source(row, payload_key, old_root, new_root):
    path = map_project_path(row['source_path'], old_root, new_root)
    if not path.is_file():
        return None
    if file_hash(path) != row.get('source_sha256'):
        raise ValueError('Retained metadata source hash mismatch')
    official, embedded = load_json(path), row[payload_key]
    normalizations = []
    if payload_key == 'submissions' and isinstance(official, dict) and isinstance(embedded, dict):
        source_cik = str(official.get('cik', '')).zfill(10)
        retained_cik = str(embedded.get('cik', '')).zfill(10)
        if re.fullmatch(r'\d{10}', source_cik) and source_cik == retained_cik == row['cik']:
            if type(official.get('cik')) is not type(embedded.get('cik')) or official.get('cik') != embedded.get('cik'):
                normalizations.append('submissions.cik_integer_or_digit_string_identity')
            official, embedded = dict(official, cik=source_cik), dict(embedded, cik=retained_cik)
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if canonical(official) != canonical(embedded):
        raise ValueError('Retained metadata payload differs from verified source bytes')
    return dict(row, source_path=str(path), source_json_normalizations=normalizations)


def pending_pages(metadata):
    pending = []
    for item in metadata:
        present = {page['name'] for page in item.get('historical_pages', [])}
        for reference in item['submissions'].get('filings', {}).get('files', []):
            name = reference.get('name', '')
            if not re.fullmatch(r'CIK'+item['cik']+r'-submissions-\d+\.json', name):
                raise ValueError('Historical metadata filename identity mismatch')
            if name not in present:
                pending.append({'cik': item['cik'], **reference, 'url': 'https://data.sec.gov/submissions/'+name,
                                'reason': 'missing_verified_historical_page', 'status': 'pending'})
    return pending


def prepare_metadata(original, ciks, *, old_root, new_root):
    """Select frozen issuers and hash-bind each retained official metadata page."""
    selected, unavailable = [], []
    originals = {}
    for row in original['metadata']:
        if row['cik'] in ciks:
            if row['cik'] in originals:
                raise ValueError('Duplicate retained issuer metadata')
            originals[row['cik']] = row
    for cik in ciks:
        row = originals.get(cik)
        if row is None:
            unavailable.append({'cik': cik, 'url': f'https://data.sec.gov/submissions/CIK{cik}.json', 'reason': 'missing_issuer_metadata', 'status': 'pending'})
            continue
        if row.get('source_url') != f'https://data.sec.gov/submissions/CIK{cik}.json':
            raise ValueError('Official submissions URL differs from issuer identity')
        value = _verify_metadata_source(row, 'submissions', old_root, new_root)
        if value is None:
            unavailable.append({'cik': cik, 'url': row['source_url'], 'reason': 'missing_retained_submissions_object', 'status': 'pending'})
            continue
        if str(value['submissions'].get('cik', '')).zfill(10) != cik:
            raise ValueError('Official submissions CIK mismatch')
        value['historical_pages'] = []
        names = set()
        for page in row.get('historical_pages', []):
            if not re.fullmatch(r'CIK'+cik+r'-submissions-\d+\.json', page['name']):
                raise ValueError('Historical metadata page differs from issuer identity')
            if page['name'] in names:
                raise ValueError('Duplicate historical metadata page')
            names.add(page['name'])
            if page.get('source_url') != 'https://data.sec.gov/submissions/'+page['name']:
                raise ValueError('Historical metadata URL differs from page identity')
            verified = _verify_metadata_source(page, 'data', old_root, new_root)
            if verified is not None:
                value['historical_pages'].append(verified)
        selected.append(value)
    pending = unavailable+pending_pages(selected)
    return selected, {'pending': pending, 'verified_issuers': len(selected), 'requested_issuers': len(ciks),
                      'metadata_complete': not pending, 'history_complete': False,
                      'scope': '2024-01-01 through 2026-10-03 with opening context; every referenced metadata page is explicit'}


def complete_metadata(metadata, ciks, broker, status_path):
    """Fetch missing official metadata using the same single broker as history."""
    by_cik = {row['cik']: deepcopy(row) for row in metadata}
    def result_row(cik, url, payload_key, name=None):
        result = broker.fetch(url)
        payload = load_json(result['path'])
        if payload_key == 'submissions' and str(payload.get('cik', '')).zfill(10) != cik:
            raise ValueError('Fetched submissions CIK mismatch')
        value = {payload_key: payload, 'source_url': url, 'source_path': result['path'],
                 'source_sha256': result['sha256'], 'retrieved_at': result['receipt'].get('retrieved_at'),
                 'receipt': result['receipt']}
        return dict(value, name=name) if name else dict(value, cik=cik, historical_pages=[])
    def status():
        pending = [{'cik': cik, 'url': f'https://data.sec.gov/submissions/CIK{cik}.json', 'status': 'pending'} for cik in ciks if cik not in by_cik]
        pending.extend(pending_pages(list(by_cik.values())))
        save_json(status_path, {'pending': pending, 'metadata_complete': not pending, 'history_complete': False})
    status()
    try:
        for cik in ciks:
            if cik not in by_cik:
                by_cik[cik] = result_row(cik, f'https://data.sec.gov/submissions/CIK{cik}.json', 'submissions')
                status()
        for task in pending_pages(list(by_cik.values())):
            by_cik[task['cik']]['historical_pages'].append(result_row(task['cik'], task['url'], 'data', task['name']))
            status()
    finally:
        save_json(Path(status_path).with_name('metadata.json'), {'metadata': [by_cik[cik] for cik in ciks if cik in by_cik]})
    return [by_cik[cik] for cik in ciks]


def collection_identities(documents):
    identities = sorted((row['url'], row['cik'], row['sha256']) for row in documents)
    if len(identities) != len(set(identities)):
        raise ValueError('Collection contains duplicate completed source identities')
    return [{'url': url, 'cik': cik, 'sha256': digest} for url, cik, digest in identities]


def verify_completed_batch(output, result):
    """Recheck completion facts and retained bytes before skipping a batch."""
    output = Path(output).resolve()
    manifest = Path(result['manifest_path']).resolve()
    if not manifest.is_relative_to(output) or file_hash(manifest) != result['manifest_sha256']:
        raise ValueError('Completed batch manifest path or hash changed')
    batch_output = output/'history'/('batch-'+str(result['batch_index']).zfill(2))
    collection_path = batch_output/'collection/manifest.json'
    if (result.get('collection_manifest_path') != str(collection_path)
            or not collection_path.is_file()
            or file_hash(collection_path) != result.get('collection_manifest_sha256')):
        raise ValueError('Completed collection manifest path or hash changed')
    collection = load_json(collection_path)
    if collection_identities(collection['documents']) != result.get('completed_source_identities'):
        raise ValueError('Completed collection URL/CIK/source identity set changed')
    for document in collection['documents']:
        for field, digest_field in (('source_path', 'sha256'), ('text_path', 'text_sha256')):
            path = Path(document[field]).resolve()
            if not path.is_relative_to(batch_output) or file_hash(path) != document[digest_field]:
                raise ValueError('Completed batch retained document path or hash changed')


def run_batches(metadata, frozen, output, broker, state, *, history_stage,
                max_exhibits=10000, limit=None):
    """Use independent fresh outputs for each explicit frozen issuer group."""
    from src.reit_inventory import build_inventory
    output = Path(output).resolve()
    inventory = build_inventory({'ciks': sorted({cik for row in frozen['batches'] for cik in row['ciks']}),
                                 'start_date': START_DATE, 'end_date': END_DATE, 'opening_context': True}, metadata)
    save_json(output/'metadata_inventory_preflight.json', inventory['coverage'])
    if not inventory['coverage']['filing_metadata_complete']:
        raise ValueError('Metadata inventory has pending pages, errors, or conflicts; history has not started')
    for batch in frozen['batches']:
        number = batch['batch_index']
        if number in state['completed_batches']:
            verify_completed_batch(output, state['batch_results'][str(number)])
            continue
        batch_output = output/'history'/('batch-'+str(number).zfill(2))
        result = history_stage(metadata, frozen['universe'], batch_output, broker, limit,
                               requested=list(batch['ciks']), batch_index=number,
                               batch_size=10, max_exhibits=max_exhibits)
        manifests = list((batch_output/'batches').glob('*/batch_manifest.json'))
        if len(manifests) != 1:
            raise ValueError('Expected one batch manifest in the fresh explicit batch output')
        collection_path = batch_output/'collection/manifest.json'
        collection = load_json(collection_path)
        identities = collection_identities(collection['documents'])
        if any(entry['cik'] not in batch['ciks'] for entry in identities):
            raise ValueError('Completed collection contains an issuer outside its frozen batch')
        reported = set(result.get('completed_document_urls', [])) | set(result.get('completed_exhibit_urls', []))
        if {entry['url'] for entry in identities} != reported:
            raise ValueError('Completed collection identity set differs from reported batch URLs')
        state['batch_results'][str(number)] = {
            'batch_index': number, 'ciks': batch['ciks'], 'manifest_path': str(manifests[0].resolve()),
            'manifest_sha256': file_hash(manifests[0]),
            'collection_manifest_path': str(collection_path),
            'collection_manifest_sha256': file_hash(collection_path),
            'completed_source_identities': identities,
            'selected_collection_complete': result['selected_collection_complete'],
            'omitted_exhibit_count': len(result['omitted_exhibits']),
            'exhibit_enumeration_cap': 10000, 'history_complete': False,
        }
        if result['selected_collection_complete']:
            state['completed_batches'].append(number)
        state['selected_batches_complete'] = len(state['completed_batches']) == len(frozen['batches'])
        save_json(output/'checkpoint.json', state)
        if not result['selected_collection_complete']:
            break
    return state
