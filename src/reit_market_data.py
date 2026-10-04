"""Databento acquisition receipts, conservative paid submission, and readiness gates.

No automatic retries of paid POSTs. A lost acknowledgement remains a durable
reservation until a human reconciles a provider job with its exact request.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse
from uuid import uuid4

import requests
from src.reit_budget import BudgetExceeded, legacy_spend

API = 'https://hist.databento.com/v0/'
DOWNLOAD_HOSTS = frozenset({'api.databento.com', 'hist.databento.com'})
RESERVE_BYTES = 1_000_000_000
QUOTE_MAX_AGE = timedelta(minutes=15)
FILTER_FIELDS = ('dataset', 'start', 'end', 'symbols', 'schema', 'stype_in', 'stype_out', 'limit')
REPRICING_GATES = ('point_in_time_features', 'matured_labels', 'past_only_folds',
                  'trial_register', 'purge_embargo', 'cost_capital_stress', 'holdout_audit')
STRICT_GATES = ('synchronized_quotes', 'dividends', 'american_exercise', 'borrow',
                'financing', 'margin', 'assignment', 'leg_risk', 'contract_identity')


class AmbiguousSubmission(RuntimeError):
    """A paid request may exist; reconciliation is required before any retry."""


def fingerprint(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def _cost(value) -> str:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Provider returned an invalid cost') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('Provider returned an invalid cost')
    return str(result)


def normalize_payload(payload: dict) -> dict:
    """Freeze defaults and symbology; reject unsupported/unquoted selectors."""
    allowed = set(FILTER_FIELDS) | {'encoding', 'compression', 'pretty_px', 'pretty_ts',
        'map_symbols', 'split_symbols', 'split_duration', 'split_size', 'delivery'}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError('Unknown acquisition request fields')
    result = {'stype_in': 'raw_symbol', 'stype_out': 'instrument_id', 'encoding': 'csv',
        'compression': 'zstd', 'pretty_px': True, 'pretty_ts': True, 'map_symbols': True,
        'split_symbols': False, 'split_duration': 'month', 'delivery': 'download', **payload}
    for field in ('dataset', 'schema', 'start', 'end', 'symbols'):
        if not result.get(field):
            raise ValueError(f'An explicit {field} is required')
    if not isinstance(result['dataset'], str) or not isinstance(result['schema'], str):
        raise ValueError('Dataset and schema must be strings')
    symbols = result['symbols']
    if isinstance(symbols, list):
        symbols = ','.join(str(item) for item in symbols)
    if not isinstance(symbols, str) or not symbols or any(not s for s in symbols.split(',')):
        raise ValueError('Symbols must be a nonempty string or list')
    if len(symbols.split(',')) > 2000 or symbols == 'ALL_SYMBOLS':
        raise ValueError('Select at most 2,000 explicit symbols; broad all-symbol purchases are disabled')
    result['symbols'] = symbols
    start, end = _time(result['start']), _time(result['end'])
    if start < _time('2024-01-01') or start >= end:
        raise ValueError('REIT research requests require January 2024 onward and start < end')
    result['start'], result['end'] = start.isoformat(), end.isoformat()
    if result['stype_out'] != 'instrument_id' or result['delivery'] != 'download':
        raise ValueError('Only instrument_id output and download delivery are supported')
    if 'limit' in result and (not isinstance(result['limit'], int) or isinstance(result['limit'], bool) or result['limit'] <= 0):
        raise ValueError('Limit must be a positive integer')
    return result


def load_api_key(project: Path) -> str:
    """Read only the required key; do not evaluate or import .env contents."""
    key = os.environ.get('DATABENTO_API_KEY', '').strip()
    if not key:
        for line in (Path(project) / '.env').read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.strip().partition('=')
            if sep and name == 'DATABENTO_API_KEY':
                key = value.strip().strip('\"\'')
                break
    if not key:
        raise ValueError('DATABENTO_API_KEY is missing')
    return key


def sanitize(value, key: str = ''):
    """Remove credential fields recursively and key values even in messages."""
    if isinstance(value, dict):
        return {str(k): sanitize(v, key) for k, v in value.items()
                if not any(secret in str(k).lower() for secret in
                           ('api_key', 'password', 'secret', 'token', 'authorization', 'credential'))}
    if isinstance(value, list):
        return [sanitize(v, key) for v in value]
    if isinstance(value, str) and key:
        return value.replace(key, '[REDACTED]')
    return value


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    with temp.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def _safe_name(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 200 or value in {'.', '..'}:
        raise ValueError('Unsafe provider filename or job identifier')
    if any(char in value for char in '/\\:<>\"|?*') or any(ord(c) < 32 for c in value) or value[-1] in '. ':
        raise ValueError('Unsafe provider filename or job identifier')
    stem = value.split('.')[0].rstrip(' .').upper()
    if stem in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in '123456789¹²³'), *(f'LPT{i}' for i in '123456789¹²³')}:
        raise ValueError('Unsafe Windows device filename')
    return value


def validate_file(item: dict) -> tuple[str, int, str, str]:
    name = _safe_name(item.get('filename'))
    if name.casefold() == 'download_manifest.json':
        raise ValueError('Provider filename conflicts with generated acquisition manifest')
    size = item.get('size')
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError('Invalid provider file size')
    digest = item.get('hash', '')
    if not isinstance(digest, str) or not re.fullmatch(r'(sha256:)?[0-9a-fA-F]{64}', digest):
        raise ValueError('SHA-256 is required for each downloaded file')
    url = item.get('urls', {}).get('https', '')
    parsed = urlparse(url)
    if (parsed.scheme != 'https' or parsed.hostname not in DOWNLOAD_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError('Unexpected authenticated download host')
    return name, size, digest.removeprefix('sha256:').lower(), url


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class DatabentoClient:
    def __init__(self, key: str, receipt_dir: Path, *, session=None, legacy_ledger=None):
        if not key:
            raise ValueError('Databento key is required')
        self._key = key
        self.receipt_dir = Path(receipt_dir)
        self.session = session if session is not None else requests.Session()
        self.legacy_ledger = Path(legacy_ledger) if legacy_ledger is not None else (
            Path(__file__).resolve().parents[1] / 'data' / 'raw' / 'databento' / 'acquisition_ledger.json')

    def _refresh_spend(self, ledger):
        ledger.refresh_external(max(Decimal('23.14'), legacy_spend(self.legacy_ledger)))
        if ledger.summary()['over_budget']:
            raise BudgetExceeded('Latest external spend plus reservations exceeds the authorized ceiling')

    def _receipt(self, operation, request, result):
        value = sanitize({'operation': operation, 'observed_at': datetime.now(timezone.utc).isoformat(),
                          'request': request, 'result': result}, self._key)
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '-' + operation + '-' + uuid4().hex[:8] + '.json'
        save_json(self.receipt_dir / name, value)

    def _call(self, method: str, endpoint: str, params=None, *, receipt=True):
        kwargs = {'auth': (self._key, ''), 'timeout': (20, 120), 'allow_redirects': False}
        kwargs['data' if method == 'POST' else 'params'] = params or {}
        try:
            response = self.session.request(method, API + endpoint, **kwargs)
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise ValueError('Unexpected API redirect')
            result = sanitize(response.json(), self._key)
        except requests.RequestException as exc:
            raise RuntimeError(f'Databento {endpoint} failed ({type(exc).__name__}); response details redacted') from None
        if receipt:
            self._receipt(endpoint, params or {}, result)
        return result

    def metadata(self, operation: str, **params):
        if operation not in {'list_datasets', 'list_schemas', 'get_dataset_range',
                             'get_dataset_condition', 'list_publishers', 'list_fields'}:
            raise ValueError('Unsupported metadata operation')
        return self._call('GET', 'metadata.' + operation, params)

    def batch(self, operation: str, **params):
        if operation not in {'list_jobs', 'list_files', 'get_job_details'}:
            raise ValueError('Only read-only job operations are exposed here')
        return self._call('GET', 'batch.' + operation, params)

    def quote(self, payload: dict) -> dict:
        frozen = normalize_payload(payload)
        dates = {'start_date': frozen['start'][:10], 'end_date': frozen['end'][:10]}
        # Date-filtered catalog discovery may return [] over broad intervals even
        # when products have coverage. Explicit dataset/schema ranges govern dates.
        datasets = self.metadata('list_datasets')
        if frozen['dataset'] not in datasets:
            raise ValueError('Dataset absent from provider catalog; inspect metadata receipt')
        schemas = self.metadata('list_schemas', dataset=frozen['dataset'])
        if frozen['schema'] not in schemas:
            raise ValueError('Schema unavailable for this dataset')
        available = self.metadata('get_dataset_range', dataset=frozen['dataset'])
        bounds = available.get('schema', {}).get(frozen['schema']) if 'schema' in available else available
        if not isinstance(bounds, dict) or not bounds.get('start') or not bounds.get('end'):
            raise ValueError('Dataset availability bounds are missing')
        if _time(frozen['start']) < _time(bounds['start']) or _time(frozen['end']) > _time(bounds['end']):
            raise ValueError('Requested period exceeds available dataset range')
        # Conditions use inclusive end dates; include only the last requested date.
        last_date = (_time(frozen['end']) - timedelta(microseconds=1)).date().isoformat()
        conditions = self.metadata('get_dataset_condition', dataset=frozen['dataset'],
                                   start_date=dates['start_date'], end_date=last_date)
        if not isinstance(conditions, list) or not conditions:
            raise ValueError('Provider returned no dataset quality evidence')
        filters = {name: frozen[name] for name in FILTER_FIELDS if name in frozen}
        cost = _cost(self._call('POST', 'metadata.get_cost', filters))
        result = {'payload': frozen, 'fingerprint': fingerprint(frozen), 'cost_usd': cost,
                  'quoted_at': datetime.now(timezone.utc).isoformat(),
                  'metadata': {'datasets': datasets, 'schemas': schemas, 'range': available,
                               'conditions': conditions},
                  'quality': 'provider_conditions_require_review',
                  'quote_scope': ('aggregated_component_venues' if frozen['dataset'] == 'EQUS.MINI'
                                  else 'unverified; schema name alone does not prove stock NBBO')}
        self._receipt('quote', frozen, result)
        return result

    def submit(self, request_id: str, payload: dict, quote: dict, ledger) -> dict:
        frozen = normalize_payload(payload)
        if quote.get('fingerprint') != fingerprint(frozen) or quote.get('payload') != frozen:
            raise ValueError('Quote does not match the exact submit payload')
        age = datetime.now(timezone.utc) - _time(quote['quoted_at'])
        if age < timedelta(0) or age > QUOTE_MAX_AGE:
            raise ValueError('Quote expired; obtain a new exact quote')
        existing = next((order for order in ledger.summary()['orders'] if order['request_id'] == request_id), None)
        if existing and existing['status'] != 'reserved':
            raise ValueError('Request has reached submission; reconcile the job instead of retrying')
        if any(order['request_id'] != request_id and order['status'] != 'released'
               and order['fingerprint'] == fingerprint(frozen) for order in ledger.summary()['orders']):
            raise ValueError('Identical request is already reserved or submitted under another ID; reconcile it')
        fresh = self.quote(frozen)
        if Decimal(fresh['cost_usd']) != Decimal(_cost(quote['cost_usd'])):
            raise ValueError('Provider quote changed; review a new exact quote before submitting')
        self._refresh_spend(ledger)
        order = ledger.reserve(request_id, frozen, fresh['cost_usd'])
        if order['status'] != 'reserved':
            raise ValueError('Request cannot be submitted in its current state')
        self._receipt('reserved', {'request_id': request_id}, order)
        self._refresh_spend(ledger)
        ledger.mark_submitting(request_id)
        # Persist submitting before the network. Any exception thereafter is ambiguous,
        # including a receipt write failure or a successful POST with malformed JSON.
        try:
            self._receipt('submitting', {'request_id': request_id}, {'fingerprint': fingerprint(frozen)})
            job = self._call('POST', 'batch.submit_job', frozen, receipt=False)
            job_id = job.get('id') or job.get('job_id')
            if not isinstance(job_id, str) or not job_id:
                raise ValueError('Provider response lacked a job identifier')
            ledger.mark_submitted(request_id, job_id)
        except Exception:
            ledger.mark_unknown(request_id, 'Submission acknowledgement unavailable; reconcile provider jobs')
            raise AmbiguousSubmission('Paid submission may exist. Funds held; do not automatically retry.') from None
        self._receipt('submitted', {'request_id': request_id, 'fingerprint': fingerprint(frozen)}, job)
        return job

    def reconcile(self, request_id: str, job_id: str, ledger) -> dict:
        """Bind only a provider job with all exact selectors and matching submit time."""
        order = next((v for v in ledger.summary()['orders'] if v['request_id'] == request_id), None)
        if not order or order['status'] not in {'submitting', 'unknown_held', 'submitted'}:
            raise ValueError('Request is not awaiting provider reconciliation')
        if order.get('job_id') is not None and order['job_id'] != job_id:
            raise ValueError('Request is already bound to a different provider job')
        job = self.batch('get_job_details', job_id=job_id)
        if any(value['request_id'] != request_id and value.get('job_id') == job_id
               for value in ledger.summary()['orders']):
            raise ValueError('Provider job is already bound to another reservation')
        if (job.get('id') or job.get('job_id')) != job_id:
            raise ValueError('Provider job identity mismatch')
        expected = order['payload']
        # Full frozen request includes encoding, flags, splits and delivery. Missing
        # exposed fields are not inferred. SDK optional limit/split_size default to
        # None; a returned explicit limit/split must never silently match absence.
        for field in ('limit', 'split_size'):
            if field not in expected and job.get(field) is not None:
                raise ValueError(f'Cannot reconcile job: unexpected {field}')
        for field, wanted in expected.items():
            actual = job.get(field)
            if field in {'limit', 'split_size'} and wanted is None and actual is None:
                continue
            if field not in job:
                raise ValueError(f'Cannot reconcile job: exact {field} is missing')
            if field == 'symbols' and isinstance(actual, list):
                actual = ','.join(str(v) for v in actual)
            if field in {'start', 'end'} and actual is not None:
                actual = _time(actual).isoformat()
            if actual != wanted or (isinstance(wanted, bool) and not isinstance(actual, bool)):
                raise ValueError(f'Cannot reconcile job: exact {field} mismatch or missing')
        if not job.get('ts_received') or _time(job['ts_received']) < _time(order['created_at']) - timedelta(seconds=5):
            raise ValueError('Cannot reconcile: job predates reservation or has no receive timestamp')
        if order['status'] == 'submitting':
            ledger.mark_unknown(request_id, 'Recovered interrupted submitting state')
        if order['status'] != 'submitted':
            ledger.mark_submitted(request_id, job_id)
        if job.get('state') == 'done' and job.get('cost_usd') is not None:
            ledger.settle(request_id, _cost(job['cost_usd']))
        self._receipt('reconciled', {'request_id': request_id}, job)
        return job

    def download(self, job_id: str, output_dir: Path, *, name_contains=None) -> dict:
        _safe_name(job_id)
        job = self.batch('get_job_details', job_id=job_id)
        if job.get('state') != 'done':
            raise ValueError('Only completed jobs can be downloaded')
        files = self.batch('list_files', job_id=job_id)
        # Validate every entry before selecting or downloading any authenticated URL.
        validated = [validate_file(item) for item in files]
        if len({name.casefold() for name, *_ in validated}) != len(validated):
            raise ValueError('Provider filenames collide')
        selected = [v for v in validated if name_contains is None or name_contains in v[0]
                    or v[0] in {'metadata.json', 'symbology.json'}]
        if not selected:
            raise ValueError('No files matched download selection')
        target = Path(output_dir).resolve() / job_id
        target.mkdir(parents=True, exist_ok=True)
        if target.resolve().parent != Path(output_dir).resolve():
            raise ValueError('Download target escaped output directory')
        pending = []
        for name, size, digest, url in selected:
            path = target / name
            if path.is_symlink() or path.resolve().parent != target.resolve():
                raise ValueError('Download path points outside its job directory')
            if not (path.exists() and path.stat().st_size == size and _sha(path) == digest):
                pending.append((path, size, digest, url))
        if sum(v[1] for v in pending) + RESERVE_BYTES > shutil.disk_usage(target).free:
            raise RuntimeError('Insufficient disk space for downloads plus 1 GB reserve')
        for path, size, digest, url in pending:
            temp = path.with_name(path.name + '.part.' + uuid4().hex)
            try:
                with self.session.request('GET', url, auth=(self._key, ''),
                        stream=True, timeout=(30, 120), allow_redirects=False) as response:
                    response.raise_for_status()
                    if not 200 <= response.status_code < 300:
                        raise ValueError('Unexpected download redirect/status')
                    count = 0
                    with temp.open('xb') as stream:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if not chunk:
                                continue
                            count += len(chunk)
                            if count > size:
                                raise ValueError('Download exceeds declared file size')
                            stream.write(chunk)
                if count != size or _sha(temp) != digest:
                    raise ValueError('Downloaded file size or SHA-256 mismatch')
                temp.replace(path)
            except requests.RequestException:
                raise RuntimeError('Databento download failed; credentials and URL redacted') from None
            finally:
                if temp.exists():
                    temp.unlink()
        manifest = {'job_id': job_id, 'state': job['state'], 'cost_usd': job.get('cost_usd'),
            'record_count': job.get('record_count'), 'actual_size': job.get('actual_size'),
            'selection': name_contains, 'available_file_count': len(files),
            'complete_job': len(selected) == len(files),
            'verified_at': datetime.now(timezone.utc).isoformat(),
            'request': {field: job[field] for field in FILTER_FIELDS if field in job},
            'files': [{'name': name, 'size': size, 'sha256': digest, 'verified': True}
                      for name, size, digest, _ in selected]}
        save_json(target / 'download_manifest.json', manifest)
        self._receipt('download', {'job_id': job_id}, manifest)
        return manifest


def market_readiness(manifest: dict) -> dict:
    """Fail closed until independent, audited inputs and research controls exist.

    This assesses declared evidence; it does not fabricate audits from file presence.
    Verified acquisition files alone never authorize a trading or OOS claim.
    """
    blockers = []
    inputs = manifest.get('inputs', {})
    roles_ready = {}
    for role in ('equity', 'options', 'futures'):
        item = inputs.get(role, {})
        issues = []
        files = item.get('files', [])
        if not isinstance(item.get('record_count'), int) or item.get('record_count', 0) <= 0:
            issues.append('nonzero records required')
        if not files or not all(file.get('verified') is True for file in files):
            issues.append('verified files required')
        if not item.get('coverage', {}).get('start') or not item.get('coverage', {}).get('end'):
            issues.append('measured coverage required')
        if item.get('quality_audited') is not True:
            issues.append('quote-quality audit required')
        if role == 'equity' and item.get('independent') is not True:
            issues.append('independent underlying feed required')
        blockers.extend(f'{role}: {issue}' for issue in issues)
        roles_ready[role] = not issues
    controls = manifest.get('evidence_gates', {})
    missing_repricing = [gate for gate in REPRICING_GATES if controls.get(gate) is not True]
    blockers.extend('research: ' + gate + ' evidence required' for gate in missing_repricing)
    repricing = roles_ready['equity'] and roles_ready['options'] and not missing_repricing
    strict_issues = []
    for role in ('equity', 'options'):
        item = inputs.get(role, {})
        if role == 'equity' and item.get('dataset') == 'EQUS.MINI':
            strict_issues.append('equity: EQUS.MINI aggregates component venues; full national executable NBBO unproven')
        if item.get('quote_scope') != 'consolidated_executable':
            strict_issues.append(f'{role}: consolidated executable quote scope required')
        for field in ('bid_ask_size', 'timestamps', 'contract_definitions'):
            if item.get(field) is not True:
                strict_issues.append(f'{role}: {field} required')
    strict_issues.extend('strict: ' + gate + ' evidence required' for gate in STRICT_GATES if controls.get(gate) is not True)
    blockers.extend(strict_issues)
    common_ready = all(controls.get(gate) is True for gate in ('trial_register', 'cost_capital_stress', 'holdout_audit'))
    strict_ready = roles_ready['equity'] and roles_ready['options'] and common_ready and not strict_issues
    return {'strict_arbitrage_ready': bool(strict_ready),
            'repricing_ready': bool(repricing),
            'index_rate_hedge_ready': bool(repricing and roles_ready['futures']),
            'futures_role': 'index/rate exposure hedge; no company-contract equivalence',
            'blockers': blockers, 'evidence_status': 'declared manifest gates; retain supporting audit receipts'}
