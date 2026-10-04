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
