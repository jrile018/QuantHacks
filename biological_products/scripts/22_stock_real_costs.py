"""
22_stock_real_costs.py - redo the stock offering trade (script 21) with REAL bid/ask quotes from Massive.

Trade: signal day t -> short the stock at the first quote after 9:30:30 ET on day t+1 (sell at the BID),
       cover at the last quote before 15:59:50 ET on day t+H (buy at the ASK).
       Hedge: buy XBI at the ask on entry, sell at the bid on exit. Same dollars on both sides.
Needs data/fds/offer_signal_slice.csv (written by script 21). Key from MASSIVE_API_KEY.

Test first:  python 22_stock_real_costs.py --limit 5
Full run  :  python 22_stock_real_costs.py            (saves as it goes, safe to restart)
Output    :  data/fds/stock_trades_real.csv  (numbers only) and a summary in the terminal.
"""
import os, sys, time, csv, argparse, threading, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests

K = os.environ.get('MASSIVE_API_KEY')
if not K:
    sys.exit('Set the key first in PowerShell:  $env:MASSIVE_API_KEY="your_key_here"')
B = 'https://api.massive.com'
ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--hold', type=int, default=5)
ap.add_argument('--limit', type=int, default=0)
ap.add_argument('--workers', type=int, default=6)
ap.add_argument('--summary_only', action='store_true')
a = ap.parse_args()
FDS = os.path.join(a.data, 'fds'); H = a.hold
OUT = os.path.join(FDS, 'stock_trades_real.csv')

def nth_sunday(y, m, n):
    d = dt.date(y, m, 1); d += dt.timedelta(days=(6 - d.weekday()) % 7); return d + dt.timedelta(weeks=n - 1)
def et_off(d): return 4 if nth_sunday(d.year, 3, 2) <= d < nth_sunday(d.year, 11, 1) else 5
def ns(d, h, m, s=0):
    return int(dt.datetime(d.year, d.month, d.day, h + et_off(d), m, s, tzinfo=dt.timezone.utc).timestamp() * 1e9)

tls = threading.local()
def get(path, params):
    if not hasattr(tls, 's'): tls.s = requests.Session()
    p = dict(params); p['apiKey'] = K
    for att in range(6):
        try:
            r = tls.s.get(B + path, params=p, timeout=40)
            if r.status_code == 429 or r.status_code >= 500: time.sleep(1.5 * (att + 1)); continue
            return r.json()
        except Exception: time.sleep(1.5 * (att + 1))
    return {}

def first_after(tk, t):   # first valid quote at or after t (same day, within 20 minutes)
    j = get(f'/v3/quotes/{tk}', {'timestamp.gte': t, 'order': 'asc', 'sort': 'timestamp', 'limit': 20})
    for q in j.get('results') or []:
        if q['sip_timestamp'] > t + 20 * 60 * 10**9: break
        if q.get('bid_price', 0) > 0 and q.get('ask_price', 0) >= q['bid_price']: return q
    return None
def last_before(tk, t):   # last valid quote at or before t (same day, within 60 minutes)
    j = get(f'/v3/quotes/{tk}', {'timestamp.lte': t, 'order': 'desc', 'sort': 'timestamp', 'limit': 20})
    for q in j.get('results') or []:
        if q['sip_timestamp'] < t - 60 * 60 * 10**9: break
        if q.get('bid_price', 0) > 0 and q.get('ask_price', 0) >= q['bid_price']: return q
    return None

# ---------- build the trade list the same way as script 21 ----------
lk = pd.read_csv(os.path.join(FDS, 'fds_lookup_cik_ticker.csv')); c2t = dict(zip(lk.cik.astype(int), lk.ticker))
S = pd.read_csv(os.path.join(FDS, 'offer_signal_slice.csv'))
S['d'] = pd.to_datetime(S.date.astype(str)); S = S.sort_values('d')
cal = pd.DatetimeIndex(sorted(pd.read_csv(os.path.join(a.data, 'raw', 'prices.csv'), usecols=['ticker', 'date']).query("ticker=='SPY'").date.pipe(pd.to_datetime).unique()))
pos = {d: i for i, d in enumerate(cal)}
trades = []; busy = {}
for r in S.itertuples():
    tk = c2t.get(int(r.cik))
    if tk is None or r.d not in pos: continue
    i = pos[r.d]
    if i + H >= len(cal) or busy.get(tk, -1) >= i: continue
    busy[tk] = i + H
    trades.append(dict(cik=int(r.cik), tk=tk, signal=r.date, entry=cal[i + 1].date(), exit=cal[i + H].date(), p=r.p, hit=r.y_8k_next5_offer))

F = ['cik', 'tk', 'signal', 'entry', 'exit', 'p', 'hit', 'status',
     's_in_bid', 's_in_ask', 's_out_bid', 's_out_ask', 'x_in_bid', 'x_in_ask', 'x_out_bid', 'x_out_ask',
     'spread_in', 'spread_out', 'ret_mid', 'ret_real', 'xbi_mid', 'xbi_real', 'hedged_mid', 'hedged_real']
def one(t):
    row = {k: np.nan for k in F}; row.update({k: t[k] for k in ('cik', 'tk', 'signal', 'p', 'hit')})
    row['entry'] = int(t['entry'].strftime('%Y%m%d')); row['exit'] = int(t['exit'].strftime('%Y%m%d'))
    e, x = t['entry'], t['exit']
    si, so = first_after(t['tk'], ns(e, 9, 30, 30)), last_before(t['tk'], ns(x, 15, 59, 50))
    xi, xo = first_after('XBI', ns(e, 9, 30, 30)), last_before('XBI', ns(x, 15, 59, 50))
    if not (si and so): row['status'] = 2; return row
    row.update(s_in_bid=si['bid_price'], s_in_ask=si['ask_price'], s_out_bid=so['bid_price'], s_out_ask=so['ask_price'])
    mi, mo = (si['bid_price'] + si['ask_price']) / 2, (so['bid_price'] + so['ask_price']) / 2
    row['spread_in'] = (si['ask_price'] - si['bid_price']) / mi; row['spread_out'] = (so['ask_price'] - so['bid_price']) / mo
    row['ret_mid'] = (mi - mo) / mi                                   # short return at mid prices
    row['ret_real'] = (si['bid_price'] - so['ask_price']) / si['bid_price']   # sell at bid, buy back at ask
    if xi and xo:
        row.update(x_in_bid=xi['bid_price'], x_in_ask=xi['ask_price'], x_out_bid=xo['bid_price'], x_out_ask=xo['ask_price'])
        row['xbi_mid'] = ((xo['bid_price'] + xo['ask_price']) / (xi['bid_price'] + xi['ask_price'])) - 1
        row['xbi_real'] = xo['bid_price'] / xi['ask_price'] - 1
        row['hedged_mid'] = row['ret_mid'] + row['xbi_mid']; row['hedged_real'] = row['ret_real'] + row['xbi_real']
        row['status'] = 0
    else: row['status'] = 3
    return row

def summary():
    d = pd.read_csv(OUT); g = d[d.status == 0].copy()
    print(f'\ntrades planned {len(d)}  with all four quotes {len(g)}  (status counts {d.status.value_counts().to_dict()})')
    if len(g) < 10: return
    print(f'average spread in {g.spread_in.mean()*100:.2f}%  out {g.spread_out.mean()*100:.2f}%   median in {g.spread_in.median()*100:.2f}%')
    print(f'hedged return at mid prices (no spread cost): mean {g.hedged_mid.mean()*100:+.2f}%  median {g.hedged_mid.median()*100:+.2f}%')
    print(f'hedged return at real bid/ask             : mean {g.hedged_real.mean()*100:+.2f}%  median {g.hedged_real.median()*100:+.2f}%  win {(g.hedged_real>0).mean():.2f}')
    g['m'] = pd.to_datetime(g.entry.astype(str)).dt.to_period('M')
    bm = g.groupby('m').hedged_real.mean()
    if len(bm) > 2 and bm.std() > 0: print(f'monthly blocks {len(bm)}  mean {bm.mean()*100:+.2f}%  t {bm.mean()/(bm.std()/np.sqrt(len(bm))):.2f}  share positive {(bm>0).mean():.2f}')
    print('after a borrow fee (annual rate, charged for the hold):')
    for b in (0.0, 0.1, 0.3, 0.6, 1.0):
        print(f'   borrow {b*100:3.0f}%/yr -> mean {(g.hedged_real - b*H/252).mean()*100:+.2f}%  win {((g.hedged_real - b*H/252)>0).mean():.2f}')
    g['bk'] = pd.cut(g.spread_in, [0, .01, .02, .04, 1], labels=['<1%', '1-2%', '2-4%', '>4%'])
    print('by entry spread bucket:'); print(g.groupby('bk', observed=True).agg(n=('hedged_real', 'size'), mid=('hedged_mid', 'mean'), real=('hedged_real', 'mean'), hit=('hit', 'mean')).round(4).to_string())
    print('\nonly trades with entry spread under 2%:')
    h = g[g.spread_in < 0.02]
    if len(h): print(f'   n {len(h)}  mean real {h.hedged_real.mean()*100:+.2f}%  win {(h.hedged_real>0).mean():.2f}')

if a.summary_only:
    summary(); sys.exit()
done = set()
if os.path.exists(OUT) and os.path.getsize(OUT) > 0:
    d0 = pd.read_csv(OUT, usecols=['cik', 'signal']); done = set(zip(d0.cik, d0.signal))
todo = [t for t in trades if (t['cik'], t['signal']) not in done]
if a.limit: todo = todo[:a.limit]
print(f'planned trades {len(trades)}, done {len(done)}, to do now {len(todo)}', flush=True)
new = (not os.path.exists(OUT)) or os.path.getsize(OUT) == 0
fh = open(OUT, 'a', newline=''); w = csv.DictWriter(fh, fieldnames=F)
if new: w.writeheader()
def work(t):
    try: return one(t)
    except Exception as ex: print('error', t['tk'], repr(ex)[:100], flush=True); return None
t0 = time.time(); n = 0
try:
    with ThreadPoolExecutor(a.workers) as pool:
        for row in pool.map(work, todo):
            if row is None: continue
            w.writerow(row); fh.flush(); n += 1
            if n % 25 == 0 or a.limit: print(f'{n}/{len(todo)} done, {n/(time.time()-t0):.1f}/s', flush=True)
except KeyboardInterrupt: print('stopped; run again to resume')
fh.close(); summary()
