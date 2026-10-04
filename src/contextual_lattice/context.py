"""At-decision context for exploratory daily lattice comparisons.

SEC acceptance is a public-availability *proxy*, not proven first-public time.
Date-only filings are available no earlier than the next calendar day. The
price-shock catch-up field is exploratory and is never a measured news surprise.
"""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

ET = 'America/New_York'
UTC = 'UTC'
LOOKBACK_DAYS = 5


def _clock(value: object) -> pd.Timestamp:
    if value is None or pd.isna(value) or str(value).strip() == '':
        return pd.NaT
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        return pd.NaT
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize(ET)
    return stamp.tz_convert(UTC)


def _filing_availability(row: Mapping) -> tuple[pd.Timestamp, str]:
    acceptance = row.get('acceptance_datetime') or row.get('acceptanceDateTime') or row.get('accepted_at')
    filing_date = row.get('filing_date') or row.get('filingDate') or row.get('filed')
    conservative_day = _clock(pd.Timestamp(filing_date).normalize() + pd.Timedelta(days=1)) if filing_date and not pd.isna(filing_date) else pd.NaT
    if acceptance and not pd.isna(acceptance):
        accepted = _clock(acceptance)
        return max(accepted, conservative_day) if pd.notna(conservative_day) else accepted, 'acceptance_timestamp_next_calendar_day_proxy'
    if filing_date and not pd.isna(filing_date):
        return conservative_day, 'date_only_next_calendar_day_proxy'
    return pd.NaT, 'missing_filing_clock'


def _filing_rows(filings: pd.DataFrame | None) -> list[dict]:
    if filings is None or filings.empty:
        return []
    rows = []
    for source in filings.to_dict('records'):
        if str(source.get('form', '')).upper() not in {'8-K', '8-K/A'}:
            continue
        raw_tickers = source.get('ticker', source.get('tickers'))
        if raw_tickers is None or pd.isna(raw_tickers):
            continue
        available_at, quality = _filing_availability(source)
        if pd.isna(available_at):
            continue
        for ticker in str(raw_tickers).upper().split(','):
            ticker = ticker.strip()
            if ticker:
                rows.append(dict(ticker=ticker, available_at=available_at,
                                 quality=quality, form=str(source['form']).upper(),
                                 items=source.get('items', None),
                                 accession=source.get('accession', None)))
    return sorted(rows, key=lambda r: (r['ticker'], r['available_at']))


def _coverage(coverage: pd.DataFrame | None) -> dict[str, str]:
    result = {}
    if coverage is None:
        return result
    for row in coverage.to_dict('records'):
        raw = row.get('ticker', row.get('tickers'))
        if raw is None or pd.isna(raw):
            continue
        for ticker in str(raw).upper().split(','):
            if ticker.strip():
                result[ticker.strip()] = str(row.get('status', 'unknown')).lower()
    return result


def _source_rows(source_shocks: pd.DataFrame | None, dates: list[pd.Timestamp]) -> dict[tuple[pd.Timestamp, str], dict]:
    """Use only the prior panel session, never an intraday surprise by accident."""
    if source_shocks is None or source_shocks.empty:
        return {}
    if not {'date', 'ticker', 'shock', 'available_at'} <= set(source_shocks):
        raise ValueError('source_shocks require date,ticker,shock,available_at')
    prior_date = dict(zip(dates[1:], dates[:-1]))
    lookup = {}
    for row in source_shocks.to_dict('records'):
        day = pd.Timestamp(row['date']).normalize()
        ticker = str(row['ticker']).upper()
        if day not in prior_date.values():
            continue
        if not np.isfinite(float(row['shock'])):
            continue
        lookup[(day, ticker)] = dict(shock=float(row['shock']), available_at=_clock(row['available_at']))
    return lookup


def build_context(features: pd.DataFrame, *, filings: pd.DataFrame | None = None,
                  coverage: pd.DataFrame | None = None,
                  source_shocks: pd.DataFrame | None = None,
                  links: pd.DataFrame | None = None, window: int = 63) -> pd.DataFrame:
    """Append causal context without dropping daily opportunities or labels.

    `features` is the multi_market daily panel. `decision_at`, if present, is
    authoritative; otherwise equity-close 16:00 ET is an explicit mark proxy.
    SEC `coverage.status=complete` means only this 8-K inventory is monitored.
    `links` requires a predecision public source, effective interval and hash.
    """
    if window < 3:
        raise ValueError('window must be at least 3')
    required = {'date', 'ticker', 'return_1d', 'volatility', 'beta',
                'market_return', 'residual_peer_shock'}
    if not required <= set(features):
        raise ValueError(f'features missing {sorted(required - set(features))}')
    data = features.copy().reset_index(drop=True)
    data['date'] = pd.to_datetime(data.date).dt.normalize()
    if data.duplicated(['date', 'ticker']).any():
        raise ValueError('duplicate date/ticker feature rows')
    if 'decision_at' in data:
        data['decision_at'] = data.decision_at.map(_clock)
    else:
        data['decision_at'] = data.date.map(lambda day: _clock(day + pd.Timedelta(hours=16)))
    if data.decision_at.isna().any():
        raise ValueError('decision_at cannot be missing')
    dates = sorted(data.date.unique())
    futures = data['root'].notna() if 'root' in data else (data['asset_class'].eq('future') if 'asset_class' in data else pd.Series(False, index=data.index))
    market = data.groupby('date').market_return.first().reindex(dates)
    market_prior_std = market.shift(2).rolling(window, min_periods=window).std()
    market_lag = market.shift(1)
    data['lagged_market_shock'] = data.date.map(market_lag)
    data.loc[futures, 'lagged_market_shock'] = data.loc[futures, 'market_return']
    source_scale = data.date.map(market_prior_std)
    if futures.any():
        source_scale.loc[futures] = data.loc[futures, 'date'].map(market.shift(1).rolling(window, min_periods=window).std())
    data['price_proxy_event'] = (data.lagged_market_shock.abs() >=
                                 2 * source_scale).fillna(False)
    data['price_proxy_kind'] = 'lagged_market_return_not_news_surprise'
    raw_residual = data.return_1d - data.beta * data.market_return
    own_z = raw_residual / data.volatility.replace(0, np.nan)
    data['context_units'] = np.where(futures,
        'futures_prior_residual_scale_approximation', 'equity_volatility_normalized_residual')
    data['own_prior_residual_scale'] = np.nan
    for _, indices in data.loc[futures].groupby('ticker', sort=False).groups.items():
        order = data.loc[list(indices)].sort_values('date').index
        scale = raw_residual.loc[order].shift(1).rolling(window, min_periods=window).std()
        data.loc[order, 'own_prior_residual_scale'] = scale.to_numpy()
        own_z.loc[order] = (raw_residual.loc[order] / scale.replace(0, np.nan)).to_numpy()
    data['peer_reaction_gap'] = own_z - data.residual_peer_shock
    data['peer_gap_prior_std'] = np.nan
    data['prior_peer_stability'] = np.nan
    for _, indices in data.groupby('ticker', sort=False).groups.items():
        order = data.loc[list(indices)].sort_values('date').index
        gaps = data.loc[order, 'peer_reaction_gap']
        data.loc[order, 'peer_gap_prior_std'] = gaps.shift(1).rolling(window, min_periods=window).std().to_numpy()
        own = own_z.loc[order]
        peer = data.loc[order, 'residual_peer_shock']
        data.loc[order, 'prior_peer_stability'] = own.shift(1).rolling(window, min_periods=window).corr(peer.shift(1)).to_numpy()
    data['reversal_event'] = (data.peer_gap_prior_std.gt(0) &
                              data.peer_reaction_gap.abs().ge(2 * data.peer_gap_prior_std)).fillna(False)
    monitoring = _coverage(coverage)
    indexed_filings = {}
    for filing in _filing_rows(filings):
        indexed_filings.setdefault(filing['ticker'], []).append(filing)
    data['filing_monitoring_status'] = data.ticker.map(monitoring).fillna('unknown')
    data['known_8k'] = pd.Series(pd.NA, index=data.index, dtype='boolean')
    for name in ['known_8k_age_days', 'known_8k_form', 'known_8k_items',
                 'filing_available_at', 'filing_clock_quality', 'known_8k_accession']:
        data[name] = pd.NA
    for idx, row in data.iterrows():
        if row.filing_monitoring_status != 'complete':
            continue
        known = [item for item in indexed_filings.get(str(row.ticker).upper(), ())
                 if item['available_at'] <= row.decision_at]
        latest = known[-1] if known else None
        age = ((row.decision_at - latest['available_at']).total_seconds() / 86400) if latest else np.nan
        data.at[idx, 'known_8k'] = bool(latest and age <= LOOKBACK_DAYS)
        if latest:
            data.at[idx, 'known_8k_age_days'] = age
            data.at[idx, 'known_8k_form'] = latest['form']
            data.at[idx, 'known_8k_items'] = latest['items']
            data.at[idx, 'filing_available_at'] = latest['available_at']
            data.at[idx, 'filing_clock_quality'] = latest['quality']
            data.at[idx, 'known_8k_accession'] = latest['accession']
    data['filing_context_available'] = data.filing_monitoring_status.eq('complete')
    data['filing_context_abstain'] = ~data.filing_context_available
    data['filing_abstention_reason'] = np.where(data.filing_context_abstain,
        'filing_monitoring_unknown', '')
    data['price_context_available'] = data.peer_gap_prior_std.gt(0) & data.peer_reaction_gap.notna()
    data['context_available'] = data.price_context_available
    data['context_reason'] = np.select(
        [data.peer_gap_prior_std.isna() | data.peer_gap_prior_std.eq(0),
         data.peer_reaction_gap.isna()],
        ['insufficient_prior_gap_history', 'missing_price_context'],
        default='at_decision_price_context')
    data['catchup_eligibility'] = 'blocked'
    data['catchup_reason'] = 'qualified_link_or_prior_source_shock_unavailable'
    data['source_shock_proxy'] = np.nan
    data['economic_link_sign'] = np.nan
    data['economic_link_source'] = pd.NA
    data['economic_link_sha256'] = pd.NA
    data['economic_link_public_at'] = pd.Series(pd.NaT, index=data.index, dtype='datetime64[ns, UTC]')
    data['economic_link_effective_from'] = pd.NaT
    data['economic_link_effective_to'] = pd.NaT
    data['source_shock_date'] = pd.NaT
    data['source_shock_available_at'] = pd.Series(pd.NaT, index=data.index, dtype='datetime64[ns, UTC]')
    data['source_shock_prior_std'] = np.nan
    data['source_price_proxy_event'] = False
    data['prior_source_relationship'] = np.nan
    sources = _source_rows(source_shocks, dates)
    if links is not None and not links.empty:
        prior_date = dict(zip(dates[1:], dates[:-1]))
        for link in links.to_dict('records'):
            needed = ('source_ticker', 'target_ticker', 'sign', 'effective_from',
                      'effective_to', 'public_at', 'sha256')
            if any(pd.isna(link.get(key)) or str(link.get(key)).strip() == '' for key in needed):
                continue
            source_ref = link.get('source_url') or link.get('source_path')
            if not source_ref or not np.isfinite(float(link['sign'])) or float(link['sign']) == 0:
                continue
            if len(str(link['sha256'])) != 64:
                continue
            first = pd.Timestamp(link['effective_from']).normalize()
            last = pd.Timestamp(link['effective_to']).normalize()
            public_at = _clock(link['public_at'])
            source_series = pd.Series({day: sources[(day, str(link['source_ticker']).upper())]['shock']
                                       for day in dates if (day, str(link['source_ticker']).upper()) in sources},
                                      dtype=float).reindex(dates)
            source_std = source_series.shift(1).rolling(window, min_periods=window).std()
            source_prior = source_series.shift(1)
            target_mask = data.ticker.eq(link['target_ticker'])
            response = pd.Series(own_z[target_mask].to_numpy(), index=data.loc[target_mask, 'date']).reindex(dates)
            for idx in data.index[data.ticker.eq(link['target_ticker']) & data.date.between(first, last, inclusive='left')]:
                row = data.loc[idx]
                source = sources.get((prior_date.get(row.date), str(link['source_ticker']).upper()))
                if source is None or pd.isna(source['available_at']) or source['available_at'] > row.decision_at:
                    continue
                if pd.isna(public_at) or public_at > row.decision_at:
                    continue
                data.at[idx, 'source_shock_proxy'] = source['shock']
                data.at[idx, 'source_shock_date'] = prior_date.get(row.date)
                data.at[idx, 'source_shock_available_at'] = source['available_at']
                data.at[idx, 'economic_link_sign'] = np.sign(float(link['sign']))
                data.at[idx, 'economic_link_source'] = source_ref
                data.at[idx, 'economic_link_sha256'] = link['sha256']
                data.at[idx, 'economic_link_public_at'] = public_at
                data.at[idx, 'economic_link_effective_from'] = first
                data.at[idx, 'economic_link_effective_to'] = last
                prior_day = prior_date.get(row.date)
                source_scale = source_std.get(prior_day, np.nan)
                data.at[idx, 'source_shock_prior_std'] = source_scale
                event = bool(np.isfinite(source_scale) and source_scale > 0 and
                             abs(source['shock']) >= 2 * source_scale)
                data.at[idx, 'source_price_proxy_event'] = event
                prior_days = [day for day in dates if day < row.date][-window:]
                x = source_prior.reindex(prior_days)
                y = response.reindex(prior_days)
                if len(prior_days) != window or x.isna().any() or y.isna().any():
                    data.at[idx, 'catchup_reason'] = 'insufficient_prior_relationship'
                    continue
                relationship = x.corr(y)
                data.at[idx, 'prior_source_relationship'] = relationship
                half = window // 2
                first_corr = x.iloc[:half].corr(y.iloc[:half])
                second_corr = x.iloc[half:].corr(y.iloc[half:])
                signed = np.sign(float(link['sign']))
                if not (np.isfinite(relationship) and signed * relationship >= .2 and
                        np.isfinite(first_corr) and signed * first_corr >= .1 and
                        np.isfinite(second_corr) and signed * second_corr >= .1):
                    data.at[idx, 'catchup_reason'] = 'prior_signed_relationship_unstable'
                elif not event:
                    data.at[idx, 'catchup_reason'] = 'source_price_proxy_below_fixed_threshold'
                else:
                    data.at[idx, 'catchup_eligibility'] = 'price_proxy_exploratory'
                    data.at[idx, 'catchup_reason'] = 'actual_news_surprise_unavailable'
    return data
