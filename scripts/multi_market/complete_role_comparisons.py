#!/usr/bin/env python3
"""Complete registered controls from frozen predictions, without fitting models.

Adds same-row forecast/sign comparisons. Aggregate exposure matching is an
after-test description; it cannot establish a causal risk policy or economics.
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

BOOTSTRAP = {'repetitions': 500, 'block_sessions': 10, 'seed': 20261003}
CANDIDATES = ['residual_state', 'graph_stability']
CONTROLS = ['baseline', 'simple_substitute', 'zero']


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def daily_mean(frame: pd.DataFrame, values: np.ndarray) -> float:
    return float(frame[['date']].assign(value=values).groupby('date').value.mean().mean())


def descriptive_risk_match(original_report: dict | None, candidates: list[str],
                           original_rows: int, excluded_rows: int) -> dict:
    risk = {'policy_comparison_status': 'inconclusive_stateless',
            'prospectively_causal': False, 'economic_status': 'blocked',
            'reason': 'Frozen reports omit training volatility/state medians and exact row exposures; no reconstruction, paired risk interval or policy promotion',
            'normalization': 'after-test aggregate row-weighted average gross exposure scaling only',
            'descriptive_average_exposure_match': {}}
    if not original_report:
        risk['aggregate_match_status'] = 'unavailable_original_report'
        return risk
    expected_rows = original_report.get('cohort', {}).get('paired_holdout_rows')
    if excluded_rows or expected_rows != original_rows:
        risk['aggregate_match_status'] = 'unavailable_aggregate_cohort_mismatch'
        return risk
    source = original_report.get('roles', {}).get('risk_filter', {})
    if not source:
        source = original_report.get('uncosted_normalized_pricing_diagnostics', {}).get('risk_filter', {})
    metrics = source.get('proxy_metrics', {})
    baseline, cash = metrics.get('baseline'), metrics.get('uniform_half_cash')
    if not baseline or not cash:
        risk['aggregate_match_status'] = 'unavailable_recorded_risk_statistics'
        return risk
    def scaled(metric: dict, gross: float) -> dict:
        factor = gross / float(metric['average_gross_exposure'])
        return {'average_gross_exposure': gross, 'uniform_scaling_factor': factor,
                'downside_second_moment': float(metric['downside_second_moment']) * factor ** 2,
                'mean_uncosted_long_mark_change': float(metric['mean_uncosted_long_mark_change']) * factor}
    for name in candidates:
        candidate = metrics.get(name)
        if not candidate:
            continue
        gross = float(candidate['average_gross_exposure'])
        if not np.isfinite(gross) or not 0 <= gross <= 1:
            raise ValueError('invalid recorded candidate exposure')
        ordinary = scaled(baseline, gross)
        uniform = scaled(cash, gross)
        moment = float(candidate['downside_second_moment'])
        risk['descriptive_average_exposure_match'][name] = {
            'candidate_recorded_statistics': candidate,
            'uniformly_scaled_baseline': ordinary,
            'uniform_risky_fraction_with_cash_remainder': uniform,
            'candidate_minus_scaled_baseline_downside': moment - ordinary['downside_second_moment'],
            'candidate_minus_uniform_cash_mix_downside': moment - uniform['downside_second_moment'],
            'candidate_downside_per_squared_gross_exposure': moment / gross ** 2 if gross else None,
            'interval_status': 'unavailable_without_row_exposures',
        }
    risk['aggregate_match_status'] = 'descriptive_only'
    risk['control_note'] = 'Pure cash has zero gross exposure; matching positive exposure uses a constant long risky fraction with cash remainder'
    return risk


def compare_frozen(predictions: pd.DataFrame, *, candidates: list[str] | None = None,
                   original_report: dict | None = None, units: str = 'input_target_units') -> dict:
    """One common finite cohort for every registered comparison and time block."""
    candidates = list(CANDIDATES if candidates is None else candidates)
    if not candidates or set(candidates) & set(CONTROLS):
        raise ValueError('distinct registered candidate names required')
    frame = predictions.copy()
    required = ['date', 'ticker', 'target', *CONTROLS, *candidates]
    absent = [c for c in required if c not in frame]
    if absent:
        raise ValueError(f'missing frozen columns: {absent}')
    frame['date'] = pd.to_datetime(frame.date, utc=True)
    if frame[['date', 'ticker']].isna().any().any():
        raise ValueError('missing decision keys')
    if frame.duplicated(['date', 'ticker']).any():
        raise ValueError('duplicate frozen decisions')
    numeric = ['target', *CONTROLS, *candidates]
    finite = np.isfinite(frame[numeric].to_numpy(dtype=float)).all(axis=1)
    excluded = int((~finite).sum())
    frame = frame.loc[finite].sort_values(['date', 'ticker']).reset_index(drop=True)
    if len(frame) < 2:
        raise ValueError('insufficient finite paired rows')
    if not frame.zero.eq(0).all():
        raise ValueError('registered zero/no-trade control must be exactly zero')
    keys = [[d.isoformat(), str(t)] for d, t in zip(frame.date, frame.ticker)]
    key_hash = hashlib.sha256(json.dumps(keys, separators=(',', ':')).encode()).hexdigest()
    counts = frame.groupby('date').size()
    report = {'status': 'exploratory_additive_registered_diagnostic',
              'units': units, 'bootstrap': BOOTSTRAP, 'cohort': {
                  'source_rows': len(predictions), 'paired_rows': len(frame), 'excluded_rows': excluded,
                  'calendar_sessions': len(counts), 'instruments_per_session_min': int(counts.min()),
                  'instruments_per_session_max': int(counts.max()), 'keys_sha256': key_hash,
                  'first_date': frame.date.min().isoformat(), 'last_date': frame.date.max().isoformat(),
                  'excluded_by_column': {c: int((~np.isfinite(predictions[c].to_numpy(dtype=float))).sum()) for c in numeric}},
              'forecast': {}, 'direct_signal': {},
              'registry_gates': {
                  'paired_forecast_vs_registered_simple_mean_and_zero': 'complete',
                  'paired_uncosted_sign_vs_registered_simple_mean_and_zero': 'complete',
                  'risk_same_average_exposure_policy': 'inconclusive_stateless',
                  'executable_or_net_economic_promotion': 'blocked'},
              'limitations': ['No new fit, rule tuning or outcome-selected trial',
                              'Previously inspected development evidence, not independent confirmation',
                              'Sign-policy mark changes omit costs, execution, account constraints and opportunity/exposure matching',
                              'Futures targets are normalized prior-risk mark units, not cash, profit or account returns',
                              'Bootstrap blocks are fixed dependence assumptions; no p-values or promotion claims'],
              'risk_filter': descriptive_risk_match(original_report, candidates, len(predictions), excluded)}
    target = frame.target.to_numpy(dtype=float)
    for candidate in candidates:
        report['forecast'][candidate] = {}
        report['direct_signal'][candidate] = {}
        candidate_prediction = frame[candidate].to_numpy(dtype=float)
        candidate_loss = (target - candidate_prediction) ** 2
        candidate_mark = np.sign(candidate_prediction) * target
        for control in CONTROLS:
            control_prediction = frame[control].to_numpy(dtype=float)
            control_loss = (target - control_prediction) ** 2
            control_mark = np.sign(control_prediction) * target
            forecast_interval = calendar_block_interval(
                frame[['date']].assign(gain=control_loss - candidate_loss), 'gain', **BOOTSTRAP)
            sign_interval = calendar_block_interval(
                frame[['date']].assign(gain=candidate_mark - control_mark), 'gain', **BOOTSTRAP)
            cmse = daily_mean(frame, control_loss)
            common = {'rows': len(frame), 'cohort_sha256': key_hash}
            report['forecast'][candidate][control] = {
                **common, 'candidate_daily_mean_mse': daily_mean(frame, candidate_loss),
                'control_daily_mean_mse': cmse, 'paired_increment': forecast_interval,
                'relative_mse_reduction': forecast_interval['mean'] / cmse if cmse else None,
                'positive_increment_means': 'lower candidate squared forecast error'}
            report['direct_signal'][candidate][control] = {
                **common, 'candidate_daily_mean_uncosted_mark_change': daily_mean(frame, candidate_mark),
                'control_daily_mean_uncosted_mark_change': daily_mean(frame, control_mark),
                'candidate_average_absolute_exposure': float(np.abs(np.sign(candidate_prediction)).mean()),
                'control_average_absolute_exposure': float(np.abs(np.sign(control_prediction)).mean()),
                'paired_increment': sign_interval,
                'positive_increment_means': 'higher candidate uncosted sign-policy mark change',
                'economic_status': 'blocked'}
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, default=ROOT / 'data/processed/multi_market')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/processed/multi_market/role-comparisons-v1')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    equity_report_path = args.input_root / 'native-equity-v1/report.json'
    futures_report_path = args.input_root / 'futures-v1/study_report.json'
    equity_report = json.loads(equity_report_path.read_text())
    futures_report = json.loads(futures_report_path.read_text())
    sources = [('EQUITY', args.input_root / 'native-equity-v1/predictions.csv', equity_report,
                equity_report_path, 'fractional_equity_adjusted_close_mark_change')]
    sources += [(root, args.input_root / f'futures-v1/{root}_paired_predictions.csv',
                 futures_report['roots'][root], futures_report_path, 'dimensionless_prior_risk_mark_units')
                for root in ['ES', 'ZN', 'CL', 'GC']]
    summary = {'status': 'additive_registered_controls_complete',
               'refit_or_retune': False, 'bootstrap': BOOTSTRAP, 'sources_unchanged': True,
               'script_sha256': sha256_file(Path(__file__)), 'markets': {}}
    for name, path, original, report_path, units in sources:
        hashes_before = {str(p.resolve()): sha256_file(p) for p in [path, report_path]}
        compared = compare_frozen(pd.read_csv(path), original_report=original, units=units)
        compared['source_sha256'] = hashes_before
        if any(sha256_file(Path(p)) != digest for p, digest in hashes_before.items()):
            raise RuntimeError('Frozen source changed while completing comparisons')
        output = args.output / f'{name}_registered_role_comparisons.json'
        output.write_text(json.dumps(compared, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
        summary['markets'][name] = {
            'paired_rows': compared['cohort']['paired_rows'],
            'calendar_sessions': compared['cohort']['calendar_sessions'],
            'output_sha256': sha256_file(output),
            'candidate_vs_simple_mean': {
                candidate: {'forecast_relative_mse_reduction': compared['forecast'][candidate]['simple_substitute']['relative_mse_reduction'],
                            'direct_sign_interval': compared['direct_signal'][candidate]['simple_substitute']['paired_increment']}
                for candidate in CANDIDATES},
            'risk_gate': compared['risk_filter']['policy_comparison_status'],
        }
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
