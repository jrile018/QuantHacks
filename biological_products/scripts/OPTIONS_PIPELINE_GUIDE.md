# Options before 8-K events: pipeline guide (Massive API)

Hand this file to your Claude. Tell it your industry and it can adapt and explain every step below.
Everything here was run on the biologics industry (SIC 2836) for Gator Quant Hacks 2026. The code is generic: it needs only an 8-K event list and a price file.

## 1. What this does

For every 8-K event of interest, it reads the options market **just before** the filing, then again **just after**, and computes the real after-spread profit of buying an at-the-money straddle (one call plus one put).

- `18_options_events.py`: for each event, finds the last market day before the 8-K, picks the at-the-money call and put on the nearest expiry and on a ~1 month expiry, reads the last bid and ask before the close, and computes spread, straddle price as % of the stock, implied volatility and an implied event move.
- `19_options_exit.py`: for the same contracts, reads the bid and ask at the close of the 8-K day and of the next market day, and computes profit buying at the ask and selling at the bid (and at the mid for comparison).
- `analyze_options.py`: prints the results.
- `17_massive_probe.py`: a 30 second check of what your Massive key can pull.

## 2. What Massive gives (checked with a real key on 2026-10-03)

| Data | Works? |
| --- | --- |
| Contract lists, active and expired, "as of" a past date | Yes |
| Daily bars per contract | Yes |
| Historical bid/ask quotes with sizes and nanosecond timestamps | **Yes** (tick level) |
| Historical trades | Yes |
| Live snapshot: implied volatility, greeks, open interest, break-even | Yes, but **today only** |
| Historical implied volatility, greeks, open interest | **No**. We compute implied volatility ourselves from the quote midpoint. |

The key had no rate limit problems at 6 parallel workers (about 20 calls per second).

## 3. Setup (Windows PowerShell)

1. `pip install requests pandas`
2. Put the key in an environment variable. **Never paste the key into code, a file, or a chat.** Anyone who sees it can use it:
   ```
   $env:MASSIVE_API_KEY="paste_your_key_here"
   ```
   (Only lasts for that PowerShell window. Set it again in a new window.)
3. Put the 4 scripts below in one folder (for example `scripts/`). Your data folder needs:
   - `raw/events_8k.csv` with columns `cik, filing_date, tertiary_category, tickers` (this is the Massive 8-K disclosures export; `tickers` looks like `['ABOS']`)
   - `raw/prices.csv` with columns `ticker, date` (and `close`). Including `SPY` makes the market calendar exact. Without it the script uses days when at least half the tickers traded.

## 4. Run order

```
python 17_massive_probe.py MRNA                       # replace MRNA with one of your tickers; expect http 200 lines
python 18_options_events.py --data C:\path\to\data --all-events --limit 5   # tiny test, look at the table it prints
python 18_options_events.py --data C:\path\to\data --all-events             # full run, saves after every event, safe to stop and restart
python 19_options_exit.py   --data C:\path\to\data --limit 5
python 19_options_exit.py   --data C:\path\to\data
python analyze_options.py   --data C:\path\to\data
```

Our run: 1,082 events (biotech categories only) took about 5 minutes and about 6,500 calls. The exit pull was about 5,000 calls and about 4 minutes. Cut the work with `--tickers AAA,BBB` or `--start 2025-01-01`.

Options for script 18:
- `--all-events`: use every 8-K in your file. Without it, only the biotech category groups in `GROUPS` at the top of the script are used (clinical results, FDA decision, financing, deal, earnings).
- `--groups my_groups.json`: your own groups, like `{"ev_ma": ["merger_agreement"], "ev_earn": ["quarterly_earnings"]}`. Category names come from the `tertiary_category` column.
- `--lookup tickers.csv`: columns `cik,ticker`, if the ticker in `events_8k.csv` is not the options underlying (for example after a ticker change).
- `--out FOLDER`: where outputs go (default `<data>/fds`).

## 5. Output files (all numbers)

`opt_events.csv` (one row per company and event date):
- `status`: 0 ok, 1 no options listed, 2 no usable quote, 4 no stock price, 9 no prior market day
- `decision_date`: the last market day before the 8-K (the "entry" day)
- `spot`: unadjusted stock close on that day
- `near_*` and `far_*`: nearest expiry at least 5 days out, and the first expiry at least 30 days out. Fields: `days`, `strike_pct` (strike vs spot), `call_bid/ask/spread_pct/bid_size/ask_size/age_min`, same for `put`, `straddle_pct` (call mid plus put mid over spot), `iv_call/iv_put/iv`
- `implied_event_move`: sqrt of (near total variance minus the far-month baseline), a crude estimate
- `ev_*`: event group flags (1 or 0)

`opt_exit.csv`: entry asks and bids, `xa_*` (exit at the 8-K day close), `xb_*` (exit at next close), `pnl_a_bid`, `pnl_a_mid`, `pnl_b_bid`, `pnl_b_mid` (return on the entry cost), `entry_cost_pct_spot`, `status` (0 both exits ok, 1 contract not found, 2 no exit quotes, 3 one exit only, 9 no later day).

## 6. What we found in biologics (for context, not a profit claim)

- 721 of 1,082 events had a usable pre-event options price (101 companies). 288 had no options listed.
- Median call spread was 63% of the option price.
- Buying the straddle at the ask and selling at the bid: **mean -43%, median -46%, win rate 9%** (439 events with both legs quoted).
- At mid prices the mean was +15% but the median was -3%, and without the top 5% of events it was about 0. The spread costs about 58 points.
- Restricting to liquid options (both spreads under 25%, 52 events): -2.7% to +8.6% mean with about 10 to 13 points of uncertainty. Indistinguishable from zero.
- Takeaway: realized moves were about as big as what options priced in, and spreads were bigger than any gap. A spread-aware rule would say "no trade" most of the time.

## 7. Known limits (tell your Claude to check these for your industry)

1. **Dividends.** The implied volatility calculation (Black-Scholes, 4% rate) ignores dividends. Biotech pays none. REITs, utilities, banks and many large caps do, so their implied volatility and event-move numbers are biased. Spreads, straddle price and profit numbers do not depend on this.
2. **American options.** Puts and dividend payers can be exercised early; the formula treats them as European.
3. **Stale quotes.** The last quote before the close can be hours old for thin contracts. `*_age_min` shows how old. We checked results with quotes under 60 minutes old and the picture was the same.
4. **At-the-money choice.** The strike nearest the spot that has both a call and a put. For low priced stocks the strike steps are coarse (`strike_pct` can be 10% away).
5. **Entry timing.** Entry is the close of the day before the filing date. If the news came out earlier (a press release before the 8-K), the option price already moved.
6. **Exit prices** use the last quote before the close of the 8-K day or the next day. A real fill could be better or worse.
7. **Ticker changes and delisted names** can break the contract lookup (status 1).
8. **Daylight saving** is handled in code (US rules, no timezone database needed).
9. **The event list decides the sample.** Different 8-K categories behave differently. Look at results by group.
10. We tried several cuts of the results. A single positive cut in a small sample is not evidence.

## 8. Prompt to give your Claude

> Here is a guide and four Python scripts for pulling options prices around 8-K events with the Massive API. My industry is ____ and my data folder is ____. Read the guide, check my `events_8k.csv` and `prices.csv` match the required columns, pick the 8-K categories that matter for my industry, adapt `GROUPS` or use `--groups`, tell me which limits in section 7 matter for my industry (especially dividends), then walk me through the run order one step at a time and help me read the results.

---

## 9. The code

### opt_common.py
```python
"""opt_common.py - small helpers shared by 18_options_events.py and 19_options_exit.py (any industry)."""
import os, ast
import pandas as pd

def add_common_args(ap):
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument('--data', default=os.path.join(here, '..', 'data'),
                    help='folder that holds raw/events_8k.csv and raw/prices.csv (your industry data folder)')
    ap.add_argument('--out', default='', help='output folder (default: <data>/fds)')
    ap.add_argument('--lookup', default='', help='optional csv with columns cik,ticker (default: derived from events_8k.csv)')

def load_lookup(data, lookup=''):
    """cik -> ticker used as the option underlying"""
    if lookup:
        d = pd.read_csv(lookup); return dict(zip(d.cik.astype(int), d.ticker))
    p = os.path.join(data, 'fds', 'fds_lookup_cik_ticker.csv')
    if os.path.exists(p):
        d = pd.read_csv(p); return dict(zip(d.cik.astype(int), d.ticker))
    e = pd.read_csv(os.path.join(data, 'raw', 'events_8k.csv'), usecols=['cik', 'tickers']).dropna()
    out = {}
    for c, t in zip(e.cik, e.tickers):
        try: lst = ast.literal_eval(t)
        except Exception: lst = []
        if lst and int(c) not in out: out[int(c)] = lst[0]
    return out

def load_cal(data):
    """market days: SPY dates if SPY is in prices.csv, else days when at least half of the tickers traded"""
    p = pd.read_csv(os.path.join(data, 'raw', 'prices.csv'), usecols=['ticker', 'date'])
    p['date'] = pd.to_datetime(p.date)
    s = p[p.ticker == 'SPY'].date
    if len(s) > 200:
        return pd.DatetimeIndex(sorted(s.unique()))
    cnt = p.groupby('date').ticker.nunique()
    return pd.DatetimeIndex(sorted(cnt[cnt >= 0.5 * cnt.max()].index))
```

### 17_massive_probe.py
```python
"""17_massive_probe.py - what does our Massive key unlock for options? Reads the key from MASSIVE_API_KEY."""
import os, sys
import requests

K = os.environ.get('MASSIVE_API_KEY')
if not K:
    sys.exit('Set the key first in PowerShell:  $env:MASSIVE_API_KEY="your_key_here"   then run again')
B = 'https://api.massive.com'
UNDER = sys.argv[1] if len(sys.argv) > 1 else 'MRNA'

def g(path, **p):
    r = requests.get(B + path, params={**p, 'apiKey': K}, timeout=30)
    try:
        j = r.json()
    except Exception:
        j = {'raw': r.text[:150]}
    return r.status_code, j

def show(name, s, j):
    rows = j.get('results')
    n = len(rows) if isinstance(rows, list) else ('object' if rows else 0)
    print(f'{name:28s} http {s}  status={j.get("status", "")}  msg={j.get("message") or j.get("error") or ""}  rows={n}')
    return rows

# 1) recent EXPIRED contracts (expired in 2026) so history exists
s, j = g('/v3/reference/options/contracts', underlying_ticker=UNDER, expired='true',
         **{'expiration_date.gte': '2026-03-01', 'expiration_date.lte': '2026-08-31'}, limit=200, order='asc', sort='strike_price')
cons = j.get('results', [])
print(f'expired contracts for {UNDER}:', s, len(cons))
found = None
for c in cons[::max(1, len(cons) // 25)]:           # sample up to ~25 contracts across strikes
    t, exp = c['ticker'], c['expiration_date']
    s, b = g(f'/v2/aggs/ticker/{t}/range/1/day/2026-01-01/{exp}')
    if s == 200 and b.get('results'):
        found = (t, exp, b['results']); break
if not found:
    sys.exit('no expired contract with daily bars found; try another underlying: python 17_massive_probe.py GILD')
t, exp, bars = found
day = __import__('datetime').datetime.utcfromtimestamp(bars[-1]['t'] / 1000).strftime('%Y-%m-%d')
print('\nusing expired contract', t, 'expiry', exp, 'bars', len(bars), 'last bar day', day)
show('daily bars', 200, {'results': bars, 'status': 'OK'})
s, j = g(f'/v3/quotes/{t}', timestamp=day, limit=5);  q = show('quotes (bid/ask) on that day', s, j)
if q: print('   sample quote:', {k: q[0].get(k) for k in ('bid_price', 'ask_price', 'bid_size', 'ask_size', 'sip_timestamp')})
s, j = g(f'/v3/trades/{t}', timestamp=day, limit=5);  tr = show('trades on that day', s, j)

# 2) a LIVE contract for snapshot (iv, greeks, open interest)
s, j = g('/v3/reference/options/contracts', underlying_ticker=UNDER, expired='false', limit=1)
live = j.get('results', [])
if live:
    lt = live[0]['ticker']
    s, j = g(f'/v3/snapshot/options/{UNDER}/{lt}')
    r = show('snapshot (live contract)', s, j)
    if isinstance(r, dict): print('   snapshot keys:', sorted(r.keys()))
else:
    print('no live contracts found for', UNDER)
```

### 18_options_events.py
```python
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
```

### 19_options_exit.py
```python
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
```

### analyze_options.py
```python
"""analyze_options.py - after-cost results of buying the at-the-money straddle before each 8-K.
Usage:  python analyze_options.py --data C:\\path\\to\\data      (reads <data>/fds/opt_events.csv and opt_exit.csv)"""
import os, argparse
import numpy as np, pandas as pd
ap = argparse.ArgumentParser(); ap.add_argument('--data', default='../data'); a = ap.parse_args()
fds = os.path.join(a.data, 'fds')
x = pd.read_csv(os.path.join(fds, 'opt_exit.csv')); o = pd.read_csv(os.path.join(fds, 'opt_events.csv'))
flag_cols = [c for c in o.columns if c.startswith('ev_')]
d = x.merge(o[['cik', 'event_date', 'near_call_spread_pct', 'near_put_spread_pct'] + flag_cols], on=['cik', 'event_date'])
g = d[(d.status == 0) & d.pnl_a_bid.notna()].copy()          # both legs quoted at entry and at exit
g['liquid'] = (g.near_call_spread_pct < 0.25) & (g.near_put_spread_pct < 0.25)

def s(v):
    v = v.dropna()
    if len(v) == 0: return 'n=0'
    return f'n={len(v)} mean={v.mean():+.1%} median={v.median():+.1%} win={(v > 0).mean():.0%} se={v.std() / np.sqrt(len(v)):.1%}'

print('events with a full round trip:', len(g), 'of', len(o))
for col, name in (('pnl_a_bid', 'exit event-day close, bid'), ('pnl_a_mid', 'exit event-day close, mid'),
                  ('pnl_b_bid', 'exit next close, bid'), ('pnl_b_mid', 'exit next close, mid')):
    print(f'{name:28s} all    {s(g[col])}')
    print(f'{"":28s} liquid {s(g[g.liquid][col])}')
print('\nby event group (bid-based, event-day exit):')
for c in flag_cols:
    t = g[g[c] == 1]
    if len(t): print(f'  {c:10s} {s(t.pnl_a_bid)}')
g['spread'] = (g.near_call_spread_pct + g.near_put_spread_pct) / 2
print('\nby average spread bucket:')
print(g.groupby(pd.cut(g.spread, [0, .1, .2, .35, .6, 5]), observed=True)
        .agg(n=('pnl_a_bid', 'size'), mean_bid=('pnl_a_bid', 'mean'), mean_mid=('pnl_a_mid', 'mean')).round(3).to_string())
```
