"""Frozen, exploratory conditional comparisons with a complete decision ledger.

Marks are statistical targets, not executable or costed returns. The registered
context and interaction columns must be constructed using decision-time inputs.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.multi_market.evaluation import _metrics, _ridge_predictions, calendar_block_interval


@dataclass
class StudyResult:
    report: dict
    predictions: pd.DataFrame
    decisions: pd.DataFrame
    ledger: pd.DataFrame


def _ledger(decisions: pd.DataFrame, hypothesis: str, names: list[str]) -> pd.DataFrame:
    if 'target_units' not in decisions:
        decisions = decisions.assign(target_units='unspecified_input_units')
    cols = ['date', 'next_date', 'ticker', 'decision_at', 'feature_available_at',
            'context_available_at', 'label_available_at', 'target_units', 'source_version',
            'status', 'trade_status',
            'abstention_reason', 'trade_abstention_reason', 'target', 'outcome_observed',
            'training_only_confidence', 'exposure_prediction']
    ledger = decisions[cols + names].melt(id_vars=cols, value_vars=names,
                                           var_name='candidate', value_name='prediction')
    ledger['hypothesis'] = hypothesis
    ledger['cost_limitations'] = 'statistical mark only; spread, fees, slippage, capital and executable timing unmeasured'
    ledger['training_only_confidence'] = ledger.training_only_confidence.where(ledger.candidate.eq('context_lattice'))
    ledger['exposure_prediction'] = ledger.exposure_prediction.where(ledger.candidate.eq('context_lattice'))
    return ledger.sort_values(['date', 'ticker', 'candidate']).reset_index(drop=True)


def _reason(row: pd.Series, baseline: list[str], context: list[str],
            interactions: list[str], lattice: list[str]) -> str:
    if pd.isna(row.decision_at):
        return 'missing_decision_clock'
    if pd.isna(row.feature_available_at) or row.feature_available_at > row.decision_at:
        return 'feature_after_decision'
    if pd.isna(row.context_available_at) or row.context_available_at > row.decision_at:
        return 'context_after_decision'
    qualified = row.context_qualified
    if pd.isna(qualified) or qualified != True:
        reason = row.get('context_reason')
        return str(reason) if reason is not None and not pd.isna(reason) and str(reason) else 'context_unqualified'
    if not np.isfinite(pd.to_numeric(row[context], errors='coerce').to_numpy(dtype=float)).all():
        return 'nonfinite_context'
    if not np.isfinite(pd.to_numeric(row[interactions], errors='coerce').to_numpy(dtype=float)).all():
        return 'nonfinite_lattice_interaction'
    if lattice and not np.isfinite(pd.to_numeric(row[lattice], errors='coerce').to_numpy(dtype=float)).all():
        return 'nonfinite_lattice_only'
    if not np.isfinite(pd.to_numeric(row[baseline], errors='coerce').to_numpy(dtype=float)).all():
        return 'nonfinite_baseline'
    return ''


def _interval(rows: pd.DataFrame, values: np.ndarray, repetitions: int, block_sessions: int, seed: int) -> dict:
    return calendar_block_interval(rows[['date']].assign(increment=values), 'increment',
                                   repetitions=repetitions, block_sessions=block_sessions, seed=seed)


def evaluate_contextual_hypothesis(
    rows: pd.DataFrame, *, hypothesis: str, baseline_columns: list[str],
    context_columns: list[str], interaction_columns: list[str], train_start,
    holdout_start, holdout_end, target_column: str = 'target_return', ridge: float = 1.,
    purge_sessions: int = 1, bootstrap_repetitions: int = 500,
    block_sessions: int = 10, seed: int = 20261003,
    lattice_columns: list[str] | None = None,
) -> StudyResult:
    """Fit exactly one nested conditional ridge packet on a common qualified cohort.

    All columns, windows and target are passed before fitting. Unqualified rows
    remain in ``decisions`` with outcomes where observable. ``predictions`` is
    the identical eligible cohort used by every comparator.
    """
    if hypothesis not in {'catchup', 'reversal', 'movement'}:
        raise ValueError('hypothesis must be catchup, reversal or movement')
    if not baseline_columns or not context_columns or not interaction_columns:
        raise ValueError('one frozen baseline, context and Lattice interaction required')
    if ridge <= 0 or purge_sessions < 1:
        raise ValueError('positive ridge and at least one purged session required')
    if hypothesis == 'movement' and not {'volatility', 'historical_abs_return_mean'} <= set(baseline_columns):
        raise ValueError('movement baseline requires volatility and historical_abs_return_mean')
    required = {'date', 'next_date', 'ticker', 'decision_at', 'feature_available_at', 'context_available_at',
                'context_qualified', 'label_available_at', 'source_version', target_column,
                *baseline_columns, *context_columns, *interaction_columns, *(lattice_columns or [])}
    missing = sorted(required - set(rows.columns))
    if missing:
        raise ValueError(f'missing required columns: {missing}')
    data = rows.copy()
    data['date'] = pd.to_datetime(data.date)
    data['next_date'] = pd.to_datetime(data.next_date, errors='coerce')
    raw_target = pd.to_numeric(data[target_column], errors='coerce')
    finite_target = np.isfinite(raw_target.to_numpy(dtype=float))
    if data.duplicated(['date', 'ticker']).any():
        raise ValueError('duplicate decision rows')
    if (data.next_date.notna() & data.next_date.le(data.date)).any() or (data.next_date.isna() & finite_target).any():
        raise ValueError('next_date must follow date for every observed target')
    if data.source_version.isna().any() or data.source_version.astype(str).str.strip().eq('').any():
        raise ValueError('source_version must be populated on every decision row')
    data['target'] = raw_target.to_numpy(dtype=float)
    for clock in ['decision_at', 'feature_available_at', 'context_available_at', 'label_available_at']:
        data[clock] = pd.to_datetime(data[clock], utc=True, errors='coerce')
    start, end, first = pd.Timestamp(holdout_start), pd.Timestamp(holdout_end), pd.Timestamp(train_start)
    if first >= start or start > end:
        raise ValueError('invalid frozen chronology')
    data = data.sort_values(['date', 'ticker']).reset_index(drop=True)
    baseline = list(dict.fromkeys(baseline_columns))
    context = list(dict.fromkeys(context_columns))
    interactions = list(dict.fromkeys(interaction_columns))
    lattice = list(dict.fromkeys(lattice_columns or []))
    if (set(baseline) & (set(context) | set(interactions) | set(lattice)) or
        set(context) & (set(interactions) | set(lattice)) or
        set(interactions) & set(lattice)):
        raise ValueError('feature families must be disjoint')
    if hypothesis == 'movement':
        data['target'] = data.target.abs()
    data['abstention_reason'] = data.apply(_reason, axis=1, args=(baseline, context, interactions, lattice))
    data['eligible_context'] = data.abstention_reason.eq('')
    before = sorted(data.loc[data.date < start, 'date'].unique())
    embargo = set(before[-purge_sessions:])
    cutoff = start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC')
    train_mask = (data.date >= first) & (data.date < start) & ~data.date.isin(embargo) & (data.label_available_at < cutoff)
    holdout_mask = data.date.between(start, end)
    decisions = data.loc[holdout_mask].copy().reset_index(drop=True)
    observed = (np.isfinite(decisions.target.to_numpy(dtype=float)) &
                decisions.label_available_at.notna().to_numpy() &
                decisions.next_date.notna().to_numpy())
    decisions['outcome_observed'] = observed
    decisions['eligible'] = decisions.eligible_context & observed
    decisions.loc[~decisions.outcome_observed, 'abstention_reason'] = 'outcome_unobserved'
    train = data.loc[train_mask & data.eligible_context & np.isfinite(data.target)].copy()
    test = decisions.loc[decisions.eligible].copy()
    spec = {'hypothesis': hypothesis, 'target': ('absolute_next_session_mark_change' if hypothesis == 'movement' else target_column),
            'baseline_columns': baseline, 'context_columns': context, 'interaction_columns': interactions,
            'lattice_columns': lattice,
            'train_start': first.isoformat(), 'holdout_start': start.isoformat(), 'holdout_end': end.isoformat(),
            'ridge': ridge, 'purge_sessions': purge_sessions,
            'bootstrap_repetitions': bootstrap_repetitions, 'block_sessions': block_sessions, 'seed': seed}
    report = {'status': 'exploratory', 'evidence': 'previously inspected 2024/2025 development windows; no independent confirmation',
              'specification': spec, 'cohort': {'paired_train_rows': len(train), 'paired_holdout_rows': len(test),
              'purged_sessions': [pd.Timestamp(d).isoformat() for d in sorted(embargo)],
              'availability_cutoff_exclusive': cutoff.isoformat()},
              'coverage': {'holdout_opportunities': len(decisions), 'qualified_decisions': len(test),
                           'abstention_reasons': decisions.loc[~decisions.eligible, 'abstention_reason'].value_counts().to_dict()},
              'metrics': {}, 'paired_comparisons': {}, 'failures': [],
              'limitations': ['uncosted statistical marks', 'no executable entry, spread or fees',
                              'adjustment vintages and point-in-time source coverage require audit',
                              'calendar block length is an exploratory assumption',
                              'no promotion or profit inference from inspected diagnostic years']}
    columns = baseline + context + interactions
    cohort_columns = columns + lattice
    names = ['baseline', 'context_only', 'context_lattice', *(['lattice_only'] if lattice else []),
             'zero', 'simple_substitute']
    predictions = test.copy()
    for name in names:
        decisions[name] = np.nan
    decisions['training_only_confidence'] = np.nan
    decisions['exposure_prediction'] = np.nan
    decisions['status'] = np.where(decisions.eligible, 'eligible', 'abstain')
    decisions['trade_status'] = 'no_trade'
    decisions['trade_abstention_reason'] = decisions.abstention_reason
    if len(train) < max(20, 3 * (len(cohort_columns) + 1)) or len(test) < 2:
        report['status'] = 'blocked'
        report['failures'].append({'stage': 'common_cohort', 'reason': 'insufficient qualified paired train/holdout rows'})
        decisions.loc[decisions.eligible, ['status', 'abstention_reason']] = ['blocked', 'insufficient_training_or_holdout']
        return StudyResult(report, predictions, decisions, _ledger(decisions, hypothesis, names))
    fits = {}
    model_columns = {'baseline': baseline, 'context_only': baseline + context,
                     'context_lattice': columns}
    if lattice:
        model_columns['lattice_only'] = baseline + lattice
    try:
        for name, selected in model_columns.items():
            predictions[name], fits[name] = _ridge_predictions(train, predictions, selected, ridge)
        predictions['zero'] = 0.
        means = train.groupby('ticker').target.mean()
        predictions['simple_substitute'] = predictions.ticker.map(means).fillna(train.target.mean()).to_numpy(dtype=float)
        fits['simple_substitute'] = {'ticker_training_means': means.to_dict(), 'global_training_mean': float(train.target.mean())}
        fits['zero'] = {'prediction': 0.}
        if not np.isfinite(predictions[list(model_columns) + ['zero', 'simple_substitute']].to_numpy(dtype=float)).all():
            raise ValueError('nonfinite fitted prediction')
    except (ValueError, np.linalg.LinAlgError) as error:
        report['status'] = 'blocked'
        report['failures'].append({'stage': 'fit', 'reason': str(error)})
        decisions.loc[decisions.eligible, ['status', 'abstention_reason']] = ['blocked', 'fit_failed']
        return StudyResult(report, predictions, decisions, _ledger(decisions, hypothesis, names))
    report['fits'] = fits
    scale = max(float(train.target.std()), 1e-12)
    for name in names:
        report['metrics'][name] = _metrics(predictions, name, scale)
        if hypothesis == 'movement':
            report['metrics'][name]['direction_accuracy'] = None
    for name in ['context_lattice', 'context_only', *(['lattice_only'] if lattice else []),
                 'baseline', 'simple_substitute', 'zero']:
        report['paired_comparisons'][name] = {}
        for comparator in (['context_only', *(['lattice_only'] if lattice else []),
                            'baseline', 'simple_substitute', 'zero'] if name == 'context_lattice' else ['baseline']):
            if name == comparator:
                continue
            gain = (predictions.target - predictions[comparator]) ** 2 - (predictions.target - predictions[name]) ** 2
            report['paired_comparisons'][name][comparator] = _interval(predictions, gain.to_numpy(), bootstrap_repetitions, block_sessions, seed)
    # Residual training error is fitted only on allowed training rows; this is a
    # diagnostic confidence scale, not calibrated trade probability.
    train_fitted, _ = _ridge_predictions(train, train, columns, ridge)
    train_context_fitted, _ = _ridge_predictions(train, train, baseline + context, ridge)
    residual_scale = max(float(np.sqrt(np.mean((train.target.to_numpy() - train_fitted) ** 2))), 1e-12)
    predictions['training_only_confidence'] = np.abs(predictions.context_lattice) / residual_scale
    predictions['exposure_prediction'] = (np.where(
        np.sign(predictions.context_lattice) == np.sign(predictions.context_only), 1., 0.)
        if hypothesis != 'movement' else np.zeros(len(predictions)))
    for col in names + ['training_only_confidence', 'exposure_prediction']:
        decisions.loc[decisions.eligible, col] = predictions[col].to_numpy()
    decisions.loc[decisions.eligible, 'status'] = 'evaluated'
    decisions.loc[decisions.eligible, 'trade_status'] = np.where(
        predictions.exposure_prediction.to_numpy() > 0, 'candidate_mark', 'no_trade')
    decisions.loc[decisions.eligible, 'trade_abstention_reason'] = (
        np.where(predictions.exposure_prediction.to_numpy() > 0, '', 'direction_conflict')
        if hypothesis != 'movement' else 'movement_has_no_direction')
    report['coverage']['forecast_qualified_decisions'] = len(predictions)
    report['coverage']['mark_no_trade_direction_conflict'] = (
        int((predictions.exposure_prediction == 0).sum()) if hypothesis != 'movement' else 0)
    decision_sign = np.sign(predictions.context_lattice.to_numpy()) * predictions.exposure_prediction.to_numpy()
    outcome = predictions.target.to_numpy()
    if hypothesis != 'movement':
        direct = {}
        for comparator in ['context_only', *(['lattice_only'] if lattice else []),
                           'baseline', 'simple_substitute', 'zero']:
            comparator_sign = np.sign(predictions[comparator].to_numpy())
            direct[comparator] = _interval(predictions, (decision_sign - comparator_sign) * outcome,
                                           bootstrap_repetitions, block_sessions, seed)
        report['direct_signal'] = {'economic_status': 'blocked', 'uncosted_direction_mark_increment': direct,
                                   'candidate_average_gross_exposure': float(np.abs(decision_sign).mean()),
                                   'comparison_limit': 'control signed policies can have different gross exposure; mark increments are descriptive',
                                   'reason': 'decision-close marks are not executable next-session net returns'}
    else:
        report['direct_signal'] = {'economic_status': 'blocked', 'reason': 'absolute movement has no direction or option premium payoff'}
    if hypothesis != 'movement':
        exposure = predictions.exposure_prediction.to_numpy(dtype=float)
        # Fix the uniform risky/cash mix using training decisions only. Its
        # realized holdout exposure can differ from the adaptive candidate.
        training_exposure = np.where(np.sign(train_fitted) == np.sign(train_context_fitted), 1., 0.)
        cash_exposure = float(training_exposure.mean())
        long_mark = exposure * outcome
        cash_mark = cash_exposure * outcome
        report['risk_filter'] = {
            'economic_status': 'blocked', 'policy': 'one unit when context-only and context-plus-Lattice forecast signs agree, zero/no-trade otherwise',
            'candidate_holdout_mean_exposure': float(exposure.mean()),
            'exposure_matched_cash_control': cash_exposure,
            'control_frozen_on': 'qualified_training_cohort',
            'paired_downside_second_moment_increment': _interval(predictions,
                np.minimum(cash_mark, 0) ** 2 - np.minimum(long_mark, 0) ** 2,
                bootstrap_repetitions, block_sessions, seed),
            'paired_mark_increment': _interval(predictions, long_mark - cash_mark,
                bootstrap_repetitions, block_sessions, seed),
            'reason': 'uncosted mark comparison; realized average exposures can differ; no transaction, mandate or capital model'}
    else:
        report['risk_filter'] = {'economic_status': 'blocked',
                                 'reason': 'absolute movement target has no signed return or option premium payoff'}
    abstained = decisions.loc[~decisions.eligible & decisions.outcome_observed]
    qualified = decisions.loc[decisions.eligible]
    report['coverage']['observed_abstention_rows'] = len(abstained)
    report['coverage']['mean_observed_abstention_target'] = (float(abstained.target.mean()) if len(abstained) else None)
    report['coverage']['mean_qualified_target'] = (float(qualified.target.mean()) if len(qualified) else None)
    report['coverage']['missed_absolute_mark_opportunity'] = (float(abstained.target.abs().mean()) if len(abstained) else None)
    report['coverage']['qualification_rate'] = len(qualified) / len(decisions) if len(decisions) else None
    if hypothesis != 'movement':
        conflict = decisions.loc[decisions.trade_abstention_reason.eq('direction_conflict') & decisions.outcome_observed]
        report['coverage']['observed_direction_conflict_no_trade_rows'] = len(conflict)
        report['coverage']['mean_target_on_direction_conflict'] = float(conflict.target.mean()) if len(conflict) else None
        report['coverage']['mean_absolute_target_on_direction_conflict'] = float(conflict.target.abs().mean()) if len(conflict) else None
        report['coverage']['direction_conflict_opportunity_limit'] = 'absolute observed mark movement is a skipped-opportunity proxy, not an attainable trading profit'
    return StudyResult(report, predictions, decisions, _ledger(decisions, hypothesis, names))
