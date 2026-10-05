"""
41_report.py - the numbers the team lead asked for, in one place: P&L, Sharpe ratio, 95% interval, win rate, equity curve,
and in-sample next to out-of-sample. Reads the files written by scripts 39 and 40 (and, if present, the team backtest output).
Writes PNG charts and summary tables into biological_products/reports/.
Usage: python 41_report.py
"""
import os, glob, json, argparse
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--lead', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'hpg_bundle', 'hpg_results'))
ap.add_argument('--boot', type=int, default=5000)
a = ap.parse_args()
FDS = os.path.join(a.data, 'fds'); OUT = os.path.join(a.data, '..', 'reports'); os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(3)
# colours: validated default palette (slot 1 blue, slot 2 orange), ink for all text
BLUE, ORANGE, INK, INK2, GRID, SURF = '#2a78d6', '#eb6834', '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2, 'xtick.color': INK2,
                     'ytick.color': INK2, 'text.color': INK, 'figure.facecolor': SURF, 'axes.facecolor': SURF, 'savefig.facecolor': SURF})

def sharpe(x): x = np.asarray(x, float); return x.mean() / x.std(ddof=1) * np.sqrt(252) if len(x) > 2 and x.std(ddof=1) > 0 else np.nan
def ci(x, block=20):
    x = np.asarray(x, float); m = len(x); out = np.empty(a.boot)
    for b in range(a.boot):
        idx = np.empty(m, dtype=int); t = 0
        while t < m:
            st = rng.integers(0, m); L = min(rng.geometric(1.0 / block), m - t); idx[t:t + L] = (st + np.arange(L)) % m; t += L
        out[b] = sharpe(x[idx])
    return np.nanpercentile(out, 2.5), np.nanpercentile(out, 97.5)
def row(name, sample, daily, trades_net, note=''):
    x = np.asarray(daily, float); eq = np.cumprod(1 + x); lo, hi = ci(x); yrs = len(x) / 252
    return dict(strategy=name, sample=sample, start=None, trades=len(trades_net), total_pnl_pct=(eq[-1] - 1) * 100, annual_return_pct=(eq[-1] ** (1 / yrs) - 1) * 100,
                sharpe=sharpe(x), ci_lo=lo, ci_hi=hi, win_rate=float((np.asarray(trades_net) > 0).mean()), avg_trade_pct=float(np.mean(trades_net)) * 100,
                max_drawdown_pct=(eq / np.maximum.accumulate(eq) - 1).min() * 100, note=note)
def style(ax, title, sub):
    nl = sub.count('\n') + 1
    ax.set_title(title, loc='left', fontsize=12, fontweight='bold', color=INK, pad=9 + 13 * nl)
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9, color=INK2, va='bottom')
    ax.grid(axis='y', color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    for s in ('top', 'right', 'left'): ax.spines[s].set_visible(False)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f'{v:+.0f}%'))
    ax.tick_params(length=0)
def endlabel(ax, x, y, text, color):
    ax.plot([x], [y], 'o', color=color, markersize=5, markeredgecolor=SURF, markeredgewidth=1.5, zorder=5)
    ax.annotate(text, (x, y), xytext=(6, 0), textcoords='offset points', va='center', fontsize=9, color=INK)

rows = []
# ---------------- 1. offering strategy ----------------
D = pd.read_csv(os.path.join(FDS, 'offer_strategy_daily.csv'), parse_dates=['date']); T = pd.read_csv(os.path.join(FDS, 'offer_strategy_trades.csv'))
T['e'] = pd.to_datetime(T.entry.astype(str))
rows.append(row('Offering short (stock vs XBI, 5 days)', 'all: 2025-01 to 2026-10', D.net, T.net, 'model is out of sample throughout; hold length and $1 price floor were chosen on this period'))
for lab, m, tm in (('first half: 2025', D.date < '2026-01-01', T.e < '2026-01-01'), ('second half: 2026', D.date >= '2026-01-01', T.e >= '2026-01-01')):
    rows.append(row('Offering short (stock vs XBI, 5 days)', lab, D.net[m], T.net[tm], 'split by calendar year to check stability'))
fig, ax = plt.subplots(figsize=(9, 4.6))
g, n = (np.cumprod(1 + D.gross) - 1) * 100, (np.cumprod(1 + D.net) - 1) * 100
ax.plot(D.date, g, color=ORANGE, linewidth=2, label='Before costs'); ax.plot(D.date, n, color=BLUE, linewidth=2, label='After real bid/ask costs and 30% borrow fee')
endlabel(ax, D.date.iloc[-1], g.iloc[-1], f'before costs {g.iloc[-1]:+.0f}%', ORANGE); endlabel(ax, D.date.iloc[-1], n.iloc[-1], f'after costs {n.iloc[-1]:+.0f}%', BLUE)
style(ax, 'Offering strategy: equity curve', f'Short flagged stocks, hedge with XBI, hold 5 days. {len(T)} trades, 20% of capital each. Sharpe after costs {sharpe(D.net):+.2f}.')
ax.legend(frameon=False, loc='upper left', fontsize=9); ax.set_xlim(D.date.iloc[0] - pd.Timedelta(days=12), D.date.iloc[-1] + pd.Timedelta(days=150)); fig.tight_layout(); fig.savefig(os.path.join(OUT, 'equity_offering.png'), dpi=150); plt.close(fig)

# ---------------- 2. trial registry strategy: design vs holdout ----------------
fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
for ax, st, lab in ((axes[0], 'design', 'In sample (rules chosen here)'), (axes[1], 'holdout', 'Out of sample (never looked at)')):
    d = pd.read_csv(os.path.join(FDS, f'strategy_audit_daily_{st}.csv'), parse_dates=['date']); t = pd.read_csv(os.path.join(FDS, f'strategy_audit_trades_{st}.csv'))
    rows.append(row('Trial registry stage (60 days, vs XBI)', 'in sample: 2024-01 to 2025-09' if st == 'design' else 'out of sample: 2025-07 to 2026-10', d.net_both, t.net_ret,
                    'rules were chosen on the in-sample half' if st == 'design' else 'one run, rule unchanged'))
    g, n = (np.cumprod(1 + d.gross_both) - 1) * 100, (np.cumprod(1 + d.net_both) - 1) * 100
    ax.plot(d.date, g, color=ORANGE, linewidth=2, label='Before costs'); ax.plot(d.date, n, color=BLUE, linewidth=2, label='After costs')
    endlabel(ax, d.date.iloc[-1], g.iloc[-1], f'{g.iloc[-1]:+.0f}%', ORANGE); endlabel(ax, d.date.iloc[-1], n.iloc[-1], f'{n.iloc[-1]:+.0f}%', BLUE)
    style(ax, lab, f'{len(t)} trades. Sharpe after costs {sharpe(d.net_both):+.2f}.'); ax.margins(x=0.12)
    ax.tick_params(axis='x', labelrotation=30)
axes[0].legend(frameon=False, loc='upper left', fontsize=9)
fig.suptitle('Trial registry strategy: worked on the data it was designed on, failed on new data', x=0.01, ha='left', fontsize=12, fontweight='bold', color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.94)); fig.savefig(os.path.join(OUT, 'equity_trial_registry.png'), dpi=150); plt.close(fig)

S = pd.DataFrame(rows).drop(columns=['start'])
S.to_csv(os.path.join(OUT, 'summary_table.csv'), index=False)
pd.set_option('display.width', 250)
print(S[['strategy', 'sample', 'trades', 'total_pnl_pct', 'annual_return_pct', 'sharpe', 'ci_lo', 'ci_hi', 'win_rate', 'avg_trade_pct', 'max_drawdown_pct']].round(2).to_string(index=False))

# ---------------- 3. team backtest output (if it has been copied back) ----------------
STR = ['stock', 'long_call', 'covered_call', 'protective_put', 'collar', 'cash_secured_put']
lead = []
for f in sorted(glob.glob(os.path.join(a.lead, 'out_*'))):
    p = os.path.join(f, 'results.csv')
    if not os.path.exists(p) or 'smoke' in f: continue
    r = pd.read_csv(p); man = json.load(open(os.path.join(f, 'manifest.json')))
    r['window'] = 'in sample ' + man['start'][:4] + '-' + man['end'][:4] if man['start'] < '2026' else 'out of sample 2026'
    r['tag'] = man['tag']; lead.append(r)
if lead:
    R = pd.concat(lead); R['horizon'] = R.horizon.astype(str)
    out = []
    for (tag, win, entry, bucket, h), g in R[(R.otm == 0.05) & R.horizon.isin(['5', '10', '21', '42'])].groupby(['tag', 'window', 'entry', 'bucket', 'horizon']):
        held = g.sessions_held.mean()
        for s in STR:
            x = g[s].dropna().values
            if len(x) < 10 or x.std(ddof=1) == 0: continue
            k = np.sqrt(252 / held); xb = x[rng.integers(0, len(x), (a.boot, len(x)))]; sb = xb.mean(1) / xb.std(1, ddof=1) * k
            out.append(dict(tag=tag, window=win, entry=entry, bucket=bucket, horizon=int(h), strategy=s, n=len(x), tickers=g.ticker.nunique(), mean_pnl_pct=x.mean() * 100,
                            median_pnl_pct=np.median(x) * 100, win_rate=(x > 0).mean(), sharpe=x.mean() / x.std(ddof=1) * k, ci_lo=np.percentile(sb, 2.5), ci_hi=np.percentile(sb, 97.5)))
    L = pd.DataFrame(out); L.to_csv(os.path.join(OUT, 'team_backtest_table.csv'), index=False)
    print('\nTEAM BACKTEST rows:', len(L), '| events per window:', R.drop_duplicates(['window', 'ticker', 'event_date']).groupby('window').size().to_dict())
    R.to_csv(os.path.join(OUT, 'team_backtest_results_all.csv'), index=False)
    # equity curves from the team backtest: add up the per event result in date order (equal stake per event, no costs)
    cells = [('stock', '10', BLUE, 'Stock, 10 days (the question set before the run)'), ('cash_secured_put', '5', ORANGE, 'Cash secured put, 5 days (noticed after the run)')]
    wins = sorted(R.window.unique())
    fig, axes = plt.subplots(1, len(wins), figsize=(11, 4.6), sharey=True)
    for ax, w in zip(np.atleast_1d(axes), wins):
        sub = []
        for s, h, col, lab in cells:
            g = R[(R.window == w) & (R.entry == 'post') & (R.bucket == '1m') & (R.horizon == h) & np.isclose(R.otm, 0.05)].dropna(subset=[s]).sort_values('entry_date')
            if len(g) < 3: continue
            d = pd.to_datetime(g.entry_date); c = g[s].cumsum().values * 100
            ax.plot(d, c, color=col, linewidth=2, label=lab, marker='o', markersize=3)
            endlabel(ax, d.iloc[-1], c[-1], f'{c[-1]:+.0f}%', col)
            k = np.sqrt(252 / g.sessions_held.mean()); sub.append(f'{s.replace("_", " ")}: n {len(g)}, win {(g[s] > 0).mean():.0%}, Sharpe {g[s].mean() / g[s].std(ddof=1) * k:+.2f}')
        style(ax, w.capitalize(), '\n'.join(sub)); ax.margins(x=0.12); ax.tick_params(axis='x', labelrotation=30)
    h_, l_ = np.atleast_1d(axes)[0].get_legend_handles_labels(); fig.legend(h_, l_, frameon=False, loc='lower center', ncol=2, fontsize=9)
    fig.suptitle('Team backtest on HiPerGator: biologics, after a public offering 8-K (running total per event, no costs)', x=0.01, ha='left', fontsize=12, fontweight='bold', color=INK)
    fig.tight_layout(rect=(0, 0.06, 1, 0.94)); fig.savefig(os.path.join(OUT, 'equity_team_backtest.png'), dpi=150); plt.close(fig)
else:
    print('\nteam backtest output not found yet in', a.lead)
print('\ncharts and tables written to', os.path.abspath(OUT))
