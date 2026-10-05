"""
lead_backtest_run.py - run the TEAM backtest (QuantHacks run_all.py / src.implementation.run_study) on the biologics universe,
then estimate a Sharpe ratio with a 95% interval from its output. Nothing in the team repo is changed: we only call it.

The team backtest: pick one 8-K tag, find every filing with that tag, and measure six strategies after it
(stock, long call, covered call, protective put, collar, cash secured put) at fixed horizons, from Massive option prices.
Its default universe is the 100 largest US companies; here we pass our own list (SIC 2836 biologics).

Usage (from this folder, with MASSIVE_API_KEY set in the environment):
  python lead_backtest_run.py --repo /blue/ai-workshop/kkatiyar/QuantHacks --tag public_offering --max-events 5 --out out_smoke
  python lead_backtest_run.py --repo ... --tag public_offering --start 2024-01-01 --end 2025-12-31 --out out_insample
  python lead_backtest_run.py --repo ... --tag public_offering --start 2026-01-01 --end 2026-08-31 --out out_oos
  python lead_backtest_run.py --summarize out_insample out_oos         (no API calls: Sharpe table from saved results)
"""
import os, sys, json, argparse
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--repo', default='/blue/ai-workshop/kkatiyar/QuantHacks')
ap.add_argument('--tag', default='public_offering')
ap.add_argument('--start', default='2024-01-01'); ap.add_argument('--end', default='2025-12-31')
ap.add_argument('--max-events', type=int, default=None)
ap.add_argument('--universe', default='data/fds/fds_lookup_cik_ticker.csv', help='csv with a ticker column, or TOP100 for the team default')
ap.add_argument('--out', default='out_run')
ap.add_argument('--summarize', nargs='*', default=None, help='only summarize these output folders')
ap.add_argument('--boot', type=int, default=5000)
a = ap.parse_args()
STRATS = ['stock', 'long_call', 'covered_call', 'protective_put', 'collar', 'cash_secured_put']
rng = np.random.default_rng(5)

def sharpe_table(res, label):
    """One row per strategy and horizon. Each event is one bet held for 'sessions_held' market days.
    Annual Sharpe = (mean / std of the per event result) x sqrt(252 / average days held): the usual way to scale an event study,
    which assumes the bets are independent and capital is reused one after another. 95% interval: bootstrap over events."""
    rows = []
    for (entry, bucket, otm, h), g in res.groupby(['entry', 'bucket', 'otm', 'horizon']):
        if h in (0, '0', 'exp'): continue
        held = pd.to_numeric(g.sessions_held, errors='coerce').mean()
        for s in STRATS:
            x = pd.to_numeric(g[s], errors='coerce').dropna().values
            if len(x) < 10 or x.std(ddof=1) == 0 or not held > 0: continue
            k = np.sqrt(252.0 / held); sh = x.mean() / x.std(ddof=1) * k
            idx = rng.integers(0, len(x), size=(a.boot, len(x))); xb = x[idx]
            sb = xb.mean(axis=1) / xb.std(axis=1, ddof=1) * k
            rows.append(dict(window=label, entry=entry, bucket=bucket, otm=otm, horizon=h, strategy=s, n=len(x), tickers=g.ticker.nunique(),
                             mean_pct=x.mean() * 100, median_pct=np.median(x) * 100, win=(x > 0).mean(), sharpe=sh,
                             ci_lo=np.nanpercentile(sb, 2.5), ci_hi=np.nanpercentile(sb, 97.5), p_le0=float(np.mean(sb <= 0))))
    return pd.DataFrame(rows)

def summarize(folders):
    out = []
    for f in folders:
        p = os.path.join(f, 'results.csv')
        if not os.path.exists(p): print('no results in', f); continue
        res = pd.read_csv(p); man = json.load(open(os.path.join(f, 'manifest.json'))) if os.path.exists(os.path.join(f, 'manifest.json')) else {}
        lab = f"{man.get('start', '?')}..{man.get('end', '?')}"
        print(f"\n===== {f}: tag {man.get('tag')} | window {lab} | events found {man.get('event_count')} | priced {man.get('priced_count')} | result rows {len(res)} =====")
        t = sharpe_table(res, lab); out.append(t)
        if t.empty: print('too few priced events for a Sharpe estimate (need at least 10 per cell)'); continue
        pd.set_option('display.width', 220)
        for entry in ('post', 'pre'):
            q = t[(t.entry == entry) & (t.otm == 0.05) & (t.horizon.astype(str).isin(['5', '10', '21', '42']))]
            if q.empty: continue
            note = 'tradable: enter the session AFTER the filing date' if entry == 'post' else 'hypothetical: enter the session BEFORE the filing (needs a forecast)'
            print(f'\nentry = {entry}  ({note}), 5% OTM legs')
            print(q[['bucket', 'horizon', 'strategy', 'n', 'tickers', 'mean_pct', 'median_pct', 'win', 'sharpe', 'ci_lo', 'ci_hi', 'p_le0']].round(2).to_string(index=False))
    if out:
        allt = pd.concat(out); allt.to_csv('lead_backtest_sharpe.csv', index=False); print('\nsaved lead_backtest_sharpe.csv', len(allt), 'rows')

if a.summarize is not None:
    summarize(a.summarize); raise SystemExit

sys.path.insert(0, a.repo)
from src.implementation import run_study            # the team engine, unchanged
from src.config import TOP_100
if a.universe.upper() == 'TOP100': uni = list(TOP_100)
else: uni = sorted(pd.read_csv(a.universe).ticker.astype(str).str.upper().unique())
print(f'team backtest from {a.repo} | tag {a.tag} | {a.start}..{a.end} | universe {len(uni)} tickers | max events {a.max_events}', flush=True)
try:
    study = run_study(a.tag, a.start, a.end, universe=uni, max_events=a.max_events)
except Exception as ex:
    print('the team backtest could not run this window:', repr(ex)); raise SystemExit(2)
os.makedirs(a.out, exist_ok=True)
for name, key in (('events', 'events'), ('dropped', 'dropped'), ('results', 'results'), ('scoreboard', 'board')):
    if key in study and isinstance(study[key], pd.DataFrame): study[key].to_csv(os.path.join(a.out, f'{name}.csv'), index=False)
man = dict(tag=a.tag, start=a.start, end=a.end, max_events=a.max_events, universe_size=len(uni), event_count=len(study['events']),
           priced_count=len(study.get('priced', [])), repo=a.repo, pandas=pd.__version__, numpy=np.__version__)
json.dump(man, open(os.path.join(a.out, 'manifest.json'), 'w'), indent=2)
print('events', man['event_count'], '| priced', man['priced_count'], '| result rows', len(study['results']))
if 'dropped' in study and len(study['dropped']):
    d = study['dropped']; c = [c for c in d.columns if 'reason' in c.lower()]
    if c: print('why events were dropped:', d[c[0]].value_counts().head(6).to_dict())
summarize([a.out])
