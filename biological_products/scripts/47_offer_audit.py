"""
47_offer_audit.py - audit numbers for the corrected offering short (trade file from script 45). Same windows as script 42.

Per trade returns here are quote based (gross = mid to mid, net = real fills), see script 45. Prints, for each window: cost sensitivity, how concentrated the profit is, best and worst trades, how much of the profit came
from trades with no offering, and the result by half year. Per trade Sharpe = mean / std x sqrt(252 / 5), same as script 42.
"""
import os, argparse
import numpy as np, pandas as pd
ap = argparse.ArgumentParser()
ap.add_argument('--is_start', default='2025-01-01'); ap.add_argument('--is_end', default='2025-10-31')
ap.add_argument('--os_start', default='2025-11-01'); ap.add_argument('--os_end', default='2026-08-31')
ap.add_argument('--borrow', type=float, default=0.30); ap.add_argument('--version', default='v3')
a = ap.parse_args()
FDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'fds'); k = np.sqrt(252 / 5)
T = pd.read_csv(os.path.join(FDS, f'offer_strategy_trades_{a.version}.csv')); T['d'] = pd.to_datetime(T.signal.astype(str))
sh = lambda x: x.mean() / x.std(ddof=1) * k if len(x) > 2 else float('nan')
W = {'in sample': T[(T.d >= a.is_start) & (T.d <= a.is_end)], 'out of sample': T[(T.d >= a.os_start) & (T.d <= a.os_end)]}
print(f'windows: in sample {a.is_start} to {a.is_end} | out of sample {a.os_start} to {a.os_end}')
print(f'trades {len(T)} | in sample {len(W["in sample"])} | out of sample {len(W["out of sample"])} | in neither window {len(T) - len(W["in sample"]) - len(W["out of sample"])}')
print('\nCOST SENSITIVITY (per trade Sharpe)')
for b in (0, .3, 1.0, 2.0): print(f'  borrow {b*100:3.0f}%/yr: ' + ' | '.join(f'{n} avg {(g.net - b*5/252).mean()*100:+.2f}% Sharpe {sh(g.net - b*5/252):+.2f}' for n, g in W.items()))
print(f'  double bid/ask cost, {a.borrow*100:.0f}% borrow: ' + ' | '.join(f'{n} Sharpe {sh(g.gross - 2*g.cost - a.borrow*5/252):+.2f}' for n, g in W.items()))
for n, g in W.items():
    q = g.assign(n=g.net - a.borrow * 5 / 252).sort_values('n'); x = q.n.sort_values(ascending=False); xg = g.gross.sort_values(ascending=False)
    print(f'\n{n.upper()}: {len(g)} trades in {g.tk.nunique()} companies')
    print(f'  cost per trade: mean {g.cost.mean()*100:.2f}%  median {g.cost.median()*100:.2f}% | entry spread under 2% in {(g.spread_in < .02).sum()} trades')
    print(f'  after costs : sum of trade results {x.sum()*100:+.0f}% | best 5 trades {x.head(5).sum()*100:+.0f}% | Sharpe {sh(x):+.2f} | without best 5 {sh(x.iloc[5:]):+.2f} | without best 10 {sh(x.iloc[10:]):+.2f} | without worst 5 {sh(x.iloc[:-5]):+.2f}')
    print(f'  before costs: sum of trade results {xg.sum()*100:+.0f}% | best 5 trades {xg.head(5).sum()*100:+.0f}% | Sharpe {sh(xg):+.2f} | without best 5 {sh(xg.iloc[5:]):+.2f} | without best 10 {sh(xg.iloc[10:]):+.2f}')
    print('  worst 3: ' + ', '.join(f'{r.tk} {r.signal} {r.n*100:+.0f}%' for r in q.head(3).itertuples()) + ' | best 3: ' + ', '.join(f'{r.tk} {r.signal} {r.n*100:+.0f}%' for r in q.tail(3).itertuples()))
    print(f'  an offering came within 5 days in {g.hit.mean()*100:.0f}% of trades | after-cost average when it came {q[q.hit == 1].n.mean()*100:+.1f}%, when it did not {q[q.hit == 0].n.mean()*100:+.1f}% | share of the profit from trades with no offering {q[q.hit == 0].n.sum() / q.n.sum()*100:.0f}%')
    bt = g.groupby('tk').net.agg(['sum', 'size']).sort_values('sum', ascending=False)
    print('  top companies by summed result: ' + ', '.join(f'{i} {r["sum"]*100:+.0f}% ({int(r["size"])} trades)' for i, r in bt.head(5).iterrows()))
h = T.assign(n=T.net - a.borrow * 5 / 252); h['half'] = h.d.dt.year.astype(str) + np.where(h.d.dt.month <= 6, ' first half', ' second half')
print('\nBY HALF YEAR (after costs, all trades)'); print(h.groupby('half').n.agg(trades='size', avg_pct=lambda v: v.mean() * 100, sum_pct=lambda v: v.sum() * 100).round(2).to_string())
