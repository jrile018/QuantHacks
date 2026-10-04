"""
46_compare_run.py - compare a fresh run of scripts 44, 45, 42 with a saved copy of an earlier run (used by hpg_bundle/run_noleak.sbatch).

--ref is a folder holding the earlier standard_results.csv, standard_portfolio.csv and offer_trades_v2.csv.
Prints the two sets of numbers next to each other and one verdict line.
"""
import os, argparse
import numpy as np, pandas as pd
ap = argparse.ArgumentParser(); ap.add_argument('--ref', required=True); a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__)); REP = os.path.join(here, '..', 'reports'); FDS = os.path.join(here, '..', 'data', 'fds')
pd.set_option('display.width', 250)

n0 = pd.read_csv(os.path.join(a.ref, 'offer_trades_v2.csv')); n1 = pd.read_csv(os.path.join(FDS, 'offer_trades_v2.csv'))
k0, k1 = set(zip(n0.cik, n0.signal)), set(zip(n1.cik, n1.signal))
m = n0.merge(n1, on=['cik', 'signal'], suffixes=('_ref', '_new')); dg = (m.gross_ref - m.gross_new).abs().max() if len(m) else np.nan
print(f'trade list: earlier run {len(k0)} trades, this run {len(k1)} trades, the same in both {len(k0 & k1)} | largest difference in a trade result {dg:.2e}')
same_trades = (k0 == k1) and (dg < 1e-9)

key = ['strategy', 'engine', 'costs', 'window']; num = ['trades', 'avg_trade_pct', 'win_rate', 'sharpe', 'ci_lo', 'ci_hi']
s0 = pd.read_csv(os.path.join(a.ref, 'standard_results.csv')); s1 = pd.read_csv(os.path.join(REP, 'standard_results.csv'))
s = s0.merge(s1, on=key, suffixes=('_ref', '_new'), how='outer')
out = pd.DataFrame({'strategy': s.strategy.str.slice(0, 34), 'costs': s.costs.str.slice(0, 12), 'window': s.window.str.slice(0, 13)})
for c in num: out[c + ' earlier'] = s[c + '_ref'].round(2); out[c + ' now'] = s[c + '_new'].round(2)
print('\nPER TRADE TABLE, earlier run vs this run'); print(out.to_string(index=False))
d_s = (s.sharpe_ref - s.sharpe_new).abs().max(); d_ci = max((s.ci_lo_ref - s.ci_lo_new).abs().max(), (s.ci_hi_ref - s.ci_hi_new).abs().max()); d_n = (s.trades_ref - s.trades_new).abs().max()

p0 = pd.read_csv(os.path.join(a.ref, 'standard_portfolio.csv')); p1 = pd.read_csv(os.path.join(REP, 'standard_portfolio.csv'))
p = p0.merge(p1, on=['strategy', 'window'], suffixes=('_ref', '_new'), how='outer')
print('\nPORTFOLIO TABLE, earlier run vs this run')
print(pd.DataFrame({'strategy': p.strategy, 'window': p.window.str.slice(0, 13), 'trades earlier': p.trades_ref, 'trades now': p.trades_new, 'return% earlier': p.total_return_pct_ref.round(2), 'return% now': p.total_return_pct_new.round(2),
                    'Sharpe earlier': p.sharpe_ref.round(2), 'Sharpe now': p.sharpe_new.round(2), 'drawdown% earlier': p.max_drawdown_pct_ref.round(2), 'drawdown% now': p.max_drawdown_pct_new.round(2)}).to_string(index=False))
d_p = (p.sharpe_ref - p.sharpe_new).abs().max()
print(f'\nlargest difference: trades {d_n:.0f} | per trade Sharpe {d_s:.4f} | portfolio Sharpe {d_p:.4f} | interval ends {d_ci:.4f}')
ok = same_trades and d_n == 0 and d_s < 0.005 and d_p < 0.005
print('VERDICT: ' + ('MATCH. This run reproduces the earlier numbers (same trades, same Sharpe).' if ok else 'DIFFERENT. The numbers of THIS run are printed above; see which rows moved.'))
