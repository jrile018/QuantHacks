"""Versioned, JSON-compatible research records; all clock parsing is strict."""
from datetime import datetime, timedelta, timezone
from math import isfinite

PROTOCOL_VERSION = '1'
MODES = {'observed', 'historical_replay'}
SCOPES = {'issuer', 'market', 'portfolio'}


def utc(value):
    """Return an aware UTC datetime; dates and timezone guesses are forbidden."""
    if isinstance(value, str):
        if 'T' not in value and ' ' not in value:
            raise ValueError('timestamp requires time and explicit timezone')
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ValueError('invalid timestamp') from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timestamp requires an aware datetime')
    return value.astimezone(timezone.utc)


def stamp(value):
    return utc(value).isoformat().replace('+00:00', 'Z')


def latency_seconds(assumption):
    if not isinstance(assumption, dict) or not assumption.get('name'):
        raise ValueError('a named latency assumption is required')
    seconds = assumption.get('seconds')
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not isfinite(seconds) or seconds < 0:
        raise ValueError('latency assumption seconds must be finite and nonnegative')
    return seconds


def validate_registry(registry):
    """Validate the research freeze without granting holdout/capital access."""
    if not registry.get('protocol_version'):
        raise ValueError('protocol_version is required')
    if registry.get('mode') not in MODES:
        raise ValueError('mode must distinguish observed from historical_replay')
    if registry.get('stage') != 'research_only':
        raise ValueError('this protocol permits research_only')
    if registry.get('capital_approved') is not False or registry.get('final_test_unlocked') is not False:
        raise ValueError('capital and final test access must remain gated')
    schedule = registry.get('decision_schedule')
    expected_schedule = {'timezone':'America/New_York','regular_cutoff':'15:30:00',
                         'early_close_minutes_before':30,'calendar_basis':'actual_reference_exchange_sessions'}
    if schedule is not None and (not isinstance(schedule,dict) or
            any(schedule.get(key,value) != value for key,value in expected_schedule.items())):
        raise ValueError('unsupported unregistered decision schedule')
    if registry.get('horizon_id') != 'daily-next-session':
        raise ValueError('unregistered primary horizon')
    if registry['mode'] == 'historical_replay':
        latency_seconds(registry.get('latency_assumption'))
    for key in ('trial_candidates', 'horizon_candidates'):
        choices = registry.get(key)
        if not isinstance(choices, list) or not choices or any(not isinstance(v, str) or not v for v in choices):
            raise ValueError(f'{key} requires a finite named candidate list')
        if len(choices) != len(set(choices)):
            raise ValueError(f'{key} contains duplicates')
    if registry['horizon_id'] not in registry['horizon_candidates']:
        raise ValueError('primary horizon must be registered')
    if set(registry.get('opportunity_families', [])) != {'strict_arb', 'repricing'}:
        raise ValueError('strict_arb and repricing must have separate registered families')
    return registry


def validate_decision(row):
    required = ('decision_id', 'scope_type', 'cik', 'decision_at_utc', 'information_cutoff_utc',
                'horizon_id', 'outcome_end_utc', 'session_id', 'mode')
    if any(key not in row for key in required):
        raise ValueError('decision is missing required keys')
    if not row['decision_id'] or not row['session_id'] or not row['horizon_id']:
        raise ValueError('decision identity/session/horizon cannot be empty')
    if row['scope_type'] not in SCOPES or row['mode'] not in MODES:
        raise ValueError('invalid decision scope or mode')
    document_only = row.get('document_only') is True
    if document_only:
        if (row['scope_type'] != 'issuer' or not row['cik'] or row.get('cohort_kind') != 'document_entity'
                or row.get('identity_quality') != 'cik_verified' or row.get('security_id')
                or any(row.get('asset_eligibility', {}).values())):
            raise ValueError('document-only cohort cannot imply tradable security eligibility')
    elif row['scope_type'] == 'issuer' and (not row['cik'] or not row.get('security_id')):
        raise ValueError('issuer decision needs CIK and dated security identity')
    if row.get('asset_class') in {'future', 'futures'} and row['scope_type'] != 'market':
        raise ValueError('futures labels require unique market scope')
    if row['scope_type'] == 'market' and (row['cik'] is not None or not row.get('instrument_id')):
        raise ValueError('market decision needs instrument_id and null CIK')
    if row['scope_type'] == 'portfolio' and not row.get('portfolio_id'):
        raise ValueError('portfolio decision requires portfolio_id')
    decision, cutoff = utc(row['decision_at_utc']), utc(row['information_cutoff_utc'])
    if cutoff > decision:
        raise ValueError('information cutoff is after decision')
    if row['outcome_end_utc'] is not None and utc(row['outcome_end_utc']) <= decision:
        raise ValueError('outcome end must follow decision')
    if row.get('target_accession') is not None:
        raise ValueError('decision identity must not depend on future accession')
    return row


def source_available_at(row):
    """Observed clocks are evidence; replay clocks are explicit assumptions."""
    mode = row.get('mode')
    public = utc(row.get('public_at_utc'))
    if mode == 'observed':
        if row.get('received_at_utc') is None:
            raise ValueError('observed receipt/received timestamp is missing')
        if row.get('processed_at_utc') is None:
            raise ValueError('observed processing timestamp is missing')
        receipt, processed = utc(row['received_at_utc']), utc(row['processed_at_utc'])
        if not public <= receipt <= processed:
            raise ValueError('observed publication/receipt/processing order is invalid')
        return processed
    if mode == 'historical_replay':
        seconds = latency_seconds(row.get('latency_assumption'))
        assumed = utc(row.get('assumed_available_at_utc'))
        if assumed < public + timedelta(seconds=seconds):
            raise ValueError('replay availability precedes public plus assumed latency')
        # Never fabricate or overwrite the original receipt/processing timestamps.
        for key in ('received_at_utc', 'processed_at_utc'):
            if row.get(key) is not None:
                utc(row[key])
        return assumed
    raise ValueError('source mode must be observed or historical_replay')
