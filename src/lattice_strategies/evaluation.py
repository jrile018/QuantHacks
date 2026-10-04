"""Matched forecast diagnostics; statistical marks cannot certify fills."""
from __future__ import annotations
import json
import numpy as np
import pandas as pd


def paired_interval(losses, candidate, control, *, repetitions=500, block=20, seed=20261004):
    """Date-clustered circular block interval; positive = lower candidate loss."""
    paired = losses[[candidate, control]].replace([np.inf, -np.inf], np.nan).dropna()
    if paired.empty:
        return {'cluster_dates': 0, 'improvement': None, 'interval_95': None}
    if block < 1 or repetitions < 1:
        raise ValueError('positive bootstrap repetitions/block required')
    gain = (paired[control] - paired[candidate]).to_numpy()
    rng = np.random.default_rng(seed)
    size = len(gain)
    samples = []
    for _ in range(repetitions):
        starts = rng.integers(0, size, size=int(np.ceil(size / block)))
        indices = ((starts[:, None] + np.arange(block)) % size).ravel()[:size]
        samples.append(float(gain[indices].mean()))
    baseline = float(paired[control].mean())
    return {'cluster_dates': size, 'improvement': float(gain.mean()),
            'relative_improvement_pct': float(100 * gain.mean() / baseline) if baseline > 0 else None,
            'interval_95': list(map(float, np.quantile(samples, [.025, .975]))),
            'interval_scope': 'unadjusted exploratory; date clusters, circular blocks'}


def summarize_forecasts(rows, *, repetitions=500, block=20, seed=20261004):
    required = {'date', 'ticker', 'model', 'horizon', 'forecast', 'outcome', 'status', 'reason'}
    if not required.issubset(rows):
        raise ValueError('forecast contract missing required columns')
    keys = ['date', 'ticker', 'horizon']
    if rows.duplicated(keys + ['model']).any():
        raise ValueError('duplicate forecast opportunity/model')
    if (rows.groupby(keys).outcome.nunique(dropna=True) > 1).any():
        raise ValueError('candidate targets differ on same opportunity')
    report = {'horizons': {}, 'primary_horizon': 1, 'promotion': False,
              'status': 'completed_exploratory', 'rows_retained': len(rows)}
    for horizon, group in rows.groupby('horizon'):
        models = sorted(group.model.unique())
        wide = group.pivot(index=['date', 'ticker'], columns='model', values='forecast')
        targets = group.pivot(index=['date', 'ticker'], columns='model', values='outcome')
        mask = np.isfinite(wide[models]).all(axis=1) & np.isfinite(targets[models]).all(axis=1)
        forecasts, outcomes = wide.loc[mask], targets.loc[mask]
        loss = (forecasts - outcomes) ** 2
        date_losses = loss.groupby(level='date').mean()
        metrics = {}
        for model in models:
            candidate = group.loc[group.model.eq(model)]
            metrics[model] = {
                'mse': float(loss[model].mean()) if len(loss) else None,
                'mae': float((forecasts[model] - outcomes[model]).abs().mean()) if len(loss) else None,
                'forecast_available': int(np.isfinite(candidate.forecast).sum()),
                'valid_model_rows': int(candidate.status.eq('ok').sum()),
                'abstentions': int(candidate.status.eq('no_trade').sum()),
                'unobserved_outcomes': int(candidate.outcome.isna().sum()),
                'reasons': {str(k): int(v) for k, v in candidate.reason.value_counts().items() if k},
            }
        graph_comparisons = {}
        if 'mst_peer_state' in models:
            for control in models:
                if control != 'mst_peer_state':
                    graph_comparisons[control] = paired_interval(date_losses, 'mst_peer_state', control,
                                                               repetitions=repetitions, block=block, seed=seed)
        valid = group.assign(valid=group.status.eq('ok')).pivot(
            index=['date', 'ticker'], columns='model', values='valid').all(axis=1)
        common_valid = mask & valid.reindex(mask.index, fill_value=False)
        valid_metrics = {model: float(loss.loc[common_valid, model].mean()) for model in models} if common_valid.any() else {}
        report['horizons'][str(int(horizon))] = {
            'role': 'primary' if horizon == 1 else 'secondary_path_diagnostic',
            'common_opportunities': int(mask.sum()), 'common_valid_model_opportunities': int(common_valid.sum()),
            'models': metrics, 'paired_graph_comparisons': graph_comparisons,
            'conditional_common_valid_mse': valid_metrics,
            'loss_unit': 'additive_fractional_return_squared',
            'target': 'sum of future daily fractional returns; not compounded multi-session PnL',
            'no_trade_handling': 'invalid model forecasts zero on full common opportunity cohort; conditional subset reported separately',
        }
    return report


def residual_cost_sensitivity(rows, costs):
    """Daily independent spread marks, normalized gross one, assumed round trips.

    No fills, short inventory, netting, funding or cash-account claim is made.
    """
    output = []
    for row in rows.loc[rows.horizon.eq(1)].itertuples():
        weights = row.hedge_weights
        if isinstance(weights, str):
            weights = json.loads(weights)
        gross = sum(abs(float(weight)) for weight in weights.values())
        active = row.status == 'ok' and np.isfinite(row.forecast) and row.forecast != 0 and gross > 0
        for bps in costs:
            observed = np.isfinite(row.hedge_outcome) if active else np.isfinite(row.outcome)
            before_cost = np.sign(row.forecast) * row.hedge_outcome / gross if active and observed else 0. if observed else np.nan
            cost = 2 * float(bps) / 10000 if active else 0.
            output.append({'date': row.date, 'ticker': row.ticker, 'model': row.model,
                           'cost_bps': bps, 'status': 'mark_proxy' if active and observed else 'no_trade' if observed else 'unmarked',
                           'gross_normalization': gross, 'signal': float(np.sign(row.forecast)) if active else 0.,
                           'round_trip_cost': cost, 'gross_mark_return': before_cost,
                           'net_mark_proxy': before_cost - cost if observed else np.nan})
    return pd.DataFrame(output)


def summarize_risk(risks, allocations, *, repetitions=500, block=20, seed=20261004):
    if (risks.groupby('date').observed_squared_return.nunique(dropna=True) > 1).any():
        raise ValueError('fixed-book risk targets differ')
    losses = risks.pivot(index='date', columns='estimator', values='qlike').replace([np.inf, -np.inf], np.nan)
    common = losses.dropna()
    metrics = {}
    for name, group in risks.groupby('estimator'):
        valid = group.loc[group.date.isin(common.index) & np.isfinite(group.qlike)]
        metrics[name] = {'qlike': float(valid.qlike.mean()) if len(valid) else None,
                         'mse': float(valid.mse.mean()) if len(valid) else None,
                         'forecast_mean': float(valid.forecast_variance.mean()) if len(valid) else None,
                         'observed_mean': float(valid.observed_squared_return.mean()) if len(valid) else None,
                         'scored': len(valid), 'available_scored': int(np.isfinite(group.qlike).sum()),
                         'abstentions': int(group.status.eq('abstain').sum()),
                         'unmarked': int(group.status.eq('unmarked').sum())}
    comparisons = {control: paired_interval(common, 'mst_tree', control, repetitions=repetitions, block=block, seed=seed)
                   for control in losses if control != 'mst_tree'}
    policy_metrics = []
    policy_panel = allocations.pivot(index='date', columns=['policy', 'cost_bps'], values='net_proxy_return').replace([np.inf, -np.inf], np.nan)
    common_policy_dates = policy_panel.dropna().index
    for (policy, bps), group in allocations.groupby(['policy', 'cost_bps']):
        valid = group.loc[group.date.isin(common_policy_dates) & np.isfinite(group.net_proxy_return)]
        policy_metrics.append({'policy': policy, 'cost_bps': float(bps), 'marked': len(valid),
                               'mean_net_mark_proxy': float(valid.net_proxy_return.mean()) if len(valid) else None,
                               'std_net_mark_proxy': float(valid.net_proxy_return.std()) if len(valid) > 1 else None,
                               'sum_net_mark_proxy': float(valid.net_proxy_return.sum()),
                               'one_way_trade_volume': float(valid.one_way_trade_volume.sum()),
                               'initial_cost': float(valid.initial_cost.sum()),
                               'terminal_cost': float(valid.terminal_cost.sum()),
                               'full_ledger_initial_cost': float(group.initial_cost.sum()),
                               'full_ledger_terminal_cost': float(group.terminal_cost.sum()),
                               'full_ledger_marked': int(np.isfinite(group.net_proxy_return).sum()),
                               'abstentions': int(group.status.eq('abstain').sum())})
    return {'estimators': metrics, 'common_dates': len(common), 'common_policy_dates': len(common_policy_dates),
            'paired_graph_comparisons': comparisons,
            'allocation_cost_scenarios': policy_metrics, 'promotion': False,
            'forecast_unit': 'fractional_return_squared_per_session', 'mse_unit': 'fractional_return_fourth_power',
            'cost_scope': 'assumed research marks with gross one; no executable or account net profit claim'}
