"""
44_offer_noleak.py - the offering short, redone WITHOUT future information.

What was wrong (found by our own check): raw/prices.csv is adjusted for splits that happened later, so five columns
(px_close_raw, fin_shares_adj_m, fin_mktcap_m, fin_log_mktcap, fin_liq_to_mcap) and the ">= $1" filter could see future reverse splits.
What this script does:
  1. real price on day t = adjusted close / (product of split ratios of splits AFTER t), from raw/splits.csv (script 43)
  2. real market cap = real price x cover page shares (shares corrected only for splits that already happened by day t)
  3. retrains the same model without the five columns, with the four rebuilt ones, with a 12 day training gap
  4. trades only stocks whose REAL close on the signal day is at least $1 (known at the time, decided before the trade)
  5. prints the standard table (team windows, same formulas as script 42), and the old leaky version next to it
Run:  python 44_offer_noleak.py        (about 2 minutes)
"""
import os, argparse
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--top', type=float, default=0.02); ap.add_argument('--min_adv', type=float, default=1.0); ap.add_argument('--min_px', type=float, default=1.0)
ap.add_argument('--gap', type=int, default=12); ap.add_argument('--boot', type=int, default=5000); ap.add_argument('--borrow', type=float, default=0.30)
ap.add_argument('--skip_old', action='store_true')
ap.add_argument('--is_start', default='2025-01-01'); ap.add_argument('--is_end', default='2025-10-31')      # same default windows as script 42
ap.add_argument('--os_start', default='2025-11-01'); ap.add_argument('--os_end', default='2026-08-31')
a = ap.parse_args()
fds = os.path.join(a.data, 'fds'); rng = np.random.default_rng(7)
IS0, IS1, OS0, OS1 = pd.Timestamp(a.is_start), pd.Timestamp(a.is_end), pd.Timestamp(a.os_start), pd.Timestamp(a.os_end)
print(f'windows: in sample {IS0.date()} to {IS1.date()} | out of sample {OS0.date()} to {OS1.date()}')
LEAKY = ['px_close_raw', 'fin_shares_adj_m', 'fin_mktcap_m', 'fin_log_mktcap', 'fin_liq_to_mcap']

X = pd.read_csv(os.path.join(fds, 'fds_features.csv')).merge(pd.read_csv(os.path.join(fds, 'fds_options.csv')), on=['cik', 'date'])
X = X.merge(pd.read_csv(os.path.join(fds, 'fds_labels.csv'), usecols=['cik', 'date', 'y_8k_next5_offer']), on=['cik', 'date'])
X['d'] = pd.to_datetime(X.date.astype(str)); X = X.sort_values(['d', 'cik']).reset_index(drop=True)
lk = pd.read_csv(os.path.join(fds, 'fds_lookup_cik_ticker.csv')); c2t = dict(zip(lk.cik.astype(int), lk.ticker)); X['tk'] = X.cik.astype(int).map(c2t)

# ---------- 1 and 2: real price and real market cap ----------
S = pd.read_csv(os.path.join(a.data, 'raw', 'splits.csv'), parse_dates=['execution_date']); S['r'] = S.split_from / S.split_to
X['R_after'] = 1.0; X['R_since_filing'] = 1.0
filed = X.d - pd.to_timedelta(X.fin_age_pub_days.fillna(0), unit='D')          # day the share count in this row was filed
for tk, g in S.groupby('ticker'):
    m = (X.tk == tk).to_numpy()
    if not m.any(): continue
    d = X.loc[m, 'd'].to_numpy(); f = filed[m].to_numpy(); ra = np.ones(m.sum()); rs = np.ones(m.sum())
    for e, r in zip(g.execution_date.to_numpy(), g.r.to_numpy()):
        ra[d < e] *= r                       # split still in the future on day d: undo the adjustment
        rs[(f < e) & (d >= e)] *= r          # split happened after the share count was filed, before day d: convert the old count
    X.loc[m, 'R_after'] = ra; X.loc[m, 'R_since_filing'] = rs
X['px_close_real'] = X.px_close_raw / X.R_after
X['fin_mktcap_real_m'] = X.px_close_real * X.fin_shares_m / X.R_since_filing
X['fin_log_mktcap_real'] = np.log(X.fin_mktcap_real_m.where(X.fin_mktcap_real_m > 0))
X['fin_liq_to_mcap_real'] = X.fin_liq_m / X.fin_mktcap_real_m.where(X.fin_mktcap_real_m > 0)
chg = X[X.px_close_raw.notna()]
print(f'rows {len(X)} | rows where the stored price was not the real price: {(chg.R_after != 1).sum()} ({(chg.R_after != 1).mean()*100:.1f}%) in {chg[chg.R_after != 1].tk.nunique()} tickers')
both = X[(X.fin_mktcap_m > 0) & (X.fin_mktcap_real_m > 0)]; q = both.fin_mktcap_m / both.fin_mktcap_real_m
print(f'stored market cap vs rebuilt: same within 10% in {((q > .9) & (q < 1.1)).mean()*100:.1f}% of rows, off by more than 2x in {((q > 2) | (q < .5)).mean()*100:.1f}%')
X[['cik', 'date', 'px_close_real', 'fin_mktcap_real_m', 'fin_log_mktcap_real', 'fin_liq_to_mcap_real']].to_csv(os.path.join(fds, 'fds_realprice.csv'), index=False)

skip = {'cik', 'date', 'd', 'tk', 'y_8k_next5_offer', 'R_after', 'R_since_filing'}
NEW = ['px_close_real', 'fin_mktcap_real_m', 'fin_log_mktcap_real', 'fin_liq_to_mcap_real']
feats_old = [c for c in X.columns if c not in skip and c not in NEW]
feats_new = [c for c in X.columns if c not in skip and c not in LEAKY]
X = X[X.y_8k_next5_offer.notna()].reset_index(drop=True)

P = pd.read_csv(os.path.join(a.data, 'raw', 'prices.csv'), usecols=['ticker', 'date', 'open', 'close']); P['date'] = pd.to_datetime(P.date)
O = P.pivot(index='date', columns='ticker', values='open'); Cc = P.pivot(index='date', columns='ticker', values='close'); cal = O.index; pos = {d: i for i, d in enumerate(cal)}

def walk(feats, gap):
    pred = pd.Series(np.nan, index=X.index)
    for q in pd.period_range('2025-01', '2026-09', freq='Q'):
        t0, t1 = q.start_time, q.end_time
        te = X.index[(X.d >= t0) & (X.d <= t1)]; tr = X.index[X.d < t0 - pd.Timedelta(days=gap)]
        if len(te) == 0 or len(tr) < 5000: continue
        m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=5.0, random_state=0)
        m.fit(X.loc[tr, feats], X.loc[tr, 'y_8k_next5_offer']); pred.loc[te] = m.predict_proba(X.loc[te, feats])[:, 1]
    return pred

def select(p, pxcol):
    T = X[p.notna()].copy(); T['p'] = p[p.notna()]
    T['ok'] = (T.px_adv20_usd_m >= a.min_adv) & (T[pxcol] >= a.min_px)
    T['rk'] = T[T.ok].groupby('d').p.rank(pct=True, ascending=False)
    return T, T[T.ok & (T.rk <= a.top)]

def trades(sel, H):
    rows = []; busy = {}
    for r in sel.sort_values('d').itertuples():
        tk = r.tk
        if tk not in O.columns or r.d not in pos: continue
        i = pos[r.d]
        if i + H >= len(cal) or busy.get(tk, -1) >= i: continue
        e, x = cal[i + 1], cal[i + H]; o, c = O.at[e, tk], Cc.at[x, tk]
        if not (o > 0 and c > 0): continue
        busy[tk] = i + H
        rows.append((r.cik, tk, r.d, e, x, r.p, r.y_8k_next5_offer, r.px_close_real, c / o - 1, Cc.at[x, 'XBI'] / O.at[e, 'XBI'] - 1))
    t = pd.DataFrame(rows, columns=['cik', 'tk', 'd', 'entry', 'exit', 'p', 'hit', 'px_close_real', 'stock', 'xbi']); t['gross'] = -t.stock + t.xbi
    return t

def line(x, H):
    x = np.asarray(x, float); n = len(x)
    if n < 8: return f'n {n:3d} too few'
    k = np.sqrt(252 / H); xb = x[rng.integers(0, n, (a.boot, n))]; sb = xb.mean(1) / xb.std(1, ddof=1) * k
    return f'n {n:3d}  avg {x.mean()*100:+6.2f}%  median {np.median(x)*100:+6.2f}%  win {(x > 0).mean()*100:3.0f}%  Sharpe {x.mean()/x.std(ddof=1)*k:+5.2f}  95% [{np.percentile(sb, 2.5):+.2f}, {np.percentile(sb, 97.5):+.2f}]'

def windows(t, col, H, name):
    print(f'  {name}')
    print(f'    in sample     {line(t[(t.d >= IS0) & (t.d <= IS1)][col], H)}')
    print(f'    out of sample {line(t[(t.d >= OS0) & (t.d <= OS1)][col], H)}')

def auc(p):
    m = p.notna(); return roc_auc_score(X.loc[m, 'y_8k_next5_offer'], p[m])

if not a.skip_old:
    p_old = walk(feats_old, 7); T, sel_old = select(p_old, 'px_close_raw')
    print(f'\nOLD (with the leak, 7 day gap, filter on the stored price): AUC {auc(p_old):.3f} | hit rate in traded slice {sel_old.y_8k_next5_offer.mean()*100:.1f}% vs base {T[T.ok].y_8k_next5_offer.mean()*100:.1f}%')
    t = trades(sel_old, 5); print(f'  trades {len(t)} | real close under $1 on the signal day: {(t.px_close_real < 1).sum()}')
    windows(t, 'gross', 5, 'before costs, all trades, 5 day hold'); windows(t[t.px_close_real >= 1], 'gross', 5, 'before costs, real close at least $1 on the signal day')

p_new = walk(feats_new, a.gap); T, sel = select(p_new, 'px_close_real')
print(f'\nNEW (no leak, {a.gap} day gap, filter on the real price): AUC {auc(p_new):.3f} | hit rate in traded slice {sel.y_8k_next5_offer.mean()*100:.1f}% vs base {T[T.ok].y_8k_next5_offer.mean()*100:.1f}%')
for yr, g in sel.groupby(sel.d.dt.year): print(f'  {yr}: flagged company-days {len(g)}, hit rate {g.y_8k_next5_offer.mean()*100:.1f}%')
for H in (1, 3, 5, 10):
    t = trades(sel, H); windows(t, 'gross', H, f'before costs, {H} day hold, trades {len(t)}')
t = trades(sel, 5)
ctl = trades(T[T.ok].sample(len(sel), random_state=1), 5); windows(ctl, 'gross', 5, 'CONTROL: random liquid company-days, same count, 5 day hold')

# costs: reuse the measured bid/ask cost where the same trade was already priced from real quotes (script 22)
old = pd.read_csv(os.path.join(fds, 'stock_trades_real_adj.csv'), usecols=['tk', 'signal', 'cost'])
t['signal'] = t.d.dt.strftime('%Y%m%d').astype(int); t = t.merge(old, on=['tk', 'signal'], how='left')
have = t.cost.notna(); print(f'\n5 day trades {len(t)} | already priced from real quotes: {have.sum()} | new, need quotes: {(~have).sum()}')
t['cost_est'] = t.cost.fillna(old.cost.median()); t['net'] = t.gross - t.cost_est - a.borrow * 5 / 252
print(f'  measured cost on the priced ones: mean {t.cost[have].mean()*100:.2f}%, median {t.cost[have].median()*100:.2f}% (the unpriced ones use the old median {old.cost.median()*100:.2f}% until script 22 is rerun)')
windows(t, 'net', 5, f'after costs (bid/ask + {a.borrow*100:.0f}%/yr borrow), 5 day hold')
windows(t[have], 'net', 5, 'after costs, only the trades with measured quotes')
t.to_csv(os.path.join(fds, 'offer_trades_v2.csv'), index=False)
sel[['cik', 'date', 'p', 'y_8k_next5_offer', 'px_close_real']].to_csv(os.path.join(fds, 'offer_signal_slice_v2.csv'), index=False)
print('\nsaved fds_realprice.csv, offer_signal_slice_v2.csv, offer_trades_v2.csv')
