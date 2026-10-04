"""Offline, quarterly long-only feature research. Never sends orders.

Select using only formation-date information; stop valuation on missing held bars.
No forward-return labels, current membership gates, or test-based parameter search.
"""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent
OUT = BASE.parent / 'processed/feature_strategies'
SPECS = {
    'operating_profitability': [('q_operating_margin', 1)],
    'cash_flow_quality': [('q_fcf_physical_capex_margin', 1)],
    'revenue_growth': [('rev_growth_yoy_q', 1)],
    'quality_growth': [('q_operating_margin', 1), ('rev_growth_yoy_q', 1), ('q_sbc_pct_rev', -1)],
    'capital_efficiency': [('q_fcf_physical_capex_margin', 1), ('capex_cash_ttm_to_revenue', -1)],
    'capex_expansion': [('capex_cash_ttm_growth_yoy', 1)],
    'lease_discipline': [('operating_lease_liability_growth_yoy', -1)],
    'momentum_6m': [('momentum_6m', 1)],
}


def score_rows(frame, terms):
    """Require every constituent, then average cross-sectional percentile ranks."""
    values = frame[[x for x, _ in terms]].replace([np.inf, -np.inf], np.nan)
    good = values.dropna()
    score = pd.Series(np.nan, index=frame.index, dtype=float)
    if len(good) < 25:
        return score
    ranks = [good[col].rank(pct=True, method='average') * sign for col, sign in terms]
    score.loc[good.index] = pd.concat(ranks, axis=1).mean(axis=1)
    return score


def replay(close, identity, dates, tickers, bps):
    """Fixed shares, full liquidation at scheduled exit. Missing holdings invalidate.

    One dollar initial cash; dividends and cash interest intentionally excluded.
    """
    if not tickers:
        return {'status': 'insufficient_signal_coverage'}, pd.DataFrame()
    marks = close.reindex(index=dates, columns=tickers)
    ids = identity.reindex(index=dates, columns=tickers)
    valid = marks.notna() & (marks > 0) & ids.eq('provider_issuer_and_share_identity_match')
    if not valid.all().all():
        bad = [(str(d.date()), t) for d, row in valid.iterrows() for t in tickers if not row[t]]
        return {'status': 'unresolved_held_price_or_identity', 'first_problem': str(bad[0]),
                'problem_cells': len(bad)}, pd.DataFrame()
    cost = bps / 10000
    # Cost-inclusive fully invested entry; shares are held unchanged.
    invested = 1 / (1 + cost)
    shares = invested / len(tickers) / marks.iloc[0]
    equity = marks.mul(shares).sum(axis=1)
    equity.iloc[-1] *= (1 - cost)
    returns = equity.pct_change()
    returns.iloc[0] = equity.iloc[0] - 1
    wealth = np.r_[1., equity.to_numpy()]
    result = {'status': 'resolved_price_only', 'net_return': float(equity.iloc[-1] - 1),
              'max_drawdown': float((wealth / np.maximum.accumulate(wealth) - 1).min()),
              'entry_cost': 1 - invested, 'exit_cost': float(equity.iloc[-1] / (1-cost)*cost)}
    daily = pd.DataFrame({'date': dates, 'net_return': returns.to_numpy(), 'equity': equity.to_numpy()})
    return result, daily


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inputs = [BASE/'final/feature_matrix_backtest.csv',
              BASE/'extracts/company_coverage/daily_bars_reviewed.csv',
              BASE/'output/factor_returns_daily.csv']
    matrix = pd.read_csv(inputs[0], dtype={'cik':str}, low_memory=False)
    bars = pd.read_csv(inputs[1], dtype={'cik':str}, parse_dates=['date'], low_memory=False)
    factors = pd.read_csv(inputs[2], parse_dates=['date']).set_index('date').sort_index()
    assert matrix.cik.nunique() == 168
    assert not matrix.duplicated(['cik', 'quarter']).any()
    assert not bars.duplicated(['ticker', 'date']).any()
    calendar = factors.index
    close = bars.pivot(index='date', columns='ticker', values='close').reindex(calendar)
    volume = bars.pivot(index='date', columns='ticker', values='volume').reindex_like(close)
    identity = bars.pivot(index='date', columns='ticker', values='price_identity_status').reindex_like(close)
    records, holdings, daily_rows, eligibility = [], [], [], []
    for quarter, original in matrix.groupby('quarter', sort=True):
        period = pd.Period(quarter, freq='Q')
        cutoff = period.end_time.normalize()
        if cutoff < pd.Timestamp('2023-12-31'):
            continue
        entry_dates = calendar[calendar > cutoff]
        exit_dates = calendar[calendar > (period + 1).end_time.normalize()]
        if not len(entry_dates) or not len(exit_dates):
            continue  # Only fully ended scheduled holding periods, never partial extrapolation.
        entry, exit_date = entry_dates[0], exit_dates[0]
        phase = 'selection_2024' if entry.year == 2024 else 'chronological_test_2025_2026'
        dates = calendar[(calendar >= entry) & (calendar <= exit_date)]
        hist = close.loc[close.index <= cutoff].tail(60)
        dollar = (hist * volume.reindex(hist.index)).median()
        last = hist.iloc[-1]
        idlast = identity.loc[identity.index <= cutoff].iloc[-1]
        allowed = (hist.count() >= 55) & (last >= 3) & (dollar >= 1e6) & idlast.eq('provider_issuer_and_share_identity_match')
        frame = original.set_index('ticker').copy()
        frame['eligible'] = allowed.reindex(frame.index).fillna(False)
        for t, row in frame.iterrows():
            eligibility.append({'quarter':quarter, 'ticker':t, 'eligible':bool(row.eligible),
                                'trailing_bars':int(hist[t].count()) if t in hist else 0,
                                'median_dollar_volume':dollar.get(t, np.nan)})
        frame = frame[frame.eligible].copy()
        old = close.loc[close.index <= cutoff].tail(127)
        mom = old.iloc[-1] / old.iloc[0] - 1
        mom[old.count() < 127] = np.nan
        frame['momentum_6m'] = mom.reindex(frame.index)
        for strategy, terms in {'equal_weight_universe':[], **SPECS}.items():
            if terms:
                scores = score_rows(frame, terms)
                pool = scores.dropna()
                # Whole tied groups at the quintile boundary; no arbitrary ticker tie break.
                n = max(1, math.ceil(len(pool) * .2))
                threshold = pool.nlargest(n).min() if len(pool) else np.nan
                chosen = sorted(pool[pool >= threshold].index)
                if pool.nunique() < 5:
                    chosen = []
            else:
                pool = pd.Series(0., index=frame.index)
                chosen = sorted(pool.index)
            for t in chosen:
                holdings.append({'quarter':quarter, 'entry_date':entry, 'exit_date':exit_date,
                                 'phase':phase, 'strategy':strategy, 'ticker':t,
                                 'weight':1/len(chosen), 'formation_score':float(pool[t])})
            for scenario, bps in [('base_10bp',10), ('stress_50bp',50)]:
                common = {'quarter':quarter, 'phase':phase, 'entry_date':entry, 'exit_date':exit_date,
                          'strategy':strategy, 'scenario':scenario, 'pool_count':len(pool),
                          'holdings_count':len(chosen)}
                result, daily = replay(close, identity, dates, chosen, bps)
                matched, _ = replay(close, identity, dates, sorted(pool.index), bps)
                market = np.prod(1+(factors.loc[dates[1:], 'mkt_rf']+factors.loc[dates[1:], 'rf'])/100)-1
                result['market_total_return_comparator'] = float(market)
                result['matched_pool_status'] = matched['status']
                result['matched_pool_net_return'] = matched.get('net_return', np.nan)
                result['excess_vs_matched_pool'] = result.get('net_return',np.nan)-matched.get('net_return',np.nan)
                records.append(common | result)
                if len(daily):
                    daily_rows.append(daily.assign(**common))
    results = pd.DataFrame(records)
    results.to_csv(OUT/'quarterly_results.csv', index=False)
    pd.DataFrame(holdings).to_csv(OUT/'holdings.csv', index=False)
    pd.DataFrame(eligibility).to_csv(OUT/'formation_eligibility.csv', index=False)
    daily_all = pd.concat(daily_rows, ignore_index=True)
    daily_all.to_csv(OUT/'daily_resolved_cohorts.csv', index=False)
    summaries = []
    for (phase, strategy, scenario), group in results.groupby(['phase','strategy','scenario']):
        resolved = group[group.status == 'resolved_price_only']
        complete = len(resolved) == len(group)
        valid_excess = resolved.excess_vs_matched_pool.dropna()
        total = np.prod(1+resolved.net_return)-1 if complete else np.nan
        drawdown = np.nan
        if complete:
            path = daily_all[(daily_all.phase==phase) & (daily_all.strategy==strategy) &
                             (daily_all.scenario==scenario)].sort_values('date')
            daily_returns = path.groupby('date').net_return.apply(lambda r: np.prod(1+r)-1)
            wealth = np.r_[1., np.cumprod(1+daily_returns)]
            np.testing.assert_allclose(wealth[-1]-1, total, atol=1e-10)
            drawdown = float((wealth/np.maximum.accumulate(wealth)-1).min())
        summaries.append({'phase':phase, 'strategy':strategy, 'scenario':scenario,
                          'scheduled_quarters':len(group), 'resolved_quarters':len(resolved),
                          'complete_path':complete, 'cumulative_net_price_return':total,
                          'daily_mark_max_drawdown':drawdown,
                          'mean_resolved_quarter_return':resolved.net_return.mean(),
                          'matched_comparison_quarters':len(valid_excess),
                          'mean_excess_vs_matched_pool':valid_excess.mean(),
                          'positive_resolved_quarters':int((resolved.net_return>0).sum()),
                          'worst_resolved_quarter':resolved.net_return.min()})
    summary = pd.DataFrame(summaries)
    summary.to_csv(OUT/'strategy_summary.csv', index=False)
    # Choose once from the selection year, retain every later result including failures.
    selection = summary[(summary.phase=='selection_2024') & (summary.scenario=='base_10bp') &
                        summary.complete_path & (summary.strategy!='equal_weight_universe')]
    winner = None if selection.empty else selection.sort_values(['cumulative_net_price_return','strategy'],ascending=[False,True]).iloc[0].strategy
    manifest = {'input_sha256':{str(p.relative_to(BASE.parents[1])):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                'selected_using_2024_only':winner, 'strategy_definitions':SPECS,
                'formation_rule':'quarter-end features; prior 60 factor sessions >=55 bars, last close >=$3, median dollar volume >=$1m, provider identity match',
                'execution_assumption':'first factor-calendar close strictly after quarter-end; liquidate next quarterly boundary close; fixed shares',
                'missing_held_marks':'invalidate full cohort; never silently drop or impute terminal return',
                'return_definition':'price only, net assumed execution costs; zero cash interest; dividends excluded',
                'selection':'2024 trading quarters; fixed candidate menu and top quintile; highest completed 2024 cumulative net price return',
                'test':'2025 and mature 2026 quarters; previously inspected historical data, NOT a fresh holdout',
                'macro_features':'PJM common across issuers; FERC/guidance too sparse or unverified for these rankings',
                'universe':'fixed current 168 issuers, survivors and price-identity limitations remain',
                'base_bps_per_side':10, 'stress_bps_per_side':50}
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    fig, ax = plt.subplots(figsize=(11,6))
    for strategy, group in results[(results.phase=='chronological_test_2025_2026') &
                                  (results.scenario=='base_10bp')].groupby('strategy'):
        if (group.status == 'resolved_price_only').all():
            path = daily_all[(daily_all.phase=='chronological_test_2025_2026') &
                             (daily_all.scenario=='base_10bp') & (daily_all.strategy==strategy)]
            daily_returns = path.groupby('date').net_return.apply(lambda r: np.prod(1+r)-1)
            ax.plot(daily_returns.index, np.cumprod(1+daily_returns), label=strategy)
    ax.set(title='Completed quarterly price-return paths (costs included)', ylabel='Growth of $1; dividends excluded')
    ax.grid(alpha=.25)
    if ax.lines: ax.legend(fontsize=8)
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(OUT/'completed_paths.png', dpi=160); plt.close(fig)
    lines = ['# Feature strategy backtest research', '',
             'Eight fixed long-only hypotheses plus an equal-weight benchmark were formed across the 168-issuer universe. Holdings use formation-date liquidity and identity checks, not future label availability or current active status.', '',
             f'Selected using completed 2024 quarters only: **{winner or "none (no complete selection path)"}**. All candidates and later failed cohorts are retained.', '',
             'Features are frozen at quarter-end. Buy at the first subsequent factor-calendar close, hold fixed shares until the next quarterly entry boundary, then sell. Single-feature and composite scores select the top quintile, including boundary ties; composites require all inputs. Fewer than 25 usable scores or fewer than five distinct scores produce no trade. Base costs are 10bp per side; stress costs are 50bp per side. These are assumed fills, not verified executable prices.', '',
             'These are price-return tests with dividends excluded and zero cash interest. The separate market comparator includes dividends and is not a like-for-like alpha estimate. Matched-pool comparison is price-only with the same cost assumptions. Capital efficiency uses physical CapEx only; capitalized software can still affect the interpretation of cash flow.', '',
             'Eligibility reduces the tradable research basket to 98–112 issuers per formation quarter; the 168-company grid is the screening universe, not a promise of 168 tradable instruments. Six mature chronological test quarters run from January 2, 2025 to July 1, 2026. Later periods lack a full subsequent quarterly boundary on the stored factor calendar.', '',
             'A missing held price or unqualified identity invalidates the entire quarterly cohort. No terminal liquidation price is fabricated. Cumulative results exist only for complete paths; resolved-quarter averages for incomplete paths are descriptive and must not be ranked as complete strategies. No forward-availability filter is applied to holdings.', '',
             'Historical membership, corporate actions, cash dividends, actual liquidity/costs and identity remain incompletely certified. Earlier research inspected later dates; chronological evaluation is not a fresh holdout. There are only six mature test quarters, so no reliable significance claim or deployable edge follows. Previously completed mean-reversion research also did not establish a reliable edge.', '',
             '## Summary', '',
             '| Phase | Strategy | Costs | Resolved / scheduled | Cumulative net price return | Daily maximum drawdown | Mean resolved quarter |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for r in summary.to_dict('records'):
        fmt = lambda v: 'unresolved' if pd.isna(v) else f'{v:.2%}'
        lines.append(f"| {r['phase']} | {r['strategy']} | {r['scenario']} | {r['resolved_quarters']}/{r['scheduled_quarters']} | {fmt(r['cumulative_net_price_return'])} | {fmt(r['daily_mark_max_drawdown'])} | {fmt(r['mean_resolved_quarter_return'])} |")
    lines += ['', '## Reproduce', '', 'Run `venv/Scripts/python.exe data/packaged_software/backtest_feature_strategies.py`.', '',
              'See holdings.csv for positions and weights, formation_eligibility.csv for all 168 issuers each quarter, quarterly_results.csv for failures and matching comparisons, strategy_summary.csv for every candidate/scenario, and manifest.json for assumptions and input hashes. The feature matrix is unchanged.']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(summary[summary.phase=='chronological_test_2025_2026'].to_string(index=False))
    print('Selected from 2024:', winner)


if __name__ == '__main__':
    main()
