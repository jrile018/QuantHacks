"""
40_offer_strategy_pnl.py - Sharpe ratio, 95% interval and audit for the OFFERING strategy.

Strategy: each day a model trained only on the past flags the 2% of liquid company-days most likely to announce a stock offering
within 5 market days (script 21). We short the flagged stock at the next open, buy XBI with the same dollars, and close both at the
close 5 market days after the signal. One position per company at a time.
Costs: the REAL bid/ask cost measured for each trade (script 22: sell at the bid, buy back at the ask, both legs) plus a borrow fee.
Every trade is out of sample for the model (walk forward from 2025-01). Choices made after seeing results: the 5 day hold
(1, 3 and 5 were looked at) and the $1 minimum price. Both are flagged in the output.
Input : data/fds/stock_trades_real_adj.csv, data/raw/prices.csv
Usage : python 40_offer_strategy_pnl.py
"""
import os, argparse
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--slot', type=float, default=0.20, help='share of capital per trade (about 2 trades are open on an average day)')
ap.add_argument('--borrow', type=float, default=0.30, help='annual borrow fee on the short (assumption)')
ap.add_argument('--boot', type=int, default=5000)
a = ap.parse_args()
RAW = os.path.join(a.data, 'raw'); FDS = os.path.join(a.data, 'fds')
rng = np.random.default_rng(11)

T0 = pd.read_csv(os.path.join(FDS, 'stock_trades_real_adj.csv'))
T0['e'] = pd.to_datetime(T0.entry.astype(str)); T0['x'] = pd.to_datetime(T0.exit.astype(str)); T0['sig'] = pd.to_datetime(T0.signal.astype(str))
P = pd.read_csv(os.path.join(RAW, 'prices.csv'), usecols=['ticker', 'date', 'open', 'close']); P['date'] = pd.to_datetime(P.date)
O = P.pivot(index='date', columns='ticker', values='open'); C = P.pivot(index='date', columns='ticker', values='close')
cal = O.index[O['XBI'].notna()]; O = O.loc[cal]; C = C.loc[cal]; pos = {d: i for i, d in enumerate(cal)}

def leg(tk, i, j):
    c = C[tk].iloc[i:j + 1].values.astype(float); r = c / np.concatenate([[O[tk].iat[i]], c[:-1]]) - 1
    return np.where(np.isfinite(r), r, 0.0)
def build(T, borrow=a.borrow, cost_mult=1.0, slot=a.slot, drop=None):
    T = T.reset_index(drop=True)
    if drop is not None: T = T[~T.index.isin(drop)].reset_index(drop=True)
    ii = T.e.map(pos).astype(int).values; jj = T.x.map(pos).astype(int).values
    first, last = ii.min(), jj.max(); G = np.zeros((len(T), last - first + 1)); N = np.zeros_like(G); OP = np.zeros_like(G, dtype=bool)
    for k in range(len(T)):
        g = -(leg(T.tk[k], ii[k], jj[k]) - leg('XBI', ii[k], jj[k]))          # short the stock, long XBI
        c = np.zeros_like(g); c[0] += T.cost[k] * cost_mult / 2; c[-1] += T.cost[k] * cost_mult / 2; c += borrow / 252
        sl = slice(ii[k] - first, jj[k] - first + 1); G[k, sl] = g; N[k, sl] = g - c; OP[k, sl] = True
    nopen = OP.sum(axis=0); w = np.minimum(slot, 1.0 / np.maximum(nopen, 1))
    D = pd.DataFrame({'date': cal[first:last + 1], 'n_open': nopen, 'gross': G.sum(axis=0) * w, 'net': N.sum(axis=0) * w})
    T = T.assign(contrib=(N * w).sum(axis=1))
    return T, D
def sharpe(x): x = np.asarray(x); return x.mean() / x.std(ddof=1) * np.sqrt(252) if x.std(ddof=1) > 0 else np.nan
def ci(x, block=10, B=a.boot):
    x = np.asarray(x); m = len(x); out = np.empty(B)
    for b in range(B):
        idx = np.empty(m, dtype=int); t = 0
        while t < m:
            st = rng.integers(0, m); L = min(rng.geometric(1.0 / block), m - t); idx[t:t + L] = (st + np.arange(L)) % m; t += L
        out[b] = sharpe(x[idx])
    return np.nanpercentile(out, 2.5), np.nanpercentile(out, 97.5), float(np.nanmean(out <= 0))
def line(lab, T, D, col='net'):
    x = D[col].values; eq = np.cumprod(1 + x); yrs = len(x) / 252; lo, hi, p0 = ci(x)
    print(f'  {lab:44s} trades {len(T):3d} | ann return {(eq[-1]**(1/yrs)-1)*100:+6.1f}% | vol {x.std(ddof=1)*np.sqrt(252)*100:5.1f}% | Sharpe {sharpe(x):+5.2f}  95% [{lo:+.2f}, {hi:+.2f}] | P(Sharpe<=0) {p0:.2f} | max drawdown {(eq/np.maximum.accumulate(eq)-1).min()*100:5.1f}%')

ALL = T0.copy(); MAIN = T0[T0.px_in >= 1].copy(); TIGHT = T0[(T0.px_in >= 1) & (T0.spread_in < 0.02)].copy()
print(f'OFFERING STRATEGY | {T0.e.min().date()} to {T0.x.max().date()} | capital per trade {a.slot*100:.0f}% | borrow fee assumed {a.borrow*100:.0f}%/yr | real bid/ask costs per trade')
print('\nMAIN RESULTS (after real trading costs and the borrow fee)')
Tm, Dm = build(MAIN); line('price >= $1 (main rule)', Tm, Dm)
Ta, Da = build(ALL); line('all flagged trades', Ta, Da)
Tt, Dt = build(TIGHT); line('price >= $1 and entry spread < 2%', Tt, Dt)
print('before any costs:'); line('price >= $1, no costs', Tm, Dm, 'gross')
print(f'average trades open per day {Dm.n_open.mean():.1f} | days with no position {(Dm.n_open == 0).mean():.0%}')

print('\nAUDIT (main rule)')
gap = (Tm.e - Tm.sig).dt.days
print(f'a. timing: every trade enters after the signal day: {bool((gap >= 1).all())} (min {gap.min()} day, max {gap.max()}) | the model was trained only on days before each test quarter (7 day gap)')
tot = Tm.contrib.sum()
def brk(lab, key):
    g = Tm.groupby(key).agg(trades=('net', 'size'), avg_net=('net', 'mean'), median_net=('net', 'median'), win=('net', lambda s: (s > 0).mean()), share=('contrib', lambda s: s.sum() / tot))
    g[['avg_net', 'median_net']] = (g[['avg_net', 'median_net']] * 100).round(1); g[['win', 'share']] = g[['win', 'share']].round(2)
    print(f'   by {lab}:'); print('   ' + g.to_string().replace('\n', '\n   '))
print('b. where the profit comes from (per trade after bid/ask costs, before borrow)')
brk('offering really came within 5 days (1 = yes)', 'hit'); brk('half year', Tm.e.dt.year.astype(str) + 'H' + ((Tm.e.dt.month > 6) + 1).astype(str))
brk('entry price', np.where(Tm.px_in < 3, '$1 to $3', np.where(Tm.px_in < 10, '$3 to $10', 'over $10')))
s = Tm.sort_values('net'); f = lambda d: d[['tk', 'entry', 'px_in', 'hit', 'net']].assign(net=lambda q: (q.net * 100).round(1)).to_string(index=False)
print('   6 worst trades:'); print(f(s.head(6))); print('   6 best trades:'); print(f(s.tail(6)))
best5 = Tm.sort_values('contrib').tail(5).index; _, D5 = build(MAIN, drop=best5)
print(f'   Sharpe with the 5 most profitable trades removed: {sharpe(D5.net):+.2f} (was {sharpe(Dm.net):+.2f})')
byc = Tm.groupby('tk').contrib.sum().sort_values(ascending=False); p = byc[byc > 0]
print(f'c. concentration: companies {len(byc)} | profitable {int((byc>0).sum())} | top {int((p.cumsum() < 0.5*p.sum()).sum())+1} make half the gains | top 5: {", ".join(f"{t} {v/tot:+.0%}" for t, v in byc.head(5).items())}')
print('d. costs: Sharpe at borrow fee', ' | '.join(f'{b*100:.0f}%: {sharpe(build(MAIN, borrow=b)[1].net):+.2f}' for b in (0, .15, .30, .60, 1.0, 2.0)))
print('   Sharpe if bid/ask costs were', ' | '.join(f'{m:.1f}x: {sharpe(build(MAIN, cost_mult=m)[1].net):+.2f}' for m in (0, 1, 1.5, 2, 3)))
_mo = Dm.groupby(Dm.date.dt.to_period('M')).net.sum()
print(f'e. monthly: {(_mo > 0).mean():.0%} of months positive ({len(_mo)} months)')
Tm.to_csv(os.path.join(FDS, 'offer_strategy_trades.csv'), index=False); Dm.to_csv(os.path.join(FDS, 'offer_strategy_daily.csv'), index=False)
