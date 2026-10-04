#!/usr/bin/env python3
"""Descriptive exact-pre-score / next-session option mark diagnostic.

Historical inspected data: no fitted forecasting model or economic profit claim.
Expiry/OTM observations collapse to one observation per event and strategy.
Run larger score scans on home-pc in detached tmux.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'stat-arb'))
from tools.options_native import _session_age

STRATEGIES = ('stock', 'long_call', 'covered_call', 'protective_put', 'collar', 'cash_secured_put')
MIN_EVENTS = 20
MIN_TICKERS = 3


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


def match_scores(events: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    """Only exact ticker/t_pre View B mahalanobis; ambiguity fails closed."""
    fixed = scores[(scores['view'] == 'B') & (scores['estimator'] == 'mahalanobis')].copy()
    fixed['date'] = pd.to_datetime(fixed['date']).dt.strftime('%Y-%m-%d')
    keys = events[['ticker', 't_pre']].drop_duplicates()
    fixed = fixed.merge(keys, left_on=['ticker', 'date'], right_on=['ticker', 't_pre'], how='inner')
    if fixed.duplicated(['ticker', 'date']).any():
        raise ValueError('duplicate exact pre-event fixed-estimator score')
    fixed = fixed[['ticker', 'date', 'depth', 'pvalue', 'inside']].rename(columns={
        'date': 'score_date', 'depth': 'score_depth', 'pvalue': 'score_pvalue', 'inside': 'score_inside'})
    matched = events.merge(fixed, left_on=['ticker', 't_pre'], right_on=['ticker', 'score_date'], how='left')
    matched['score_present'] = matched['score_date'].notna()
    return matched


def read_scores(path: Path, events: pd.DataFrame) -> pd.DataFrame:
    """Arrow predicate pushdown before materializing the bounded score subset."""
    data = ds.dataset(path, format='parquet')
    date_type = data.schema.field('date').type
    dates = sorted(set(events['t_pre']))
    if pa.types.is_date(date_type):
        dates = [pd.Timestamp(day).date() for day in dates]
    elif pa.types.is_timestamp(date_type):
        dates = [pd.Timestamp(day).to_pydatetime() for day in dates]
    predicate = (ds.field('ticker').isin(sorted(set(events['ticker']))) &
                 ds.field('date').isin(dates) & (ds.field('view') == 'B') &
                 (ds.field('estimator') == 'mahalanobis'))
    return data.to_table(columns=['date', 'ticker', 'view', 'estimator', 'depth', 'pvalue', 'inside'],
                         filter=predicate).to_pandas()


def grade_marks(bars: pd.DataFrame, contracts: list[str], sessions: list[str]) -> tuple[str, int | None]:
    """Grade causal last trades; a future bar can never fill a missing mark."""
    ages = []
    for ticker in contracts:
        available = bars[bars['contract_ticker'] == ticker]
        for session in sessions:
            prior = available[available['session'] <= session]
            if prior.empty:
                return 'missing_last_trade', None
            latest = prior.sort_values('session').iloc[-1]
            if not _finite(latest['close']) or latest['close'] <= 0:
                return 'invalid_last_trade', None
            ages.append(_session_age(str(latest['session']), session))
    age = max(ages) if ages else None
    return ('fresh_last_trade' if age == 0 else 'stale_last_trade'), age


def _valid_quote(row: dict | None, session: str) -> bool:
    if row is None:
        return False
    if not all(_finite(row.get(key)) for key in ('bid', 'ask', 'mid', 'minutes_before_1600')):
        return False
    if not (0 < row['bid'] <= row['ask'] and 0 <= row['minutes_before_1600'] <= 5):
        return False
    if not math.isclose(row['mid'], (row['bid'] + row['ask']) / 2, abs_tol=1e-6):
        return False
    try:
        instant = pd.Timestamp(row['mark_time_utc'])
        return instant.tzinfo is not None and str(instant.tz_convert('America/New_York').date()) == session
    except (ValueError, TypeError, KeyError):
        return False


def _leg_codes(otm: float) -> tuple[str, str]:
    return f'C_U{otm}', f'P_L{otm}'


def _required(strategy: str, otm: float) -> tuple[str, ...]:
    # ATM pair is needed even for single-leg outcomes: it is the normalization
    # denominator and the same-cohort synthetic-stock control in the source.
    call, put = _leg_codes(otm)
    extra = {'stock': (), 'long_call': (), 'covered_call': (call,),
             'protective_put': (put,), 'collar': (call, put), 'cash_secured_put': (put,)}
    return ('C_K', 'P_K') + extra[strategy]


def _mid_changes(strategy: str, otm: float, entry: dict, exit_: dict, strike: float) -> tuple[float, float]:
    """Undiscounted parity marks reproduce the source's synthetic-stock convention."""
    spot_entry = strike + entry['C_K'] - entry['P_K']
    spot_exit = strike + exit_['C_K'] - exit_['P_K']
    if spot_entry <= 0:
        return math.nan, math.nan
    stock = (spot_exit - spot_entry) / spot_entry
    call, put = _leg_codes(otm)
    change = {'stock': lambda: stock,
        'long_call': lambda: (exit_['C_K'] - entry['C_K']) / spot_entry,
        'covered_call': lambda: stock - (exit_[call] - entry[call]) / spot_entry,
        'protective_put': lambda: stock + (exit_[put] - entry[put]) / spot_entry,
        'collar': lambda: stock + (exit_[put] - entry[put] - exit_[call] + entry[call]) / spot_entry,
        'cash_secured_put': lambda: -(exit_[put] - entry[put]) / spot_entry}
    return float(change[strategy]()), float(stock)


def build_rows(events, contracts, bars, quotes, outcomes) -> pd.DataFrame:
    by_event = events.set_index('event_id').to_dict('index')
    by_legs = {(event, bucket): group.set_index('leg_code').to_dict('index')
               for (event, bucket), group in contracts.groupby(['event_id', 'bucket'])}
    if bars.duplicated(['contract_ticker', 'session']).any() or quotes.duplicated(['contract_ticker', 'session']).any():
        raise ValueError('ambiguous contract/session marks')
    by_quote = quotes.set_index(['contract_ticker', 'session']).to_dict('index')
    horizon = pd.to_numeric(outcomes['horizon'], errors='coerce')
    selected = outcomes[(horizon == 1) & (outcomes['entry'] == 'post') &
                        (pd.to_numeric(outcomes['sessions_held'], errors='coerce') == 1)]
    rows = []
    grade_cache = {}
    for source in selected.to_dict('records'):
        event = by_event[source['event_id']]
        if source['entry_date'] != event['t_0'] or _session_age(source['entry_date'], source['exit_date']) != 1:
            raise ValueError('post horizon=1 is not the next exchange session')
        if not event['t_pre'] < event['event_date'] < source['entry_date'] < source['exit_date']:
            raise ValueError('noncausal event/outcome chronology')
        legs = by_legs.get((source['event_id'], source['bucket']), {})
        otm = float(source['otm'])
        for strategy in STRATEGIES:
            codes = _required(strategy, otm)
            complete = all(code in legs for code in codes)
            tickers = [legs[code]['contract_ticker'] for code in codes] if complete else []
            if complete and any(legs[code]['selection_date'] != event['t_pre'] for code in codes):
                raise ValueError('leg was not selected at t_pre')
            cache_key = (tuple(tickers), source['entry_date'], source['exit_date'])
            if cache_key not in grade_cache:
                grade_cache[cache_key] = (grade_marks(bars, tickers, list(cache_key[1:])) if complete
                                         else ('missing_contract', None))
            grade, age = grade_cache[cache_key]
            paired_quotes = {(code, session): by_quote.get((legs[code]['contract_ticker'], session))
                for code in codes for session in (source['entry_date'], source['exit_date'])} if complete else {}
            valid = complete and all(_valid_quote(q, session) for (_, session), q in paired_quotes.items())
            size = valid and all(_finite(q.get('bid_size')) and _finite(q.get('ask_size'))
                                 and q['bid_size'] >= 1 and q['ask_size'] >= 1 for q in paired_quotes.values())
            quote_outcome, quote_stock = math.nan, math.nan
            if valid:
                entry_mid = {code: paired_quotes[(code, source['entry_date'])]['mid'] for code in codes}
                exit_mid = {code: paired_quotes[(code, source['exit_date'])]['mid'] for code in codes}
                quote_outcome, quote_stock = _mid_changes(strategy, otm, entry_mid, exit_mid, legs['C_K']['strike'])
            pre_quotes = {code: by_quote.get((legs[code]['contract_ticker'], event['t_pre']))
                          for code in ('C_K', 'P_K')} if complete else {}
            pre_valid = complete and all(_valid_quote(q, event['t_pre']) for q in pre_quotes.values())
            implied, parity_gap = math.nan, math.nan
            if pre_valid:
                spot = legs['C_K']['spot_pre']
                implied = (pre_quotes['C_K']['mid'] + pre_quotes['P_K']['mid']) / spot
                parity = legs['C_K']['strike'] + pre_quotes['C_K']['mid'] - pre_quotes['P_K']['mid']
                parity_gap = parity / spot - 1
            row = {key: event.get(key) for key in ('ticker', 't_pre', 'score_depth', 'score_pvalue', 'score_present')}
            row.update(event_id=source['event_id'], strategy=strategy, bucket=source['bucket'], otm=otm,
                entry_date=source['entry_date'], exit_date=source['exit_date'], outcome=quote_outcome,
                paired_stock=quote_stock, bar_outcome=source.get(strategy), bar_paired_stock=source.get('stock'),
                mark_grade=grade, max_mark_age_sessions=age, quote_valid=bool(valid),
                quote_size_eligible=bool(size), pre_quote_valid=bool(pre_valid),
                pre_implied_move=implied, pre_parity_spot_gap=parity_gap,
                dte_calendar_days=(pd.Timestamp(legs['C_K']['expiration_date']) - pd.Timestamp(event['t_pre'])).days if complete else None)
            row['primary_eligible'] = bool(event['score_present'] and _finite(event['score_depth'])
                and valid and size and pre_valid and abs(parity_gap) <= .04 and _finite(quote_outcome))
            row['fresh_bar_eligible'] = bool(event['score_present'] and _finite(event['score_depth'])
                and grade == 'fresh_last_trade' and _finite(source.get(strategy)) and _finite(source.get('stock')))
            rows.append(row)
    columns = ['event_id', 'ticker', 't_pre', 'strategy', 'bucket', 'otm', 'outcome', 'paired_stock',
               'score_depth', 'score_pvalue', 'score_present', 'primary_eligible', 'fresh_bar_eligible',
               'mark_grade', 'quote_valid', 'quote_size_eligible']
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=columns)


def collapse_groups(rows: pd.DataFrame, eligibility: str) -> pd.DataFrame:
    selected = rows[rows[eligibility]].copy()
    if selected.empty:
        return pd.DataFrame(columns=['event_id', 'ticker', 'strategy', 'outcome', 'paired_stock',
                                      'score_depth', 'excess_vs_stock'])
    if eligibility == 'fresh_bar_eligible':
        selected['outcome'] = selected['bar_outcome']
        selected['paired_stock'] = selected['bar_paired_stock']
    selected['excess_vs_stock'] = selected['outcome'] - selected['paired_stock']
    keys = ['event_id', 'ticker', 't_pre', 'strategy']
    metrics = [column for column in ('outcome', 'paired_stock', 'excess_vs_stock',
        'score_depth', 'score_pvalue', 'pre_implied_move', 'pre_parity_spot_gap', 'dte_calendar_days')
        if column in selected]
    # First collapse OTM repeats within an expiry, then equally weight expiry
    # medians. More OTM rows must not give an expiry more weight.
    bucket = selected.groupby(keys + ['bucket'], as_index=False)[metrics].median()
    groups = bucket.groupby(keys, as_index=False)[metrics].median()
    counts = bucket.groupby(keys).size().rename('expiry_buckets').reset_index()
    return groups.merge(counts, on=keys)


def _rank_corr(x, y) -> float | None:
    x, y = pd.Series(x, dtype=float), pd.Series(y, dtype=float)
    if x.nunique() < 2 or y.nunique() < 2:
        return None
    value = x.rank().corr(y.rank())
    return float(value) if _finite(value) else None


def association(groups: pd.DataFrame, repetitions: int = 500, seed: int = 20261003) -> dict:
    n = int(groups['event_id'].nunique())
    reasons = []
    if n < MIN_EVENTS:
        reasons.append('insufficient_independent_events')
    if groups['ticker'].nunique() < MIN_TICKERS:
        reasons.append('ticker_concentration')
    if not groups.empty and groups['event_id'].duplicated().any():
        reasons.append('multiple_strategy_rows_passed_to_single_association')
    if not groups.empty and groups['score_depth'].nunique() < 2:
        reasons.append('constant_score')
    result = {'status': 'inconclusive' if reasons else 'exploratory_descriptive',
              'distinct_event_ids': n, 'tickers': int(groups['ticker'].nunique()), 'reasons': reasons,
              'minimum_events': MIN_EVENTS, 'minimum_tickers': MIN_TICKERS}
    if reasons:
        return result
    rng = np.random.default_rng(seed)
    results = {}
    for metric in ('outcome', 'excess_vs_stock', 'absolute_outcome'):
        target = groups['outcome'].abs() if metric == 'absolute_outcome' else groups[metric]
        corr = _rank_corr(groups['score_depth'], target)
        if corr is None:
            results[metric] = {'status': 'inconclusive', 'reason': 'constant_or_invalid_outcome'}
            continue
        draws = []
        for _ in range(repetitions):
            positions = rng.integers(0, len(groups), len(groups))
            value = _rank_corr(groups['score_depth'].iloc[positions], target.iloc[positions])
            if value is not None:
                draws.append(value)
        results[metric] = {'spearman': corr, 'event_block_bootstrap_repetitions': repetitions,
                          'valid_bootstrap_draws': len(draws),
                          'interval_95': list(map(float, np.quantile(draws, [.025, .975]))) if len(draws) >= 100 else None}
    result['correlation'] = results
    result['controls'] = {metric: _rank_corr(groups['score_depth'], groups[metric])
        for metric in ('paired_stock', 'pre_implied_move', 'dte_calendar_days') if metric in groups}
    result['limitation'] = 'Contemporaneous descriptive associations; controls diagnose confounding without identifying causality or holdout forecasting skill.'
    return result


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ingest-dir', type=Path, required=True)
    parser.add_argument('--scores', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New directory; must not exist')
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(f'output already exists: {args.output}')
    manifest_path = args.ingest_dir / 'manifest.json'
    ingest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if ingest.get('stage') != 'gm-options-ingest' or ingest.get('schema_version') != '1.0.0':
        raise ValueError('invalid native options ingest manifest')
    paths = {name: args.ingest_dir / f'{name}.parquet'
             for name in ('events', 'contracts', 'bars', 'outcomes', 'capacity')}
    if (args.ingest_dir / 'quotes.parquet').exists():
        paths['quotes'] = args.ingest_dir / 'quotes.parquet'
    hashes = {'ingest_manifest': _sha(manifest_path), 'scores': _sha(args.scores), 'script': _sha(Path(__file__)),
              'calendar_module': _sha(ROOT / 'stat-arb/tools/options_native.py'),
              'bridge_import': _sha(ROOT / 'stat-arb/tools/options_bridge.py')}
    tables = {}
    for name, path in paths.items():
        hashes[name] = _sha(path)
        if ingest.get('output_hashes', {}).get(path.name) != hashes[name]:
            raise ValueError(f'ingest hash mismatch: {path.name}')
        tables[name] = pq.read_table(path).to_pandas()
    events = tables['events']
    if events['event_id'].duplicated().any():
        raise ValueError('duplicate event identity')
    events = match_scores(events, read_scores(args.scores, events))
    quotes = tables.get('quotes', pd.DataFrame(columns=['contract_ticker', 'session']))
    rows = build_rows(events, tables['contracts'], tables['bars'], quotes, tables['outcomes'])
    primary = collapse_groups(rows, 'primary_eligible')
    fresh_bars = collapse_groups(rows, 'fresh_bar_eligible')
    protocol = {'stage': 'options-matched-descriptive', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_sha256': hashes, 'source_paths': {**{name: str(path.resolve()) for name, path in paths.items()},
            'scores': str(args.scores.resolve())}, 'score_join': 'exact ticker,t_pre; View B; mahalanobis; no date fill',
        'horizon': 1, 'entry': 'post t_0', 'holding_period_sessions': 1,
        'primary_outcome': 'quote-mid strategy mark change per entry undiscounted parity spot',
        'primary_eligibility': 'finite exact score; valid <=5min-to-16:00 quotes and sizes>=1 at both marks; valid pre ATM quotes; pre parity/spot gap<=4%',
        'expiry_collapse': 'OTM median within expiry bucket, then equal median of buckets per event/strategy',
        'bars': 'fresh same-session bars diagnostic separately; prior bars graded stale and excluded from fresh cohort',
        'minimum_events_for_association': MIN_EVENTS, 'minimum_tickers_for_association': MIN_TICKERS,
        'economic_profit_claim': False, 'synthetic_market_data': False,
        'limitations': ['Previously inspected sample; no untouched holdout.',
            'Exact ticker/t_pre date matching does not establish exact first-public or processing timestamps.',
            'CBBO interval mark clock is not original quote-update freshness; carried-forward quotes may be stale.',
            'Distinct event IDs may share releases, tickers or sessions; they are not proven independent.',
            'Minimum 20 events and three tickers is a coverage heuristic, not a statistical power guarantee.',
            'Source stock exposure and denominator use option parity; no carry/dividend correction.',
            'Quotes and displayed sizes describe potential access; no fill, fees, latency, slippage or profitability validation.',
            'Capacity is source context; not a contemporaneous executable sizing decision.',
            'Event block bootstrap does not remove ticker/time dependence or confounding.']}
    associations = {}
    for label, cohort in [('primary_quote_mid', primary), ('fresh_last_trade', fresh_bars)]:
        associations[label] = {strategy: association(cohort[cohort['strategy'] == strategy]) for strategy in STRATEGIES}
    per_event = rows.groupby(['event_id', 'ticker']).agg(raw_strategy_rows=('strategy', 'size'),
        expiry_buckets=('bucket', 'nunique'), primary_strategy_rows=('primary_eligible', 'sum'),
        valid_quote_rows=('quote_valid', 'sum'), quote_size_eligible_rows=('quote_size_eligible', 'sum'))
    coverage = {'events': len(events), 'exact_pre_score_events': int(events['score_present'].sum()),
        'finite_depth_exact_pre_events': int((events['score_present'] & pd.to_numeric(events['score_depth'], errors='coerce').map(_finite)).sum()),
        'missing_exact_pre_events': int((~events['score_present']).sum()),
        'source_outcome_rows': len(tables['outcomes']), 'one_session_post_strategy_rows': len(rows),
        'valid_quote_event_strategy_groups': len(collapse_groups(rows.assign(valid=rows['quote_valid']), 'valid')),
        'quote_size_eligible_event_strategy_groups': len(collapse_groups(rows.assign(valid=rows['quote_size_eligible']), 'valid')),
        'primary_event_strategy_groups': len(primary), 'primary_distinct_event_ids': int(primary['event_id'].nunique()),
        'fresh_bar_event_strategy_groups': len(fresh_bars), 'fresh_bar_distinct_event_ids': int(fresh_bars['event_id'].nunique()),
        'mark_grade_rows': {str(k): int(v) for k, v in rows['mark_grade'].value_counts().items()},
        'source_capacity_rows': len(tables['capacity'])}
    primary_statuses = [item['status'] for item in associations['primary_quote_mid'].values()]
    summary = {'status': 'exploratory_descriptive' if 'exploratory_descriptive' in primary_statuses else 'inconclusive',
        'coverage': coverage, 'forecasts': {'status': 'blocked', 'reason': 'no independent holdout; no forecasting model fitted'},
        'risk': {'status': 'descriptive_only', 'metric': 'score association with absolute next-session mark change'},
        'direct': {'status': 'blocked_for_economic_claim', 'reason': 'mark changes and quoted opportunities do not establish realizable net profit'},
        'associations': associations, 'economic_profit_claim': False}
    args.output.mkdir(parents=True, exist_ok=False)
    _write_json(args.output / 'protocol.json', protocol)
    _write_json(args.output / 'summary.json', summary)
    events.to_csv(args.output / 'matched_events.csv', index=False)
    rows.to_parquet(args.output / 'diagnostic_rows.parquet', index=False)
    primary.to_csv(args.output / 'primary_event_strategy_groups.csv', index=False)
    fresh_bars.to_csv(args.output / 'fresh_bar_event_strategy_groups.csv', index=False)
    per_event.reset_index().to_csv(args.output / 'group_counts_per_event.csv', index=False)
    print(json.dumps({'status': summary['status'], 'coverage': coverage}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
