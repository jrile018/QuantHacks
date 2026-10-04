"""
19_options_exit.py - price the EXIT of the at-the-money straddle used in 18_options_events.py.

Entry  : buy call + put at the ASK, last quote before the close of the day before the 8-K (from opt_events.csv).
Exit A : sell both at the BID at the close of the 8-K day.
Exit B : sell both at the BID at the close of the next market day (for 8-Ks filed after the close).
Also saves mid-price versions so we can see how much the spread costs.

Test first:  python 19_options_exit.py --limit 5
Full run  :  python 19_options_exit.py          (saves as it goes, safe to stop and restart)
Key from the MASSIVE_API_KEY environment variable. Output: <data>/fds/opt_exit.csv (numbers only).
Other industries: add  --data C:\\path\\to\\your_industry\\data  (same folder you used for script 18).
"""
import os, sys, time, math, csv, argparse, threading, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import requests
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from opt_common import add_common_args, load_lookup, load_cal

K = os.environ.get('MASSIVE_API_KEY')
if not K:
    sys.exit('Set the key first in PowerShell:  $env:MASSIVE_API_KEY="your_key_here"')
B = 'https://api.massive.com'

ap = argparse.ArgumentParser()
add_common_args(ap)
ap.add_argument('--limit', type=int, default=0)
ap.add_argument('--workers', type=int, default=6)
args = ap.parse_args()
DATA = args.data
OUTDIR = args.out or os.path.join(DATA, 'fds')
os.makedirs(OUTDIR, exist_ok=True)
IN = os.path.join(OUTDIR, 'opt_events.csv')
OUT = os.path.join(OUTDIR, 'opt_exit.csv')

ev = pd.read_csv(IN)
ev = ev[ev.status == 0].copy()
C2T = load_lookup(DATA, args.lookup)
cal = load_cal(DATA)

done = set()
if os.path.exists(OUT) and os.path.getsize(OUT) > 0:
    d0 = pd.read_csv(OUT, usecols=['cik', 'event_date'])
    done = set(zip(d0.cik, d0.event_date))
todo = [r for r in ev.to_dict('records') if (r['cik'], r['event_date']) not in done]
if args.limit:
    todo = todo[:args.limit]
print(f'usable entry events {len(ev)}, already done {len(done)}, to do now {len(todo)}', flush=True)

tls = threading.local()
def get(path, params=None, url=None):
    if not hasattr(tls, 's'): tls.s = requests.Session()
    p = dict(params or {}); p['apiKey'] = K
    for attempt in range(6):
        try:
            r = tls.s.get(url or (B + path), params=p, timeout=40)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(1.5 * (attempt + 1)); continue
            return r.status_code, r.json()
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return 0, {}

def nth_sunday(y, m, n):
    d = dt.date(y, m, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)
def et_offset(d):
    return 4 if nth_sunday(d.year, 3, 2) <= d < nth_sunday(d.year, 11, 1) else 5
def close_ns(d):
    return int(dt.datetime(d.year, d.month, d.day, 16 + et_offset(d), 0, tzinfo=dt.timezone.utc).timestamp() * 1e9)
def open_ns(d):
    return int(dt.datetime(d.year, d.month, d.day, 4 + et_offset(d), 0, tzinfo=dt.timezone.utc).timestamp() * 1e9)

def exit_quote(opt, d):
    """last quote on day d before the close; bid may be 0 (worthless), ask must be positive"""
    s, j = get(f'/v3/quotes/{opt}', {'timestamp.lte': close_ns(d), 'order': 'desc', 'sort': 'timestamp', 'limit': 1})
    res = j.get('results') or []
    if not res: return None
    q = res[0]
    if q.get('sip_timestamp', 0) < open_ns(d) or not (q.get('ask_price', 0) > 0 and q.get('bid_price', 0) >= 0):
        return None
    return q

NAN = float('nan')
F = ['cik', 'event_date', 'decision_date', 'status', 'expiry', 'strike', 'entry_call_ask', 'entry_put_ask', 'entry_call_bid', 'entry_put_bid',
     'spot0', 'spot_a', 'spot_b']
for w in ('a', 'b'):
    F += [f'x{w}_call_bid', f'x{w}_call_ask', f'x{w}_put_bid', f'x{w}_put_ask', f'x{w}_call_age_min', f'x{w}_put_age_min',
          f'pnl_{w}_bid', f'pnl_{w}_mid']      # percent return on the entry cost
F += ['entry_cost_pct_spot']

def one(r):
    row = {k: NAN for k in F}
    row.update(cik=r['cik'], event_date=r['event_date'], decision_date=r['decision_date'])
    tk = C2T[r['cik']]
    d0 = dt.datetime.strptime(str(int(r['decision_date'])), '%Y%m%d').date()
    ed = pd.Timestamp(dt.datetime.strptime(str(int(r['event_date'])), '%Y%m%d'))
    after = cal[cal >= ed]
    if len(after) < 2: row['status'] = 9; return row
    da, db = after[0].date(), after[1].date()
    exp = d0 + dt.timedelta(days=int(r['near_days']))
    row['expiry'] = int(exp.strftime('%Y%m%d'))
    target = r['spot'] * (1 + r['near_strike_pct'])
    row['strike'] = target
    # find the same contracts
    cons = {}
    for flag in ('true', 'false'):
        s, j = get('/v3/reference/options/contracts', {'underlying_ticker': tk, 'expiration_date': exp.isoformat(), 'as_of': d0.isoformat(),
                                                       'expired': flag, 'limit': 1000})
        for c in j.get('results', []) or []:
            cons[c['ticker']] = c
    calls = [c for c in cons.values() if c['contract_type'] == 'call' and abs(c['strike_price'] - target) < 1e-6 * max(1, target)]
    puts = [c for c in cons.values() if c['contract_type'] == 'put' and abs(c['strike_price'] - target) < 1e-6 * max(1, target)]
    if not calls or not puts: row['status'] = 1; return row
    ct, pt = calls[0]['ticker'], puts[0]['ticker']
    ca, pa = r['near_call_ask'], r['near_put_ask']
    row.update(entry_call_ask=ca, entry_put_ask=pa, entry_call_bid=r['near_call_bid'], entry_put_bid=r['near_put_bid'], spot0=r['spot'])
    cost = ca + pa
    row['entry_cost_pct_spot'] = cost / r['spot']
    entry_mid = (r['near_call_bid'] + ca) / 2 + (r['near_put_bid'] + pa) / 2
    # underlying closes (unadjusted)
    s, j = get(f'/v2/aggs/ticker/{tk}/range/1/day/{da}/{db}', {'adjusted': 'false'})
    for bar in j.get('results', []) or []:
        day = dt.datetime.fromtimestamp(bar['t'] / 1000, dt.timezone.utc).date()
        if day == da: row['spot_a'] = bar['c']
        if day == db: row['spot_b'] = bar['c']
    got = 0
    for w, d in (('a', da), ('b', db)):
        qc, qp = exit_quote(ct, d), exit_quote(pt, d)
        if qc:
            row[f'x{w}_call_bid'] = qc['bid_price']; row[f'x{w}_call_ask'] = qc['ask_price']
            row[f'x{w}_call_age_min'] = (close_ns(d) - qc['sip_timestamp']) / 6e10
        if qp:
            row[f'x{w}_put_bid'] = qp['bid_price']; row[f'x{w}_put_ask'] = qp['ask_price']
            row[f'x{w}_put_age_min'] = (close_ns(d) - qp['sip_timestamp']) / 6e10
        if qc and qp:
            got += 1
            row[f'pnl_{w}_bid'] = (qc['bid_price'] + qp['bid_price']) / cost - 1
            row[f'pnl_{w}_mid'] = ((qc['bid_price'] + qc['ask_price']) / 2 + (qp['bid_price'] + qp['ask_price']) / 2) / entry_mid - 1
    row['status'] = 0 if got == 2 else (3 if got == 1 else 2)
    return row

new = (not os.path.exists(OUT)) or os.path.getsize(OUT) == 0
lock = threading.Lock()
fh = open(OUT, 'a', newline='')
w = csv.DictWriter(fh, fieldnames=F)
if new: w.writeheader()
t0 = time.time(); n = 0; stat = {}
def work(r):
    try: return one(r)
    except Exception as ex:
        print('error', r['cik'], r['event_date'], repr(ex)[:120], flush=True); return None
try:
    with ThreadPoolExecutor(args.workers) as pool:
        for row in pool.map(work, todo):
            if row is None: continue
            with lock:
                w.writerow(row); fh.flush()
            n += 1; stat[row['status']] = stat.get(row['status'], 0) + 1
            if n % 25 == 0 or args.limit:
                rate = n / (time.time() - t0)
                print(f'{n}/{len(todo)} done, {rate:.1f}/s, ETA {(len(todo) - n) / max(rate, 1e-9) / 60:.0f} min, status {stat}', flush=True)
except KeyboardInterrupt:
    print('stopped; run again to resume')
fh.close()
print('finished. status (0=both exits ok 1=contract not found 2=no exit quotes 3=one exit only 9=no later day):', stat)
if args.limit:
    d = pd.read_csv(OUT)
    print(d.tail(args.limit)[['cik', 'event_date', 'status', 'entry_cost_pct_spot', 'pnl_a_bid', 'pnl_a_mid', 'pnl_b_bid', 'pnl_b_mid']].to_string())
