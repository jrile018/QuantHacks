"""
43_pull_splits.py - download the stock split history for our tickers from Massive (one small call per ticker).

Why: our price file is adjusted for splits that happened LATER. To know the real price on a past day (what a trader saw then)
we need each split's date and ratio. Output: data/raw/splits.csv (ticker, execution_date, split_from, split_to).
Usage (PowerShell, key in the environment):  python 43_pull_splits.py
"""
import os, sys, time
import pandas as pd, requests

K = os.environ.get('MASSIVE_API_KEY')
if not K: sys.exit('Set the key first in PowerShell:  $env:MASSIVE_API_KEY="your_key_here"')
here = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(here, '..', 'data')
tick = sorted(pd.read_csv(os.path.join(DATA, 'fds', 'fds_lookup_cik_ticker.csv')).ticker.astype(str).unique()) + ['XBI', 'SPY']
rows = []; s = requests.Session()
for i, t in enumerate(tick, 1):
    url = 'https://api.massive.com/v3/reference/splits'; params = {'ticker': t, 'limit': 1000, 'apiKey': K}
    for attempt in range(5):
        try:
            r = s.get(url, params=params, timeout=30)
            if r.status_code == 429 or r.status_code >= 500: time.sleep(1.5 * (attempt + 1)); continue
            j = r.json(); break
        except Exception: time.sleep(1.5 * (attempt + 1)); j = {}
    for x in j.get('results', []) or []:
        rows.append(dict(ticker=x.get('ticker', t), execution_date=x.get('execution_date'), split_from=x.get('split_from'), split_to=x.get('split_to')))
    if i % 25 == 0: print(f'{i}/{len(tick)} tickers, {len(rows)} splits so far', flush=True)
d = pd.DataFrame(rows, columns=['ticker', 'execution_date', 'split_from', 'split_to']).drop_duplicates()
d.to_csv(os.path.join(DATA, 'raw', 'splits.csv'), index=False)
print('saved data/raw/splits.csv | splits', len(d), '| tickers with at least one split', d.ticker.nunique())
print(d[d.execution_date >= '2024-01-01'].sort_values('execution_date').tail(15).to_string(index=False))
