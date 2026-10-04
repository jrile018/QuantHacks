"""Bounded, retrospective forecast diagnostics. Protected test access stays closed.

Panels can be lists or dictionaries containing rows. No future accession is
required: ordinary controls use a null economic_event_group. Input quality
attestations are necessary, and are not independently established here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import random
import statistics


def _time(value):
    if not isinstance(value, str) or 'T' not in value:
        raise ValueError('precise_aware_timestamp_required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('precise_aware_timestamp_required')
    return result.astimezone(timezone.utc)


def _number(value):
    if isinstance(value, bool):
        raise ValueError('finite_number_required')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('finite_number_required')
    return result


def _rows(panel):
    return panel.get('rows', []) if isinstance(panel, dict) else panel


def _hash(value):
    # Hash incoming malformed numeric tokens too; row gates exclude them below.
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=True).encode()).hexdigest()


def _prepare(train, columns):
    if len(columns) > 64:
        raise ValueError('bounded_runner_max_64_features')
    medians = []
    for column in columns:
        values = [_number(r['features'][column]) for r in train if r['features'][column] is not None]
        if not values:
            raise ValueError('all_train_values_missing:' + column)
        medians.append(statistics.median(values))
    vectors = [[medians[i] if r['features'][name] is None else _number(r['features'][name]) for i, name in enumerate(columns)] + [float(r['features'][name] is None) for name in columns] for r in train]
    means = [statistics.mean(c) for c in zip(*vectors)]
    scales = [statistics.pstdev(c) or 1.0 for c in zip(*vectors)]
    return {'columns': columns, 'medians': medians, 'means': means, 'scales': scales}


def _vector(row, prep):
    columns = prep['columns']
    values = [prep['medians'][i] if row['features'][name] is None else _number(row['features'][name]) for i, name in enumerate(columns)] + [float(row['features'][name] is None) for name in columns]
    return [(v-m)/s for v, m, s in zip(values, prep['means'], prep['scales'])]


def _solve(matrix, rhs):
    # Small software runner only; large panels/fits belong on detached remote compute.
    augmented = [list(row) + [value] for row, value in zip(matrix, rhs)]
    for i in range(len(rhs)):
        pivot = max(range(i, len(rhs)), key=lambda j: abs(augmented[j][i]))
        augmented[i], augmented[pivot] = augmented[pivot], augmented[i]
        divisor = augmented[i][i]
        if abs(divisor) < 1e-14:
            raise ValueError('singular_ridge')
        augmented[i] = [v/divisor for v in augmented[i]]
        for j in range(len(rhs)):
            if i != j:
                factor = augmented[j][i]
                augmented[j] = [a-factor*b for a, b in zip(augmented[j], augmented[i])]
    return [_number(r[-1]) for r in augmented]


def _fit(train, columns, estimator, alpha):
    """Fit a declared estimator; scored validation outcomes never select it."""
    prep = _prepare(train, columns)
    x = [_vector(row, prep) for row in train]
    intercept = statistics.mean(row['target'] for row in train)
    baseline = {'estimator': 'training_mean', 'alpha': None, 'intercept': intercept, 'coefficients': [0.0]*len(x[0]), 'preprocessing': prep}
    candidates = [baseline]
    if estimator == 'ridge':
        n = len(x[0])
        matrix = [[sum(v[i]*v[j] for v in x) + (alpha if i == j else 0) for j in range(n)] for i in range(n)]
        rhs = [sum(v[i]*(row['target']-intercept) for row, v in zip(train, x)) for i in range(n)]
        candidates.append(dict(baseline, estimator='ridge', alpha=alpha, coefficients=_solve(matrix, rhs)))
    chosen = candidates[-1]
    diagnostics = [{'estimator': m['estimator'], 'alpha': m['alpha'], 'diagnostic_training_mse': statistics.mean((_predict(row,m)-row['target'])**2 for row in train), 'selected_by_ex_ante_config': m is chosen, 'selection_scope':'ex_ante_configuration_train_only_fit'} for m in candidates]
    return chosen, diagnostics


def _predict(row, model):
    return _number(model['intercept'] + sum(v*c for v, c in zip(_vector(row, model['preprocessing']), model['coefficients'])))


def _paired_uncertainty(rows, differences, config):
    days = int(config.get('block_days', 5))
    count = int(config.get('resamples', 500))
    if days <= 0 or not 1 <= count <= 10000:
        raise ValueError('invalid_bounded_uncertainty_config')
    # All issuers observed in a calendar block resample together. Economic groups
    # spanning blocks union those blocks, preventing an event being resampled apart.
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc).date()
    keys = [(r['_decision'].date()-epoch).days//days for r in rows]
    parent = {k: k for k in keys}
    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k
    event_block = {}
    for row, key in zip(rows, keys):
        group = row['economic_event_group']
        if group in event_block:
            parent[find(key)] = find(event_block[group])
        event_block[group] = key
    blocks = {}
    for key, value in zip(keys, differences):
        blocks.setdefault(find(key), []).append(value)
    values = list(blocks.values())
    interval = None
    if len(values) >= 2:
        rng = random.Random(config.get('seed', 0))
        estimates = sorted(statistics.mean(v for block in rng.choices(values, k=len(values)) for v in block) for _ in range(count))
        interval = [estimates[int(.025*(count-1))], estimates[int(.975*(count-1))]]
    width = interval[1]-interval[0] if interval else None
    required = config.get('required_interval_width')
    return {'method': 'paired_shared_calendar_blocks_with_economic_group_union', 'calendar_blocks': len(values), 'block_days': days, 'resamples': count, 'interval_95': interval, 'interval_width': width, 'adequacy': 'not_established' if required is None or width is None else ('precision_met' if width <= _number(required) else 'inconclusive'), 'limitation': 'Development diagnostics; few blocks, dependence and regime stability need independent review.'}


def evaluate_forecasts(features, labels, folds, experiment):
    """Train-only declared mean/ridge, untouched development scores and paired losses.

    Requires qualified numeric labels; missing labels are exclusions. This
    bounded entry point never evaluates a protected final holdout.
    """
    report = {'schema_version': '1.0', 'mode': 'research_only', 'status': 'insufficient', 'final_test_evaluations': 0, 'folds': [], 'comparisons': {}, 'excluded': [], 'diagnostics': [], 'limitations': ['Software minimums are not statistical sample adequacy.', 'Historical results remain research only; source quality requires independent audit.']}
    report['target_units'] = experiment.get('target_units')
    report['target_unit_validation'] = 'explicit_expected_units' if 'target_units' in experiment else 'legacy_no_explicit_units_not_canonical_qualification'
    if experiment.get('mode') != 'research_only' or experiment.get('evaluate_final_test'):
        return dict(report, status='ineligible', diagnostics=['final_test_closed_or_invalid_mode'])
    feature_rows, label_rows = _rows(features), _rows(labels)
    if len(feature_rows) > 10000:
        return dict(report, status='ineligible', diagnostics=['bounded_runner_max_10000_rows_use_remote_compute'])
    try:
        fold_rows = _rows(folds)
        holdout_start = registered_validation_end = None
        if experiment.get('split_protocol') is not None:
            split = experiment['split_protocol']
            try:
                registered_train_end, registered_validation_end, holdout_start, holdout_end = [_time(split[k]) for k in ('train_end_utc','validation_end_utc','holdout_start_utc','holdout_end_utc')]
            except (KeyError,TypeError,ValueError) as exc:
                raise ValueError('incomplete_split_protocol') from exc
            if not registered_train_end < registered_validation_end <= holdout_start < holdout_end:
                raise ValueError('invalid_registered_split_chronology')
            if any(_time(f['validation_end_utc']) > registered_validation_end or _time(f['validation_end_utc']) >= holdout_start or _time(f['train_end_utc']) >= holdout_start for f in fold_rows):
                raise ValueError('fold_crosses_registered_development_boundary')
        estimator = experiment.get('estimator','ridge')
        if estimator == 'train_mean':
            estimator = 'training_mean'
        if estimator not in {'ridge','training_mean'}:
            raise ValueError('registered_supported_estimator_required')
        alphas = experiment.get('ridge_alphas',[1.0])
        alpha = None
        if estimator == 'ridge':
            if 'ridge_alpha' in experiment:
                alpha = _number(experiment['ridge_alpha'])
                if 'ridge_alphas' in experiment and alpha not in [_number(v) for v in alphas]:
                    raise ValueError('unregistered_ex_ante_ridge_alpha')
            elif len(alphas) == 1:
                alpha = _number(alphas[0])
            else:
                raise ValueError('ex_ante_ridge_alpha_required')
            if alpha <= 0:
                raise ValueError('ridge_alpha_must_be_positive')
        report['model_selection_scope'] = 'ex_ante_configuration_train_only_fit'
        report['input_hashes'] = {'features': _hash(features), 'labels': _hash(labels), 'experiment': _hash(experiment), 'folds': _hash(folds)}
        ablations = experiment['ablations']
        if 'market_only' not in ablations or any(not v or len(v) != len(set(v)) for v in ablations.values()):
            raise ValueError('registered_market_only_and_nonempty_unique_columns_required')
        if len(ablations) > 12 or len(experiment.get('ridge_alphas', [1.0])) > 12:
            raise ValueError('bounded_finite_trial_family_required')
        required = set(c for columns in ablations.values() for c in columns)
        feature_map = {}
        for row in feature_rows:
            key = (row['decision_id'], row['instrument_id'])
            if key in feature_map:
                raise ValueError('duplicate_feature_identity')
            feature_map[key] = row
        development_end = max((_time(f['validation_end_utc']) for f in _rows(folds)), default=None)
        if development_end is None:
            raise ValueError('registered_development_folds_required')
        rows, identities = [], set()
        for label in label_rows:
            key = (label.get('decision_id'), label.get('instrument_id'))
            try:
                if not all(isinstance(v, str) and v for v in key):
                    raise ValueError('missing_decision_or_instrument_id')
                decision = _time(label['decision_at_utc'])
                if label.get('partition') in {'final_test','test','protected_holdout'} or (holdout_start is not None and decision >= holdout_start):
                    raise ValueError('protected_holdout_row')
                if decision > development_end:
                    raise ValueError('outside_development_window')
                end, available = [_time(label[k]) for k in ('outcome_end_utc', 'target_available_at_utc')]
                identity = (label['instrument_id'], decision, experiment['horizon_id'], experiment['target_name'])
                if identity in identities:
                    raise ValueError('duplicate_instrument_decision')
                identities.add(identity)
                if not decision < end <= available:
                    raise ValueError('invalid_outcome_interval')
                if label.get('quality') != 'qualified':
                    raise ValueError('unqualified_target')
                if label.get('target_name', experiment['target_name']) != experiment['target_name'] or label.get('horizon_id', experiment['horizon_id']) != experiment['horizon_id']:
                    raise ValueError('target_or_horizon_mismatch')
                # Named targets can still carry incompatible dimensions. Explicit
                # producer or experiment units require an exact two-sided contract.
                if 'target_units' in experiment or 'target_units' in label:
                    expected_units, actual_units = experiment.get('target_units'), label.get('target_units')
                    if (not isinstance(expected_units,str) or not expected_units.strip()
                            or not isinstance(actual_units,str) or not actual_units.strip()):
                        raise ValueError('target_unit_contract_missing')
                    if actual_units != expected_units:
                        raise ValueError('target_units_mismatch')
                f = feature_map.get(key)
                if f is None:
                    raise ValueError('missing_features')
                if _time(f['decision_at_utc']) != decision:
                    raise ValueError('decision_clock_mismatch')
                if _time(f['available_at_utc']) > decision:
                    raise ValueError('future_feature')
                if required-set(f['features']):
                    raise ValueError('missing_ablation_feature_schema')
                for column in required:
                    if f['features'][column] is not None:
                        _number(f['features'][column])
                rows.append(dict(label, target=_number(label['target']), features=f['features'], economic_event_group=label.get('economic_event_group') or 'control:'+label['decision_id'], _decision=decision, _end=end, _available=available))
            except (ValueError, TypeError, KeyError) as exc:
                report['excluded'].append({'decision_id': key[0], 'instrument_id': key[1], 'reason': str(exc)})
                if str(exc) == 'duplicate_instrument_decision':
                    raise ValueError('duplicate_instrument_decision') from exc
        report['eligible_rows'] = len(rows)
        report['input_rows'] = len(label_rows)
        report['excluded_rows'] = len(report['excluded'])
        paired, scored = {name: [] for name in ablations}, set()
        all_scored = []
        for fold in _rows(folds):
            train_end, val_end = _time(fold['train_end_utc']), _time(fold['validation_end_utc'])
            if train_end >= val_end:
                raise ValueError('invalid_forward_fold')
            result = {'fold_id': fold['fold_id'], 'models': {}, 'purged': [], 'status': 'insufficient', 'selection_scope':'ex_ante_configuration_train_only_fit', 'registered_but_not_fit_alphas':[v for v in alphas if v != alpha]}
            report['folds'].append(result)
            train = [r for r in rows if r['_decision'] <= train_end]
            validation = [r for r in rows if train_end < r['_decision'] <= val_end]
            train_groups = {r['economic_event_group'] for r in train}
            val_groups = {r['economic_event_group'] for r in validation}
            crossing = train_groups & val_groups
            def eligible(row, training):
                reason = None
                if row['economic_event_group'] in crossing:
                    reason = 'economic_group_crosses_boundary'
                elif training and any(row['_decision'] <= v['_end'] and row['_end'] >= v['_decision'] for v in validation):
                    reason = 'overlapping_outcome_interval'
                elif row['_available'] > (train_end if training else val_end):
                    reason = 'target_not_mature_at_train_cutoff' if training else 'target_not_mature_at_validation_cutoff'
                if reason:
                    result['purged'].append({'decision_id': row['decision_id'], 'reason': reason})
                return reason is None
            train, validation = [r for r in train if eligible(r, True)], [r for r in validation if eligible(r, False)]
            result.update(train_decision_ids=[r['decision_id'] for r in train], validation_decision_ids=[r['decision_id'] for r in validation])
            result['counts'] = {'train_rows':len(train), 'train_groups':len({r['economic_event_group'] for r in train}), 'validation_rows':len(validation), 'validation_groups':len({r['economic_event_group'] for r in validation})}
            result['software_minimums'] = {'train_rows':int(experiment.get('min_train_rows',30)), 'validation_rows':int(experiment.get('min_validation_rows',10))}
            if len(train) < int(experiment.get('min_train_rows', 30)) or len(validation) < int(experiment.get('min_validation_rows', 10)) or not train or not validation:
                continue
            if any((r['decision_id'], r['instrument_id']) in scored for r in validation):
                raise ValueError('repeated_validation_rows_across_folds')
            staged = {}
            try:
                for name, columns in ablations.items():
                    model, candidates = _fit(train, columns, estimator, alpha)
                    predictions = [_predict(row, model) for row in validation]
                    staged[name] = {'model': model, 'selection': candidates, 'predictions': predictions}
            except ValueError as exc:
                result['diagnostics'] = [str(exc)]
                continue
            mean = statistics.mean(r['target'] for r in train)
            result['training_mean_validation_mse'] = statistics.mean((mean-r['target'])**2 for r in validation)
            for name, item in staged.items():
                result['models'][name] = item['model']
                result.setdefault('selection', {})[name] = item['selection']
                losses = [(p-r['target'])**2 for p, r in zip(item['predictions'], validation)]
                result.setdefault('metrics', {})[name] = {'mse': statistics.mean(losses), 'mae': statistics.mean(abs(p-r['target']) for p, r in zip(item['predictions'], validation))}
                result.setdefault('forecasts', {})[name] = [{'decision_id': r['decision_id'], 'instrument_id': r['instrument_id'], 'decision_at_utc': r['decision_at_utc'], 'prediction': p, 'mode': 'research_only'} for r, p in zip(validation, item['predictions'])]
                paired[name].extend(losses)
            scored.update((r['decision_id'], r['instrument_id']) for r in validation)
            all_scored.extend(validation)
            result['status'] = 'evaluated'
        if all_scored:
            report['status'] = 'evaluated'
            baseline = paired['market_only']
            for name, loss in paired.items():
                differences = [a-b for a,b in zip(loss, baseline)]
                report['comparisons'][name] = {'paired_rows': len(loss), 'mean_loss_difference_vs_market': statistics.mean(differences), 'uncertainty': _paired_uncertainty(all_scored, differences, experiment.get('uncertainty', {})), 'conclusion': 'development_diagnostic_only'}
        return report
    except (KeyError, TypeError, ValueError) as exc:
        return dict(report, status='ineligible', diagnostics=[str(exc)], comparisons={})
