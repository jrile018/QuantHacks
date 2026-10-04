"""Frozen chronological ridge comparisons on one explicitly paired cohort."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class StudyResult:
    report: dict
    predictions: pd.DataFrame


def calendar_block_interval(rows: pd.DataFrame, column: str, *, repetitions: int = 500,
                            block_sessions: int = 10, seed: int = 20261003) -> dict:
    """Moving calendar-session blocks; every date's instruments stay bundled.

    Estimand is the mean of equally weighted daily cross-sectional means. The
    fixed block length is an exploratory dependence assumption, not a p-value.
    """
    if repetitions < 1 or block_sessions < 1:
        raise ValueError('positive bootstrap repetitions/block_sessions required')
    daily = rows.groupby('date', sort=True)[column].mean().dropna().to_numpy()
    if not len(daily):
        return {'mean': None, 'lower': None, 'upper': None, 'calendar_sessions': 0}
    rng = np.random.default_rng(seed)
    n = len(daily)
    block = min(block_sessions, n)
    count = (n + block - 1) // block
    starts = rng.integers(0, n - block + 1, size=(repetitions, count))
    indices = (starts[..., None] + np.arange(block)).reshape(repetitions, -1)[:, :n]
    estimates = daily[indices].mean(axis=1)
    lower, upper = np.quantile(estimates, [.025, .975])
    return {'mean': float(daily.mean()), 'lower': float(lower), 'upper': float(upper),
            'calendar_sessions': n, 'block_sessions': block, 'repetitions': repetitions,
            'seed': seed, 'method': 'noncircular_moving_calendar_blocks_daily_mean'}


def _ridge_predictions(train: pd.DataFrame, test: pd.DataFrame, columns: list[str],
                       ridge: float) -> tuple[np.ndarray, dict]:
    x = train[columns].to_numpy(dtype=float)
    y = train.target.to_numpy(dtype=float)
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale = np.where(scale > 1e-12, scale, 1.)
    x = np.column_stack([np.ones(len(x)), (x - mean) / scale])
    penalty = ridge * np.eye(x.shape[1])
    penalty[0, 0] = 0
    coef = np.linalg.solve(x.T @ x + penalty, x.T @ y)
    test_x = np.column_stack([np.ones(len(test)), (test[columns].to_numpy(dtype=float) - mean) / scale])
    return test_x @ coef, {'features': columns, 'training_mean': mean.tolist(),
                          'training_scale': scale.tolist(), 'coefficients': coef.tolist()}


def _metrics(predictions: pd.DataFrame, name: str, target_scale: float) -> dict:
    y = predictions.target.to_numpy()
    p = predictions[name].to_numpy()
    loss = (y - p) ** 2
    daily_mse = float(pd.Series(loss, index=predictions.date).groupby(level=0).mean().mean())
    if np.std(p) > 1e-12:
        slope, intercept = np.polyfit(p, y, 1)
    else:
        slope, intercept = None, float(y.mean() - p.mean())
    return {'rows': len(y), 'daily_mean_mse': daily_mse,
            'training_scale_standardized_mse': daily_mse / target_scale ** 2,
            'rmse': float(np.sqrt(daily_mse)), 'mean_prediction': float(p.mean()),
            'mean_outcome': float(y.mean()), 'calibration_intercept': intercept,
            'calibration_slope': None if slope is None else float(slope),
            'direction_accuracy': float(np.mean(np.sign(p) == np.sign(y)))}


def _role_diagnostics(predictions: pd.DataFrame, train: pd.DataFrame, names: list[str],
                      candidates: dict[str, list[str]], repetitions: int,
                      block_sessions: int, seed: int) -> dict:
    """Uncosted mark diagnostics. These functions cannot declare economic alpha."""
    roles = {
        'forecast': {'status': 'exploratory_pricing_proxy'},
        'risk_filter': {'economic_status': 'blocked', 'proxy_metrics': {},
                        'reason': 'quotes, costs, account limits and comparable opportunity/exposure not audited'},
        'direct_signal': {'economic_status': 'blocked', 'proxy_metrics': {},
                          'reason': 'daily mark targets are not executable entry/exit or net account returns'},
        'futures_es_mes': {'status': 'blocked', 'reason': 'actual-contract futures panel, roll/lifecycle, quotes, fees and margin absent'},
        'options': {'status': 'blocked', 'reason': 'synchronized exact-contract pricing and executable lifecycle absent'},
        'hedge': {'status': 'blocked', 'reason': 'fixed underlying portfolio and exposure/account contract absent'},
    }
    if 'volatility' not in predictions or not len(predictions):
        return roles
    vol = predictions.volatility.to_numpy(dtype=float)
    finite_vol = train.volatility.to_numpy(dtype=float)
    risk_reference = float(np.median(finite_vol[np.isfinite(finite_vol) & (finite_vol > 0)]))
    if not np.isfinite(risk_reference) or risk_reference <= 0:
        return roles
    base_exposure = np.clip(risk_reference / np.maximum(vol, 1e-12), 0, 1)
    target = predictions.target.to_numpy(dtype=float)
    baseline_proxy = np.sign(predictions.baseline.to_numpy()) * target
    for name in names:
        signed = np.sign(predictions[name].to_numpy()) if name != 'zero' else np.zeros(len(predictions))
        proxy = signed * target
        paired = predictions[['date']].assign(gain=proxy - baseline_proxy)
        roles['direct_signal']['proxy_metrics'][name] = {
            'mean_uncosted_mark_change': float(pd.Series(proxy, index=predictions.date).groupby(level=0).mean().mean()),
            'average_absolute_exposure': float(np.abs(signed).mean()),
            'paired_mark_increment': calendar_block_interval(paired, 'gain', repetitions=repetitions,
                 block_sessions=block_sessions, seed=seed),
            'units': 'input_target_units; equity fractional mark changes or futures same-contract points',
        }
        exposure = base_exposure.copy()
        if name in candidates:
            state = candidates[name][-1]
            threshold = float(train[state].median())
            exposure *= np.where(predictions[state].to_numpy() > threshold, .5, 1.)
        elif name == 'zero':
            exposure[:] = 0
        mark = exposure * target
        roles['risk_filter']['proxy_metrics'][name] = {
            'mean_uncosted_long_mark_change': float(mark.mean()),
            'downside_second_moment': float(np.mean(np.minimum(mark, 0) ** 2)),
            'average_gross_exposure': float(exposure.mean()),
            'opportunity_cost_vs_full_long': float(np.mean(target - mark)),
            'policy': 'past-training median volatility / current volatility capped at one; candidate halves exposure above past-training state median',
        }
    cash_mark = .5 * target
    roles['risk_filter']['proxy_metrics']['uniform_half_cash'] = {
        'mean_uncosted_long_mark_change': float(cash_mark.mean()),
        'downside_second_moment': float(np.mean(np.minimum(cash_mark, 0) ** 2)),
        'average_gross_exposure': .5, 'opportunity_cost_vs_full_long': float(np.mean(target - cash_mark)),
    }
    roles['risk_filter']['comparison_limit'] = 'Different average exposures; lower downside is not proof of superior filtering'
    return roles


def evaluate_forecasts(rows: pd.DataFrame, *, baseline: list[str],
                       candidates: dict[str, list[str]], holdout_start, holdout_end,
                       train_start=None, ridge: float = 1., purge_sessions: int = 1,
                       bootstrap_repetitions: int = 500, block_sessions: int = 10,
                       seed: int = 20261003) -> StudyResult:
    """One frozen fit per registered packet, shared complete train/test cohorts.

    Label availability must be earlier than the first holdout decision. Purge
    removes the last pre-holdout panel sessions in addition to that clock gate.
    Future holdout outcomes are used for diagnostics only, never normalizers.
    """
    if not baseline or not candidates or len(candidates) > 3:
        raise ValueError('baseline and one to three registered candidate families required')
    if set(candidates) & {'baseline', 'zero', 'simple_substitute'}:
        raise ValueError('reserved candidate model name')
    if ridge <= 0 or purge_sessions < 1:
        raise ValueError('positive ridge and at least one purged session required')
    data = rows.copy()
    data['date'] = pd.to_datetime(data.date)
    if data.duplicated(['date', 'ticker']).any():
        raise ValueError('duplicate decision rows')
    start, end = pd.Timestamp(holdout_start), pd.Timestamp(holdout_end)
    if start > end:
        raise ValueError('holdout dates reversed')
    all_features = list(dict.fromkeys(baseline + [c for family in candidates.values() for c in family]))
    missing = [c for c in all_features if c not in data]
    if 'label_available_at' not in data or 'target' not in data:
        raise ValueError('target and label_available_at required')
    for column in missing:
        data[column] = np.nan
    data = data.sort_values(['date', 'ticker']).reset_index(drop=True)
    before = sorted(data.loc[data.date < start, 'date'].unique())
    embargo = set(before[-purge_sessions:])
    cutoff = start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC')
    available = pd.to_datetime(data.label_available_at, utc=True)
    train_mask = (data.date < start) & ~data.date.isin(embargo) & (available < cutoff)
    if train_start is not None:
        train_mask &= data.date >= pd.Timestamp(train_start)
    test_mask = data.date.between(start, end)
    complete = np.isfinite(data[all_features + ['target']].to_numpy(dtype=float)).all(axis=1)
    train = data.loc[train_mask & complete]
    test = data.loc[test_mask & complete]
    trials = [{'id': name, 'features': cols, 'ridge': ridge, 'status': 'registered',
               'holdout_start': start.isoformat(), 'holdout_end': end.isoformat()}
              for name, cols in {'baseline': baseline, **{n: baseline + c for n, c in candidates.items()},
                                'zero': [], 'simple_substitute': []}.items()]
    report = {'status': 'exploratory', 'evidence': 'previously inspected adjusted-close development panel',
              'cohort': {'eligible_train_rows_before_feature_exclusions': int(train_mask.sum()),
                         'eligible_holdout_rows_before_feature_exclusions': int(test_mask.sum()),
                         'excluded_train_rows': int(train_mask.sum() - len(train)),
                         'excluded_holdout_rows': int(test_mask.sum() - len(test)),
                         'paired_train_rows': len(train), 'paired_holdout_rows': len(test),
                         'excluded_by_feature': {c: int((test_mask & ~np.isfinite(data[c])).sum()) for c in all_features},
                         'purged_sessions': [pd.Timestamp(d).isoformat() for d in sorted(embargo)],
                         'availability_cutoff_exclusive': cutoff.isoformat()},
              'trials': trials, 'failures': [], 'metrics': {}, 'paired_comparisons': {},
              'limitations': ['no executable or net alpha inference', 'no independent confirmation',
                              'adjustment vintages and PIT eligibility not audited',
                              'bootstrap block assumption unvalidated; no significance or promotion claim']}
    predictions = test.copy().reset_index(drop=True)
    if len(train) < max(20, 3 * (len(all_features) + 1)) or len(test) < 2:
        report['status'] = 'blocked'
        report['failures'].append({'stage': 'common_cohort', 'reason': 'insufficient complete paired training/holdout rows',
                                   'missing_columns': missing})
        for trial in trials:
            trial['status'] = 'blocked'
        report['roles'] = _role_diagnostics(predictions.iloc[:0], train, [], candidates,
                                           bootstrap_repetitions, block_sessions, seed)
        return StudyResult(report, predictions)
    names = ['baseline', *candidates, 'zero', 'simple_substitute']
    for trial in trials:
        name, cols = trial['id'], trial['features']
        try:
            if name == 'zero':
                pred, fit = np.zeros(len(test)), {'features': [], 'prediction': 0.}
            elif name == 'simple_substitute':
                means = train.groupby('ticker').target.mean()
                pred = test.ticker.map(means).fillna(train.target.mean()).to_numpy()
                fit = {'features': [], 'ticker_training_means': means.to_dict()}
            else:
                pred, fit = _ridge_predictions(train, test, cols, ridge)
            if not np.isfinite(pred).all():
                raise ValueError('nonfinite forecast')
            predictions[name] = pred
            trial.update(status='evaluated', fit=fit)
        except (ValueError, np.linalg.LinAlgError) as error:
            trial['status'] = 'failed'
            report['failures'].append({'trial': name, 'reason': str(error)})
    if report['failures']:
        report['status'] = 'blocked'
        report['roles'] = _role_diagnostics(predictions.iloc[:0], train, [], candidates,
                                           bootstrap_repetitions, block_sessions, seed)
        return StudyResult(report, predictions)
    target_scale = max(float(train.target.std()), 1e-12)
    report['target_training_scale'] = target_scale
    for name in names:
        report['metrics'][name] = _metrics(predictions, name, target_scale)
        if name != 'baseline':
            comparison = predictions[['date']].assign(gain=(predictions.target - predictions.baseline) ** 2 -
                                                       (predictions.target - predictions[name]) ** 2)
            report['paired_comparisons'][name] = calendar_block_interval(comparison, 'gain',
                repetitions=bootstrap_repetitions, block_sessions=block_sessions, seed=seed)
            bmse = report['metrics']['baseline']['daily_mean_mse']
            report['paired_comparisons'][name]['relative_mse_reduction'] = (
                report['paired_comparisons'][name]['mean'] / bmse if bmse else None)
    report['roles'] = _role_diagnostics(predictions, train, names, candidates,
                                       bootstrap_repetitions, block_sessions, seed)
    return StudyResult(report, predictions)
