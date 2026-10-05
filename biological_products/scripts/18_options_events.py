"""
18_options_events.py - options price just BEFORE each 8-K event (any industry).

For every (company, 8-K date) with an event of interest, take the last market day before the 8-K,
read the last bid/ask of the at-the-money call and put (near expiry and ~1 month expiry) before the close,
and compute spread, straddle price as % of stock (implied move) and implied volatility.

Needs in your data folder:  raw/events_8k.csv (cik, filing_date, tertiary_category, tickers)  and  raw/prices.csv (ticker, date).
Other industries:  python 18_options_events.py --data C:\\path\\to\\your_industry\\data --all-events
  --all-events   use every 8-K (default: only the categories in GROUPS below)
  --groups f.json  your own groups, like {"ev_ma": ["merger_agreement"], "ev_earn": ["quarterly_earnings"]}
  --lookup f.csv   csv with columns cik,ticker if the tickers cannot be read from events_8k.csv

Run a tiny test first:   python 18_options_events.py --limit 5
Then the full run:       python 18_options_events.py
It saves after every event and skips finished ones, so you can stop (Ctrl+C) and restart any time.
Key is read from the MASSIVE_API_KEY environment variable. Output: <data>/fds/opt_events.csv (numbers only).
"""
import os, sys, time, math, csv, json, argparse, threading, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import requests
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from opt_common import add_common_args, load_lookup, load_cal

K = os.environ.get('MASSIVE_API_KEY')
if not K:
    sys.exit('Set the key first in PowerShell:  $env:MASSIVE_API_KEY="your_key_here"')
B = 'https://api.massive.com'
R_FREE = 0.04
GROUPS = {
    'ev_trial': ['clinical_trial_results'],
    'ev_reg': ['regulatory_decision'],
    'ev_offer': ['public_offering', 'underwriting_agreement', 'private_placement'],
    'ev_deal': ['partnership_or_collaboration', 'licensing_agreement'],
    'ev_earn': ['quarterly_earnings', 'preliminary_results', 'guidance_issuance_or_update'],
}

ap = argparse.ArgumentParser()
add_common_args(ap)
ap.add_argument('--limit', type=int, default=0)
ap.add_argument('--workers', type=int, default=6)
ap.add_argument('--tickers', type=str, default='')   # optional comma list to restrict
ap.add_argument('--start', default='2024-01-02')
ap.add_argument('--end', default='')
ap.add_argument('--all-events', action='store_true')
ap.add_argument('--groups', default='')
args = ap.parse_args()
if args.groups:
    GROUPS = json.load(open(args.groups))
DATA = args.data
OUTDIR = args.out or os.path.join(DATA, 'fds')
os.makedirs(OUTDIR, exist_ok=True)
OUT = os.path.join(OUTDIR, 'opt_events.csv')

# ---------------------------------------------------------------- events
cal = load_cal(DATA)
START = pd.Timestamp(args.start)
END = pd.Timestamp(args.end) if args.end else cal.max()
C2T = load_lookup(DATA, args.lookup)
ev = pd.read_csv(os.path.join(DATA, 'raw', 'events_8k.csv'), usecols=['cik', 'filing_date', 'tertiary_category']).dropna(subset=['cik'])
ev['cik'] = ev.cik.astype(int); ev['filing_date'] = pd.to_datetime(ev.filing_date)
ev = ev[(ev.filing_date >= START) & (ev.filing_date <= END) & ev.cik.isin(C2T)]
rows = {}
for r in ev.itertuples():
    hit = False
    for g, cats in GROUPS.items():
        if r.tertiary_category in cats:
            rows.setdefault((r.cik, r.filing_date), {k: 0 for k in GROUPS})[g] = 1; hit = True
    if args.all_events and not hit:
        rows.setdefault((r.cik, r.filing_date), {k: 0 for k in GROUPS})
for f in rows.values():
    f['ev_any'] = 1
events = sorted([(c, d, f) for (c, d), f in rows.items()], key=lambda x: (x[1], x[0]))
if args.tickers:
    keep = set(args.tickers.split(','))
    events = [e for e in events if C2T[e[0]] in keep]

done = set()
if os.path.exists(OUT) and os.path.getsize(OUT) > 0:
    d0 = pd.read_csv(OUT, usecols=['cik', 'event_date'])
    done = set(zip(d0.cik, d0.event_date))
todo = [e for e in events if (e[0], int(e[1].strftime('%Y%m%d'))) not in done]
if args.limit:
    todo = todo[:args.limit]
print(f'events total {len(events)}, already done {len(done)}, to do now {len(todo)}', flush=True)

# ---------------------------------------------------------------- http
tls = threading.local()
def sess():
    if not hasattr(tls, 's'):
        tls.s = requests.Session()
    return tls.s

def get(path, params=None, url=None):
    p = dict(params or {}); p['apiKey'] = K
    for attempt in range(6):
        try:
            r = sess().get(url or (B + path), params=p, timeout=40)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(1.5 * (attempt + 1)); continue
            return r.status_code, r.json()
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return 0, {}

def get_all(path, params, pages=3):
    s, j = get(path, params); out = list(j.get('results', []) or [])
    n = 1
    while j.get('next_url') and n < pages:
        s, j = get(None, url=j['next_url']); out += list(j.get('results', []) or []); n += 1
    return out

# ---------------------------------------------------------------- time helpers (US Eastern, no tz database needed)
def nth_sunday(y, m, n):
    d = dt.date(y, m, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)
def et_offset(d):
    return 4 if nth_sunday(d.year, 3, 2) <= d < nth_sunday(d.year, 11, 1) else 5
def close_ns(d):   # 16:00 Eastern in UTC nanoseconds
    t = dt.datetime(d.year, d.month, d.day, 16 + et_offset(d), 0, tzinfo=dt.timezone.utc)
    return int(t.timestamp() * 1e9)
def open_ns(d):
    t = dt.datetime(d.year, d.month, d.day, 4 + et_offset(d), 0, tzinfo=dt.timezone.utc)   # 04:00 ET
    return int(t.timestamp() * 1e9)

# ---------------------------------------------------------------- Black-Scholes implied vol (no dividends)
def ncdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def bs(S, Kx, T, sig, call):
    d1 = (math.log(S / Kx) + (R_FREE + 0.5 * sig * sig) * T) / (sig * math.sqrt(T)); d2 = d1 - sig * math.sqrt(T)
    if call: return S * ncdf(d1) - Kx * math.exp(-R_FREE * T) * ncdf(d2)
    return Kx * math.exp(-R_FREE * T) * ncdf(-d2) - S * ncdf(-d1)
def iv(S, Kx, T, price, call):
    if T <= 0 or price <= 0: return float('nan')
    lo, hi = 1e-3, 8.0
    if price < bs(S, Kx, T, lo, call) or price > bs(S, Kx, T, hi, call): return float('nan')
    for _ in range(60):
        mid = (lo + hi) / 2
        if bs(S, Kx, T, mid, call) > price: hi = mid
        else: lo = mid
    return (lo + hi) / 2

NAN = float('nan')
FIELDS = (['cik', 'event_date', 'decision_date', 'status'] + list(GROUPS) + ['ev_any'] + ['spot', 'n_contracts_listed'] +
          [f'{w}_{x}' for w in ('near', 'far') for x in
           ('days', 'strike_pct', 'call_bid', 'call_ask', 'call_spread_pct', 'call_bid_size', 'call_ask_size', 'call_age_min',
            'put_bid', 'put_ask', 'put_spread_pct', 'put_bid_size', 'put_ask_size', 'put_age_min',
            'straddle_pct', 'iv_call', 'iv_put', 'iv')] + ['implied_event_move'])

def last_quote(opt, d, decision_ns):
    s, j = get(f'/v3/quotes/{opt}', {'timestamp.lte': decision_ns, 'order': 'desc', 'sort': 'timestamp', 'limit': 1})
    res = j.get('results') or []
    if not res: return None
    q = res[0]
    if q.get('sip_timestamp', 0) < open_ns(d) or not (q.get('bid_price', 0) > 0 and q.get('ask_price', 0) > q.get('bid_price', 0)):
        return None
    return q

def one(cik, edate, flags):
    tk = C2T[cik]
    row = {k: NAN for k in FIELDS}
    row.update(cik=cik, event_date=int(edate.strftime('%Y%m%d')), **flags)
    prev = cal[cal < edate]
    if len(prev) == 0: row['status'] = 9; return row
    d = prev[-1].date(); row['decision_date'] = int(prev[-1].strftime('%Y%m%d'))
    dns = close_ns(d)
    # spot (unadjusted close of the decision day)
    s, j = get(f'/v2/aggs/ticker/{tk}/range/1/day/{d}/{d}', {'adjusted': 'false'})
    res = j.get('results') or []
    if not res: row['status'] = 4; return row
    spot = res[0]['c']; row['spot'] = spot
    # contracts alive on the decision day, expiring 5 to 75 days after it
    lo = (d + dt.timedelta(days=5)).isoformat(); hi = (d + dt.timedelta(days=75)).isoformat()
    cons = {}
    for exp_flag in ('true', 'false'):
        for c in get_all('/v3/reference/options/contracts', {'underlying_ticker': tk, 'as_of': d.isoformat(), 'expired': exp_flag,
                                                              'expiration_date.gte': lo, 'expiration_date.lte': hi, 'limit': 1000}):
            cons[c['ticker']] = c
    row['n_contracts_listed'] = len(cons)
    if not cons: row['status'] = 1; return row
    exps = sorted({c['expiration_date'] for c in cons.values()})
    near = exps[0]
    far = next((e for e in exps if (dt.date.fromisoformat(e) - d).days >= 30), None)
    ivs = {}
    anyquote = False
    for label, exp in (('near', near), ('far', far)):
        if exp is None: continue
        T = (dt.date.fromisoformat(exp) - d).days / 365.0
        calls = {c['strike_price']: c['ticker'] for c in cons.values() if c['expiration_date'] == exp and c['contract_type'] == 'call'}
        puts = {c['strike_price']: c['ticker'] for c in cons.values() if c['expiration_date'] == exp and c['contract_type'] == 'put'}
        both = [k for k in calls if k in puts]
        if not both: continue
        kx = min(both, key=lambda k: abs(k - spot))
        row[f'{label}_days'] = (dt.date.fromisoformat(exp) - d).days
        row[f'{label}_strike_pct'] = kx / spot - 1
        mids = {}
        for side, tick in (('call', calls[kx]), ('put', puts[kx])):
            q = last_quote(tick, d, dns)
            if not q: continue
            anyquote = True
            b, a = q['bid_price'], q['ask_price']; m = (a + b) / 2
            row[f'{label}_{side}_bid'] = b; row[f'{label}_{side}_ask'] = a; row[f'{label}_{side}_spread_pct'] = (a - b) / m
            row[f'{label}_{side}_bid_size'] = q.get('bid_size', NAN); row[f'{label}_{side}_ask_size'] = q.get('ask_size', NAN)
            row[f'{label}_{side}_age_min'] = (dns - q['sip_timestamp']) / 6e10
            mids[side] = m
            row[f'{label}_iv_{side}'] = iv(spot, kx, T, m, side == 'call')
        if len(mids) == 2:
            row[f'{label}_straddle_pct'] = (mids['call'] + mids['put']) / spot
        vs = [row[f'{label}_iv_{x}'] for x in ('call', 'put') if row[f'{label}_iv_{x}'] == row[f'{label}_iv_{x}']]
        if vs:
            row[f'{label}_iv'] = sum(vs) / len(vs)
            ivs[label] = (row[f'{label}_iv'], T)
    if 'near' in ivs and 'far' in ivs:
        (i1, t1), (i2, t2) = ivs['near'], ivs['far']
        extra = i1 * i1 * t1 - i2 * i2 * t1          # near total variance above the far-month baseline
        row['implied_event_move'] = math.sqrt(extra) if extra > 0 else 0.0
    row['status'] = 0 if anyquote else 2
    return row

# ---------------------------------------------------------------- run
new = (not os.path.exists(OUT)) or os.path.getsize(OUT) == 0
lock = threading.Lock()
fh = open(OUT, 'a', newline='')
w = csv.DictWriter(fh, fieldnames=FIELDS)
if new: w.writeheader()
t0 = time.time(); n = 0; stat = {}
def work(e):
    try:
        return one(*e)
    except Exception as ex:
        print('error', e[0], e[1].date(), repr(ex)[:120], flush=True)
        return None
try:
    with ThreadPoolExecutor(args.workers) as pool:
        for row in pool.map(work, todo):
            if row is None: continue
            with lock:
                w.writerow(row); fh.flush()
            n += 1; stat[row['status']] = stat.get(row['status'], 0) + 1
            if n % 25 == 0 or args.limit:
                rate = n / (time.time() - t0)
                print(f'{n}/{len(todo)} done, {rate:.1f}/s, ETA {(len(todo) - n) / max(rate, 1e-9) / 60:.0f} min, status counts {stat}', flush=True)
except KeyboardInterrupt:
    print('stopped; run again to resume')
fh.close()
print('finished. status counts (0=ok 1=no contracts 2=no usable quote 4=no stock bar 9=no prior day):', stat)
if args.limit:
    d = pd.read_csv(OUT)
    print(d.tail(args.limit)[['cik', 'event_date', 'status', 'spot', 'near_days', 'near_strike_pct', 'near_call_spread_pct', 'near_straddle_pct', 'near_iv', 'far_iv', 'implied_event_move']].to_string())
