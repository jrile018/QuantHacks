"""
21_stock_offer_test.py - does the snapshot make money by shorting stocks that are about to announce an offering?

Step 1  walk forward model: train only on the past (7 day gap), predict P(offering 8-K in next 5 days) for each company-day.
Step 2  trade: on days when P is in the top slice, short the stock at the NEXT day's open, cover at the close H days later.
        Hedge: buy the same dollar amount of XBI over the same window (removes the biotech market move).
Step 3  costs: show results after a grid of round trip trading costs and a borrow fee (annual %).
All numbers only. Prices come from raw/prices.csv (split adjusted). Run:  python 21_stock_offer_test.py
"""
import os, argparse
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--top', type=float, default=0.02, help='share of company-days traded each day (top by P)')
ap.add_argument('--min_adv', type=float, default=1.0, help='min 20d average dollar volume in millions')
ap.add_argument('--min_px', type=float, default=1.0)
a = ap.parse_args()
fds = os.path.join(a.data, 'fds')

X = pd.read_csv(os.path.join(fds, 'fds_features.csv'))
Xo = pd.read_csv(os.path.join(fds, 'fds_options.csv'))
Y = pd.read_csv(os.path.join(fds, 'fds_labels.csv'), usecols=['cik', 'date', 'y_8k_next5_offer'])
X = X.merge(Xo, on=['cik', 'date']).merge(Y, on=['cik', 'date'])
X['d'] = pd.to_datetime(X.date.astype(str))
X = X.sort_values(['d', 'cik']).reset_index(drop=True)
feats = [c for c in X.columns if c not in ('cik', 'date', 'd', 'y_8k_next5_offer')]
X = X[X.y_8k_next5_offer.notna()].reset_index(drop=True)

# prices: ticker for each cik, open/close matrices
lk = pd.read_csv(os.path.join(fds, 'fds_lookup_cik_ticker.csv')); c2t = dict(zip(lk.cik.astype(int), lk.ticker))
P = pd.read_csv(os.path.join(a.data, 'raw', 'prices.csv'), usecols=['ticker', 'date', 'open', 'close'])
P['date'] = pd.to_datetime(P.date)
O = P.pivot(index='date', columns='ticker', values='open'); Cc = P.pivot(index='date', columns='ticker', values='close')
cal = O.index
pos = {d: i for i, d in enumerate(cal)}

# ---------- walk forward predictions ----------
qs = pd.period_range('2025-01', '2026-09', freq='Q')
pred = pd.Series(np.nan, index=X.index)
for q in qs:
    t0, t1 = q.start_time, q.end_time
    te = X.index[(X.d >= t0) & (X.d <= t1)]
    tr = X.index[X.d < t0 - pd.Timedelta(days=7)]
    if len(te) == 0 or len(tr) < 5000: continue
    m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=200,
                                       l2_regularization=5.0, random_state=0)
    m.fit(X.loc[tr, feats], X.loc[tr, 'y_8k_next5_offer'])
    pred.loc[te] = m.predict_proba(X.loc[te, feats])[:, 1]
    print(q, 'train', len(tr), 'test', len(te), 'AUC', round(roc_auc_score(X.loc[te, 'y_8k_next5_offer'], pred.loc[te]), 3)
          if X.loc[te, 'y_8k_next5_offer'].nunique() > 1 else '')
X['p'] = pred
T = X[X.p.notna()].copy()
print('out of sample rows', len(T), 'base rate', round(T.y_8k_next5_offer.mean(), 4), 'overall AUC',
      round(roc_auc_score(T.y_8k_next5_offer, T.p), 3))
T['ok'] = (T.px_adv20_usd_m >= a.min_adv) & (T.px_close_raw >= a.min_px)
T['rk'] = T[T.ok].groupby('d').p.rank(pct=True, ascending=False)
sel = T[T.ok & (T.rk <= a.top)]
print('precision in traded slice', round(sel.y_8k_next5_offer.mean(), 4), 'vs base', round(T[T.ok].y_8k_next5_offer.mean(), 4),
      'lift', round(sel.y_8k_next5_offer.mean() / T[T.ok].y_8k_next5_offer.mean(), 2))

# ---------- trades ----------
def trades(df, H):
    rows = []; busy = {}
    for r in df.sort_values('d').itertuples():
        tk = c2t.get(int(r.cik));
        if tk not in O.columns or r.d not in pos: continue
        i = pos[r.d]
        if i + 1 + (H - 1) >= len(cal): continue
        if busy.get(tk, -1) >= i: continue
        e, x = cal[i + 1], cal[i + H]
        o, c = O.at[e, tk], Cc.at[x, tk]
        xo, xc = O.at[e, 'XBI'], Cc.at[x, 'XBI']
        if not (o > 0 and c > 0): continue
        busy[tk] = i + H
        rows.append((r.d, tk, c / o - 1, xc / xo - 1, r.y_8k_next5_offer))
    return pd.DataFrame(rows, columns=['d', 'tk', 'stock', 'xbi', 'hit'])

def report(tr, H, name):
    if len(tr) < 20: print(name, 'too few trades', len(tr)); return
    g = -(tr.stock) + tr.xbi          # short stock, long XBI
    print(f'\n{name}  H={H}d  trades {len(tr)}  offering within 5d {tr.hit.mean():.3f}')
    print(f'  short stock gross mean {-tr.stock.mean():+.4f} | hedged gross mean {g.mean():+.4f} median {g.median():+.4f} win {(g>0).mean():.2f}')
    byd = g.groupby(tr.d.dt.to_period('M')).mean()          # monthly blocks for a cautious t stat
    tstat = byd.mean() / (byd.std() / np.sqrt(len(byd))) if len(byd) > 2 and byd.std() > 0 else float('nan')
    print(f'  monthly blocks {len(byd)}  mean {byd.mean():+.4f}  t {tstat:.2f}   share of months positive {(byd>0).mean():.2f}')
    for cost in (0.005, 0.01, 0.02, 0.03):
        for borrow in (0.0, 0.30):
            net = g - cost - borrow * H / 252
            print(f'  round trip cost {cost*100:.1f}%  borrow {borrow*100:.0f}%/yr  ->  mean {net.mean():+.4f}  win {(net>0).mean():.2f}')
    be = g.mean() - 0.0
    print(f'  break even round trip cost (no borrow fee): {be*100:.2f}% of trade')

for H in (1, 3, 5):
    report(trades(sel, H), H, 'TOP SLICE BY MODEL')
# comparison: all liquid names with the same hedge, and random same-size slice
allok = T[T.ok]
rs = allok.sample(len(sel), random_state=1)
report(trades(rs, 5), 5, 'RANDOM SAME SIZE (control)')
sel.to_csv(os.path.join(fds, 'offer_signal_slice.csv'), index=False, columns=['cik', 'date', 'p', 'y_8k_next5_offer'])
