#!/usr/bin/env python3
"""Recover frozen past-only risk constants; add paired pricing diagnostics.

No forecast refit. Control scaling is fixed by TRAINING average gross exposure.
Holdout exposure mismatch is reported; these are uncosted mark diagnostics.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.multi_market.evaluation import calendar_block_interval

BOOTSTRAP = dict(repetitions=500, block_sessions=10, seed=20261003)
EXPOSURE_TOLERANCE = .01  # absolute gross exposure; an audit flag, no policy tuning


def _utc(value):
    return pd.Timestamp(value).tz_localize('UTC') if pd.Timestamp(value).tzinfo is None else pd.Timestamp(value).tz_convert('UTC')


def _keys(frame):
    return [[d.isoformat(), str(t)] for d, t in zip(frame.date, frame.ticker)]


def _key_hash(frame):
    return hashlib.sha256(json.dumps(_keys(frame), separators=(',', ':')).encode()).hexdigest()


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def complete_risk(features: pd.DataFrame, predictions: pd.DataFrame, original_report: dict, *,
                  baseline: list[str], candidates: dict[str, list[str]], train_start,
                  holdout_start, holdout_end, purge_sessions: int = 1) -> dict:
    data = features.copy()
    test = predictions.copy()
    for frame in [data, test]:
        frame['date'] = pd.to_datetime(frame.date, utc=True)
        if frame.duplicated(['date', 'ticker']).any():
            raise ValueError('duplicate decision keys')
    data = data.sort_values(['date', 'ticker']).reset_index(drop=True)
    test = test.sort_values(['date', 'ticker']).reset_index(drop=True)
    start, end = _utc(holdout_start), _utc(holdout_end)
    columns = list(dict.fromkeys(baseline + [c for family in candidates.values() for c in family]))
    complete = np.isfinite(data[columns + ['target']].to_numpy(dtype=float)).all(axis=1)
    before = sorted(data.loc[data.date < start, 'date'].unique())
    embargo = before[-purge_sessions:]
    available = pd.to_datetime(data.label_available_at, utc=True)
    train_mask = (data.date < start) & (data.date >= _utc(train_start)) & ~data.date.isin(embargo) & (available < start)
    test_mask = data.date.between(start, end)
    train = data.loc[train_mask & complete].reset_index(drop=True)
    expected_test = data.loc[test_mask & complete].reset_index(drop=True)
    counts = {'eligible_train_rows_before_feature_exclusions': int(train_mask.sum()),
              'eligible_holdout_rows_before_feature_exclusions': int(test_mask.sum()),
              'excluded_train_rows': int(train_mask.sum() - len(train)),
              'excluded_holdout_rows': int(test_mask.sum() - len(expected_test)),
              'paired_train_rows': len(train), 'paired_holdout_rows': len(expected_test)}
    original = original_report['cohort']
    for field, count in counts.items():
        if original[field] != count:
            raise ValueError(f'original cohort mismatch {field}: {original[field]} != {count}')
    if _keys(test) != _keys(expected_test):
        raise ValueError('original holdout keys mismatch reconstructed finite cohort')
    if not np.allclose(test[columns + ['target']], expected_test[columns + ['target']], rtol=1e-10, atol=1e-12):
        raise ValueError('original holdout features/targets mismatch')
    excluded = {c: int((test_mask & ~np.isfinite(data[c])).sum()) for c in columns}
    if 'excluded_by_feature' in original and excluded != original['excluded_by_feature']:
        raise ValueError('original per-feature exclusion statistics mismatch')
    for trial in original_report.get('trials', []):
        if trial['id'] == 'baseline' and 'training_mean' in trial.get('fit', {}):
            if not np.allclose(train[baseline].mean(), trial['fit']['training_mean'], rtol=1e-10, atol=1e-12):
                raise ValueError('original frozen training means mismatch')
    vols = train.volatility.to_numpy(dtype=float)
    reference = float(np.median(vols[np.isfinite(vols) & (vols > 0)]))
    if not np.isfinite(reference) or reference <= 0:
        raise ValueError('invalid causal training volatility median')
    base_train = np.clip(reference / np.maximum(vols, 1e-12), 0, 1)
    base_test = np.clip(reference / np.maximum(test.volatility.to_numpy(dtype=float), 1e-12), 0, 1)
    target = test.target.to_numpy(dtype=float)
    constants = {'training_volatility_median': reference, 'candidates': {},
                 'holdout_exposure_audit_absolute_tolerance': EXPOSURE_TOLERANCE,
                 'normalization_source': 'only reconstructed paired training rows'}
    exposures = {'baseline': base_test, 'fixed_half_cash': np.full(len(test), .5), 'zero': np.zeros(len(test))}
    comparisons = {}
    for name, family in candidates.items():
        state = family[-1]
        threshold = float(train[state].median())
        candidate_train = base_train * np.where(train[state].to_numpy() > threshold, .5, 1.)
        candidate_test = base_test * np.where(test[state].to_numpy() > threshold, .5, 1.)
        average_train = float(candidate_train.mean())
        base_average_train = float(base_train.mean())
        scale = average_train / base_average_train
        constants['candidates'][name] = {'state_column': state, 'past_training_state_median': threshold,
             'candidate_train_average_gross': average_train, 'baseline_train_average_gross': base_average_train,
             'baseline_uniform_scale': scale}
        exposures[name] = candidate_test
        control_name = f'{name}_baseline_scaled_from_train'
        cash_name = f'{name}_uniform_train_fraction_with_cash'
        exposures[control_name] = base_test * scale
        exposures[cash_name] = np.full(len(test), average_train)
        candidate_mark = candidate_test * target
        comparisons[name] = {}
        for control in [control_name, cash_name, 'baseline', 'fixed_half_cash', 'zero']:
            control_exposure = exposures[control]
            control_mark = control_exposure * target
            downside_gain = np.minimum(control_mark, 0) ** 2 - np.minimum(candidate_mark, 0) ** 2
            opportunity_gain = candidate_mark - control_mark
            gross_gap = float(candidate_test.mean() - control_exposure.mean())
            row = test[['date']]
            comparisons[name][control] = {
                'rows': len(test), 'candidate_average_gross': float(candidate_test.mean()),
                'control_average_gross': float(control_exposure.mean()), 'holdout_gross_difference': gross_gap,
                'holdout_exposure_within_audit_tolerance': abs(gross_gap) <= EXPOSURE_TOLERANCE,
                'equivalent_holdout_exposure_claim': False,
                'candidate_daily_mean_downside_second_moment': float(row.assign(x=np.minimum(candidate_mark, 0) ** 2).groupby('date').x.mean().mean()),
                'control_daily_mean_downside_second_moment': float(row.assign(x=np.minimum(control_mark, 0) ** 2).groupby('date').x.mean().mean()),
                'downside_increment': calendar_block_interval(row.assign(gain=downside_gain), 'gain', **BOOTSTRAP),
                'opportunity_increment': calendar_block_interval(row.assign(gain=opportunity_gain), 'gain', **BOOTSTRAP),
                'positive_increment_means': 'less candidate downside squared mark change; higher candidate uncosted long mark opportunity',
                'economic_status': 'blocked'}
    risk_source = original_report.get('roles', {}).get('risk_filter', {}) or original_report.get('uncosted_normalized_pricing_diagnostics', {}).get('risk_filter', {})
    original_metrics = risk_source.get('proxy_metrics', {})
    reproduced = {}
    for name in ['baseline', *candidates]:
        if name in original_metrics:
            exp = exposures[name]
            observed = {'average_gross_exposure': float(exp.mean()),
                        'downside_second_moment': float(np.mean(np.minimum(exp * target, 0) ** 2)),
                        'mean_uncosted_long_mark_change': float(np.mean(exp * target))}
            for field, value in observed.items():
                if not np.isclose(value, original_metrics[name][field], rtol=1e-9, atol=1e-12):
                    raise ValueError(f'original risk policy metric mismatch {name}/{field}')
            reproduced[name] = observed
    return {'status': 'registered_risk_pricing_proxy_completed',
            'cohort': {**counts, 'excluded_by_feature': excluded, 'training_keys_sha256': _key_hash(train),
                       'holdout_keys_sha256': _key_hash(test), 'original_holdout_keys_match': True,
                       'purged_sessions': [pd.Timestamp(d).isoformat() for d in embargo],
                       'availability_cutoff_exclusive': start.isoformat()},
            'training_constants': constants, 'original_risk_statistics_reproduced': reproduced,
            'row_keys': _keys(test), 'row_exposures': {k: v.tolist() for k, v in exposures.items()},
            'paired_risk': comparisons, 'bootstrap': BOOTSTRAP,
            'registry_gate': 'risk role paired downside/opportunity comparisons complete; economic promotion blocked',
            'limitations': ['Control normalization frozen from training, no holdout fitting or forecast refit',
                            'Holdout average exposure may differ; no equivalent exposure benefit claim',
                            'Uncosted pricing proxy; fees, execution, lifecycle, portfolio and coverage gates remain',
                            'Normalized futures marks are not cash, profit or account return',
                            'Exploratory evidence; bootstrap assumptions do not establish economic promotion']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, default=ROOT / 'data/processed/multi_market')
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/experiments/multi-market-v1.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/processed/multi_market/risk-comparisons-v1')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.config.read_text())
    equity_path = args.input_root / 'native-equity-v1/report.json'
    futures_path = args.input_root / 'futures-v1/study_report.json'
    equity = json.loads(equity_path.read_text()); futures = json.loads(futures_path.read_text())
    e_features_path = args.input_root / 'native-equity-v1/features.parquet'
    f_features_path = args.input_root / 'futures-v1/causal_features_and_labels.csv'
    e_features = pd.read_parquet(e_features_path); f_features = pd.read_csv(f_features_path)
    protocol = equity['input_provenance']
    sources = [('EQUITY', e_features, e_features_path, args.input_root / 'native-equity-v1/predictions.csv', equity, equity_path,
                protocol['train_start'], protocol['holdout_start'], protocol['holdout_end'], protocol['purge_sessions'])]
    dates = config['futures_sample_diagnostic']
    sources += [(r, f_features[f_features.root == r], f_features_path, args.input_root / f'futures-v1/{r}_paired_predictions.csv',
                 futures['roots'][r], futures_path, dates['training_dates'][0], dates['diagnostic_dates'][0], dates['diagnostic_dates'][1], 1)
                for r in ['ES', 'ZN', 'CL', 'GC']]
    summary = {'status': 'registered_risk_pricing_proxy_completed', 'forecast_refit': False,
               'config_sha256': _hash(args.config), 'script_sha256': _hash(__file__), 'markets': {}}
    for market, features, feature_path, prediction_path, report, report_path, train_start, start, end, purge in sources:
        before = {str(p.resolve()): _hash(p) for p in [feature_path, prediction_path, report_path, args.config]}
        trial_features = {t['id']: t['features'] for t in report['trials']}
        baseline = trial_features['baseline']
        candidates = {n: [c for c in trial_features[n] if c not in baseline] for n in ['residual_state', 'graph_stability']}
        predictions = pd.read_csv(prediction_path)
        result = complete_risk(features, predictions, report, baseline=baseline, candidates=candidates,
                               train_start=train_start, holdout_start=start, holdout_end=end, purge_sessions=purge)
        result['source_sha256'] = before
        if any(_hash(p) != digest for p, digest in before.items()):
            raise RuntimeError('Original frozen source changed')
        out = args.output / f'{market}_registered_risk_comparisons.json'
        out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
        records = pd.DataFrame({'date': [x[0] for x in result['row_keys']], 'ticker': [x[1] for x in result['row_keys']],
                                **result['row_exposures']})
        records.to_csv(args.output / f'{market}_frozen_row_exposures.csv', index=False)
        summary['markets'][market] = {'paired_train_rows': result['cohort']['paired_train_rows'],
             'paired_holdout_rows': result['cohort']['paired_holdout_rows'], 'original_statistics_reproduced': True,
             'candidate_vs_train_scaled_baseline': {n: result['paired_risk'][n][f'{n}_baseline_scaled_from_train'] for n in candidates},
             'output_sha256': _hash(out)}
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
