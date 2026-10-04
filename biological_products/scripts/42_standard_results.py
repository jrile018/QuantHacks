"""
42_standard_results.py - ONE standard for every strategy, so in-sample and out-of-sample mean the same thing everywhere.

STANDARD WINDOWS (the team's own settings in src/config.py):
    in sample      2024-01-01 .. 2025-12-31
    out of sample  2026-01-01 .. 2026-08-31
A trade belongs to the window of its SIGNAL date (the day the information became usable). Daily series are cut by calendar day.

STANDARD NUMBERS for every strategy and window:
    trades, total P&L (sum of per trade results), average per trade, win rate,
    Sharpe = mean / std of the per trade result x sqrt(252 / holding days), 95% interval by bootstrap over trades (5000 draws).
For our own two backtests we also give the portfolio version (daily profit and loss, block bootstrap), same windows.

Reads: data/fds/offer_strategy_trades.csv + offer_strategy_daily.csv (script 40), data/fds/ct_event_study.csv (script 36),
       hpg_bundle/hpg_results/out_* (team engine runs on HiPerGator).
Writes: reports/standard_results.csv, standard_portfolio.csv and std_*.png
"""
import os, json, argparse
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--lead', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'hpg_bundle', 'hpg_results'))
ap.add_argument('--boot', type=int, default=5000)
ap.add_argument('--borrow', type=float, default=0.30)
# default windows: the 20 months in which the offering model has trades (Jan 2025 to Aug 2026), cut into two equal halves of 10 months.
# the first team windows from src/config.py were 2024-01-01..2025-12-31 and 2026-01-01..2026-08-31 (pass them to get the earlier tables).
ap.add_argument('--is_start', default='2025-01-01'); ap.add_argument('--is_end', default='2025-10-31')
ap.add_argument('--os_start', default='2025-11-01'); ap.add_argument('--os_end', default='2026-08-31')
ap.add_argument('--out', default='reports', help='output folder name inside biological_products')
ap.add_argument('--offer_trades', default='offer_strategy_trades_v3.csv', help='offering short trade file in data/fds (v3 = dataset v2 + quote clock, scripts 48, 22, 45)')
a = ap.parse_args()
RAW = os.path.join(a.data, 'raw'); FDS = os.path.join(a.data, 'fds'); OUT = os.path.join(a.data, '..', a.out); os.makedirs(OUT, exist_ok=True)
IS0, IS1, OS0, OS1 = pd.Timestamp(a.is_start), pd.Timestamp(a.is_end), pd.Timestamp(a.os_start), pd.Timestamp(a.os_end)
DEFAULT = (a.is_start, a.is_end, a.os_start, a.os_end) == ('2024-01-01', '2025-12-31', '2026-01-01', '2026-08-31')
fm = lambda d: d.strftime('%b %Y')
LIS, LOS = ('in sample 2024-2025', 'out of sample Jan-Aug 2026') if DEFAULT else (f'in sample {fm(IS0)} to {fm(IS1)}', f'out of sample {fm(OS0)} to {fm(OS1)}')
WIN = {LIS: (IS0, IS1), LOS: (OS0, OS1)}
rng = np.random.default_rng(21)
BLUE, ORANGE, INK, INK2, GRID, SURF = '#2a78d6', '#eb6834', '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2, 'xtick.color': INK2,
                     'ytick.color': INK2, 'text.color': INK, 'figure.facecolor': SURF, 'axes.facecolor': SURF, 'savefig.facecolor': SURF})

def ev_stats(x, hold, dates=None):
    """per trade stats. Two 95% intervals: ci_lo/ci_hi resample trades one by one (assumes independent trades, optimistic);
    cib_lo/cib_hi resample whole signal WEEKS (trades in the same week overlap and share market shocks), the lead's audit A5."""
    x = np.asarray(x, float); ok_ = np.isfinite(x); x = x[ok_]
    if len(x) < 8: return dict(trades=len(x), total_pnl_pct=np.nan, avg_trade_pct=np.nan, median_trade_pct=np.nan, win_rate=np.nan, sharpe=np.nan, ci_lo=np.nan, ci_hi=np.nan, cib_lo=np.nan, cib_hi=np.nan)
    k = np.sqrt(252.0 / hold); xb = x[rng.integers(0, len(x), (a.boot, len(x)))]; sb = xb.mean(1) / xb.std(1, ddof=1) * k
    res = dict(trades=len(x), total_pnl_pct=x.sum() * 100, avg_trade_pct=x.mean() * 100, median_trade_pct=np.median(x) * 100, win_rate=(x > 0).mean(),
                sharpe=x.mean() / x.std(ddof=1) * k, ci_lo=np.percentile(sb, 2.5), ci_hi=np.percentile(sb, 97.5), cib_lo=np.nan, cib_hi=np.nan)
    if dates is not None:
        wk = pd.to_datetime(pd.Series(np.asarray(dates)[ok_])).dt.to_period('W').astype(str).values; groups = [x[wk == w] for w in np.unique(wk)]; G = len(groups)
        if G >= 6:
            out = np.empty(a.boot)
            for b in range(a.boot):
                xs = np.concatenate([groups[i] for i in rng.integers(0, G, G)]); out[b] = xs.mean() / xs.std(ddof=1) * k if xs.std(ddof=1) > 0 else np.nan
            res['cib_lo'], res['cib_hi'] = np.nanpercentile(out, 2.5), np.nanpercentile(out, 97.5)
    return res
def sharpe_d(x): x = np.asarray(x, float); return x.mean() / x.std(ddof=1) * np.sqrt(252) if len(x) > 5 and x.std(ddof=1) > 0 else np.nan
def ci_d(x, block=20):
    x = np.asarray(x, float); m = len(x); out = np.empty(a.boot)
    for b in range(a.boot):
        idx = np.empty(m, dtype=int); t = 0
        while t < m:
            st = rng.integers(0, m); L = min(rng.geometric(1.0 / block), m - t); idx[t:t + L] = (st + np.arange(L)) % m; t += L
        out[b] = sharpe_d(x[idx])
    return np.nanpercentile(out, 2.5), np.nanpercentile(out, 97.5)
def port_stats(x):
    x = np.asarray(x, float)
    if len(x) < 30: return dict(days=len(x))
    eq = np.cumprod(1 + x); lo, hi = ci_d(x)
    return dict(days=len(x), total_return_pct=(eq[-1] - 1) * 100, annual_return_pct=(eq[-1] ** (252 / len(x)) - 1) * 100, vol_pct=x.std(ddof=1) * np.sqrt(252) * 100,
                sharpe=sharpe_d(x), ci_lo=lo, ci_hi=hi, max_drawdown_pct=(eq / np.maximum.accumulate(eq) - 1).min() * 100)
def style(ax, title, sub):
    nl = sub.count('\n') + 1
    ax.set_title(title, loc='left', fontsize=11, fontweight='bold', color=INK, pad=9 + 13 * nl)
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9, color=INK2, va='bottom')
    ax.grid(axis='y', color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    for s in ('top', 'right', 'left'): ax.spines[s].set_visible(False)
    ax.axhline(0, color=INK2, linewidth=0.8); ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f'{v:+.0f}%'))
    ax.tick_params(length=0); ax.tick_params(axis='x', labelrotation=30)
def endlabel(ax, x, y, text, color):
    ax.plot([x], [y], 'o', color=color, markersize=5, markeredgecolor=SURF, markeredgewidth=1.5, zorder=5)
    ax.annotate(text, (x, y), xytext=(6, 0), textcoords='offset points', va='center', fontsize=9, color=INK)
def two_panel(fname, suptitle, series):
    """series: {window: [(dates, values_pct, color, label), ...], and subtitle text}"""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.7), sharey=True)
    for ax, w in zip(axes, WIN):
        lines, sub = series[w]
        for d, v, col, lab in lines:
            if len(v) == 0: continue
            ax.plot(d, v, color=col, linewidth=2, label=lab); endlabel(ax, d[-1], v[-1], f'{v[-1]:+.0f}%', col)
        style(ax, WTITLE[w], sub); ax.margins(x=0.12)
    h_, l_ = axes[0].get_legend_handles_labels()
    if not h_: h_, l_ = axes[1].get_legend_handles_labels()
    fig.legend(h_, l_, frameon=False, loc='lower center', ncol=2, fontsize=9)
    fig.suptitle(suptitle, x=0.01, ha='left', fontsize=12, fontweight='bold', color=INK)
    fig.tight_layout(rect=(0, 0.06, 1, 0.94)); fig.savefig(os.path.join(OUT, fname), dpi=150); plt.close(fig)

rows, prow = [], []
def add(strategy, engine, costs, hold, df, col, datecol):
    for w, (d0, d1) in WIN.items():
        g = df[(df[datecol] >= d0) & (df[datecol] <= d1)]
        rows.append(dict(strategy=strategy, engine=engine, costs=costs, hold_days=hold, window=w, **ev_stats(g[col], hold, g[datecol])))

P = pd.read_csv(os.path.join(RAW, 'prices.csv'), usecols=['ticker', 'date', 'open', 'close']); P['date'] = pd.to_datetime(P.date)
O = P.pivot(index='date', columns='ticker', values='open'); C = P.pivot(index='date', columns='ticker', values='close')
cal = O.index[O['XBI'].notna()]; O = O.loc[cal]; C = C.loc[cal]; n_cal = len(cal); pos = {d: i for i, d in enumerate(cal)}
def leg(tk, i, j):
    c = C[tk].iloc[i:j + 1].values.astype(float); r = c / np.concatenate([[O[tk].iat[i]], c[:-1]]) - 1; return np.where(np.isfinite(r), r, 0.0)
def window_series(Gm, Nm, OPm, days, slot):
    """daily portfolio return built ONLY from the trades of one window (so a trade never leaks its profit into the other window)"""
    nopen = OPm.sum(0); idx = np.where(nopen > 0)[0]
    if len(idx) == 0: return days[:0], np.array([]), np.array([])
    w = np.minimum(slot, 1.0 / np.maximum(nopen, 1)); sl = slice(idx[0], idx[-1] + 1)
    return days[sl], (Gm.sum(0) * w)[sl], (Nm.sum(0) * w)[sl]
WTITLE = {LIS: 'In sample: 2024 to 2025', LOS: 'Out of sample: Jan to Aug 2026'} if DEFAULT else {LIS: f'In sample: {fm(IS0)} to {fm(IS1)}', LOS: f'Out of sample: {fm(OS0)} to {fm(OS1)}'}

# ============ 1. offering short, our backtest (real bid/ask costs + borrow fee) ============
T = pd.read_csv(os.path.join(FDS, a.offer_trades)); T['sig'] = pd.to_datetime(T.signal.astype(str))
T['net_all'] = T.net - a.borrow * 5 / 252
add('Offering short: short stocks the model flags, hedge XBI', 'our backtest', f'real bid/ask + {a.borrow*100:.0f}%/yr borrow', 5, T, 'net_all', 'sig')
add('Offering short: short stocks the model flags, hedge XBI', 'our backtest', 'none (quote mid to mid)', 5, T, 'gross', 'sig')
if 'gross_bar' in T: add('Offering short: short stocks the model flags, hedge XBI', 'our backtest', 'none (daily bars, old clock)', 5, T, 'gross_bar', 'sig')
add('Offering short, liquid subset: entry bid/ask spread under 2%', 'our backtest', f'real bid/ask + {a.borrow*100:.0f}%/yr borrow', 5, T[T.spread_in < 0.02], 'net_all', 'sig')
T['e'] = pd.to_datetime(T.entry.astype(str)); T['x'] = pd.to_datetime(T.exit.astype(str)); T = T.reset_index(drop=True)
ii, jj = T.e.map(pos).astype(int).values, T.x.map(pos).astype(int).values; f0, f1 = ii.min(), jj.max()
Go = np.zeros((len(T), f1 - f0 + 1)); No = np.zeros_like(Go); OPo = np.zeros_like(Go, dtype=bool)
for k in range(len(T)):
    g = -(leg(T.tk[k], ii[k], jj[k]) - leg('XBI', ii[k], jj[k])); c = np.zeros_like(g); c[0] += T.cost[k] / 2; c[-1] += T.cost[k] / 2; c += a.borrow / 252
    sl = slice(ii[k] - f0, jj[k] - f0 + 1); Go[k, sl] = g; No[k, sl] = g - c; OPo[k, sl] = True
ser = {}
for w, (d0, d1) in WIN.items():
    m = ((T.sig >= d0) & (T.sig <= d1)).values; dd, dg, dn = window_series(Go[m], No[m], OPo[m], cal[f0:f1 + 1], 0.20)
    prow.append(dict(strategy='Offering short', window=w, trades=int(m.sum()), **port_stats(dn)))
    m2 = m & (T.spread_in < 0.02).values; _, _, dn2 = window_series(Go[m2], No[m2], OPo[m2], cal[f0:f1 + 1], 0.20)
    prow.append(dict(strategy='Offering short, liquid subset', window=w, trades=int(m2.sum()), **port_stats(dn2)))
    ser[w] = ([(dd.values, (np.cumprod(1 + dg) - 1) * 100, ORANGE, 'Before costs'), (dd.values, (np.cumprod(1 + dn) - 1) * 100, BLUE, 'After costs')],
              f'{int(m.sum())} trades. Portfolio Sharpe after costs {sharpe_d(dn):+.2f}' + ('\n(the model has no trades in 2024: it needs that year to train)' if (d0 == IS0 and IS0.year == 2024) else '\n'))
two_panel('std_offering_short.png', 'Offering short (our backtest): equity curve, same windows as the team', ser)

# ============ 2. trial registry stage, our backtest, one chain over the whole period ============
UP = ['to_active_not_recruiting', 'pc_reached', 'enroll_actual']; DN = ['sites_up', 'enroll_target_up', 'to_recruiting']
E = pd.read_csv(os.path.join(FDS, 'ct_event_study.csv')); E['ed'] = pd.to_datetime(E.ed); E['ud'] = pd.to_datetime(E.ud)
# fixes after our own check: real price and real market cap (no later splits), and the 8-K filter looks BACK only (event day and 2 days before)
RP = pd.read_csv(os.path.join(FDS, 'fds_realprice.csv'), usecols=['cik', 'date', 'px_close_real', 'fin_mktcap_real_m']); RP['fd'] = pd.to_datetime(RP.date.astype(str)); E['fd'] = pd.to_datetime(E.fd)
E = E.merge(RP.drop(columns='date'), on=['cik', 'fd'], how='left')
K8 = pd.read_csv(os.path.join(RAW, 'events_8k.csv'), usecols=['cik', 'filing_date']); K8['kd'] = pd.to_datetime(K8.filing_date)
kset = {int(c): np.sort(g.kd.values.astype('datetime64[ns]')) for c, g in K8.groupby('cik')}
def k8_back(c, e):
    v = kset.get(int(c))
    if v is None: return 0
    j = np.searchsorted(v, np.datetime64(e - pd.Timedelta(days=2))); return int(j < len(v) and v[j] <= np.datetime64(e))
E['k8_back'] = [k8_back(c, e) for c, e in zip(E.cik, E.ed)]
E = E[(E.px_adv20_usd_m >= 1) & (E.px_close_real >= 1) & (E.k8_back == 0) & (E.fin_mktcap_real_m < 2000)].copy()
E['side'] = np.where(E.change_type.isin(UP), 1, np.where(E.change_type.isin(DN), -1, 0)); E = E[E.side != 0]
E = E[~(E.groupby(['ticker', 'ed']).side.transform('nunique') > 1)].sort_values(['ed', 'ticker']).drop_duplicates(['ticker', 'ed'])
tr, busy = [], {}
for r in E.itertuples():
    i = int(np.searchsorted(cal.values, np.datetime64(r.ud)))
    if i >= n_cal or r.ticker not in O.columns or not (O[r.ticker].iat[i] > 0) or busy.get(r.ticker, -1) >= i: continue
    j = min(i + 59, n_cal - 1); busy[r.ticker] = j; tr.append((r.ticker, r.side, r.ed, r.ud, i, j))
R = pd.DataFrame(tr, columns=['ticker', 'side', 'ed', 'ud', 'i', 'j']); first, last = R.i.min(), R.j.max()
G = np.zeros((len(R), last - first + 1)); N = np.zeros_like(G); OP = np.zeros_like(G, dtype=bool); gr, nr = [], []
for k, r in enumerate(R.itertuples()):
    g = r.side * (leg(r.ticker, r.i, r.j) - leg('XBI', r.i, r.j)); c = np.zeros_like(g); c[0] += 0.01025; c[-1] += 0.01025
    if r.side < 0: c += 0.15 / 252
    sl = slice(r.i - first, r.j - first + 1); G[k, sl] = g; N[k, sl] = g - c; OP[k, sl] = True
    cs = C[r.ticker].iloc[r.i:r.j + 1].dropna(); bh = r.side * ((cs.iloc[-1] / O[r.ticker].iat[r.i] - 1 if len(cs) else 0.0) - (C['XBI'].iat[r.j] / O['XBI'].iat[r.i] - 1))
    gr.append(bh); nr.append(bh - c.sum())      # per trade result = buy and hold over the whole trade (a short can lose more than 100%)
R['gross'] = gr; R['net'] = nr
add('Trial registry stage: short while building a trial, buy when enrollment ends, hedge XBI', 'our backtest', '2% round trip + 15%/yr borrow', 60, R, 'net', 'ud')
add('Trial registry stage: short while building a trial, buy when enrollment ends, hedge XBI', 'our backtest', 'none', 60, R, 'gross', 'ud')
days = cal[first:last + 1]; ser = {}
for w, (d0, d1) in WIN.items():
    m = ((R.ud >= d0) & (R.ud <= d1)).values; dd, dg, dn = window_series(G[m], N[m], OP[m], days, 0.05)
    prow.append(dict(strategy='Trial registry stage', window=w, trades=int(m.sum()), **port_stats(dn)))
    ser[w] = ([(dd.values, (np.cumprod(1 + dg) - 1) * 100, ORANGE, 'Before costs'), (dd.values, (np.cumprod(1 + dn) - 1) * 100, BLUE, 'After costs')],
              f'{int(m.sum())} trades. Portfolio Sharpe after costs {sharpe_d(dn):+.2f}' + ('\n(the rules were designed on events up to June 2025)' if d0 == IS0 else '\n'))
two_panel('std_trial_registry.png', 'Trial registry stage (our backtest): equity curve, same windows as the team', ser)

# ============ 3 and 4. team engine runs on HiPerGator ============
def engine(folders, col, sign, hold, strategy, fname, title, date_col='event_date'):
    fs = [os.path.join(a.lead, f) for f in folders if os.path.exists(os.path.join(a.lead, f, 'results.csv'))]
    if not fs: print('not found yet:', folders); return
    r = pd.concat([pd.read_csv(os.path.join(f, 'results.csv')) for f in fs]); r['horizon'] = r.horizon.astype(str)
    r = r[(r.entry == 'post') & (r.bucket == '1m') & (r.horizon == str(hold)) & np.isclose(r.otm, 0.05)].copy()
    r['d'] = pd.to_datetime(r[date_col]); r['x'] = sign * r[col]; r = r.dropna(subset=['x']).sort_values('entry_date')
    add(strategy, 'team engine on HiPerGator', 'none (engine uses last trade prices)', hold, r, 'x', 'd')
    ser = {}
    for w, (d0, d1) in WIN.items():
        g = r[(r.d >= d0) & (r.d <= d1)]; s = ev_stats(g.x, hold)
        ser[w] = ([(pd.to_datetime(g.entry_date).values, g.x.cumsum().values * 100, BLUE, 'Running total of per event results (no costs)')] if len(g) else [],
                  f'{len(g)} events priced' + (f'. Win rate {s["win_rate"]:.0%}, Sharpe {s["sharpe"]:+.2f}' if len(g) >= 8 else ' (too few for a Sharpe)') + '\n')
    two_panel(fname, title, ser)
engine(['out_insample_public_offering', 'out_oos_public_offering'], 'stock', 1, 10, 'Buy after an offering 8-K (stock, 10 days)', 'std_engine_buy_after_offering.png',
       'Team engine: buy the stock after a public offering 8-K, hold 10 days')
engine(['out_signal_offer'], 'stock', -1, 5, 'Offering short: the same model signal, priced by the team engine', 'std_engine_offering_short.png',
       'Team engine: short the stocks our model flags, hold 5 days')

S = pd.DataFrame(rows); S.to_csv(os.path.join(OUT, 'standard_results.csv'), index=False)
Pp = pd.DataFrame(prow); Pp.to_csv(os.path.join(OUT, 'standard_portfolio.csv'), index=False)
pd.set_option('display.width', 260); pd.set_option('display.max_colwidth', 60)
print('STANDARD RESULTS (per trade; same windows and same formula for every strategy)')
print(S.assign(strategy=S.strategy.str.slice(0, 44))[['strategy', 'engine', 'costs', 'window', 'trades', 'total_pnl_pct', 'avg_trade_pct', 'median_trade_pct', 'win_rate', 'sharpe', 'ci_lo', 'ci_hi', 'cib_lo', 'cib_hi']].round(2).to_string(index=False))
print('ci = trades resampled one by one (independent trades assumed); cib = whole signal weeks resampled (allows for overlap and shared shocks)')
print('\nPORTFOLIO VERSION (daily profit and loss, our own backtests, after costs)')
print(Pp.round(2).to_string(index=False))
print('\nwritten to', os.path.abspath(OUT))
