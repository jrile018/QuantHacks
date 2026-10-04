"""
51_pull_borrow.py - pull HISTORICAL stock-borrow data (Interactive Brokers fee rate and shares available) from iborrowdesk.com
for every ticker in our universe. This is the only free source we found with a history of both fields. How far back it goes
is unknown until we look, so the script reports the earliest date per ticker.

Usage (PowerShell):  python 51_pull_borrow.py          test:  python 51_pull_borrow.py --limit 3
Output: data/raw/borrow/<TICKER>.json (raw) and data/raw/borrow_history.csv (ticker, date, fee_pct, rebate_pct, available_shares).
Be polite to the site: one request per second, no retries beyond 3.
"""
import os, sys, time, json, argparse
import pandas as pd, requests
ap = argparse.ArgumentParser(); ap.add_argument('--limit', type=int, default=0); ap.add_argument('--sleep', type=float, default=1.0); a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(here, '..', 'data'); RAWB = os.path.join(DATA, 'raw', 'borrow'); os.makedirs(RAWB, exist_ok=True)
tick = sorted(pd.read_csv(os.path.join(DATA, 'fds', 'fds_lookup_cik_ticker.csv')).ticker.astype(str).unique())
if a.limit: tick = tick[:a.limit]
s = requests.Session(); s.headers.update({'User-Agent': 'QuantHacks-student-research (contact: team lead via GitHub jrile018/QuantHacks)'})
rows = []; shape_shown = False
for i, t in enumerate(tick, 1):
    out = os.path.join(RAWB, f'{t}.json')
    if os.path.exists(out) and os.path.getsize(out) > 2:
        j = json.load(open(out))
    else:
        j = None
        for att in range(3):
            try:
                r = s.get(f'https://iborrowdesk.com/api/ticker/{t}', timeout=30)
                if r.status_code == 200: j = r.json(); break
                if r.status_code == 404: j = {}; break
                time.sleep(3 * (att + 1))
            except Exception as ex:
                print('error', t, repr(ex)[:80]); time.sleep(3 * (att + 1))
        if j is None: print(f'{t}: no answer'); continue
        json.dump(j, open(out, 'w')); time.sleep(a.sleep)
    if not shape_shown and j:
        print('response keys:', list(j.keys())[:12]); shape_shown = True
    recs = None
    for k in ('daily', 'history', 'data', 'records'):
        if isinstance(j.get(k), list) and j[k]: recs = j[k]; break
    if recs is None:
        print(f'{t}: no history list in response'); continue
    for x in recs:
        d = x.get('time') or x.get('date') or x.get('timestamp')
        rows.append(dict(ticker=t, date=str(d)[:10], fee_pct=x.get('fee'), rebate_pct=x.get('rebate'), available_shares=x.get('available')))
    if i % 10 == 0: print(f'{i}/{len(tick)} tickers, {len(rows)} rows so far', flush=True)
d = pd.DataFrame(rows)
if len(d):
    d.to_csv(os.path.join(DATA, 'raw', 'borrow_history.csv'), index=False)
    g = d.groupby('ticker').date.agg(['min', 'max', 'size'])
    print(f'\nsaved data/raw/borrow_history.csv | rows {len(d)} | tickers with data {d.ticker.nunique()} of {len(tick)}')
    print(f'earliest date overall {d.date.min()} | median earliest per ticker {g["min"].median()} | tickers with data before 2025-01-01: {(g["min"] < "2025-01-01").sum()}')
    print(g.sort_values('min').head(10).to_string())
else: print('no rows collected')
