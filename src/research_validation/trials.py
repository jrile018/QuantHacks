"""Local append-only, hash-chained experiment/trial and protected-access ledger.

A local ledger guards software reuse; it cannot certify external noninspection.
Exclusive creation of a sibling lock serializes writers; interrupted writers
leave the lock for operator review rather than silently overwriting history.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


def config_hash(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read_ledger(path):
    path = Path(path)
    rows, previous = [], None
    if not path.exists():
        return rows
    for line in path.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        digest = row.pop('record_hash')
        if row.get('previous_hash') != previous or config_hash(row) != digest:
            raise ValueError('ledger_hash_mismatch')
        row['record_hash'] = digest
        rows.append(row)
        previous = digest
    return rows


@contextmanager
def _locked(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name+'.lock')
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError('ledger_locked_review_stale_lock_before_retry') from exc
    try:
        os.close(descriptor)
        yield path, read_ledger(path)
    finally:
        lock.unlink()


def _append(path, rows, kind, config, **payload):
    record = {'schema_version': '1.0', 'kind': kind, 'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'experiment_id': config['experiment_id'], 'horizon_id': config['horizon_id'], 'holdout_id': config.get('holdout_id'), 'config_hash': config_hash(config), 'previous_hash': rows[-1]['record_hash'] if rows else None, **payload}
    record['record_hash'] = config_hash(record)
    with path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(record, sort_keys=True, allow_nan=False)+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    return record


def _frozen(rows, config):
    frozen = [r for r in rows if r['kind'] == 'freeze' and r['experiment_id'] == config['experiment_id']]
    if not frozen:
        raise ValueError('experiment_not_frozen')
    if frozen[0]['config_hash'] != config_hash(config):
        raise ValueError('frozen_config_changed')
    return frozen[0]


def freeze_experiment(path, config):
    """Append the exact config once; never rename a used holdout to retune it."""
    if not config.get('experiment_id') or not config.get('horizon_id') or int(config.get('max_trials', 0)) <= 0:
        raise ValueError('experiment_horizon_and_finite_trial_budget_required')
    with _locked(path) as (path, rows):
        accessed = [r for r in rows if r['kind'] == 'holdout_access']
        if accessed and any(r['holdout_id'] != config.get('holdout_id') for r in accessed):
            raise ValueError('holdout_changed_after_access')
        if any(r['kind'] == 'freeze' and r['experiment_id'] == config['experiment_id'] for r in rows):
            return _frozen(rows, config)
        return _append(path, rows, 'freeze', config, frozen_config=config)


def register_trial(path, config, trial):
    """Record finite attempts including failed outcomes; no mutable results."""
    with _locked(path) as (path, rows):
        _frozen(rows, config)
        trials = [r for r in rows if r['kind'] in {'trial', 'trial_start'} and r['experiment_id'] == config['experiment_id']]
        if len(trials) >= int(config['max_trials']):
            raise ValueError('trial_budget_exhausted')
        if not trial.get('trial_id') or trial.get('outcome') not in {'evaluated', 'failed', 'ineligible', 'insufficient'}:
            raise ValueError('trial_id_and_outcome_required')
        if trial['outcome'] == 'failed' and not trial.get('failure_reason'):
            raise ValueError('failed_trial_reason_required')
        if any(r['trial']['trial_id'] == trial['trial_id'] for r in trials):
            raise ValueError('duplicate_trial_id')
        return _append(path, rows, 'trial', config, trial=trial)


def reserve_holdout(path, config):
    """Consume local one-use access before reading any holdout outcomes.

    This helper alone does not enable final evaluation in evaluate_forecasts.
    A caller must freeze a concrete, complete artifact protocol separately.
    """
    required = {'experiment_id', 'horizon_id', 'holdout_id', 'objective', 'decision_schedule', 'target_name', 'primary_metric', 'feature_sets', 'split_protocol', 'quote_policy', 'costs', 'sizing_policy', 'uncertainty', 'code_hash', 'data_hash'}
    if any(not config.get(k) for k in required):
        raise ValueError('incomplete_protocol')
    if config.get('final_test_enabled') is not True:
        raise ValueError('final_test_not_enabled')
    from datetime import time
    from .evaluate import _time
    try:
        split = config['split_protocol']
        train, validation, start, end = [_time(split[k]) for k in ('train_end_utc','validation_end_utc','holdout_start_utc','holdout_end_utc')]
        if not train < validation <= start < end:
            raise ValueError('invalid_holdout_chronology')
        time.fromisoformat(config['decision_schedule']['decision_time_utc'])
        if not config['decision_schedule']['calendar_id']:
            raise ValueError('reference_calendar_required')
        if config['objective'] not in {'standalone','protection'}:
            raise ValueError('invalid_objective')
        if config['objective'] == 'protection' and not config.get('dated_exposure'):
            raise ValueError('dated_exposure_required')
        for name in ('code_hash','data_hash'):
            if len(config[name]) != 64 or any(c not in '0123456789abcdef' for c in config[name]):
                raise ValueError('sha256_artifact_hash_required')
        if int(config['uncertainty']['block_days']) <= 0:
            raise ValueError('calendar_block_protocol_required')
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError('incomplete_protocol:'+str(exc)) from exc
    with _locked(path) as (path, rows):
        _frozen(rows, config)
        if any(r['kind'] == 'holdout_access' for r in rows):
            raise ValueError('holdout_already_accessed')
        return _append(path, rows, 'holdout_access', config)



def start_trial(path, config, trial_id):
    """Reserve the finite attempt before any fit or outcome inspection."""
    with _locked(path) as (path, rows):
        _frozen(rows, config)
        attempts = [r for r in rows if r['kind'] in {'trial', 'trial_start'} and r['experiment_id'] == config['experiment_id']]
        if len(attempts) >= int(config['max_trials']):
            raise ValueError('trial_budget_exhausted')
        if not trial_id or any(r['trial']['trial_id'] == trial_id for r in attempts):
            raise ValueError('missing_or_duplicate_trial_id')
        return _append(path, rows, 'trial_start', config, trial={'trial_id':trial_id,'outcome':'started'})


def finish_trial(path, config, trial):
    """Append a terminal outcome to an already reserved attempt, once."""
    with _locked(path) as (path, rows):
        _frozen(rows, config)
        trial_id = trial.get('trial_id')
        matching = [r for r in rows if r['experiment_id'] == config['experiment_id'] and r['kind'] in {'trial_start', 'trial_result'} and r['trial']['trial_id'] == trial_id]
        if not matching:
            raise ValueError('trial_not_started')
        if any(r['kind'] == 'trial_result' for r in matching):
            raise ValueError('trial_already_finished')
        if trial.get('outcome') not in {'evaluated','failed','ineligible','insufficient'} or (trial['outcome']=='failed' and not trial.get('failure_reason')):
            raise ValueError('terminal_outcome_and_failure_reason_required')
        return _append(path, rows, 'trial_result', config, trial=trial)
