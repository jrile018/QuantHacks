"""Small causal panel features, version 1. No full-history reference fits.

Daily equity adjusted closes are a pricing proxy whose adjustment vintages and
universe eligibility must be audited separately. Futures use same-contract point
changes, including zero/negative prices; a roll is an unavailable observation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BASELINE_FEATURES = ['return_1d', 'momentum', 'volatility', 'beta',
                     'market_return', 'average_correlation']
CANDIDATE_FAMILIES = {
    'residual_state': ['residual_peer_shock', 'residual_concentration'],
    'graph_stability': ['edge_turnover'],
}


def price_changes(prices: pd.DataFrame) -> pd.DataFrame:
    """Do not bridge missing sessions, invalid equity prices, or futures rolls."""
    data = prices.copy()
    required = {'date', 'ticker'}
    if not required.issubset(data):
        raise ValueError('prices require date and ticker')
    data['date'] = pd.to_datetime(data.date)
    if data.duplicated(['date', 'ticker']).any():
        raise ValueError('duplicate date/ticker prices')
    if 'asset_class' not in data:
        data['asset_class'] = 'equity'
    if not data.asset_class.isin(['equity', 'future']).all():
        raise ValueError('unsupported asset_class; option labels need their own adapter')
    futures = data.asset_class.eq('future')
    if futures.any() and ('contract_id' not in data or data.loc[futures, 'contract_id'].isna().any()):
        raise ValueError('futures require actual contract_id')
    if futures.any() and 'close' not in data:
        raise ValueError('futures require actual-contract close')
    equity_column = 'adjclose' if 'adjclose' in data else 'close'
    if not futures.all() and equity_column not in data:
        raise ValueError('equities require adjclose or close')
    data = data.sort_values(['ticker', 'date']).reset_index(drop=True)
    raw = pd.Series(np.nan, index=data.index)
    if not futures.all():
        raw.loc[~data.asset_class.eq('future')] = pd.to_numeric(
            data.loc[~data.asset_class.eq('future'), equity_column], errors='coerce')
    if futures.any():
        raw.loc[data.asset_class.eq('future')] = pd.to_numeric(
            data.loc[data.asset_class.eq('future'), 'close'], errors='coerce')
    if ('available_at' in data) != ('decision_at' in data):
        raise ValueError('available_at and decision_at must be supplied together')
    if 'available_at' in data:
        known = pd.to_datetime(data.available_at, utc=True) <= pd.to_datetime(data.decision_at, utc=True)
        raw = raw.where(known)
    previous = raw.groupby(data.ticker).shift(1)
    changes = raw / previous - 1
    is_future = data.asset_class.eq('future')
    changes = changes.where((raw > 0) & (previous > 0))
    if is_future.any():
        same_contract = data.contract_id.eq(data.contract_id.groupby(data.ticker).shift(1))
        changes.loc[is_future] = (raw - previous).where(same_contract).loc[is_future]
    calendar = sorted(data.date.unique())
    previous_session = dict(zip(calendar[1:], calendar[:-1]))
    prior_date = data.date.groupby(data.ticker).shift(1)
    consecutive = prior_date.eq(data.date.map(previous_session))
    data['price_change'] = changes.where(consecutive).replace([np.inf, -np.inf], np.nan)
    return data


def _correlation(values: np.ndarray, shrinkage: float) -> np.ndarray:
    covariance = np.cov(values, rowvar=False)
    scales = np.sqrt(np.maximum(np.diag(covariance), 1e-20))
    corr = covariance / np.outer(scales, scales)
    corr = np.nan_to_num(corr, nan=0.)
    np.fill_diagonal(corr, 1.)
    return (1 - shrinkage) * corr + shrinkage * np.eye(len(corr))


def build_features(prices: pd.DataFrame, *, benchmark: str = 'SPY', window: int = 63,
                   shrinkage: float = .1, edge_threshold: float = .5) -> pd.DataFrame:
    """Current-session features and next *panel-session* labels.

    Beta uses strictly earlier returns. Current peer shocks use those causal
    coefficients. Correlations/residual spectra use only windows ending at the
    decision. No backward filling, future fitting, or coordinate alignment.
    Appending labels can reveal an earlier outcome without changing its features.
    """
    if window < 3 or not 0 <= shrinkage <= 1 or not 0 <= edge_threshold <= 1:
        raise ValueError('invalid fixed feature parameters')
    data = price_changes(prices)
    if data.asset_class.nunique() != 1:
        raise ValueError('equity and futures units require separate panels')
    returns = data.pivot(index='date', columns='ticker', values='price_change').sort_index()
    if benchmark != '__equal_weight_panel__' and benchmark not in returns:
        raise ValueError(f'benchmark {benchmark} absent')
    market = returns.mean(axis=1) if benchmark == '__equal_weight_panel__' else returns[benchmark]
    previous_returns = returns.shift(1)
    prior_market = market.shift(1)
    beta = previous_returns.rolling(window).cov(prior_market).div(
        prior_market.rolling(window).var().replace(0, np.nan), axis=0)
    residual = returns - beta.mul(market, axis=0)
    vol = returns.rolling(window).std().replace(0, np.nan)
    momentum = returns.rolling(window).mean()
    pieces = []
    previous_edges = None
    previous_nodes = None
    for i, date in enumerate(returns.index):
        row = pd.DataFrame({'ticker': returns.columns})
        row['date'] = date
        row['return_1d'] = returns.iloc[i].to_numpy()
        row['momentum'] = momentum.iloc[i].to_numpy()
        row['volatility'] = vol.iloc[i].to_numpy()
        row['beta'] = beta.iloc[i].to_numpy()
        row['market_return'] = market.iloc[i]
        for name in ['average_correlation', 'residual_peer_shock',
                     'residual_concentration', 'edge_turnover']:
            row[name] = np.nan
        history = returns.iloc[max(0, i - window + 1):i + 1]
        eligible = history.columns[history.notna().all() & (history.std() > 1e-12)]
        if len(history) == window and len(eligible) >= 3:
            corr = _correlation(history[eligible].to_numpy(), shrinkage)
            upper = np.triu_indices(len(eligible), 1)
            row['average_correlation'] = float(corr[upper].mean())
            edges = np.abs(corr[upper]) >= edge_threshold
            if previous_nodes == tuple(eligible):
                row['edge_turnover'] = float(np.mean(edges != previous_edges))
            previous_edges, previous_nodes = edges, tuple(eligible)
        else:
            previous_edges, previous_nodes = None, None
        residual_history = residual.iloc[max(0, i - window + 1):i + 1]
        nodes = residual_history.columns[residual_history.notna().all() &
                                         (residual_history.std() > 1e-12)]
        if len(residual_history) == window and len(nodes) >= 2:
            rcorr = _correlation(residual_history[nodes].to_numpy(), shrinkage)
            row['residual_concentration'] = float(np.linalg.eigvalsh(rcorr)[-1] / len(nodes))
            weights = np.abs(rcorr)
            np.fill_diagonal(weights, 0.)
            denom = weights.sum(axis=1)
            shocks = residual.loc[date, nodes] / vol.loc[date, nodes]
            peer = (weights @ shocks.to_numpy()) / np.maximum(denom, 1e-12)
            row.loc[row.ticker.isin(nodes), 'residual_peer_shock'] = peer
        pieces.append(row)
    features = pd.concat(pieces, ignore_index=True)
    next_changes = returns.shift(-1).reset_index().melt(id_vars='date', var_name='ticker', value_name='target')
    features = features.merge(next_changes, on=['date', 'ticker'])
    next_dates = pd.Series(returns.index, index=returns.index).shift(-1)
    features['label_available_at'] = features.date.map(next_dates) + pd.Timedelta(hours=23, minutes=59)
    if 'available_at' in data:
        available = data.pivot(index='date', columns='ticker', values='available_at').reindex(returns.index)
        known_labels = available.shift(-1).reset_index().melt(id_vars='date', var_name='ticker', value_name='actual_label_available_at')
        features = features.merge(known_labels, on=['date', 'ticker'])
        features['label_available_at'] = features.pop('actual_label_available_at')
    return features.sort_values(['date', 'ticker']).reset_index(drop=True)
