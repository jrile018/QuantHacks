"""
48_offer_v3.py - the offering short on the VERSION 2 dataset (script 16, rebuilt after the lead's audit), plus matched controls.

What changed versus script 44: the dataset itself no longer holds the five split-adjusted columns, the SEC-letter count, or the
current-snapshot trial columns; it holds the real close, real market cap, trial features from monthly registry snapshots, and a
news clock at 16:00 New York. So nothing is dropped here: the model sees every column in fds_features.csv (+ the options block).
Same model, same walk-forward (quarterly, 12 day gap), same rule (top 2% per day, 5 day hold, real close >= $1, ADV >= $1M).

Matched controls (lead's repair item 7): for every traded signal, up to 3 other eligible names on the SAME day that were NOT flagged,
matched on market cap bucket, runway bucket and dollar-volume bucket. Same hedge, same hold, bar prices (no quotes for controls).

Run:  python 48_offer_v3.py        Output: data/fds/offer_signal_slice_v3.csv, offer_trades_v3.csv, offer_controls_v3.csv
"""
import os, argparse
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--top', type=float, default=0.02); ap.add_argument('--min_adv', type=float, default=1.0); ap.add_argument('--min_px', type=float, default=1.0)
ap.add_argument('--gap', type=int, default=12); ap.add_argument('--hold', type=int, default=5); ap.add_argument('--boot', type=int, default=5000)
ap.add_argument('--is_start', default='2025-01-01'); ap.add_argument('--is_end', default='2025-10-31'); ap.add_argument('--os_start', default='2025-11-01'); ap.add_argument('--os_end', default='2026-08-31')
a = ap.parse_args()
fds = os.path.join(a.data, 'fds'); rng = np.random.default_rng(7)
IS0, IS1, OS0, OS1 = map(pd.Timestamp, (a.is_start, a.is_end, a.os_start, a.os_end))
FORBIDDEN = ['px_close_raw', 'fin_shares_adj_m', 'fin_mktcap_m_old', 'fin_log_mktcap_old', 'fin_liq_to_mcap_old', 'fil_seccorr_n180']

X = pd.read_csv(os.path.join(fds, 'fds_features.csv')).merge(pd.read_csv(os.path.join(fds, 'fds_options.csv')), on=['cik', 'date'])
X = X.merge(pd.read_csv(os.path.join(fds, 'fds_labels.csv'), usecols=['cik', 'date', 'y_8k_next5_offer']), on=['cik', 'date'])
bad = [c for c in X.columns if c in FORBIDDEN]; assert not bad, f'dataset still holds unsafe columns {bad}; rebuild with 16_build_fds.py v2'
assert 'px_close_real' in X.columns and 'tr_snapshot_age_days' in X.columns, 'this is not the v2 dataset'
X['d'] = pd.to_datetime(X.date.astype(str)); X = X.sort_values(['d', 'cik']).reset_index(drop=True)
lk = pd.read_csv(os.path.join(fds, 'fds_lookup_cik_ticker.csv')); c2t = dict(zip(lk.cik.astype(int), lk.ticker)); X['tk'] = X.cik.astype(int).map(c2t)
feats = [c for c in X.columns if c not in ('cik', 'date', 'd', 'tk', 'y_8k_next5_offer')]
print(f'rows {len(X)} | features {len(feats)} | dataset version 2 (real prices, snapshot trials)')
X = X[X.y_8k_next5_offer.notna()].reset_index(drop=True)

P = pd.read_csv(os.path.join(a.data, 'raw', 'prices.csv'), usecols=['ticker', 'date', 'open', 'close']); P['date'] = pd.to_datetime(P.date)
O = P.pivot(index='date', columns='ticker', values='open'); Cc = P.pivot(index='date', columns='ticker', values='close'); cal = O.index; pos = {d: i for i, d in enumerate(cal)}

pred = pd.Series(np.nan, index=X.index); aucs = []
for q in pd.period_range('2025-01', '2026-09', freq='Q'):
    t0, t1 = q.start_time, q.end_time
    te = X.index[(X.d >= t0) & (X.d <= t1)]; tr = X.index[X.d < t0 - pd.Timedelta(days=a.gap)]
    if len(te) == 0 or len(tr) < 5000: continue
    m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200, l2_regularization=5.0, random_state=0)
    m.fit(X.loc[tr, feats], X.loc[tr, 'y_8k_next5_offer']); pred.loc[te] = m.predict_proba(X.loc[te, feats])[:, 1]
    if X.loc[te, 'y_8k_next5_offer'].nunique() > 1: aucs.append((str(q), round(roc_auc_score(X.loc[te, 'y_8k_next5_offer'], pred.loc[te]), 3), int(X.loc[te, 'y_8k_next5_offer'].sum())))
print('AUC by quarter (quarter, AUC, offerings):', aucs)
T = X[pred.notna()].copy(); T['p'] = pred[pred.notna()]
T['ok'] = (T.px_adv20_usd_m >= a.min_adv) & (T.px_close_real >= a.min_px)
T['rk'] = T[T.ok].groupby('d').p.rank(pct=True, ascending=False)
sel = T[T.ok & (T.rk <= a.top)].copy()
print(f'overall AUC {roc_auc_score(T.y_8k_next5_offer, T.p):.3f} | eligible company-days {int(T.ok.sum())} base rate {T[T.ok].y_8k_next5_offer.mean()*100:.2f}% | flagged company-days {len(sel)} hit rate {sel.y_8k_next5_offer.mean()*100:.1f}% ({int(sel.y_8k_next5_offer.sum())}/{len(sel)})')
for yr, g in sel.groupby(sel.d.dt.year): print(f'  {yr}: flagged {len(g)}, hit rate {g.y_8k_next5_offer.mean()*100:.1f}%')

def trade_rows(df, H):
    rows = []; busy = {}
    for r in df.sort_values('d').itertuples():
        tk = r.tk
        if tk not in O.columns or r.d not in pos: continue
        i = pos[r.d]
        if i + H >= len(cal) or busy.get(tk, -1) >= i: continue
        e, x = cal[i + 1], cal[i + H]; o, c = O.at[e, tk], Cc.at[x, tk]
        if not (o > 0 and c > 0): continue
        busy[tk] = i + H
        rows.append((r.cik, tk, r.d, e, x, r.p, r.y_8k_next5_offer, r.px_close_real, r.fin_mktcap_m, r.fin_runway_q, r.px_adv20_usd_m, c / o - 1, Cc.at[x, 'XBI'] / O.at[e, 'XBI'] - 1))
    t = pd.DataFrame(rows, columns=['cik', 'tk', 'd', 'entry', 'exit', 'p', 'hit', 'px_close_real', 'mktcap_m', 'runway_q', 'adv_m', 'stock', 'xbi']); t['gross'] = -t.stock + t.xbi
    return t
def line(x, H):
    x = np.asarray(x, float); n = len(x)
    if n < 8: return f'n {n:3d} too few'
    k = np.sqrt(252 / H); xb = x[rng.integers(0, n, (a.boot, n))]; sb = xb.mean(1) / xb.std(1, ddof=1) * k
    return f'n {n:3d}  avg {x.mean()*100:+6.2f}%  median {np.median(x)*100:+6.2f}%  win {(x > 0).mean()*100:3.0f}%  Sharpe {x.mean()/x.std(ddof=1)*k:+5.2f}  95% [{np.percentile(sb, 2.5):+.2f}, {np.percentile(sb, 97.5):+.2f}]'
def windows(t, col, H, name):
    print(f'  {name}'); print(f'    in sample     {line(t[(t.d >= IS0) & (t.d <= IS1)][col], H)}'); print(f'    out of sample {line(t[(t.d >= OS0) & (t.d <= OS1)][col], H)}')

print('\nBEFORE COSTS, bar prices (next open to close H sessions after the signal), short stock + long XBI')
for H in (1, 3, 5, 10):
    t = trade_rows(sel, H); windows(t, 'gross', H, f'{H} day hold, trades {len(t)}')
t = trade_rows(sel, a.hold)

# ---------- matched controls ----------
elig = T[T.ok & (T.rk > a.top)].copy()
def bucket(s, edges): return np.digitize(s.fillna(-1), edges)
for df in (elig, t):
    df['b_cap'] = bucket(df['fin_mktcap_m'] if 'fin_mktcap_m' in df else df['mktcap_m'], [50, 150, 500, 2000])
    df['b_run'] = bucket(df['fin_runway_q'] if 'fin_runway_q' in df else df['runway_q'], [2, 4, 8])
    df['b_adv'] = bucket(df['px_adv20_usd_m'] if 'px_adv20_usd_m' in df else df['adv_m'], [3, 10, 50])
ctl_rows = []; by_day = {d: g for d, g in elig.groupby('d')}
for r in t.itertuples():
    g = by_day.get(r.d)
    if g is None: continue
    g = g[(g.b_cap == r.b_cap) & (g.b_run == r.b_run)]
    if len(g) > 3: g = g.sample(3, random_state=int(r.cik) % 1000)
    for c in g.itertuples(): ctl_rows.append(dict(trade_cik=r.cik, trade_tk=r.tk, d=r.d, cik=c.cik, tk=c.tk, p=c.p, y_8k_next5_offer=c.y_8k_next5_offer, px_close_real=c.px_close_real, fin_mktcap_m=c.fin_mktcap_m, fin_runway_q=c.fin_runway_q, px_adv20_usd_m=c.px_adv20_usd_m))
CT = pd.DataFrame(ctl_rows)
ct = trade_rows(CT.rename(columns={}), a.hold) if len(CT) else pd.DataFrame()
print(f'\nMATCHED CONTROLS: {len(CT)} control company-days for {CT.trade_cik.nunique() if len(CT) else 0} traded signals (same day, same market cap and runway bucket, not flagged)')
if len(ct): windows(ct, 'gross', a.hold, f'controls, {a.hold} day hold, before costs'); print(f'    control offering rate within 5 days: {ct.hit.mean()*100:.1f}% (model picks: {t.hit.mean()*100:.1f}%)')
rnd = trade_rows(T[T.ok].sample(len(sel), random_state=1), a.hold); windows(rnd, 'gross', a.hold, 'random eligible company-days, same count')

t['signal'] = t.d.dt.strftime('%Y%m%d').astype(int)
t.to_csv(os.path.join(fds, 'offer_trades_v3.csv'), index=False)
sel[['cik', 'date', 'p', 'y_8k_next5_offer', 'px_close_real']].to_csv(os.path.join(fds, 'offer_signal_slice_v3.csv'), index=False)
if len(ct): ct.assign(signal=ct.d.dt.strftime('%Y%m%d').astype(int)).to_csv(os.path.join(fds, 'offer_controls_v3.csv'), index=False)
old = pd.read_csv(os.path.join(fds, 'stock_trades_real_v2.csv'), usecols=['cik', 'signal'])
same = t.merge(old, on=['cik', 'signal']); print(f'\ntrades {len(t)} | already have real quotes from the v2 list: {len(same)} | need new quotes: {len(t) - len(same)}')
print('saved offer_signal_slice_v3.csv, offer_trades_v3.csv, offer_controls_v3.csv')
