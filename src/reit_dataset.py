"""Offline content-addressed REIT exports with retained-source verification.

Publication is a research artifact integrity gate, never financial, authority,
historical coverage, public availability, or trading validation.
"""
from __future__ import annotations

import csv
from hashlib import sha256
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import sqlite3
import tempfile
from urllib.parse import unquote, urlsplit

SCHEMA_VERSION = 'reit-dataset-3'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_FIELDS = ('source_path', 'text_path', 'text_artifact_path')
TABLES = ('financial_histories', 'instrument_financial_histories', 'entities', 'company_entities', 'instruments', 'role_edges',
          'intersections', 'review', 'issuers', 'securities', 'filings', 'sources', 'documents')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _hash(value):
    return sha256(_json(value).encode('utf-8')).hexdigest()


def _file_hash(path):
    digest = sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _rows(value, key):
    rows = value.get(key, [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f'{key} must be an array of objects')
    return rows


def _references(value):
    if isinstance(value, dict):
        if value.get('source_path') and (value.get('source_sha256') or value.get('sha256') or value.get('raw_sha256')):
            yield value
        for child in value.values():
            yield from _references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _references(child)


def _resolve_reference(reference, source_root=None, *, relative_only=False):
    """Resolve a reference for I/O, bounding portable paths to the project."""
    path = Path(reference)
    if source_root is None:
        return path.resolve()
    windows = PureWindowsPath(reference)
    if relative_only and (path.is_absolute() or windows.anchor):
        raise ValueError(f'unsafe source reference: {reference}')
    if windows.anchor and not path.is_absolute():
        raise ValueError(f'unsafe source reference: {reference}')
    # Published references use POSIX separators on every host.
    if not path.is_absolute():
        path = source_root / Path(str(reference).replace('\\', '/'))
    resolved = path.resolve()
    if not resolved.is_relative_to(source_root):
        raise ValueError(f'source reference outside source root: {reference}')
    return resolved


def _normalize_paths(value, source_root=None, *, relative_only=False):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in REFERENCE_FIELDS and isinstance(child, str) and child:
                resolved = _resolve_reference(child, source_root, relative_only=relative_only)
                value[key] = resolved.relative_to(source_root).as_posix() if source_root else str(resolved)
            else:
                _normalize_paths(child, source_root, relative_only=relative_only)
    elif isinstance(value, list):
        for child in value:
            _normalize_paths(child, source_root, relative_only=relative_only)


def _lineage(inputs, source_root=None):
    """Hash raw bytes and extracted JSON independently of caller eligibility."""
    lineage, gaps = [], []
    references = list(inputs['documents']) + list(_references(inputs))
    seen = set()
    for source in references:
        path = source.get('source_path')
        digest = source.get('sha256') or source.get('source_sha256') or source.get('raw_sha256')
        url = source.get('url') or source.get('source_url')
        text_path = source.get('text_path') or source.get('text_artifact_path')
        declarations = [source[field] for field in ('extracted_text_sha256', 'text_artifact_sha256', 'text_sha256')
                        if source.get(field)]
        anchored = bool(declarations) and not source.get('original_extraction_digest_unanchored', False)
        key = _json([path, digest, url, source.get('accession'), text_path, declarations, anchored])
        if key in seen:
            continue
        seen.add(key)
        record = {'source_path': path if path else None,
                  'raw_sha256': digest, 'source_url': url, 'accession': source.get('accession'),
                  'document_id': source.get('document_id'), 'text_path': None,
                  'text_sha256': None, 'raw_verified': False, 'text_verified': False}
        if not path or not digest:
            gaps.append({'kind': 'raw_reference_incomplete', 'document_id': source.get('document_id')})
        else:
            try:
                actual = _file_hash(_resolve_reference(path, source_root))
            except OSError:
                gaps.append({'kind': 'source_unreadable', 'source_path': str(path)})
            else:
                if actual != digest:
                    raise ValueError(f'raw source hash mismatch: {path}')
                record['raw_verified'] = True
        if url and source.get('accession') and '/Archives/edgar/data/' in url:
            parts = urlsplit(url)
            accession = str(source['accession']).replace('-', '')
            if accession not in unquote(parts.path).split('/'):
                raise ValueError(f'source URL accession identity mismatch: {url}')
            match = re.search(r'/Archives/edgar/data/(\d+)/', parts.path)
            if match and source.get('cik') and int(match.group(1)) != int(source['cik']):
                raise ValueError(f'source URL CIK identity mismatch: {url}')
        if text_path:
            record['text_path'] = text_path
            try:
                resolved_text = _resolve_reference(text_path, source_root)
                text_sha = _file_hash(resolved_text)
                extracted = json.loads(resolved_text.read_text(encoding='utf-8-sig'))
            except (OSError, ValueError):
                raise ValueError(f'extracted JSON unreadable: {text_path}') from None
            if not isinstance(extracted, dict):
                raise ValueError('extracted JSON must be an object')
            if any(declared != text_sha for declared in declarations):
                raise ValueError(f'extracted JSON hash mismatch: {text_path}')
            if not anchored:
                gaps.append({'kind':'extracted_digest_unanchored','text_path':str(text_path),
                             'limitation':'A newly computed cache digest does not prove its original native extraction.'})
            binding = extracted.get('sha256') or extracted.get('source_sha256') or extracted.get('extracted_raw_sha256')
            if not digest or binding != digest:
                raise ValueError(f'extracted JSON raw identity mismatch: {text_path}')
            extracted_path = extracted.get('source_path')
            if source_root is not None and extracted_path and (Path(extracted_path).is_absolute() or PureWindowsPath(extracted_path).anchor):
                raise ValueError(f'portable extracted JSON requires project-relative source_path or omission; create host-neutral derived JSON: {text_path}')
            if extracted.get('source_path') and path and _resolve_reference(extracted['source_path'], source_root) != _resolve_reference(path, source_root):
                raise ValueError(f'extracted JSON source path identity mismatch: {text_path}')
            extracted_url = extracted.get('source_url') or extracted.get('url')
            for field, wanted, observed in [('URL', url, extracted_url),
                                             ('accession', source.get('accession'), extracted.get('accession'))]:
                if wanted and observed and wanted != observed:
                    raise ValueError(f'extracted JSON {field} identity mismatch: {text_path}')
                if wanted and not observed:
                    gaps.append({'kind': 'extracted_' + field.lower() + '_identity_missing', 'text_path': str(text_path)})
            record['text_sha256'] = text_sha
            record['text_verified'] = record['raw_verified'] and anchored
        elif source in inputs['documents']:
            gaps.append({'kind': 'extracted_json_missing', 'document_id': source.get('document_id')})
        lineage.append(record)
    return sorted(lineage, key=_json), sorted(gaps, key=_json)


def _export(stage, tables):
    database = sqlite3.connect(stage / 'dataset.sqlite')
    try:
        for name, rows in tables.items():
            with (stage / (name + '.jsonl')).open('w', encoding='utf-8', newline='\n') as stream:
                for row in rows:
                    stream.write(_json(row) + '\n')
            fields = sorted({key for row in rows for key in row})
            with (stage / (name + '.csv')).open('w', encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields or ['row_json'])
                writer.writeheader()
                for row in rows:
                    writer.writerow({key: _json(value) if isinstance(value, (dict, list)) else value for key, value in row.items()})
            database.execute(f'CREATE TABLE "{name}" (row_number INTEGER PRIMARY KEY, record_id TEXT, issuer_cik TEXT, effective_at TEXT, available_at TEXT, evidence_json TEXT, row_json TEXT NOT NULL)')
            for index, row in enumerate(rows):
                cik = row.get('issuer_cik') or row.get('cik')
                if not cik and str(row.get('company_id', '')).startswith('cik:'):
                    cik = row['company_id'][4:]
                cik = str(cik).zfill(10) if cik is not None and str(cik).isdigit() else cik
                database.execute(f'INSERT INTO "{name}" VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (index, row.get('record_id') or row.get('entity_id') or row.get('instrument_id') or row.get('assertion_id'),
                     cik, row.get('effective_at') or row.get('period_end') or row.get('filing_date') or row.get('date'),
                     row.get('available_at') or row.get('accepted_at'), _json(row.get('evidence', [])), _json(row)))
            database.execute(f'CREATE INDEX "{name}_issuer_date" ON "{name}"(issuer_cik, effective_at)')
        database.commit()
    finally:
        database.close()


def _write_manifest(stage, manifest):
    with (stage / 'manifest.json').open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(_json(manifest) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def publish_snapshot(output_root, *, universe, inventory, quality, histories, network, documents, provenance, source_root=None):
    """Publish exports atomically; reject corrupt inputs and never overwrite."""
    inputs = dict(universe=universe, inventory=inventory, quality=quality, histories=histories,
                  network=network, documents=documents, provenance=provenance)
    for name in ('universe', 'inventory', 'quality', 'histories', 'network', 'provenance'):
        if not isinstance(inputs[name], dict):
            raise ValueError(f'{name} must be an object')
    if isinstance(documents, dict):
        documents = documents.get('documents')
        inputs['documents'] = documents
    if not isinstance(documents, list) or any(not isinstance(row, dict) for row in documents):
        raise ValueError('documents must be an array of objects')
    # Strict serialization rejects NaN and non-JSON objects before staging.
    inputs = json.loads(_json(inputs))
    source_root = Path(source_root).resolve() if source_root is not None else None
    _normalize_paths(inputs, source_root)
    universe, inventory, quality, histories, network, documents = (inputs[name] for name in
        ('universe', 'inventory', 'quality', 'histories', 'network', 'documents'))
    lineage, gaps = _lineage(inputs, source_root)
    tables = {'financial_histories': _rows(histories, 'financial_history'),
              'instrument_financial_histories': _rows(network, 'financial_history'),
              **{name: _rows(network, name) for name in ('entities', 'company_entities', 'instruments', 'role_edges', 'intersections')},
              'review': [{'review_origin': origin, **row} for origin, value in [('histories', histories), ('network', network)] for row in _rows(value, 'review')],
              'issuers': _rows(universe, 'issuers'), 'securities': _rows(universe, 'securities'),
              'filings': _rows(inventory, 'selected'), 'sources': _rows(quality, 'sources'), 'documents': documents}
    implementation_paths = [Path(__file__)] + [Path(__file__).with_name('reit_' + name + '.py') for name in ('universe', 'inventory', 'source_quality', 'histories', 'relationships')]
    implementation = {path.name: _file_hash(path) for path in implementation_paths if path.exists()}
    for name in ('universe', 'inventory', 'quality', 'histories', 'network'):
        if not inputs[name]:
            gaps.append({'kind': 'empty_input', 'input': name})
        coverage = inputs[name].get('coverage', {})
        if coverage:
            gaps.append({'kind': 'upstream_coverage', 'input': name, 'coverage': coverage})
    required_fields = {'universe': ('issuers', 'securities'), 'inventory': ('selected',),
                       'quality': ('sources',), 'histories': ('financial_history', 'review'),
                       'network': ('entities', 'instruments', 'role_edges', 'intersections', 'review')}
    for name, fields in required_fields.items():
        for field in fields:
            if field not in inputs[name]:
                gaps.append({'kind': 'missing_input_field', 'input': name, 'field': field})
    base = {'schema_version': SCHEMA_VERSION, 'reference_mode': 'project_relative' if source_root else 'absolute',
            'input_sha256': {key: _hash(value) for key, value in inputs.items()},
            'implementation_sha256': implementation, 'lineage': lineage, 'counts': {key: len(value) for key, value in tables.items()},
            'gaps': gaps, 'limits': ['retained_source_scope', 'no_independent_authority_or_financial_validation',
                                   'historical_availability_and_executable_trading_unverified', 'no_performance_claims'],
            'source_integrity_verified': bool(lineage) and all(row['raw_verified'] for row in lineage),
            'historical_ready': False, 'trading_ready': False, 'pipeline_complete': False}
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.staging-', dir=root))
    try:
        (stage / 'inputs.json').write_text(_json(inputs) + '\n', encoding='utf-8', newline='\n')
        _export(stage, tables)
        artifacts = {path.name: {'sha256': _file_hash(path), 'bytes': path.stat().st_size} for path in sorted(stage.iterdir())}
        manifest = {**base, 'artifacts': artifacts}
        fingerprint = _hash(manifest)
        manifest['fingerprint'] = fingerprint
        target = root / ('snapshot-' + fingerprint)
        _write_manifest(stage, manifest)  # Commit marker is written last, before atomic publication.
        staged_check = verify_snapshot(stage, source_root=source_root)
        if not staged_check['valid']:
            raise ValueError('staged snapshot verification failed: ' + _json(staged_check['errors']))
        if target.exists():
            checked = verify_snapshot(target, source_root=source_root)
            if not checked['valid'] or checked['fingerprint'] != fingerprint:
                raise ValueError('existing immutable snapshot failed verification')
        else:
            try:
                stage.rename(target)
            except FileExistsError:
                checked = verify_snapshot(target, source_root=source_root)
                if not checked['valid'] or checked['fingerprint'] != fingerprint:
                    raise ValueError('concurrent immutable snapshot failed verification') from None
        return {**manifest, 'snapshot_dir': str(target), 'verified': True}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def verify_snapshot(snapshot_dir, *, source_root=None):
    """Reopen exports and rehash retained raw/text references, without mutation."""
    directory = Path(snapshot_dir)
    errors = []
    manifest = {}
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        fingerprint = manifest.get('fingerprint')
        if manifest.get('schema_version') not in (SCHEMA_VERSION, 'reit-dataset-2'):
            errors.append('unsupported_schema')
        mode = manifest.get('reference_mode', 'absolute' if manifest.get('schema_version') == 'reit-dataset-2' else None)
        if mode not in ('absolute', 'project_relative'):
            raise ValueError('unsupported_reference_mode')
        reference_root = Path(source_root).resolve() if source_root is not None else PROJECT_ROOT
        if mode == 'absolute':
            reference_root = None
        if _hash({key: value for key, value in manifest.items() if key != 'fingerprint'}) != fingerprint:
            errors.append('manifest_fingerprint_mismatch')
        if directory.name.startswith('snapshot-') and directory.name != 'snapshot-' + str(fingerprint):
            errors.append('directory_fingerprint_mismatch')
        artifacts = manifest['artifacts']
        required = {'inputs.json', 'dataset.sqlite'} | {name + ext for name in TABLES for ext in ('.jsonl', '.csv')}
        if set(artifacts) != required:
            errors.append('artifact_inventory_mismatch')
        for name, receipt in artifacts.items():
            if Path(name).name != name or name in ('.', '..'):
                errors.append('unsafe_artifact_path')
                continue
            path = directory / name
            if _file_hash(path) != receipt['sha256'] or path.stat().st_size != receipt['bytes']:
                errors.append('artifact_hash_mismatch:' + name)
        inputs = json.loads((directory / 'inputs.json').read_text(encoding='utf-8'))
        if {key: _hash(value) for key, value in inputs.items()} != manifest['input_sha256']:
            errors.append('input_fingerprint_mismatch')
        normalized = json.loads(_json(inputs))
        _normalize_paths(normalized, reference_root, relative_only=mode == 'project_relative')
        if normalized != inputs:
            errors.append('noncanonical_source_reference')
        lineage, _ = _lineage(inputs, reference_root)
        if lineage != manifest['lineage']:
            errors.append('retained_source_lineage_mismatch')
        connection = sqlite3.connect((directory / 'dataset.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
        try:
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                errors.append('sqlite_integrity_failure')
            for name in TABLES:
                if connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] != manifest['counts'][name]:
                    errors.append('table_count_mismatch:' + name)
        finally:
            connection.close()
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        errors.append(str(exc))
    return {'valid': not errors, 'fingerprint': manifest.get('fingerprint'), 'errors': errors,
            'historical_ready': False, 'trading_ready': False, 'pipeline_complete': False}
