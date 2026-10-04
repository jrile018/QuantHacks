"""Streaming source qualification, bounded diagnostics, and fail-closed economics.

This is a producer adapter. It does not evaluate outcomes, fit models, import
canonical decisions, infer missing contract terms, or assert execution.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import io
import json
import logging
import math
from pathlib import Path
import re
import sqlite3

START = '2024-01-01T00:00:00Z'
END = '2026-01-01T00:00:00Z'
FROZEN_RULE_SHA256 = '8a10928738733b5756e614d4e937ed3cea02f24e5092a0728cb1f505a3b063d4'
DATASET_CLASSES = {'EQUS.MINI': {'K'}, 'OPRA.PILLAR': {'C', 'P'}, 'GLBX.MDP3': {'F'}}
QUOTE_SCHEMAS = {'EQUS.MINI': 'bbo-1m', 'OPRA.PILLAR': 'cbbo-1m', 'GLBX.MDP3': 'bbo-1m'}
INTERVAL_REPLAY_ASSUMPTION = 'historical_interval_endpoint_replay'
CSV_SUFFIXES = ('.csv', '.csv.zst')
COST_FIELDS = ('fees', 'slippage', 'financing', 'borrow', 'dividends', 'margin',
               'assignment', 'american_exercise', 'adjusted_deliverables', 'corporate_actions')
SENTINELS = {'', 'nan', 'none', 'null', 'inf', '-inf', '2147483647', '4294967295',
             '9223372036854775807', '18446744073709551615', '9223372036.854775807'}


def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def _utc(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('aware_timestamp_required')
    return result.astimezone(timezone.utc)


def _ns(value):
    """Preserve nanoseconds; datetime alone truncates submicrosecond futures."""
    text = str(value)
    match = re.fullmatch(r'(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)', text)
    if not match:
        raise ValueError('aware_timestamp_required')
    whole = _utc(match[1] + match[3])
    return int(whole.timestamp()) * 1_000_000_000 + int((match[2] or '').ljust(9, '0'))


def _stamp_ns(value):
    return datetime.fromtimestamp(value//1_000_000_000, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + f'.{value%1_000_000_000:09d}Z'


def _number(value, *, positive=True, maximum=None):
    if isinstance(value, bool) or str(value).strip().lower() in SENTINELS:
        return None
    try:
        decimal = Decimal(str(value))
        if not decimal.is_finite() or (decimal <= 0 if positive else decimal < 0):
            return None
        if maximum is not None and decimal >= Decimal(str(maximum)):
            return None
        result = float(decimal)
        return result if math.isfinite(result) else None
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return None


def _identity(row):
    publisher, instrument = str(row.get('publisher_id', '')), str(row.get('instrument_id', ''))
    if not publisher.isdigit() or not instrument.isdigit() or int(instrument) <= 0:
        raise ValueError('invalid_instrument_identity')
    return publisher, instrument


def verified_csv_rows(file):
    """Accept CSV source descriptors and verify bytes; never salvage malformed CSV."""
    path = Path(file['path'])
    if not path.name.endswith(CSV_SUFFIXES):
        raise ValueError('non_csv_source_descriptor:' + path.name)
    if not isinstance(file.get('size'), int) or isinstance(file['size'], bool) or path.stat().st_size != file['size']:
        raise ValueError('raw_size_mismatch')
    if not re.fullmatch('[0-9a-f]{64}', str(file.get('sha256', ''))):
        raise ValueError('raw_sha256_required')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != file['sha256']:
        raise ValueError('raw_hash_mismatch')
    with path.open('rb') as compressed:
        if path.name.endswith('.zst'):
            import zstandard
            decoded = zstandard.ZstdDecompressor().stream_reader(compressed)
        else:
            decoded = compressed
        with io.TextIOWrapper(decoded, encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream, strict=True)
            fields = reader.fieldnames
            if not fields or any(not field for field in fields) or len(fields) != len(set(fields)):
                raise ValueError('duplicate_csv_columns')
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError('malformed_csv_row')
                yield row, {'raw_file': str(path), 'raw_sha256': file['sha256'],
                            'raw_bytes': file['size'], 'row_number': reader.line_num,
                            'hash_verification': 'local_raw_hash_verified'}


class DefinitionIndex:
    """Disk index scoped to dataset, publisher, ID, observed UTC date and receive time.

    A prior date is deliberately not treated as evidence of current validity.
    Same-time inconsistent identities are ambiguous; deletion invalidates a quote.
    """
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute('PRAGMA cache_size=-32768')
        self.connection.execute('PRAGMA temp_store=FILE')
        self.connection.execute('CREATE TABLE IF NOT EXISTS definitions (dataset TEXT, publisher TEXT, instrument TEXT, day TEXT, received INTEGER, payload TEXT)')
        self.connection.execute('CREATE INDEX IF NOT EXISTS dated_identity ON definitions(dataset,publisher,instrument,day,received)')
        self.pending = 0

    def add(self, dataset, row, provenance):
        publisher, instrument = _identity(row)
        received, event = _ns(row['ts_recv']), _ns(row['ts_event'])
        if event > received:
            raise ValueError('future_definition_event')
        if not row.get('raw_symbol') or row.get('symbol', row['raw_symbol']) != row['raw_symbol']:
            raise ValueError('definition_symbol_mismatch')
        value = {key: row.get(key, '') for key in ('raw_symbol', 'symbol', 'instrument_class',
            'security_update_action', 'underlying', 'asset', 'currency', 'expiration', 'activation',
            'strike_price', 'min_price_increment', 'display_factor', 'contract_multiplier',
            'contract_multiplier_unit', 'unit_of_measure_qty', 'leg_count')}
        value.update(ts_recv=row['ts_recv'], ts_event=row['ts_event'], provenance=provenance)
        self.connection.execute('INSERT INTO definitions VALUES (?,?,?,?,?,?)',
            (dataset, publisher, instrument, _utc(row['ts_recv']).date().isoformat(), received, _dump(value)))
        self.pending += 1
        if self.pending >= 10000:
            self.finish()

    def finish(self):
        self.connection.commit()
        self.pending = 0

    def lookup(self, dataset, row):
        publisher, instrument = _identity(row)
        received = _ns(row['ts_recv'])
        day = _utc(row['ts_recv']).date().isoformat()
        rows = self.connection.execute('SELECT received,payload FROM definitions WHERE dataset=? AND publisher=? AND instrument=? AND day=? AND received<=? ORDER BY received DESC LIMIT 32',
            (dataset, publisher, instrument, day, received)).fetchall()
        if not rows:
            return None, 'dated_definition_missing_or_identity_mismatch'
        latest = rows[0][0]
        values = [json.loads(payload) for stamp, payload in rows if stamp == latest]
        signatures = {_dump({k: v for k, v in value.items() if k != 'provenance'}) for value in values}
        # 32 equal-time records might conceal another identity outside the limit.
        if len(signatures) > 1 or len(values) == 32:
            return None, 'ambiguous_dated_definition'
        value = values[0]
        if value['raw_symbol'] != row.get('symbol'):
            return None, 'dated_definition_missing_or_identity_mismatch'
        return value, None

    def close(self):
        self.connection.close()


def _window_dates(start, end):
    day, last = _utc(start).date(), _utc(end).date()
    while day <= last:
        yield day.isoformat()
        day += timedelta(days=1)


def normalize_quote(row, *, dataset, schema, index, degraded_dates, provenance, interval_replay_assumption=None):
    reasons = []
    definition = None
    last_trade = None
    if interval_replay_assumption not in (None, INTERVAL_REPLAY_ASSUMPTION):
        raise ValueError('unsupported_interval_replay_assumption')
    if QUOTE_SCHEMAS.get(dataset) != schema:
        reasons.append('unsupported_dataset_or_schema')
    try:
        publisher, instrument = _identity(row)
        received = _ns(row['ts_recv'])
        interval_start = _stamp_ns(received-60*1_000_000_000)
        if not _ns(START) <= received < _ns(END):
            reasons.append('quote_outside_development')
        trade = row.get('ts_event')
        if str(trade).strip().lower() not in SENTINELS:
            try:
                if _ns(trade) > received:
                    reasons.append('future_last_trade')
                else:
                    last_trade = trade
            except (ValueError, TypeError):
                reasons.append('invalid_last_trade_timestamp')
        if set(_window_dates(interval_start, row['ts_recv'])) & set(degraded_dates):
            reasons.append('degraded_quote_interval')
        definition, missing = index.lookup(dataset, row)
        if missing:
            reasons.append(missing)
    except (ValueError, TypeError, KeyError):
        reasons.append('missing_or_invalid_timestamp_or_identity')
    bid, ask = (_number(row.get(key), maximum=9223372036) for key in ('bid_px_00', 'ask_px_00'))
    bid_size, ask_size = (_number(row.get(key), maximum=4294967295) for key in ('bid_sz_00', 'ask_sz_00'))
    if bid is None or ask is None:
        reasons.append('missing_or_invalid_price')
    elif bid >= ask:
        reasons.append('crossed_or_locked_quote')
    if bid_size is None or ask_size is None or any(value is not None and not value.is_integer() for value in (bid_size, ask_size)):
        reasons.append('missing_or_invalid_size')
    if definition:
        if definition['instrument_class'] not in DATASET_CLASSES.get(dataset, set()) or (
                dataset == 'GLBX.MDP3' and _number(definition['leg_count']) is not None):
            reasons.append('unsupported_instrument_class')
        if definition['security_update_action'] == 'D':
            reasons.append('definition_deleted')
        elif definition['security_update_action'] not in {'A', 'M'}:
            reasons.append('unknown_definition_action')
        for field, future in (('activation', True), ('expiration', False)):
            value = definition[field]
            if value and value.lower() not in SENTINELS:
                try:
                    if (_ns(value) > received if future else _ns(value) <= received):
                        reasons.append('inactive_or_expired_instrument')
                except ValueError:
                    reasons.append('invalid_contract_lifecycle')
        if dataset == 'OPRA.PILLAR' and (not definition['underlying'] or definition['expiration'].lower() in SENTINELS
                or _number(definition['strike_price']) is None):
            reasons.append('option_terms_missing')
    if reasons:
        return {'mark': None, 'reasons': sorted(set(reasons)), 'provenance': provenance,
                'dated_identity_matched': definition is not None}
    multiplier = _number(definition['contract_multiplier'], maximum=1_000_000)
    mark = {'instrument_id': f'{dataset}:{publisher}:{instrument}', 'provider_instrument_id': instrument,
        'publisher_id': publisher, 'symbol': row['symbol'], 'dataset': dataset, 'provider_schema': schema,
        'evidence_kind': 'interval_cbbo' if schema == 'cbbo-1m' else 'interval_bbo',
        'mark_at_utc': row['ts_recv'], 'interval_start_at_utc': interval_start, 'interval_end_at_utc': row['ts_recv'],
        'last_trade_at_utc': last_trade, 'quote_updated_at_utc': None,
        'quote_age_seconds': None, 'quote_freshness_verified': False,
        'public_at_utc': None, 'available_at_utc': None, 'received_at_utc': None, 'processed_at_utc': None,
        'assumed_available_at_utc': row['ts_recv'] if interval_replay_assumption else None,
        'latency_assumption': interval_replay_assumption, 'availability_semantics': 'observed_availability_unknown',
        'canonical_consumer_ready': False, 'live_processed_availability_verified': False, 'mode': 'raw', 'raw_price': True,
        'bid': bid, 'ask': ask, 'mid': (bid+ask)/2, 'bid_size': int(bid_size), 'ask_size': int(ask_size),
        'instrument_class': definition['instrument_class'], 'currency': definition['currency'] or None,
        'underlying': definition['underlying'] or None, 'expiration': definition['expiration'] or None,
        'strike_price': _number(definition['strike_price']), 'contract_multiplier': multiplier,
        'multiplier_status': 'provider_value_unreviewed' if multiplier is not None else 'unknown_or_sentinel',
        'national_nbbo': False, 'execution_verified': False, 'provenance': provenance,
        'definition_provenance': definition['provenance'], 'definition_received_at_utc': definition['ts_recv'],
        'historical_identity_independently_verified': False, 'adjusted_deliverables_verified': False}
    mark['quote_id'] = hashlib.sha256(_dump([dataset, provenance['raw_sha256'], provenance['row_number']]).encode()).hexdigest()
    return {'mark': mark, 'reasons': [], 'provenance': provenance, 'dated_identity_matched': True}


def _verified_cost(costs, field, marks):
    """Numerical costs need retained source/hash, dates and independent review."""
    item = costs.get(field)
    if not isinstance(item, dict) or item.get('verified') is not True or not item.get('source') or not item.get('reviewer'):
        return False
    if not re.fullmatch('[0-9a-f]{64}', str(item.get('source_sha256', ''))):
        return False
    if _number(item.get('value'), positive=False) is None:
        return False
    source = Path(item['source'])
    try:
        if not source.is_file() or source.stat().st_size > 8*1024*1024:
            return False
        if hashlib.sha256(source.read_bytes()).hexdigest() != item['source_sha256']:
            return False
    except OSError:
        return False
    try:
        start, end = _ns(item['valid_from']), _ns(item['valid_to'])
        public = _ns(item['public_at_utc'])
        if _ns(item['reviewed_at_utc']) < _ns(item['retrieved_at_utc']):
            return False
        return bool(marks) and start < end and all(start <= _ns(mark['mark_at_utc']) < end
            and public <= _ns(mark['mark_at_utc']) for mark in marks)
    except (KeyError, ValueError):
        return False


def qualify_tracks(marks, *, costs):
    unknown = [field + '_unknown' for field in COST_FIELDS if not _verified_cost(costs, field, marks)]
    base = [] if marks else ['no_qualified_diagnostic_marks']
    repricing = base + unknown + ['canonical_trial_register_pending', 'matured_labels_not_bound',
        'past_only_folds_pending', 'purge_embargo_pending', 'capital_stress_pending', 'consumer_acceptance_pending',
        'observed_market_availability_unknown']
    strict = base + unknown + ['interval_quotes_not_simultaneous_execution', 'national_equity_nbbo_unverified',
        'fills_and_leg_risk_unverified', 'historical_action_coverage_unverified', 'margin_lifecycle_unverified',
        'quote_update_clock_unknown', 'observed_market_availability_unknown']
    if any(mark.get('contract_multiplier') is None for mark in marks) or not marks:
        strict.append('contract_multiplier_unknown')
    if any(mark.get('historical_identity_independently_verified') is not True for mark in marks):
        strict.append('independent_dated_identity_review_pending')
    return {'diagnostic': {'status': 'candidate_only' if marks else 'insufficient', 'reasons': base},
            'repricing': {'status': 'insufficient', 'reasons': sorted(set(repricing))},
            'strict_arbitrage': {'status': 'rejected', 'reasons': sorted(set(strict))},
            'arbitrage_claim': False, 'cost_evidence': costs}


def equity_candidate(mark, degraded_dates, *, holding_seconds=3600, lookback_seconds=60):
    """A single frozen persistence forecast, without touching a label/outcome."""
    reasons = []
    if mark.get('dataset') != 'EQUS.MINI' or mark.get('instrument_class') != 'K':
        reasons.append('equity_diagnostic_only')
    decision = _utc(mark['mark_at_utc'])
    decision_ns = _ns(mark['mark_at_utc'])
    if mark.get('latency_assumption') != INTERVAL_REPLAY_ASSUMPTION or mark.get('assumed_available_at_utc') is None:
        reasons.append('interval_replay_assumption_required')
    try:
        if mark.get('assumed_available_at_utc') is not None and _ns(mark['assumed_available_at_utc']) > decision_ns:
            reasons.append('feature_not_available_at_decision')
    except (KeyError, ValueError):
        reasons.append('feature_not_available_at_decision')
    start = decision-timedelta(seconds=lookback_seconds)
    end = decision+timedelta(seconds=holding_seconds)
    if not 0 <= lookback_seconds <= 86400 or not 0 < holding_seconds <= 86400:
        raise ValueError('bounded_positive_candidate_window_required')
    try:
        if not decision_ns-lookback_seconds*1_000_000_000 <= _ns(mark['interval_start_at_utc']) < _ns(mark['interval_end_at_utc']) <= decision_ns:
            reasons.append('feature_interval_outside_lookback')
    except (KeyError, ValueError, TypeError):
        reasons.append('feature_interval_outside_lookback')
    if start < _utc(START) or end >= _utc(END):
        reasons.append('holding_window_outside_development')
    touched = sorted(set(_window_dates(start.isoformat(), end.isoformat())) & set(degraded_dates))
    if touched:
        reasons.append('degraded_full_window')
    if reasons:
        return {'candidate': None, 'reasons': reasons, 'excluded_dates': touched}
    row = {'candidate_id': 'equity-persistence-' + mark['quote_id'], 'instrument_id': mark['instrument_id'],
        'symbol': mark['symbol'], 'decision_at_utc': mark['mark_at_utc'], 'feature_available_at_utc': None,
        'feature_assumed_available_at_utc': mark['assumed_available_at_utc'],
        'feature_availability_assumption': mark['latency_assumption'], 'feature_clock_mode': 'interval_replay_assumption',
        'canonical_consumer_ready': False,
        'feature_window_start_utc': start.isoformat(), 'holding_end_utc': end.isoformat(),
        'model': 'frozen_persistence_baseline', 'prediction_mid': mark['mid'], 'horizon_seconds': holding_seconds,
        'features': {'mid': mark['mid'], 'spread': mark['ask']-mark['bid'],
                     'size_imbalance': (mark['bid_size']-mark['ask_size'])/(mark['bid_size']+mark['ask_size'])},
        'quote_id': mark['quote_id'], 'quote_provenance': mark['provenance'],
        'definition_provenance': mark['definition_provenance'], 'outcomes_read': False,
        'status': 'diagnostic_candidate_unscored', 'target': None, 'net_return': None,
        'execution_claim': False, 'consumer_accepted': False,
        'required_next_step': 'Bind reviewed historical mappings/actions/calendar/cost artifacts and matured labels through canonical market_handoff; register trial before evaluation.'}
    return {'candidate': row, 'reasons': [], 'excluded_dates': []}


def run_qualification(config, rule, output, *, sample_limit=128, quote_month=None, candidate_symbol='AMT', costs=None,
                      interval_replay_assumption=None):
    """Stream all selected rows; SQLite stays on the compute host, JSON is bounded."""
    if not isinstance(sample_limit, int) or not 1 <= sample_limit <= 1024:
        raise ValueError('sample_limit_must_be_1_to_1024')
    if interval_replay_assumption not in (None, INTERVAL_REPLAY_ASSUMPTION):
        raise ValueError('unsupported_interval_replay_assumption')
    if quote_month is not None and not re.fullmatch('202[45](0[1-9]|1[0-2])', quote_month):
        raise ValueError('development_quote_month_required')
    jobs = config.get('jobs')
    if not isinstance(jobs, list) or not jobs or len(jobs) > 6:
        raise ValueError('explicit_bounded_jobs_required')
    ids = [job['job_id'] for job in jobs]
    if len(ids) != len(set(ids)):
        raise ValueError('unique_job_ids_required')
    degraded = set(rule['union_dates'])
    for day in degraded:
        datetime.strptime(day, '%Y-%m-%d')
    selected, unscanned, raw_paths = [], [], set()
    for job in jobs:
        if job['dataset'] not in DATASET_CLASSES or job['schema'] not in {'definition', QUOTE_SCHEMAS.get(job['dataset'])}:
            raise ValueError('unsupported_dataset_or_schema')
        files = job.get('files')
        if not isinstance(files, list) or len(files) > 128:
            raise ValueError('bounded_explicit_files_required')
        for file in sorted(files, key=lambda item: item['path']):
            if not Path(file['path']).name.endswith(CSV_SUFFIXES):
                raise ValueError('non_csv_source_descriptor:' + Path(file['path']).name)
            path_key = str(Path(file['path']).resolve())
            if path_key in raw_paths:
                raise ValueError('duplicate_raw_file')
            raw_paths.add(path_key)
            if quote_month and job['schema'] != 'definition' and job['dataset'] != 'EQUS.MINI' and quote_month not in Path(file['path']).name:
                unscanned.append({'job_id': job['job_id'], **file, 'reason': 'frozen_derivative_month_selection'})
            else:
                selected.append((job, file))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    selection = {'config_sha256': hashlib.sha256(_dump(config).encode()).hexdigest(),
        'rule_content_sha256': hashlib.sha256(_dump(rule).encode()).hexdigest(),
        'quality_rule_file_sha256': config.get('quality_rule_file_sha256'),
        'quote_month': quote_month, 'candidate_symbol': candidate_symbol, 'sample_limit': sample_limit,
        'interval_replay_assumption': interval_replay_assumption, 'canonical_consumer_ready': False,
        'cost_evidence_sha256': hashlib.sha256(_dump(costs or {}).encode()).hexdigest(),
        'forecast': {'model': 'frozen_persistence_baseline', 'lookback_seconds': 60, 'holding_seconds': 3600},
        'selected_files': [{'job_id': job['job_id'], **file} for job, file in selected],
        'unscanned_files': unscanned, 'outcomes_read': False}
    _write(output/'frozen_selection.json', selection)
    index = DefinitionIndex(output/'definitions.sqlite')
    definitions, quotes = {}, {}
    samples, rejection_samples = defaultdict(list), defaultdict(list)
    candidates, candidate_rejections = [], Counter()
    scanned, file_counts = [], Counter()
    try:
        for job, file in selected:
            if job['schema'] != 'definition':
                continue
            counts = definitions.setdefault(job['dataset'], {'rows': 0, 'indexed_rows': 0,
                'rejection_counts': Counter(), 'instrument_classes': Counter(), 'multiplier_status_counts': Counter(),
                'underlying_counts': Counter()})
            count = 0
            for row, provenance in verified_csv_rows(file):
                count += 1
                counts['rows'] += 1
                provenance.update(job_id=job['job_id'], dataset=job['dataset'], source_schema=job['schema'])
                try:
                    index.add(job['dataset'], row, provenance)
                    counts['indexed_rows'] += 1
                except (ValueError, KeyError, TypeError) as exc:
                    counts['rejection_counts'][str(exc)] += 1
                counts['instrument_classes'][row.get('instrument_class', '')] += 1
                counts['multiplier_status_counts']['provider_value_unreviewed' if _number(row.get('contract_multiplier'), maximum=1_000_000) is not None else 'unknown_or_sentinel'] += 1
                if row.get('underlying'):
                    counts['underlying_counts'][row['underlying']] += 1
            index.finish()
            logging.info('Indexed %s %s rows=%s', job['job_id'], Path(file['path']).name, count)
            scanned.append({'job_id': job['job_id'], **file, 'parsed_rows': count, 'raw_hash_size_verified': True})
            file_counts[job['job_id']] += count
        for job, file in selected:
            if job['schema'] == 'definition':
                continue
            counts = quotes.setdefault(job['dataset'], {'rows': 0, 'qualified_diagnostic_rows': 0,
                'rejection_counts': Counter(), 'symbol_counts': Counter(), 'dated_identity_matched_rows': 0,
                'qualified_rows_by_utc_date': Counter(), 'sample_only': True})
            count = 0
            for row, provenance in verified_csv_rows(file):
                count += 1
                counts['rows'] += 1
                provenance.update(job_id=job['job_id'], dataset=job['dataset'], source_schema=job['schema'])
                result = normalize_quote(row, dataset=job['dataset'], schema=job['schema'], index=index,
                    degraded_dates=degraded, provenance=provenance,
                    interval_replay_assumption=interval_replay_assumption)
                if result['dated_identity_matched']:
                    counts['dated_identity_matched_rows'] += 1
                if quote_month and job['dataset'] != 'EQUS.MINI':
                    try:
                        if _utc(row['ts_recv']).strftime('%Y%m') != quote_month:
                            result['mark'] = None
                            result['reasons'].append('quote_outside_frozen_derivative_month')
                    except (KeyError, ValueError):
                        pass  # The normalizer already rejects an invalid timestamp.
                counts['rejection_counts'].update(result['reasons'])
                mark = result['mark']
                if mark is None:
                    if len(rejection_samples[job['dataset']]) < sample_limit:
                        rejection_samples[job['dataset']].append({'reasons': result['reasons'], 'provenance': provenance,
                            'symbol': row.get('symbol'), 'instrument_id': row.get('instrument_id'),
                            'ts_recv': row.get('ts_recv'), 'ts_event': row.get('ts_event')})
                    continue
                counts['qualified_diagnostic_rows'] += 1
                # Count families, not every option strike symbol, to keep the packet bounded.
                counts['symbol_counts'][mark['underlying'] or mark['symbol']] += 1
                counts['qualified_rows_by_utc_date'][_utc(mark['mark_at_utc']).date().isoformat()] += 1
                if len(samples[job['dataset']]) < sample_limit:
                    samples[job['dataset']].append(mark)
                if job['dataset'] == 'EQUS.MINI' and mark['symbol'] == candidate_symbol and len(candidates) < sample_limit:
                    candidate = equity_candidate(mark, degraded)
                    if candidate['candidate'] is not None:
                        candidates.append(candidate['candidate'])
                    else:
                        candidate_rejections.update(candidate['reasons'])
            scanned.append({'job_id': job['job_id'], **file, 'parsed_rows': count, 'raw_hash_size_verified': True})
            file_counts[job['job_id']] += count
            logging.info('Qualified %s %s rows=%s diagnostic_total=%s', job['job_id'], Path(file['path']).name,
                         count, counts['qualified_diagnostic_rows'])
        for job in jobs:
            entire = not any(file['job_id'] == job['job_id'] for file in unscanned)
            if entire and job.get('provider_record_count') is not None and file_counts[job['job_id']] != job['provider_record_count']:
                raise ValueError('provider_record_count_mismatch:' + job['job_id'])
        tracks = qualify_tracks([row for rows in samples.values() for row in rows], costs=costs or {})
        report = {'schema_version': 'reit-market-qualification-v1', 'status': 'producer_qualification_only',
            'scope': 'development_2024_2025_selected_raw_files', 'coverage_complete': False,
            'scan_complete_for_selected_files': True, 'whole_config_scanned': not unscanned,
            'whole_delivery_scanned': not unscanned and len(jobs) == 6 and
                {(job['dataset'], job['schema'] == 'definition') for job in jobs} ==
                {(dataset, definition) for dataset in DATASET_CLASSES for definition in (True, False)},
            'independent_dated_history_qualified': False, 'consumer_accepted': False, 'canonical_consumer_ready': False,
            'definitions': definitions, 'quotes': quotes, 'tracks': tracks,
            'candidate_count': len(candidates), 'candidate_window_rejection_counts': candidate_rejections,
            'frozen_degraded_dates': sorted(degraded), 'frozen_selection': selection,
            'scanned_files': scanned, 'unscanned_files': unscanned,
            'limitations': ['Same-day past-only definitions are observed provider mappings, not independent action/deliverable history.',
                'Minute endpoints are diagnostic marks, not observed availability or synchronized execution evidence; ts_event is last trade, not quote update.',
                'EQUS.MINI component quotes do not establish national NBBO.',
                'Counts are selected observations, not complete per-instrument sessions or survivorship coverage.',
                'No outcomes, returns, fitted models, holdout evaluation, fill proof or arbitrage claim.']}
        _write(output/'normalized_quote_samples.json', {'schema_version': 'reit-normalized-quote-samples-v1',
            'sample_limit_per_dataset': sample_limit, 'samples': dict(samples), 'rejections': dict(rejection_samples),
            'canonical_consumer_ready': False,
            'authoritative_source_verified': False, 'review': {'status': 'pending'}})
        _write(output/'equity_forecast_candidates.json', {'schema_version': 'reit-equity-forecast-candidates-v1',
            'rows': candidates, 'outcomes_read': False, 'consumer_accepted': False, 'canonical_consumer_ready': False})
        _write(output/'strict_arbitrage_rejection.json', {'schema_version': 'reit-strict-arbitrage-rejection-v1',
            **tracks['strict_arbitrage'], 'arbitrage_claim': False, 'candidate_count': 0,
            'raw_quote_candidate_only': bool(samples), 'evidence': selection})
        _write(output/'qualification_report.json', report)
        return report
    except Exception as exc:
        _write(output/'failure_report.json', {'status': 'failed', 'failure_type': type(exc).__name__,
            'reason': str(exc), 'scan_complete_for_selected_files': False,
            'consumer_accepted': False, 'scanned_files': scanned,
            'partial_definitions': definitions, 'partial_quotes': quotes})
        raise
    finally:
        index.close()
