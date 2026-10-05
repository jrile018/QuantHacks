"""
38_strategy_pnl.py - turn the trial-stage rules into trades, a daily profit-and-loss series, a Sharpe ratio and a 95% interval.

RULES (fixed before the holdout was looked at). Companies under $2B market cap, liquid (20 day dollar volume >= $1M, price >= $1),
no 8-K within 2 days of the registry change, one position per company at a time, hold 60 market days, hedge with XBI (same dollars):
  SHORT "ramp stage":  the trial starts recruiting, adds 20%+ sites, or raises its enrollment target 10%+
  BUY   "data stage":  enrollment finished, primary completion reached, or final enrollment posted
Entry at the OPEN of the first market day after the change was posted. Exit at the close 60 market days later.

PORTFOLIO: each trade gets 5% of capital (stock leg) with an equal and opposite XBI leg. If more than 20 trades are open, all are scaled
down so the total never exceeds 100%. Days with no open trade earn 0.
COSTS (assumptions, change with flags): 2% round trip on the stock leg, 0.05% on the XBI leg, 15% per year borrow fee on shorts.

Usage:  python 38_strategy_pnl.py                       (design set: events up to 2025-06-30)
        python 38_strategy_pnl.py --set holdout --confirm_holdout     (ONE time only; every run is logged)
Writes data/fds/strategy_trades_<set>.csv and strategy_daily_<set>.csv
"""
import os, argparse, datetime as dt
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--set', default='design', choices=['design', 'holdout'])
ap.add_argument('--confirm_holdout', action='store_true')
ap.add_argument('--hold', type=int, default=60)
ap.add_argument('--max_mcap', type=float, default=2000.0)
ap.add_argument('--slot', type=float, default=0.05, help='share of capital per trade')
ap.add_argument('--cost_rt', type=float, default=0.02, help='round trip cost on the stock leg')
ap.add_argument('--cost_hedge', type=float, default=0.0005)
ap.add_argument('--borrow', type=float, default=0.15, help='annual borrow fee on short stock positions')
ap.add_argument('--boot', type=int, default=5000)
a = ap.parse_args()
RAW = os.path.join(a.data, 'raw'); FDS = os.path.join(a.data, 'fds')
if a.set == 'holdout' and not a.confirm_holdout:
    raise SystemExit('The holdout is a one time test. Add --confirm_holdout only when the rules are final.')
rng = np.random.default_rng(7)
UP = ['to_active_not_recruiting', 'pc_reached', 'enroll_actual']        # data stage -> buy
DN = ['sites_up', 'enroll_target_up', 'to_recruiting']                  # ramp stage -> short
H = a.hold

E = pd.read_csv(os.path.join(FDS, 'ct_event_study.csv'))
E['ed'] = pd.to_datetime(E.ed); E['ud'] = pd.to_datetime(E.ud)
E = E[(E.set == a.set) & E.liquid & (E.k8_near == 0) & (E.fin_mktcap_m < a.max_mcap)].copy()
E['side'] = np.where(E.change_type.isin(UP), 1, np.where(E.change_type.isin(DN), -1, 0))
E = E[E.side != 0].copy()
both = E.groupby(['ticker', 'ed']).side.transform('nunique') > 1          # same company, same day, signals in both directions: skip
print('events:', len(E), '| skipped because the same day had both a buy and a short signal:', int(both.sum()))
E = E[~both].sort_values(['ed', 'ticker']).drop_duplicates(['ticker', 'ed'])

P = pd.read_csv(os.path.join(RAW, 'prices.csv'), usecols=['ticker', 'date', 'open', 'close']); P['date'] = pd.to_datetime(P.date)
O = P.pivot(index='date', columns='ticker', values='open'); C = P.pivot(index='date', columns='ticker', values='close')
cal = O.index[O['XBI'].notna()]; O = O.loc[cal]; C = C.loc[cal]; n_cal = len(cal)

def leg(tk, i, j):
    """daily returns of one ticker from the open of day i to the close of day j"""
    c = C[tk].iloc[i:j + 1].values.astype(float); o = O[tk].iat[i]
    prev = np.concatenate([[o], c[:-1]])
    r = c / prev - 1
    return np.where(np.isfinite(r), r, 0.0)

trades = []; busy = {}
for r in E.itertuples():
    i = int(np.searchsorted(cal.values, np.datetime64(r.ud)))          # first market day on or after the usable date
    if i >= n_cal or r.ticker not in O.columns or not (O[r.ticker].iat[i] > 0): continue
    if busy.get(r.ticker, -1) >= i: continue                            # one position per company at a time (either side)
    j = min(i + H - 1, n_cal - 1)
    busy[r.ticker] = j
    trades.append(dict(ticker=r.ticker, cik=r.cik, side=int(r.side), change_type=r.change_type, event_date=r.ed.date(),
                       entry_date=cal[i].date(), exit_date=cal[j].date(), i=i, j=j, complete=int(j == i + H - 1), mktcap_m=r.fin_mktcap_m))
T = pd.DataFrame(trades)
if len(T) == 0: raise SystemExit('no trades')

# daily hedged return of every trade, then the portfolio
n = len(T); first, last = T.i.min(), T.j.max()
G = np.zeros((n, last - first + 1)); N = np.zeros_like(G); OPEN = np.zeros_like(G, dtype=bool)
for k, r in enumerate(T.itertuples()):
    s = leg(r.ticker, r.i, r.j); x = leg('XBI', r.i, r.j)
    g = r.side * (s - x)                                               # long stock / short XBI, or the reverse
    c = np.zeros_like(g)
    c[0] += a.cost_rt / 2 + a.cost_hedge / 2; c[-1] += a.cost_rt / 2 + a.cost_hedge / 2
    if r.side < 0: c += a.borrow / 252
    G[k, r.i - first:r.j - first + 1] = g; N[k, r.i - first:r.j - first + 1] = g - c; OPEN[k, r.i - first:r.j - first + 1] = True
    T.loc[T.index[k], 'gross_ret'] = np.prod(1 + g) - 1; T.loc[T.index[k], 'net_ret'] = np.prod(1 + g) - 1 - c.sum()
days = cal[first:last + 1]
n_open = OPEN.sum(axis=0)
w = np.minimum(a.slot, 1.0 / np.maximum(n_open, 1))                     # 5% each, scaled down when more than 20 are open
def port(M, mask): return (M[mask].sum(axis=0) * w) if mask.any() else np.zeros(len(days))
sh, lg = (T.side.values == -1), (T.side.values == 1)
daily = pd.DataFrame({'date': days, 'n_open': n_open, 'gross_short': port(G, sh), 'gross_long': port(G, lg), 'gross_both': port(G, sh | lg),
                      'net_short': port(N, sh), 'net_long': port(N, lg), 'net_both': port(N, sh | lg)})

def sharpe(x): return x.mean() / x.std(ddof=1) * np.sqrt(252) if x.std(ddof=1) > 0 else np.nan
def boot_ci(x, block=20, B=a.boot):
    """stationary block bootstrap of the annualized Sharpe ratio (keeps runs of days together because trades overlap)"""
    x = np.asarray(x); m = len(x); out = np.empty(B)
    for b in range(B):
        idx = np.empty(m, dtype=int); t = 0
        while t < m:
            start = rng.integers(0, m); L = min(rng.geometric(1.0 / block), m - t)
            idx[t:t + L] = (start + np.arange(L)) % m; t += L
        out[b] = sharpe(x[idx])
    return np.nanpercentile(out, [2.5, 97.5]), np.nanmean(out <= 0)
def stats(col, label, ntr):
    x = daily[col].values; eq = np.cumprod(1 + x); dd = (eq / np.maximum.accumulate(eq) - 1).min()
    yrs = len(x) / 252; ann = eq[-1] ** (1 / yrs) - 1; vol = x.std(ddof=1) * np.sqrt(252)
    (lo, hi), p0 = boot_ci(x)
    print(f'  {label:26s} trades {ntr:3d} | ann return {ann*100:+6.1f}% | vol {vol*100:5.1f}% | Sharpe {sharpe(x):+5.2f}  95% interval [{lo:+.2f}, {hi:+.2f}] | chance Sharpe <= 0: {p0:.2f} | max drawdown {dd*100:5.1f}% | total {(eq[-1]-1)*100:+6.1f}%')

print(f'SET: {a.set} | trades {len(T)} (short {int(sh.sum())}, buy {int(lg.sum())}) | companies {T.ticker.nunique()} | {days[0].date()} to {days[-1].date()} ({len(days)} market days)')
print(f'trades cut short by the end of the price data: {int((T.complete == 0).sum())} | average trades open per day {n_open.mean():.1f}, max {n_open.max()}')
print(f'per trade (60 day hedged return): SHORT gross {T[sh].gross_ret.mean()*100:+.1f}% net {T[sh].net_ret.mean()*100:+.1f}% win {(T[sh].net_ret>0).mean():.2f} | BUY gross {T[lg].gross_ret.mean()*100:+.1f}% net {T[lg].net_ret.mean()*100:+.1f}% win {(T[lg].net_ret>0).mean():.2f}')
print(f'\nBEFORE COSTS')
stats('gross_short', 'short ramp stage', int(sh.sum())); stats('gross_long', 'buy data stage', int(lg.sum())); stats('gross_both', 'both together', len(T))
print(f'\nAFTER COSTS (stock round trip {a.cost_rt*100:.1f}%, borrow {a.borrow*100:.0f}%/yr on shorts)')
stats('net_short', 'short ramp stage', int(sh.sum())); stats('net_long', 'buy data stage', int(lg.sum())); stats('net_both', 'both together', len(T))
turn = 2 * a.slot * len(T) / (len(days) / 252)
print(f'\nturnover about {turn:.1f}x capital per year (stock legs). Sharpe interval: stationary block bootstrap, 20 day blocks, {a.boot} resamples.')

T.drop(columns=['i', 'j']).to_csv(os.path.join(FDS, f'strategy_trades_{a.set}.csv'), index=False)
daily.to_csv(os.path.join(FDS, f'strategy_daily_{a.set}.csv'), index=False)
if a.set == 'holdout':
    logp = os.path.join(FDS, 'ct_holdout_log.csv'); new = not os.path.exists(logp)
    with open(logp, 'a') as fh:
        if new: fh.write('run_at,rule,n_holdout,mean_holdout\n')
        fh.write(f'{dt.datetime.now().isoformat(timespec="seconds")},"38_strategy_pnl hold={H} mcap<{a.max_mcap}",{len(T)},{T.net_ret.mean()}\n')
    print('holdout runs logged so far:', sum(1 for _ in open(logp)) - 1)
