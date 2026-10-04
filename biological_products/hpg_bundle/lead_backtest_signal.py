"""
lead_backtest_signal.py - run OUR offering signal through the TEAM backtest engine (QuantHacks src.implementation), unchanged.

The team engine normally takes 8-K filing dates as events. Here the events are the days our model flagged a company as likely
to announce an offering (155 trades, 2025-01 to 2026-10). The engine prices each event from Massive option data exactly as it
does for 8-K events: entry at the close of the first session AFTER the signal day, fixed horizons, synthetic stock from options.
Our trade is a SHORT, so we report minus the engine's "stock" result (and its other strategies as they are, for reference).

Usage (MASSIVE_API_KEY in the environment):
  python lead_backtest_signal.py --repo /blue/ai-workshop/kkatiyar/QuantHacks --events offer_signal_events.csv --out out_signal_offer
  python lead_backtest_signal.py --summarize out_signal_offer
"""
import os, sys, json, argparse
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--repo', default='/blue/ai-workshop/kkatiyar/QuantHacks')
ap.add_argument('--events', default='offer_signal_events.csv')
ap.add_argument('--out', default='out_signal_offer')
ap.add_argument('--max-events', type=int, default=None)
ap.add_argument('--summarize', default=None)
ap.add_argument('--boot', type=int, default=5000)
a = ap.parse_args()
rng = np.random.default_rng(9)

def summarize(folder):
    r = pd.read_csv(os.path.join(folder, 'results.csv')); r['horizon'] = r.horizon.astype(str)
    r = r[np.isclose(r.otm, 0.05) & (r.entry == 'post')].copy()
    r['short_stock'] = -r['stock']
    r['year'] = pd.to_datetime(r.event_date).dt.year
    ev = r.drop_duplicates(['ticker', 'event_date'])
    print(f'\npriced events {len(ev)} | tickers {ev.ticker.nunique()} | by year {ev.year.value_counts().sort_index().to_dict()} | by bucket {r.drop_duplicates(["ticker","event_date","bucket"]).bucket.value_counts().to_dict()}')
    def cell(g, col):
        x = g[col].dropna().values
        if len(x) < 8: return f'n {len(x):3d} too few'
        k = np.sqrt(252 / g.sessions_held.mean()); xb = x[rng.integers(0, len(x), (a.boot, len(x)))]; sb = xb.mean(1) / xb.std(1, ddof=1) * k
        return f'n {len(x):3d} mean {x.mean()*100:+6.2f}% median {np.median(x)*100:+6.2f}% win {(x>0).mean():.2f} Sharpe {x.mean()/x.std(ddof=1)*k:+5.2f} [{np.percentile(sb,2.5):+.2f}, {np.percentile(sb,97.5):+.2f}]'
    for bucket in ('1m', '2m', '3-6m'):
        b = r[r.bucket == bucket]
        if b.empty: continue
        print(f'\nbucket {bucket}: SHORT the stock (minus the engine stock result), entry the session after the signal, no costs')
        for h in ('1', '3', '5', '10', '21'):
            g = b[b.horizon == h]
            print(f'  hold {h:>2} sessions | all: {cell(g, "short_stock")}')
            print(f'  {"":16s} | 2025: {cell(g[g.year == 2025], "short_stock")}')
            print(f'  {"":16s} | 2026: {cell(g[g.year == 2026], "short_stock")}')
    g = r[(r.bucket == '1m') & (r.horizon == '5')]
    print('\nreference, bucket 1m, hold 5 sessions, the engine strategies as they are (long side):')
    for s in ('stock', 'long_call', 'covered_call', 'protective_put', 'collar', 'cash_secured_put'): print(f'  {s:17s} {cell(g, s)}')
    g.sort_values('short_stock')[['ticker', 'event_date', 'entry_date', 'exit_date', 'S_entry', 'S_exit', 'short_stock']].to_csv(os.path.join(folder, 'short_trades_1m_h5.csv'), index=False)

if a.summarize:
    summarize(a.summarize); raise SystemExit

sys.path.insert(0, a.repo)
from src.implementation import price_events, evaluate          # team engine, unchanged
from src.data import safe_entry_session, session_before
from src.config import EXPIRY_BUCKETS

ev = pd.read_csv(a.events)
ev['filing_date'] = pd.to_datetime(ev.signal_date.astype(str)); ev['ticker'] = ev.ticker.astype(str).str.upper()
ev = ev.sort_values('filing_date').reset_index(drop=True)
ev['event_date'] = ev['filing_date']
ev['t_0'] = ev['filing_date'].map(safe_entry_session)            # first session strictly after the signal day
ev['t_pre'] = ev['filing_date'].map(session_before)
if a.max_events: ev = ev.head(a.max_events).copy()
print(f'team engine from {a.repo} | our signal events {len(ev)} | {ev.filing_date.min().date()} to {ev.filing_date.max().date()} | tickers {ev.ticker.nunique()}', flush=True)
pr, drops = price_events(ev[['ticker', 'filing_date', 'event_date', 't_0', 't_pre']], EXPIRY_BUCKETS, label='offering signal')
if not pr: print('no events could be priced'); raise SystemExit(2)
res = evaluate(pr)
os.makedirs(a.out, exist_ok=True)
res.to_csv(os.path.join(a.out, 'results.csv'), index=False); drops.to_csv(os.path.join(a.out, 'dropped.csv'), index=False); ev.to_csv(os.path.join(a.out, 'events.csv'), index=False)
json.dump(dict(kind='offering signal through the team engine', events=len(ev), priced_pairs=len(pr), repo=a.repo, pandas=pd.__version__),
          open(os.path.join(a.out, 'manifest.json'), 'w'), indent=2)
print('events', len(ev), '| priced (event, bucket) pairs', len(pr), '| result rows', len(res))
if len(drops): print('why events were dropped:', drops.reason.value_counts().head(6).to_dict())
summarize(a.out)
