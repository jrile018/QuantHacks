"""
23_finra_short.py - download FINRA short selling data for our tickers (free, no key).

 1) DAILY short sale volume   (cdn.finra.org/equity/regsho/daily/CNMSshvolYYYYMMDD.txt)
    columns: short volume, short exempt volume, total volume per ticker per day. Published after the close.
 2) BI-MONTHLY short interest (cdn.finra.org/equity/otcmarket/biweekly/shrtYYYYMMDD.csv)
    shares sold short and days to cover on the settlement date (mid month and end of month). Published ~7 business days later.

Test first:  python 23_finra_short.py --test
Full run  :  python 23_finra_short.py        (about 5-10 minutes, saves as it goes, safe to restart)
Output    :  data/raw/finra_shortvol.csv  and  data/raw/finra_shortint.csv  (numbers and tickers only)
"""
import os, sys, io, time, argparse, threading, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import pandas as pd, requests

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--start', default='2023-11-01')
ap.add_argument('--end', default='')
ap.add_argument('--test', action='store_true')
ap.add_argument('--only', default='', help='si = only short interest, vol = only daily short volume')
ap.add_argument('--workers', type=int, default=6)
a = ap.parse_args()
RAW = os.path.join(a.data, 'raw'); FDS = os.path.join(a.data, 'fds')
lk = pd.read_csv(os.path.join(FDS, 'fds_lookup_cik_ticker.csv'))
TICK = set(lk.ticker.astype(str).str.upper())
end = pd.Timestamp(a.end) if a.end else pd.Timestamp.today().normalize()
start = pd.Timestamp(a.start)
HDR = {'User-Agent': 'Mozilla/5.0 (research; UF Gator Quant Hacks) abhay.dronavalli@gmail.com'}
tls = threading.local()
def fetch(url):
    if not hasattr(tls, 's'): tls.s = requests.Session(); tls.s.headers.update(HDR)
    for att in range(4):
        try:
            r = tls.s.get(url, timeout=40)
            if r.status_code == 200: return r.text
            if r.status_code in (403, 404): return None
            time.sleep(1.5 * (att + 1))
        except Exception:
            time.sleep(1.5 * (att + 1))
    return None

def read_table(txt):
    first = txt.splitlines()[0]
    sep = '|' if first.count('|') > first.count(',') else ','
    d = pd.read_csv(io.StringIO(txt), sep=sep, dtype=str)
    d.columns = [c.strip().lower() for c in d.columns]
    return d

# ---------- 1) daily short volume ----------
days = [d for d in pd.bdate_range(start, end)]
if a.test: days = days[-3:]
if a.only == 'si': days = []
def daily(d):
    txt = fetch(f'https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d:%Y%m%d}.txt')
    if not txt: return d, None
    t = read_table(txt)
    sym = next((c for c in t.columns if c.startswith('symbol')), None)
    if sym is None: return d, None
    t = t[t[sym].str.upper().isin(TICK)].copy()
    t['date'] = int(f'{d:%Y%m%d}')
    out = pd.DataFrame({'date': t['date'], 'ticker': t[sym].str.upper(),
                        'short_vol': pd.to_numeric(t.get('shortvolume'), errors='coerce'),
                        'short_exempt_vol': pd.to_numeric(t.get('shortexemptvolume'), errors='coerce'),
                        'total_vol': pd.to_numeric(t.get('totalvolume'), errors='coerce')})
    return d, out
print(f'daily short volume: trying {len(days)} weekdays', flush=True)
parts, miss = [], 0
with ThreadPoolExecutor(a.workers) as pool:
    for i, (d, out) in enumerate(pool.map(daily, days)):
        if out is None: miss += 1
        else: parts.append(out)
        if (i + 1) % 100 == 0: print(f'  {i+1}/{len(days)}  found {len(parts)}  missing {miss}', flush=True)
sv = pd.concat(parts) if parts else pd.DataFrame()
print(f'daily: files found {len(parts)}, missing/holidays {miss}, rows {len(sv)}, tickers {sv.ticker.nunique() if len(sv) else 0}')
if len(sv):
    sv = sv.groupby(['date', 'ticker'], as_index=False).sum(numeric_only=True)   # several venues -> one row per ticker-day
    if not a.test: sv.to_csv(os.path.join(RAW, 'finra_shortvol.csv'), index=False)
    print(sv.tail(3).to_string())

# ---------- 2) short interest ----------
cands = []
for m in pd.period_range(start.to_period('M'), end.to_period('M'), freq='M'):
    mid = pd.Timestamp(m.year, m.month, 15); lastd = m.end_time.normalize()
    for base in (mid, lastd):
        b = base
        while b.weekday() > 4: b -= pd.Timedelta(days=1)
        cands.append(b)
cands = [c for c in cands if c <= end - pd.Timedelta(days=12)]   # newest files are not published yet
if a.test: cands = cands[-3:]
if a.only == 'vol': cands = []
def si(d):
    for ext in ('csv', 'txt'):
        for off in (0, -1, -2, 1):           # settlement dates move around holidays
            dd = d + pd.Timedelta(days=off)
            if dd.weekday() > 4: continue
            txt = fetch(f'https://cdn.finra.org/equity/otcmarket/biweekly/shrt{dd:%Y%m%d}.{ext}')
            if txt:
                t = read_table(txt)
                sym = next((c for c in t.columns if c.startswith('symbol')), None)
                if sym is None: continue
                t = t[t[sym].str.upper().isin(TICK)]
                col = lambda *names: next((c for c in t.columns if any(n in c for n in names)), None)
                cur, prv, adv, dtc = col('currentshortposition', 'current short'), col('previousshortposition', 'previous short'), col('averagedailyvolume', 'average daily'), col('daystocover', 'days to cover')
                st = col('settlementdate', 'settlement')
                out = pd.DataFrame({'settle': int(f'{dd:%Y%m%d}'), 'ticker': t[sym].str.upper(),
                                    'short_int': pd.to_numeric(t[cur], errors='coerce') if cur else float('nan'),
                                    'prev_short_int': pd.to_numeric(t[prv], errors='coerce') if prv else float('nan'),
                                    'avg_daily_vol': pd.to_numeric(t[adv], errors='coerce') if adv else float('nan'),
                                    'days_to_cover': pd.to_numeric(t[dtc], errors='coerce') if dtc else float('nan')})
                return d, out
    return d, None
print(f'\nshort interest: trying {len(cands)} settlement dates', flush=True)
parts, miss = [], []
with ThreadPoolExecutor(a.workers) as pool:
    for d, out in pool.map(si, cands):
        if out is None: miss.append(f'{d:%Y-%m-%d}')
        else: parts.append(out)
si_df = pd.concat(parts) if parts else pd.DataFrame()
print(f'short interest: files found {len(parts)}, missing {len(miss)} {miss[:6]}, rows {len(si_df)}, tickers {si_df.ticker.nunique() if len(si_df) else 0}')
if len(si_df):
    if not a.test: si_df.to_csv(os.path.join(RAW, 'finra_shortint.csv'), index=False)
    print(si_df.tail(3).to_string())
if a.test: print('\ntest only, nothing saved. If both parts found rows, run again without --test.')
