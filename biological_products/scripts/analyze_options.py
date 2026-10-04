"""analyze_options.py - after-cost results of buying the at-the-money straddle before each 8-K.
Usage:  python analyze_options.py --data C:\\path\\to\\data      (reads <data>/fds/opt_events.csv and opt_exit.csv)"""
import os, argparse
import numpy as np, pandas as pd
ap = argparse.ArgumentParser(); ap.add_argument('--data', default='../data'); a = ap.parse_args()
fds = os.path.join(a.data, 'fds')
x = pd.read_csv(os.path.join(fds, 'opt_exit.csv')); o = pd.read_csv(os.path.join(fds, 'opt_events.csv'))
flag_cols = [c for c in o.columns if c.startswith('ev_')]
d = x.merge(o[['cik', 'event_date', 'near_call_spread_pct', 'near_put_spread_pct'] + flag_cols], on=['cik', 'event_date'])
g = d[(d.status == 0) & d.pnl_a_bid.notna()].copy()          # both legs quoted at entry and at exit
g['liquid'] = (g.near_call_spread_pct < 0.25) & (g.near_put_spread_pct < 0.25)

def s(v):
    v = v.dropna()
    if len(v) == 0: return 'n=0'
    return f'n={len(v)} mean={v.mean():+.1%} median={v.median():+.1%} win={(v > 0).mean():.0%} se={v.std() / np.sqrt(len(v)):.1%}'

print('events with a full round trip:', len(g), 'of', len(o))
for col, name in (('pnl_a_bid', 'exit event-day close, bid'), ('pnl_a_mid', 'exit event-day close, mid'),
                  ('pnl_b_bid', 'exit next close, bid'), ('pnl_b_mid', 'exit next close, mid')):
    print(f'{name:28s} all    {s(g[col])}')
    print(f'{"":28s} liquid {s(g[g.liquid][col])}')
print('\nby event group (bid-based, event-day exit):')
for c in flag_cols:
    t = g[g[c] == 1]
    if len(t): print(f'  {c:10s} {s(t.pnl_a_bid)}')
g['spread'] = (g.near_call_spread_pct + g.near_put_spread_pct) / 2
print('\nby average spread bucket:')
print(g.groupby(pd.cut(g.spread, [0, .1, .2, .35, .6, 5]), observed=True)
        .agg(n=('pnl_a_bid', 'size'), mean_bid=('pnl_a_bid', 'mean'), mean_mid=('pnl_a_mid', 'mean')).round(3).to_string())
