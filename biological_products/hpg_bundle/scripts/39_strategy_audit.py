"""
39_strategy_audit.py - audit of the trial-stage strategy: why is each number what it is?

Same rules as 38_strategy_pnl.py (it must reproduce that script's Sharpe). Prints:
  a. timing check        b. where the profit comes from      c. concentration
  d. cost sensitivity    e. setting sensitivity (design only) f. data problems
Usage: python 39_strategy_audit.py                                   (design half)
       python 39_strategy_audit.py --set holdout --confirm_holdout   (one time; logged)
"""
import os, argparse, datetime as dt
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--set', default='design', choices=['design', 'holdout'])
ap.add_argument('--confirm_holdout', action='store_true')
ap.add_argument('--boot', type=int, default=3000)
a = ap.parse_args()
if a.set == 'holdout' and not a.confirm_holdout: raise SystemExit('holdout is a one time test: add --confirm_holdout')
RAW = os.path.join(a.data, 'raw'); FDS = os.path.join(a.data, 'fds')
UP = ['to_active_not_recruiting', 'pc_reached', 'enroll_actual']; DN = ['sites_up', 'enroll_target_up', 'to_recruiting']

E0 = pd.read_csv(os.path.join(FDS, 'ct_event_study.csv')); E0['ed'] = pd.to_datetime(E0.ed); E0['ud'] = pd.to_datetime(E0.ud)
P = pd.read_csv(os.path.join(RAW, 'prices.csv'), usecols=['ticker', 'date', 'open', 'close']); P['date'] = pd.to_datetime(P.date)
O = P.pivot(index='date', columns='ticker', values='open'); C = P.pivot(index='date', columns='ticker', values='close')
cal = O.index[O['XBI'].notna()]; O = O.loc[cal]; C = C.loc[cal]; n_cal = len(cal)

def leg(tk, i, j):
    c = C[tk].iloc[i:j + 1].values.astype(float); o = O[tk].iat[i]
    r = c / np.concatenate([[o], c[:-1]]) - 1
    return np.where(np.isfinite(r), r, 0.0), int((~np.isfinite(r)).sum())

def run(which, hold=60, slot=0.05, cost_rt=0.02, borrow=0.15, hedge=True, max_mcap=2000.0, cost_hedge=0.0005, drop=None):
    E = E0[(E0.set == which) & E0.liquid & (E0.k8_near == 0) & (E0.fin_mktcap_m < max_mcap)].copy()
    E['side'] = np.where(E.change_type.isin(UP), 1, np.where(E.change_type.isin(DN), -1, 0)); E = E[E.side != 0]
    both = E.groupby(['ticker', 'ed']).side.transform('nunique') > 1
    E = E[~both].sort_values(['ed', 'ticker']).drop_duplicates(['ticker', 'ed'])
    rows = []; busy = {}
    for r in E.itertuples():
        i = int(np.searchsorted(cal.values, np.datetime64(r.ud)))
        if i >= n_cal or r.ticker not in O.columns or not (O[r.ticker].iat[i] > 0): continue
        if busy.get(r.ticker, -1) >= i: continue
        j = min(i + hold - 1, n_cal - 1); busy[r.ticker] = j
        rows.append(dict(ticker=r.ticker, side=int(r.side), change_type=r.change_type, event_date=r.ed, entry_date=cal[i], exit_date=cal[j],
                         i=i, j=j, mktcap_m=r.fin_mktcap_m))
    T = pd.DataFrame(rows)
    if drop is not None: T = T[~T.index.isin(drop)]
    first, last = T.i.min(), T.j.max(); n = len(T)
    G = np.zeros((n, last - first + 1)); N = np.zeros_like(G); OP = np.zeros_like(G, dtype=bool)
    gr, nr, bad, big = [], [], [], []
    for k, r in enumerate(T.itertuples()):
        s, nb = leg(r.ticker, r.i, r.j); x = leg('XBI', r.i, r.j)[0] if hedge else 0.0
        g = r.side * (s - x); c = np.zeros_like(g)
        c[0] += cost_rt / 2 + (cost_hedge / 2 if hedge else 0); c[-1] += cost_rt / 2 + (cost_hedge / 2 if hedge else 0)
        if r.side < 0: c += borrow / 252
        sl = slice(r.i - first, r.j - first + 1); G[k, sl] = g; N[k, sl] = g - c; OP[k, sl] = True
        gr.append(np.prod(1 + g) - 1); nr.append(np.prod(1 + g) - 1 - c.sum()); bad.append(nb); big.append(float(np.abs(s).max()))
    T = T.assign(gross_ret=gr, net_ret=nr, missing_days=bad, max_abs_daily=big)
    nopen = OP.sum(axis=0); w = np.minimum(slot, 1.0 / np.maximum(nopen, 1))
    sh, lg = T.side.values == -1, T.side.values == 1
    f = lambda M, m: M[m].sum(axis=0) * w if m.any() else np.zeros(G.shape[1])
    D = pd.DataFrame({'date': cal[first:last + 1], 'n_open': nopen, 'gross_both': f(G, sh | lg), 'net_short': f(N, sh), 'net_long': f(N, lg), 'net_both': f(N, sh | lg)})
    T['contrib'] = (N * w).sum(axis=1)                       # each trade's share of the portfolio's total (sum of daily contributions)
    return T, D
def sharpe(x): x = np.asarray(x); return x.mean() / x.std(ddof=1) * np.sqrt(252) if x.std(ddof=1) > 0 else np.nan
rng = np.random.default_rng(7)
def ci(x, block=20, B=a.boot):
    x = np.asarray(x); m = len(x); out = np.empty(B)
    for b in range(B):
        idx = np.empty(m, dtype=int); t = 0
        while t < m:
            st = rng.integers(0, m); L = min(rng.geometric(1.0 / block), m - t); idx[t:t + L] = (st + np.arange(L)) % m; t += L
        out[b] = sharpe(x[idx])
    return np.nanpercentile(out, 2.5), np.nanpercentile(out, 97.5), float(np.nanmean(out <= 0))
def desc(x):
    x = np.asarray(x); eq = np.cumprod(1 + x); yrs = len(x) / 252
    return f'ann return {(eq[-1] ** (1 / yrs) - 1) * 100:+6.1f}% | vol {x.std(ddof=1) * np.sqrt(252) * 100:5.1f}% | Sharpe {sharpe(x):+5.2f} | max drawdown {(eq / np.maximum.accumulate(eq) - 1).min() * 100:5.1f}%'

T, D = run(a.set)
print(f'================ {a.set.upper()} SET ================')
print(f'trades {len(T)} (short {(T.side==-1).sum()}, buy {(T.side==1).sum()}) | companies {T.ticker.nunique()} | {D.date.iloc[0].date()} to {D.date.iloc[-1].date()} | avg open {D.n_open.mean():.1f}')
for col, lab in (('gross_both', 'both, before costs'), ('net_both', 'both, after costs'), ('net_short', 'short only, after costs'), ('net_long', 'buy only, after costs')):
    lo, hi, p0 = ci(D[col].values)
    print(f'  {lab:26s} {desc(D[col].values)} | 95% interval [{lo:+.2f}, {hi:+.2f}] | chance Sharpe<=0 {p0:.2f}')

print('\na. TIMING')
gap = (T.entry_date - T.event_date).dt.days
print(f'   every trade enters after the registry change was posted: {bool((gap >= 1).all())} | days from posting to entry: min {gap.min()}, median {gap.median():.0f}, max {gap.max()}')
print(T.sample(min(8, len(T)), random_state=3)[['ticker', 'side', 'change_type', 'event_date', 'entry_date', 'exit_date', 'net_ret']].assign(net_ret=lambda d: (d.net_ret * 100).round(1)).to_string(index=False))

print('\nb. WHERE THE PROFIT COMES FROM (per trade, after costs; "share" = share of total profit)')
tot = T.contrib.sum()
def brk(lab, key):
    g = T.groupby(key).agg(trades=('net_ret', 'size'), avg_net=('net_ret', 'mean'), median_net=('net_ret', 'median'), win=('net_ret', lambda s: (s > 0).mean()), share=('contrib', lambda s: s.sum() / tot))
    g[['avg_net', 'median_net']] = (g[['avg_net', 'median_net']] * 100).round(1); g[['win', 'share']] = g[['win', 'share']].round(2)
    print(f'   by {lab}:'); print('   ' + g.to_string().replace('\n', '\n   '))
brk('side (-1 short, +1 buy)', 'side'); brk('event type', 'change_type')
brk('half year', T.entry_date.dt.year.astype(str) + 'H' + ((T.entry_date.dt.month > 6) + 1).astype(str))
brk('company size', np.where(T.mktcap_m < 300, 'under $300M', '$300M to $2B'))
srt = T.sort_values('net_ret')
show = lambda d: d[['ticker', 'side', 'change_type', 'entry_date', 'net_ret']].assign(net_ret=lambda x: (x.net_ret * 100).round(1)).to_string(index=False)
print('   8 worst trades:'); print(show(srt.head(8))); print('   8 best trades:'); print(show(srt.tail(8)))
best5 = T.sort_values('contrib').tail(5).index
T2, D2 = run(a.set, drop=best5)
print(f'   Sharpe after costs with the 5 most profitable trades removed: {sharpe(D2.net_both):+.2f} (was {sharpe(D.net_both):+.2f})')

print('\nc. CONCENTRATION')
byc = T.groupby('ticker').contrib.sum().sort_values(ascending=False); pos = byc[byc > 0]
k = int((pos.cumsum() < 0.5 * pos.sum()).sum()) + 1
print(f'   companies traded {len(byc)} | profitable {int((byc > 0).sum())} | the top {k} companies make half of all gains | top 5: {", ".join(f"{t} {v/tot:+.0%}" for t, v in byc.head(5).items())}')
print(f'   worst 5: {", ".join(f"{t} {v/tot:+.0%}" for t, v in byc.tail(5).items())}')

print('\nd. COSTS: Sharpe of both sides together')
print('   round trip cost on the stock (borrow 15%/yr):', ' | '.join(f'{c*100:.0f}%: {sharpe(run(a.set, cost_rt=c)[1].net_both):+.2f}' for c in (0, .01, .02, .03, .04, .06)))
print('   yearly borrow fee on shorts (round trip 2%)  :', ' | '.join(f'{b*100:.0f}%: {sharpe(run(a.set, borrow=b)[1].net_both):+.2f}' for b in (0, .15, .30, .60, 1.0)))
print('   short side alone, borrow fee                 :', ' | '.join(f'{b*100:.0f}%: {sharpe(run(a.set, borrow=b)[1].net_short):+.2f}' for b in (0, .15, .30, .60, 1.0)))

if a.set == 'design':
    print('\ne. SETTINGS (design half only; shown to see how fragile the result is, not to pick the best)')
    print('   hold length      :', ' | '.join(f'{h}d: {sharpe(run("design", hold=h)[1].net_both):+.2f}' for h in (20, 40, 60, 90)))
    print('   no XBI hedge     :', f'{sharpe(run("design", hedge=False)[1].net_both):+.2f}')
    print('   capital per trade:', ' | '.join(f'{s*100:.1f}%: {sharpe(run("design", slot=s)[1].net_both):+.2f}' for s in (0.025, 0.05, 0.10)))
    print('   size limit       :', ' | '.join(f'under ${m:.0f}M: {sharpe(run("design", max_mcap=m)[1].net_both):+.2f}' for m in (300, 1000, 2000, 5000, 1e9)))

print('\nf. DATA PROBLEMS')
print(f'   trades with a missing price day inside the hold: {(T.missing_days > 0).sum()} | trades with a one day stock move over 100%: {(T.max_abs_daily > 1).sum()} | trades cut short by the end of data: {((T.j - T.i + 1) < 60).sum()}')
if (T.max_abs_daily > 1).any(): print(show(T[T.max_abs_daily > 1]))

T.drop(columns=['i', 'j']).to_csv(os.path.join(FDS, f'strategy_audit_trades_{a.set}.csv'), index=False)
D.to_csv(os.path.join(FDS, f'strategy_audit_daily_{a.set}.csv'), index=False)
if a.set == 'holdout':
    logp = os.path.join(FDS, 'ct_holdout_log.csv'); new = not os.path.exists(logp)
    with open(logp, 'a') as fh:
        if new: fh.write('run_at,rule,n_holdout,mean_holdout\n')
        fh.write(f'{dt.datetime.now().isoformat(timespec="seconds")},"39_strategy_audit main rule",{len(T)},{T.net_ret.mean()}\n')
    print('\nholdout runs logged so far:', sum(1 for _ in open(logp)) - 1)
