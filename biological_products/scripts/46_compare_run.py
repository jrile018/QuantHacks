"""
46_compare_run.py - strict comparison of a fresh run with a saved reference run (used by hpg_bundle/run_noleak.sbatch).

v2 (after the lead's audit, finding A9): the first version only compared trade keys and Sharpe and could print MATCH for files that
differed in other columns or had rows missing. This version:
  * requires the same set of rows (unique keys, same count) in every compared file, no missing or extra rows
  * compares EVERY numeric column of every compared file under a tolerance (default 1e-6 absolute, 1e-6 relative); NaN must match NaN
  * compares the daily account curve (ledger_daily.csv) day by day, not only its summary
  * hashes the inputs the run depends on and the outputs it produced, and writes them to a manifest
  * exits 1 on DIFFERENT, 2 on an invalid reference (missing file, duplicate keys), 0 only on a full MATCH
--ref: folder with the reference copies. Files compared (if present in the reference): standard_results.csv, standard_portfolio.csv,
       ledger_daily.csv, ledger_trades.csv, ledger_summary.csv, offer_trades_v3.csv (or v2), offer_strategy_trades_v3.csv (or v2).
Regression fixtures:  python 46_compare_run.py --fixtures   (two cases that fooled the first version must now FAIL; exits 0 if they do)
"""
import os, sys, argparse, hashlib, json
import numpy as np, pandas as pd
ap = argparse.ArgumentParser(); ap.add_argument('--ref'); ap.add_argument('--tol', type=float, default=1e-6); ap.add_argument('--fixtures', action='store_true'); a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__)); REP = os.path.join(here, '..', 'reports'); FDS = os.path.join(here, '..', 'data', 'fds'); RAW = os.path.join(here, '..', 'data', 'raw')
KEYS = {'standard_results.csv': ['strategy', 'engine', 'costs', 'window'], 'standard_portfolio.csv': ['strategy', 'window'], 'ledger_daily.csv': ['date'],
        'ledger_trades.csv': ['tk', 'signal'], 'ledger_summary.csv': ['window'], 'offer_trades_v3.csv': ['cik', 'signal'], 'offer_trades_v2.csv': ['cik', 'signal'],
        'offer_strategy_trades_v3.csv': ['cik', 'signal'], 'offer_strategy_trades_v2.csv': ['cik', 'signal']}
WHERE = {k: (FDS if 'offer_' in k else REP) for k in KEYS}

def compare(ref_df, new_df, keys, tol, name):
    """returns list of problem strings (empty = identical under tolerance)"""
    probs = []
    for lab, df in (('reference', ref_df), ('new', new_df)):
        miss = [k for k in keys if k not in df.columns]
        if miss: return [f'{name}: {lab} is missing key columns {miss}']
        if df.duplicated(keys).any(): probs.append(f'{name}: {lab} has duplicate keys ({int(df.duplicated(keys).sum())})')
    if probs: return probs
    r = ref_df.set_index(keys).sort_index(); n = new_df.set_index(keys).sort_index()
    only_r = r.index.difference(n.index); only_n = n.index.difference(r.index)
    if len(only_r): probs.append(f'{name}: {len(only_r)} rows only in reference, e.g. {list(only_r[:3])}')
    if len(only_n): probs.append(f'{name}: {len(only_n)} rows only in new, e.g. {list(only_n[:3])}')
    if set(r.columns) != set(n.columns): probs.append(f'{name}: column sets differ: only ref {sorted(set(r.columns) - set(n.columns))}, only new {sorted(set(n.columns) - set(r.columns))}')
    common = r.index.intersection(n.index); cols = [c for c in r.columns if c in n.columns]
    for c in cols:
        x, y = r.loc[common, c], n.loc[common, c]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            xn, yn = x.isna().values, y.isna().values
            if (xn != yn).any(): probs.append(f'{name}.{c}: NaN pattern differs in {int((xn != yn).sum())} rows'); continue
            xv, yv = x.values[~xn].astype(float), y.values[~yn].astype(float)
            bad = ~np.isclose(xv, yv, rtol=tol, atol=tol)
            if bad.any(): probs.append(f'{name}.{c}: {int(bad.sum())} values differ, max abs diff {np.abs(xv - yv)[bad].max():.3g}')
        else:
            if (x.astype(str).values != y.astype(str).values).any(): probs.append(f'{name}.{c}: text values differ')
    return probs

def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for ch in iter(lambda: f.read(1 << 20), b''): h.update(ch)
    return h.hexdigest()

if a.fixtures:
    import tempfile
    base_r = pd.DataFrame(dict(strategy=['A', 'B'], engine=['e', 'e'], costs=['c', 'c'], window=['w', 'w'], trades=[10, 20], avg_trade_pct=[1.0, 2.0], win_rate=[0.5, 0.6], sharpe=[1.0, 2.0], ci_lo=[0.0, 1.0], ci_hi=[2.0, 3.0]))
    # fixture A: a strategy row deleted from both files -> the first version said MATCH (keys matched after the merge). Now the reference must be the full set.
    new_a = base_r.iloc[:1].copy()
    # fixture B: means, win rates, interval endpoints changed, keys and Sharpe kept -> first version said MATCH
    new_b = base_r.copy(); new_b['avg_trade_pct'] = [9.0, 9.0]; new_b['win_rate'] = [0.1, 0.1]; new_b['ci_lo'] = [-5.0, -5.0]
    pa = compare(base_r, new_a, KEYS['standard_results.csv'], 1e-6, 'fixtureA'); pb = compare(base_r, new_b, KEYS['standard_results.csv'], 1e-6, 'fixtureB')
    pc = compare(base_r, base_r.copy(), KEYS['standard_results.csv'], 1e-6, 'fixtureC')
    print('fixture A (row deleted):', 'FAILS as it should' if pa else 'WRONGLY PASSES', pa[:2]); print('fixture B (values changed, keys and Sharpe kept):', 'FAILS as it should' if pb else 'WRONGLY PASSES', pb[:2])
    print('fixture C (identical):', 'passes as it should' if not pc else 'WRONGLY FAILS', pc[:2])
    sys.exit(0 if (pa and pb and not pc) else 1)

if not a.ref: sys.exit('need --ref')
problems = []; compared = []; manifest = dict(reference=os.path.abspath(a.ref), compared=[], inputs={}, outputs={})
for fn, keys in KEYS.items():
    rp = os.path.join(a.ref, fn); np_ = os.path.join(WHERE[fn], fn)
    if not os.path.exists(rp): continue
    if not os.path.exists(np_): problems.append(f'{fn}: reference exists but the new run did not produce it'); continue
    try: r = pd.read_csv(rp); n = pd.read_csv(np_)
    except Exception as ex: problems.append(f'{fn}: cannot read ({ex})'); continue
    pr = compare(r, n, keys, a.tol, fn); problems += pr; compared.append(fn); manifest['compared'].append(dict(file=fn, rows_ref=len(r), rows_new=len(n), problems=len(pr)))
    manifest['outputs'][fn] = sha(np_); manifest['outputs'][fn + ' (reference)'] = sha(rp)
REQUIRED = ['standard_results.csv', 'ledger_daily.csv', 'ledger_trades.csv', 'ledger_summary.csv', 'offer_trades_v3.csv', 'offer_strategy_trades_v3.csv']
missing_req = [f for f in REQUIRED if not os.path.exists(os.path.join(a.ref, f))]
if missing_req: print('INVALID REFERENCE: required reference files missing:', missing_req); sys.exit(2)
if any('duplicate keys' in p for p in problems): print('INVALID: duplicate keys in a compared file'); [print('  -', p) for p in problems if 'duplicate' in p]; sys.exit(2)
if not compared: print('INVALID REFERENCE: no comparable files found in', a.ref); sys.exit(2)
for fn in ('fds_features.csv', 'fds_labels.csv', 'fds_options.csv', 'fds_lookup_cik_ticker.csv', 'fds_realprice.csv', 'stock_trades_real_v2.csv', 'stock_trades_real_v3.csv'):
    p = os.path.join(FDS, fn)
    if os.path.exists(p): manifest['inputs'][fn] = sha(p)
for fn in ('prices.csv', 'splits.csv', 'events_8k.csv'):
    p = os.path.join(RAW, fn)
    if os.path.exists(p): manifest['inputs'][fn] = sha(p)
json.dump(manifest, open(os.path.join(REP, 'run_manifest.json'), 'w'), indent=1, default=str)
print('compared files:', compared); print('input hashes written to reports/run_manifest.json')
if problems:
    print('VERDICT: DIFFERENT. Problems:'); [print('  -', p) for p in problems[:40]]; sys.exit(1)
print('VERDICT: MATCH. Every row and every numeric value of the compared files agrees with the reference within', a.tol); sys.exit(0)
