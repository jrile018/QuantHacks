#!/usr/bin/env python3
"""
16_build_fds.py  -  point-in-time company snapshot (FDS) for SIC 2836 biologics.

One row per (company, market day). Decision clock = market close (21:00 UTC rule).
Rule for anything that only has a DATE (SEC filings): usable from the NEXT calendar day.
Timestamped items (news) are usable if published before 16:00 America/New_York that day (v2 fix: was a fixed 21:00 UTC, wrong in summer).
v2 (2026-10-04): real (unadjusted) prices and market cap from the split history; trial features from monthly AACT registry snapshots;
SEC comment letter counts dropped (released weeks after their date); spike filter no longer looks at the next day's bar.
Features and labels are written to separate files so labels cannot leak into features.
Matrix values are numeric only. Missing = NaN, with a reason code in fds_missing.csv.
"""
import os, sys, json, glob, re
import numpy as np, pandas as pd

BASE = os.environ.get('BP_DATA') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
RAW, PROC, OUT = [os.path.join(BASE, d) for d in ('raw', 'processed', 'fds')]
os.makedirs(OUT, exist_ok=True)
PANEL_START = pd.Timestamp('2024-01-02')
CAL_START = pd.Timestamp('2019-06-01')

# missing / status codes
C_OK, C_NOTYET, C_NEVER, C_STALE, C_INSUFF, C_NOTCOLL, C_INAPP, C_DERIVED = 0, 1, 2, 3, 4, 5, 6, 7
CODE_LEGEND = {C_OK: 'present', C_NOTYET: 'not public yet at this date', C_NEVER: 'company never reported it',
               C_STALE: 'present but older than 200 days', C_INSUFF: 'not enough history to compute',
               C_NOTCOLL: 'not collected', C_INAPP: 'inapplicable or none in coverage window',
               C_DERIVED: 'present, derived from other reported values'}

# ------------------------------------------------------------------ helpers
F, C, DOC = {}, {}, {}

def add(name, values, code=None, block='', unit='', desc=''):
    v = pd.Series(np.asarray(values, dtype='float64'))
    F[name] = v.to_numpy()
    if code is None:
        code = np.where(v.notna(), C_OK, C_INAPP)
    C[name] = np.asarray(code, dtype='int8')
    DOC[name] = (block, unit, desc)

def dcode(val, parents):
    """reason code for a derived value: 0 if present else worst code among NaN parents, else inapplicable"""
    val = pd.Series(np.asarray(val, dtype='float64'))
    cs = [np.where(pd.Series(F[p]).isna(), C[p], 0) for p in parents]
    m = np.maximum.reduce(cs) if cs else np.zeros(len(val), dtype=int)
    return np.where(val.notna(), C_OK, np.where(m == 0, C_INAPP, m))

import time
_T0 = time.time()
def log(*a):
    print(f'[{time.time() - _T0:5.0f}s]', *a, flush=True)

# ------------------------------------------------------------------ load basics
log('loading')
fl = pd.read_csv(os.path.join(RAW, 'facts_long.csv'), usecols=['file', 'cik'])
fl['ticker'] = fl.file.str.replace('.json', '', regex=False)
tmap = fl.drop_duplicates('ticker')[['ticker', 'cik']].reset_index(drop=True)
tmap['cik'] = tmap.cik.astype(int)
T2C = dict(zip(tmap.ticker, tmap.cik))

px = pd.read_csv(os.path.join(RAW, 'prices.csv'), parse_dates=['date'])
cal = pd.DatetimeIndex(sorted(px[px.ticker == 'SPY'].date.unique()))
END = cal.max()
DAILY = pd.date_range(CAL_START, END)

# ------------------------------------------------------------------ price cleaning
def clean_one(g, tk, logrows):
    g = g.sort_values('date').reset_index(drop=True)
    n0 = len(g)
    g = g[(g.close > 0.02) & g.close.notna()].reset_index(drop=True)
    drop_low = n0 - len(g)
    # v2: the old 'reverting spike' filter looked at the NEXT day's close to decide whether a bar exists (look-ahead). It removed 1 bar
    # in the whole dataset (ELOX). Removed. Bad prints are now left in and the real-price floor handles sub-dollar names.
    bad = np.zeros(len(g), bool)
    c = g.close.to_numpy()
    r = np.ones(len(g))
    r[1:] = c[1:] / c[:-1]
    big = np.maximum(r, 1 / r)
    k = np.round(big)
    split = (big > 3) & (k >= 2) & (np.abs(big - k) / np.maximum(k, 1) < 0.05)
    ret = r - 1
    ret[split] = 0.0
    adj = c[0] * np.cumprod(1 + ret)
    adj = adj * (c[-1] / adj[-1]) if len(adj) else adj
    g['adj'] = adj
    g['fac'] = adj / c
    g['adj_open'] = g.open * g.fac
    g['rng'] = (g.high - g.low) / g.close
    g['dvol'] = g.close * g.volume
    logrows.append((tk, T2C.get(tk, 0), drop_low, int(bad.sum()), int(split.sum())))
    return g

log('cleaning prices')
logrows, parts = [], {}
for tk, g in px.groupby('ticker'):
    parts[tk] = clean_one(g, tk, logrows)
pd.DataFrame(logrows, columns=['ticker', 'cik', 'dropped_low_price_bars', 'dropped_spike_bars', 'split_days_adjusted']
             ).to_csv(os.path.join(OUT, 'fds_price_cleaning_log.csv'), index=False)

def wide(col):
    d = {tk: g.set_index('date')[col] for tk, g in parts.items()}
    return pd.DataFrame(d).reindex(cal)

ADJ, ADJO, RNG, DV, VOL, TRD, CLS = [wide(c) for c in ('adj', 'adj_open', 'rng', 'dvol', 'volume', 'n_trades', 'close')]
STK = [t for t in ADJ.columns if t in T2C]

# panel keys: stock has a (clean) bar that day
has = CLS[STK].notna()
pl = has.unstack()
pl = pl[pl & (pl.index.get_level_values(1) >= PANEL_START)]
panel = pd.DataFrame({'ticker': pl.index.get_level_values(0), 'date': pl.index.get_level_values(1)})
panel['cik'] = panel.ticker.map(T2C)
panel = panel.sort_values(['cik', 'date']).reset_index(drop=True)
N = len(panel)
log('panel rows', N, 'tickers', panel.ticker.nunique())
KT = pd.MultiIndex.from_arrays([panel.ticker, panel.date])
KC = pd.MultiIndex.from_arrays([panel.cik, panel.date])

def at_t(w):
    return w.unstack().reindex(KT).to_numpy()
def at_c(w):
    return w.unstack().reindex(KC).to_numpy()
def at_d(s):
    return s.reindex(panel.date).to_numpy()

# ------------------------------------------------------------------ MARKET BLOCK
log('market block')
A = ADJ.ffill(limit=3)
LR = np.log(A / A.shift(1))
xbi = A['XBI']
spy = A['SPY']
def retw(w, n): return w / w.shift(n) - 1
for n in (1, 5, 20, 60, 120):
    add(f'px_ret_{n}d', at_t(retw(A, n)), block='market', unit='fraction', desc=f'adjusted close return over last {n} market days')
for n in (5, 20, 60):
    add(f'px_xs_{n}d', at_t(retw(A, n).sub(retw(xbi.to_frame(), n)['XBI'], axis=0)), block='market', unit='fraction', desc=f'{n}d return minus XBI')
add('px_vol_20d', at_t(LR.rolling(20, min_periods=15).std()), block='market', unit='daily_std', desc='std of daily log returns, 20d')
add('px_vol_60d', at_t(LR.rolling(60, min_periods=40).std()), block='market', unit='daily_std', desc='std of daily log returns, 60d')
add('px_off_hi_252', at_t(A / A.rolling(252, min_periods=120).max() - 1), block='market', unit='fraction', desc='distance below 252d high')
add('px_off_lo_252', at_t(A / A.rolling(252, min_periods=120).min() - 1), block='market', unit='fraction', desc='distance above 252d low')
add('px_adv20_usd_m', at_t(DV.rolling(20, min_periods=10).mean() / 1e6), block='market', unit='usd_m', desc='avg dollar volume 20d')
add('px_vol_spike', at_t((VOL / VOL.rolling(20, min_periods=10).median().shift(1).clip(lower=1000)).clip(upper=100)), block='market', unit='ratio', desc="today's volume / median volume of prior 20d (median floored at 1000 shares, ratio capped at 100)")
add('px_gap_open', at_t(ADJO / A.shift(1) - 1), block='market', unit='fraction', desc='open vs previous close, same day')
add('px_range_20d', at_t(RNG.rolling(20, min_periods=10).mean()), block='market', unit='fraction', desc='mean (high-low)/close, 20d')
add('px_trades_20d', at_t(TRD.rolling(20, min_periods=10).mean()), block='market', unit='count', desc='mean trades per day, 20d')
add('px_bars_20d', at_t(CLS.notna().astype(float).rolling(20, min_periods=1).sum()), block='market', unit='count', desc='days with a price bar in last 20 market days')
# v2: REAL price. The price source is adjusted for splits that happened LATER, so the delivered close is not what traders saw.
# real close on day t = delivered close / product of (split_from / split_to) over all splits executed AFTER t  (data/raw/splits.csv, script 43)
SPL = pd.read_csv(os.path.join(RAW, 'splits.csv'), parse_dates=['execution_date']); SPL['r'] = SPL.split_from / SPL.split_to
RAFT = pd.DataFrame(1.0, index=cal, columns=CLS.columns)           # product of later split ratios, per (day, ticker)
for tk_, g_ in SPL.groupby('ticker'):
    if tk_ not in RAFT.columns: continue
    for e_, r_ in zip(g_.execution_date, g_.r): RAFT.loc[RAFT.index < e_, tk_] *= r_
assert (RAFT > 0).all().all()
add('px_close_real', at_t(CLS / RAFT), block='market', unit='usd', desc='real close as traders saw it that day (delivered close with later splits undone)')
F_RAFT = at_t(RAFT)   # kept for the market cap below; not a feature
# the old px_close_raw (delivered, split adjusted to today) is NOT written: it reveals later reverse splits
for nm, ser in (('spy', spy), ('xbi', xbi)):
    for n in (5, 20, 60):
        if nm == 'spy' and n == 60: continue
        add(f'mkt_{nm}_ret_{n}d', at_d(ser / ser.shift(n) - 1), block='market_state', unit='fraction', desc=f'{nm.upper()} return {n}d (same for all companies on a date)')
    add(f'mkt_{nm}_vol_20d', at_d(np.log(ser / ser.shift(1)).rolling(20, min_periods=15).std()), block='market_state', unit='daily_std', desc=f'{nm.upper()} 20d volatility')
add('mkt_xbi_off_hi_252', at_d(xbi / xbi.rolling(252, min_periods=120).max() - 1), block='market_state', unit='fraction', desc='XBI distance below 252d high')

# calendar
d = panel.date
qend = d.dt.to_period('Q').dt.end_time.dt.normalize()
qstart = d.dt.to_period('Q').dt.start_time
add('cal_dow', d.dt.dayofweek, block='calendar', unit='0-4', desc='day of week, Monday=0')
add('cal_month', d.dt.month, block='calendar', unit='1-12', desc='month')
add('cal_doy', d.dt.dayofyear, block='calendar', unit='1-366', desc='day of year')
add('cal_days_to_qend', (qend - d).dt.days, block='calendar', unit='days', desc='days to calendar quarter end')
add('cal_days_since_qstart', (d - qstart).dt.days, block='calendar', unit='days', desc='days since calendar quarter start')

# ------------------------------------------------------------------ FINANCIAL BLOCK (SEC XBRL, point in time)
log('financial block')
INST = {'Assets': 'assets', 'AssetsCurrent': 'cur_assets', 'Liabilities': 'liab', 'LiabilitiesCurrent': 'cur_liab',
        'LiabilitiesAndStockholdersEquity': 'lse', 'StockholdersEquity': 'equity',
        'RetainedEarningsAccumulatedDeficit': 'deficit', 'CashAndCashEquivalentsAtCarryingValue': 'cash',
        'CashCashEquivalentsAndShortTermInvestments': 'cash_sti', 'ShortTermInvestments': 'sti',
        'MarketableSecuritiesCurrent': 'mkt_sec', 'AvailableForSaleSecuritiesDebtSecurities': 'afs', 'LongTermDebt': 'debt',
        'EntityCommonStockSharesOutstanding': 'shares', 'EntityPublicFloat': 'float'}
FLOW = {'ResearchAndDevelopmentExpense': 'rd', 'GeneralAndAdministrativeExpense': 'ga', 'OperatingExpenses': 'opex',
        'OperatingIncomeLoss': 'opinc', 'NetIncomeLoss': 'ni', 'NetCashProvidedByUsedInOperatingActivities': 'opcf',
        'NetCashProvidedByUsedInFinancingActivities': 'fincf', 'ProceedsFromIssuanceOfCommonStock': 'stockproc',
        'ShareBasedCompensation': 'sbc', 'Revenues': 'rev_a', 'RevenueFromContractWithCustomerExcludingAssessedTax': 'rev_b'}
WANT = {**INST, **FLOW}
rows = []
for f in glob.glob(os.path.join(RAW, 'companyfacts', '*.json')):
    j = json.load(open(f))
    cik = int(j['cik'])
    for tax in ('us-gaap', 'dei'):
        for tag, short in WANT.items():
            e = j['facts'].get(tax, {}).get(tag)
            if not e: continue
            for unit, arr in e['units'].items():
                for r in arr:
                    if 'filed' in r and 'end' in r:
                        rows.append((cik, short, r.get('start'), r['end'], r['val'], r.get('accn'), r['filed']))
facts = pd.DataFrame(rows, columns=['cik', 'short', 'start', 'end', 'val', 'accn', 'filed'])
for c_ in ('start', 'end', 'filed'):
    facts[c_] = pd.to_datetime(facts[c_])
facts = facts.sort_values(['cik', 'short', 'filed']).reset_index(drop=True)
log('fact rows', len(facts))

def ttm_from(cur):
    ann = [(k, v) for k, v in cur.items() if 350 <= (k[1] - k[0]).days <= 380]
    if not ann: return (np.nan, pd.NaT, None)
    (as_, ae), (av, aa) = max(ann, key=lambda x: x[0][1])
    cand = [(k, v) for k, v in cur.items() if k[1] > ae and 60 <= (k[1] - k[0]).days <= 300 and abs((k[0] - (ae + pd.Timedelta(days=1))).days) <= 7]
    if not cand: return (av, ae, aa)
    (ys, ye), (yv, ya) = max(cand, key=lambda x: (x[0][1], (x[0][1] - x[0][0]).days))
    prior = [v for k, v in cur.items() if abs((k[0] - (ys - pd.Timedelta(days=365))).days) <= 10 and abs((k[1] - (ye - pd.Timedelta(days=365))).days) <= 10]
    if not prior: return (np.nan, ye, ya)
    return (av + yv - prior[0][0], ye, ya)

TL = {}
_tldp = os.path.join(OUT, '_tld_v2.pkl')
_groups = [] if os.path.exists(_tldp) else facts.groupby(['cik', 'short'], sort=False)
for (cik, short), g in _groups:
    out = []
    if short in INST.values():
        cur = {}
        for fdt, gg in g.groupby('filed', sort=True):
            for r in gg.itertuples():
                cur[r.end] = (r.val, r.accn)
            e = max(cur)
            out.append((fdt, cur[e][0], e, cur[e][1]))
    else:
        cur = {}
        for fdt, gg in g.groupby('filed', sort=True):
            for r in gg.itertuples():
                if pd.isna(r.start): continue
                cur[(r.start, r.end)] = (r.val, r.accn)
            v, e, a = ttm_from(cur)
            out.append((fdt, v, e, a))
    TL.setdefault(short, []).append(pd.DataFrame(out, columns=['filed', 'val', 'end', 'accn']).assign(cik=cik))
if os.path.exists(_tldp):
    TLD = pd.read_pickle(_tldp)
else:
    TLD = {s: pd.concat(v, ignore_index=True) for s, v in TL.items()}
    pd.to_pickle(TLD, _tldp + '.tmp'); os.replace(_tldp + '.tmp', _tldp)
log('timelines ready')
prov = pd.concat([v.assign(tag=s) for s, v in TLD.items()], ignore_index=True)
prov['usable_from'] = prov.filed + pd.Timedelta(days=1)
prov[['cik', 'tag', 'filed', 'usable_from', 'end', 'val', 'accn']].to_csv(os.path.join(OUT, 'fds_fin_provenance.csv'), index=False)

def add_div(tl):
    """divisor = product of later reverse splits (share count drops by an integer ratio and stays there)"""
    tl = tl.sort_values(['cik', 'filed']).reset_index(drop=True)
    out = np.ones(len(tl)); fixes = []
    for cik, g in tl.groupby('cik'):
        v = g.val.to_numpy(dtype=float); ix = g.index.to_numpy(); n = len(v); k = np.ones(n)
        # filers sometimes enter share counts x1000 by mistake: fix when value/1000 matches the neighbours
        for i in range(n):
            nb = np.r_[v[max(0, i - 2):i], v[i + 1:i + 3]]
            if len(nb) and v[i] >= 1e8:
                md = np.median(nb)
                if md > 0 and v[i] / md > 50 and 0.3 <= v[i] / 1000 / md <= 3:
                    fixes.append((cik, g.filed.iloc[i], v[i], v[i] / 1000)); v[i] = v[i] / 1000
        tl.loc[ix, 'val'] = v
        for i in range(1, n):
            if not (v[i - 1] > 0 and v[i] > 0): continue
            r = v[i] / v[i - 1]
            if r <= 0.5:
                kk = 1 / r; kr = round(kk)
                if kr >= 2 and abs(kk - kr) / kr < 0.04:
                    prev_ok = (i < 2) or (v[i - 2] > 0 and 0.5 <= v[i - 1] / v[i - 2] <= 2)
                    if prev_ok: k[i] = kr
        suff = np.cumprod(k[::-1])[::-1]
        out[ix] = np.append(suff[1:], 1.0)
    tl['div'] = out
    pd.DataFrame(fixes, columns=['cik', 'filed', 'reported', 'used']).to_csv(os.path.join(OUT, 'fds_share_scale_fixes.csv'), index=False)
    return tl
TLD['shares'] = add_div(TLD['shares'])
pd.DataFrame({'cik': TLD['shares'].cik, 'filed': TLD['shares'].filed, 'div': TLD['shares']['div']}).query('div > 1').to_csv(os.path.join(OUT, 'fds_share_split_divisors.csv'), index=False)

def asof_tbl(short, shift_days=0):
    P = panel[['cik', 'date']].copy()
    P['d2'] = P.date - pd.Timedelta(days=shift_days)
    P = P.reset_index().sort_values('d2')
    tl = TLD.get(short)
    if tl is None:
        out = pd.DataFrame({'val': np.nan, 'end': pd.NaT, 'usable': pd.NaT}, index=range(N))
        return out, np.zeros(N, bool)
    tl = tl.assign(usable=tl.filed + pd.Timedelta(days=1)).sort_values('usable')
    keep_cols = ['cik', 'usable', 'val', 'end'] + (['div'] if 'div' in tl.columns else [])
    m = pd.merge_asof(P, tl[keep_cols], left_on='d2', right_on='usable', by='cik', direction='backward')
    m = m.set_index('index').reindex(range(N))
    ever = panel.cik.isin(tl.cik.unique()).to_numpy()
    return m, ever

M, EVER = {}, {}
for s in list(INST.values()) + list(FLOW.values()):
    M[s], EVER[s] = asof_tbl(s)
M['shares_1y'], EVER['shares_1y'] = asof_tbl('shares', 365)

def lvl_code(s, kind='x'):
    m = M[s]; ever = EVER[s]
    matched = m.usable.notna().to_numpy()
    val = m.val.notna().to_numpy()
    return np.where(val, C_OK, np.where(matched, C_INSUFF, np.where(ever, C_NOTYET, C_NEVER)))

def put_level(name, s, scale, block, unit, desc, stale=True):
    m = M[s]
    v = m.val / scale
    code = lvl_code(s)
    if stale:
        age = (panel.date - m.end).dt.days
        code = np.where((code == C_OK) & (age > 200), C_STALE, code)
    add(name, v, code, block, unit, desc)

BS = 'fin_balance'; FL = 'fin_flow'
put_level('fin_assets_m', 'assets', 1e6, BS, 'usd_m', 'total assets, latest filed')
put_level('fin_cur_assets_m', 'cur_assets', 1e6, BS, 'usd_m', 'current assets')
put_level('fin_cur_liab_m', 'cur_liab', 1e6, BS, 'usd_m', 'current liabilities')
put_level('fin_equity_m', 'equity', 1e6, BS, 'usd_m', "stockholders' equity")
put_level('fin_deficit_m', 'deficit', 1e6, BS, 'usd_m', 'accumulated deficit (negative = deficit)')
put_level('fin_debt_m', 'debt', 1e6, BS, 'usd_m', 'long term debt as tagged (missing often means no debt tag)')
put_level('fin_cash_m', 'cash', 1e6, BS, 'usd_m', 'cash and cash equivalents')
put_level('fin_float_m', 'float', 1e6, BS, 'usd_m', 'public float from cover page (reported once a year, as of mid-year)', stale=False)
put_level('fin_shares_m', 'shares', 1e6, BS, 'shares_m', 'shares outstanding from cover page')

# liabilities (derived when not tagged)
liab = M['liab'].val.copy()
lcode = lvl_code('liab')
der = liab.isna() & M['lse'].val.notna() & M['equity'].val.notna() & (M['lse'].end == M['equity'].end)
liab = liab.where(~der, M['lse'].val - M['equity'].val)
lcode = np.where(der, C_DERIVED, lcode)
add('fin_liab_m', liab / 1e6, lcode, BS, 'usd_m', 'total liabilities (derived = assets - equity when not tagged)')

# liquidity = cash + short term investments, matched on the same period
cash, ce = M['cash'].val, M['cash'].end
combo = M['cash_sti']; sti = M['sti']; msec = M['mkt_sec']; afs = M['afs']
inv = pd.Series(np.nan, index=range(N)); idef = pd.Series(0.0, index=range(N))
for src, dd in ((afs, 4), (msec, 2), (sti, 2)):
    ok = src.val.notna() & (src.end == ce)
    inv = inv.where(~ok, src.val); idef = idef.where(~ok, dd)
liq = cash.copy(); ldef = pd.Series(np.where(cash.notna(), 3, 0), index=range(N), dtype=float)
okI = inv.notna(); liq = liq.where(~okI, cash + inv); ldef = ldef.where(~okI, idef)
okC = combo.val.notna() & ((combo.end == ce) | cash.isna())
liq = liq.where(~okC, combo.val); ldef = ldef.where(~okC, 1)
lq_code = np.where(liq.notna(), C_OK, lvl_code('cash'))
age_c = (panel.date - ce).dt.days
lq_code = np.where((lq_code == C_OK) & (age_c > 200), C_STALE, lq_code)
add('fin_liq_m', liq / 1e6, lq_code, BS, 'usd_m', 'cash + short term investments (same period only)')
add('fin_liq_def', ldef.where(liq.notna()), lq_code, BS, 'code', '1=combined tag 2=cash+ST investments 3=cash only (may understate) 4=cash+AFS securities')

# TTM flows
for s, desc in (('rd', 'R&D'), ('ga', 'G&A'), ('opex', 'operating expenses'),
                ('opinc', 'operating income'), ('ni', 'net income'),
                ('opcf', 'operating cash flow'), ('fincf', 'financing cash flow'),
                ('stockproc', 'proceeds from common stock issuance'), ('sbc', 'stock based compensation')):
    put_level(f'fin_{s}_ttm_m', s, 1e6, FL, 'usd_m', f'{desc}, trailing 12 months from filed periods')
rev = M['rev_a'].val.where(M['rev_a'].val.notna(), M['rev_b'].val)
rcode = np.where(M['rev_a'].val.notna(), lvl_code('rev_a'), lvl_code('rev_b'))
add('fin_rev_ttm_m', rev / 1e6, rcode, FL, 'usd_m', 'revenue TTM (Revenues, else contract revenue)')

# ages and alignment
add('fin_age_bs_days', (panel.date - M['assets'].end).dt.days, lvl_code('assets'), 'fin_meta', 'days', 'days since latest balance sheet date')
add('fin_age_pub_days', (panel.date - (M['assets'].usable - pd.Timedelta(days=1))).dt.days, lvl_code('assets'), 'fin_meta', 'days', 'days since that balance sheet became public (filing date)')
add('fin_bs_aligned', ((M['cash'].end == M['assets'].end) & M['assets'].end.notna()).astype(float).where(M['assets'].end.notna()), lvl_code('assets'), 'fin_meta', 'flag', '1 if cash and assets come from the same period')
add('fin_age_ttm_days', (panel.date - M['rd'].end).dt.days, lvl_code('rd'), 'fin_meta', 'days', 'days since end of period behind the R&D TTM')

# derived
fv = lambda n: pd.Series(F[n])
burn = -fv('fin_opcf_ttm_m') / 4
burn = burn.where(burn > 0)
add('fin_burn_q_m', burn, dcode(burn, ['fin_opcf_ttm_m']), 'fin_derived', 'usd_m', 'quarterly cash burn (only when operating cash flow < 0)')
rw = (fv('fin_liq_m') / burn).clip(0, 40)
add('fin_runway_q', rw, dcode(rw, ['fin_liq_m', 'fin_burn_q_m']), 'fin_derived', 'quarters', 'liquidity / quarterly burn, capped at 40')
x = fv('fin_cur_assets_m') / fv('fin_cur_liab_m').where(fv('fin_cur_liab_m') > 0)
add('fin_cur_ratio', x, dcode(x, ['fin_cur_assets_m', 'fin_cur_liab_m']), 'fin_derived', 'ratio', 'current assets / current liabilities')
x = fv('fin_liq_m') / fv('fin_assets_m').where(fv('fin_assets_m') > 0)
add('fin_liq_to_assets', x, dcode(x, ['fin_liq_m', 'fin_assets_m']), 'fin_derived', 'ratio', 'liquidity / total assets')
x = fv('fin_rd_ttm_m') / fv('fin_opex_ttm_m').where(fv('fin_opex_ttm_m') > 0)
add('fin_rd_share', x, dcode(x, ['fin_rd_ttm_m', 'fin_opex_ttm_m']), 'fin_derived', 'ratio', 'R&D / operating expenses')
x = fv('fin_debt_m') / fv('fin_liq_m').where(fv('fin_liq_m') > 0)
add('fin_debt_to_liq', x, dcode(x, ['fin_debt_m', 'fin_liq_m']), 'fin_derived', 'ratio', 'debt / liquidity')
x = fv('fin_stockproc_ttm_m') / fv('fin_liq_m').where(fv('fin_liq_m') > 0)
add('fin_raise_to_liq', x, dcode(x, ['fin_stockproc_ttm_m', 'fin_liq_m']), 'fin_derived', 'ratio', 'stock proceeds TTM / liquidity (financing intensity)')
x = (fv('fin_equity_m') < 0).astype(float).where(fv('fin_equity_m').notna())
add('fin_equity_neg', x, dcode(x, ['fin_equity_m']), 'fin_derived', 'flag', '1 if equity below zero')
# The price source is already split adjusted to today. Cover page shares are in the units of their own date, so
# earlier counts are divided by every LATER reverse split found in the share series (unit conversion only, not information).
# v2: shares in the units of day t = cover page shares, converted by the splits that happened between the filing date and day t
# (both known by day t). The old version converted by ALL later splits (future information) and multiplied by the adjusted price.
sh_filed = panel.date - pd.to_timedelta(pd.Series(F['fin_age_pub_days']).fillna(0).to_numpy(), unit='D')
RSF = np.ones(N)
for tk_, g_ in SPL.groupby('ticker'):
    m_ = (panel.ticker == tk_).to_numpy()
    if not m_.any(): continue
    d_ = panel.date.to_numpy()[m_]; f_ = sh_filed.to_numpy()[m_]; rs_ = np.ones(m_.sum())
    for e_, r_ in zip(g_.execution_date.to_numpy(), g_.r.to_numpy()): rs_[(f_ < e_) & (d_ >= e_)] *= r_
    RSF[m_] = rs_
sh_now = M['shares'].val / 1e6 / RSF
add('fin_shares_now_m', sh_now, np.where(sh_now.notna(), C_OK, lvl_code('shares')), BS, 'shares_m', 'cover page shares in the units of this day (splits between the filing and this day applied)')
mcap = pd.Series(F['px_close_real']) * sh_now
add('fin_mktcap_m', mcap, dcode(mcap, ['fin_shares_now_m']), 'fin_derived', 'usd_m', 'real close x shares in the units of this day (approximate)')
x = fv('fin_liq_m') / mcap.where(mcap > 0)
add('fin_liq_to_mcap', x, dcode(x, ['fin_liq_m', 'fin_mktcap_m']), 'fin_derived', 'ratio', 'liquidity / market cap (cash backing)')
x = (M['shares'].val / M['shares']['div']) / (M['shares_1y'].val / M['shares_1y']['div']) - 1    # later splits cancel in the ratio; only splits between the two filings remain, known by day t
add('fin_shares_chg_1y', x, np.where(x.notna(), C_OK, lvl_code('shares_1y')), 'fin_derived', 'fraction', 'change in cover page shares vs one year earlier (dilution)')
lm = np.log(mcap.where(mcap > 0))
add('fin_log_mktcap', lm, dcode(lm, ['fin_mktcap_m']), 'fin_derived', 'log_usd_m', 'log market cap')

# ------------------------------------------------------------------ FILINGS BLOCK (EDGAR index, date only -> usable next day)
log('filings block')
ef = pd.read_csv(os.path.join(RAW, 'edgar_filings.csv'), dtype={'form': str, 'items': str})
ef['cik'] = ef.cik.astype(int)
ef['filing_date'] = pd.to_datetime(ef.filing_date)
ef = ef[ef.cik.isin(set(T2C.values())) & (ef.filing_date >= CAL_START)]
def fgrp(f):
    u = f.upper()
    if u == '8-K': return 'k8'
    if u in ('4', '4/A'): return 'f4'
    if u == '144': return 'f144'
    if u.startswith('SC 13') or u.startswith('SCHEDULE 13'): return 's13'
    if u.startswith('424B'): return 'p424b'
    if u.startswith('S-3'): return 's3'
    if u.startswith('S-1'): return 's1'
    if u == 'S-8': return 's8'
    if u.startswith('NT '): return 'nt'
    if u in ('CORRESP', 'UPLOAD'): return 'seccorr'
    if u == 'EFFECT': return 'effect'
    if u == '10-Q': return 'q10'
    if u == '10-K': return 'k10'
    if u == '425': return 'f425'
    if u in ('DEF 14A', 'PRE 14A', 'DEFA14A', 'DEFM14A'): return 'proxy'
    return None
ef['g'] = ef.form.map(fgrp)
ALLC = sorted(set(T2C.values()))

def daily(df, datecol='filing_date'):
    w = df.groupby([datecol, 'cik']).size().unstack(fill_value=0)
    return w.reindex(index=DAILY, columns=ALLC, fill_value=0).astype(float)

def roll_n(cnt, n):
    return cnt.rolling(n, min_periods=1).sum().shift(1)

def days_since(cnt):
    s = (cnt > 0).to_numpy()
    arr = np.where(s, DAILY.values[:, None], np.datetime64('NaT'))
    last = pd.DataFrame(arr, index=DAILY, columns=ALLC).ffill().shift(1)
    delta = DAILY.values[:, None] - last.values.astype('datetime64[ns]')
    return pd.DataFrame(delta / np.timedelta64(1, 'D'), index=DAILY, columns=ALLC)

def add_count(name, w, block, unit, desc):
    v = at_c(w.reindex(cal))
    add(name, v, np.where(~np.isnan(v), C_OK, C_INAPP), block, unit, desc)

SPEC = {'k8': (30, 90, 365, 'dsl'), 'f4': (30, 90, 'dsl'), 'f144': (30, 90), 's13': (90,), 'p424b': (90, 365, 'dsl'),
        's3': (365,), 's1': (365,), 's8': (365,), 'nt': (365,), 'effect': (90,), 'q10': ('dsl',),
        # v2: 'seccorr' (CORRESP/UPLOAD) dropped: the SEC releases comment letters weeks after their index date
        'k10': ('dsl',), 'f425': (180,), 'proxy': (180,)}
GN = {'k8': '8-K', 'f4': 'Form 4', 'f144': 'Form 144', 's13': '13D/13G', 'p424b': '424B prospectus', 's3': 'S-3', 's1': 'S-1', 's8': 'S-8',
      'nt': 'late filing notice', 'seccorr': 'SEC comment letters', 'effect': 'registration effective', 'q10': '10-Q', 'k10': '10-K', 'f425': 'merger comms', 'proxy': 'proxy'}
for g_, spec in SPEC.items():
    cnt = daily(ef[ef.g == g_])
    for s_ in spec:
        if s_ == 'dsl':
            add_count(f'fil_{g_}_dsl', days_since(cnt), 'filings', 'days', f'days since last {GN[g_]} filing (none in coverage = NaN)')
        else:
            add_count(f'fil_{g_}_n{s_}', roll_n(cnt, s_), 'filings', 'count', f'{GN[g_]} filings in last {s_} days')
# 8-K item counts
k8 = ef[ef.g == 'k8'].copy()
for it in ['1.01', '1.02', '1.03', '2.02', '2.03', '2.05', '3.01', '3.02', '4.01', '4.02', '5.02', '5.07', '7.01', '8.01']:
    sel = k8[k8['items'].fillna('').str.split(',').apply(lambda L: it in [x.strip() for x in L])]
    add_count(f'fil_k8_i{it.replace(".", "_")}_n90', roll_n(daily(sel), 90), 'filings', 'count', f'8-Ks with item {it} in last 90 days')

# ------------------------------------------------------------------ 8-K CATEGORY HISTORY (Massive taxonomy)
log('category block')
ev = pd.read_csv(os.path.join(RAW, 'events_8k.csv'), usecols=['cik', 'filing_date', 'tertiary_category'])
ev['cik'] = ev.cik.astype(int); ev['filing_date'] = pd.to_datetime(ev.filing_date)
ev = ev[ev.cik.isin(set(T2C.values()))]
GRP = {'trial': ['clinical_trial_results'], 'reg': ['regulatory_decision'],
       'offer': ['public_offering', 'underwriting_agreement', 'private_placement', 'warrant_or_conversion'],
       'deal': ['partnership_or_collaboration', 'licensing_agreement', 'deal_termination'],
       'mgmt': ['executive_officer_departure', 'executive_officer_appointment', 'cfo_appointment', 'cfo_departure', 'ceo_departure', 'director_departure', 'director_appointment', 'executive_compensation_change'],
       'listing': ['listing_deficiency_notice'], 'earn': ['quarterly_earnings', 'preliminary_results', 'business_update', 'guidance_issuance_or_update'],
       'pres': ['investor_presentation'], 'debt': ['credit_facility']}
EVD = {}
for gname, cats in GRP.items():
    cnt = daily(ev[ev.tertiary_category.isin(cats)])
    EVD[gname] = cnt
    add_count(f'cat_{gname}_n90', roll_n(cnt, 90), 'category_history', 'count', f'8-Ks of type {gname} in last 90 days')
    add_count(f'cat_{gname}_n365', roll_n(cnt, 365), 'category_history', 'count', f'8-Ks of type {gname} in last 365 days')
    if gname in ('trial', 'reg', 'offer', 'deal', 'earn'):
        add_count(f'cat_{gname}_dsl', days_since(cnt), 'category_history', 'days', f'days since last 8-K of type {gname}')

# ------------------------------------------------------------------ INSIDER (Form 4)
log('insider block')
f4 = pd.read_csv(os.path.join(RAW, 'form4_tx.csv'), usecols=['cik', 'filing_date', 'code', 'shares', 'price', 'is_officer'])
f4['cik'] = f4.cik.astype(int); f4['filing_date'] = pd.to_datetime(f4.filing_date)
f4 = f4[f4.cik.isin(set(T2C.values())) & f4.code.isin(['P', 'S'])]
f4['val'] = np.where((f4.price > 0) & (f4.price < 5000), f4.shares * f4.price, 0.0)
buy, sell = f4[f4.code == 'P'], f4[f4.code == 'S']
def dsum(df, col):
    w = df.groupby(['filing_date', 'cik'])[col].sum().unstack(fill_value=0)
    return w.reindex(index=DAILY, columns=ALLC, fill_value=0).astype(float)
nb, ns = daily(buy), daily(sell)
vb, vs = dsum(buy, 'val'), dsum(sell, 'val')
nso = daily(sell[sell.is_officer == 1])
for n in (30, 90):
    add_count(f'ins_n_buy_{n}', roll_n(nb, n), 'insider', 'count', f'open market buy transactions, {n}d')
    add_count(f'ins_n_sell_{n}', roll_n(ns, n), 'insider', 'count', f'sell transactions, {n}d')
add_count('ins_net_val_90_m', (roll_n(vb, 90) - roll_n(vs, 90)) / 1e6, 'insider', 'usd_m', 'buys minus sells in dollars, 90d (not 10b5-1 aware)')
add_count('ins_n_officer_sell_90', roll_n(nso, 90), 'insider', 'count', 'officer sell transactions, 90d')

# ------------------------------------------------------------------ NEWS
log('news block')
nw = pd.read_csv(os.path.join(PROC, 'news_scored.csv'), usecols=['ticker', 'published_utc', 'ml_sent'])
nw = nw[nw.ticker.isin(STK)]
ts_ny = pd.to_datetime(nw.published_utc, utc=True).dt.tz_convert('America/New_York')     # v2: the close is 16:00 New York, not a fixed UTC hour
ts = ts_ny.dt.tz_localize(None)
d0 = ts.dt.normalize()
idx = cal.searchsorted(d0.values, side='left')
after = ((ts - d0) >= pd.Timedelta(hours=16)).to_numpy()
same = cal.values[np.minimum(idx, len(cal) - 1)] == d0.values
idx = idx + (after & same).astype(int)
keep = idx < len(cal)
nw = nw[keep].copy(); idx = idx[keep]
nw['day'] = cal[idx]
nw['neg'] = (nw.ml_sent < -0.1).astype(float)
cn = nw.groupby(['day', 'ticker']).size().unstack(fill_value=0).reindex(index=cal, columns=STK, fill_value=0).astype(float)
cs = nw.groupby(['day', 'ticker']).ml_sent.sum().unstack(fill_value=0).reindex(index=cal, columns=STK, fill_value=0).astype(float)
cg = nw.groupby(['day', 'ticker']).neg.sum().unstack(fill_value=0).reindex(index=cal, columns=STK, fill_value=0).astype(float)
for n in (5, 20, 60):
    v = at_t(cn.rolling(n, min_periods=1).sum())
    add(f'news_n_{n}d', v, np.where(~np.isnan(v), C_OK, C_INAPP), 'news', 'count', f'articles usable by close, last {n} market days')
for n in (5, 20):
    c_ = cn.rolling(n, min_periods=1).sum(); s_ = cs.rolling(n, min_periods=1).sum()
    add(f'news_sent_{n}d', at_t(s_ / c_.where(c_ > 0)), block='news', unit='score', desc=f'mean ML sentiment of articles, last {n} market days (NaN if none)')
c20 = cn.rolling(20, min_periods=1).sum()
add('news_neg_share_20d', at_t(cg.rolling(20, min_periods=1).sum() / c20.where(c20 > 0)), block='news', unit='fraction', desc='share of articles with sentiment < -0.1, 20d')
add('news_spike', at_t(cn.rolling(5, min_periods=1).sum() / (cn.rolling(60, min_periods=1).sum() / 12 + 0.5)), block='news', unit='ratio', desc='5d article count / typical 5d count over 60d')

# ------------------------------------------------------------------ TRIALS (v2: from monthly AACT registry snapshots, point in time)
# Each AACT snapshot is the registry as it stood on the snapshot date; it is usable from the next day. For day t we use the latest
# snapshot dated before t and read that snapshot's dates, phase and enrollment. Nothing from a later registry version can reach day t.
# A trial counts only once its first posting date is on or before the snapshot date. Trial-to-company mapping uses the sponsor list
# from trials.csv (Oct 2026 pull); a trial whose sponsor changed hands is attributed to today's owner (known limit). Month-only registry dates are the 1st in AACT;
# we move start dates to the END of the month (conservative: a trial is not counted active before it certainly started).
log('trials block (AACT snapshots)')
tr0 = pd.read_csv(os.path.join(RAW, 'trials.csv'), usecols=['ticker', 'nct_id'])
tr0['cik'] = tr0.ticker.map(T2C); tr0 = tr0[tr0.cik.notna()]; N2C = dict(zip(tr0.nct_id, tr0.cik.astype(int)))
AS = pd.read_csv(os.path.join(RAW, 'aact_snapshots.csv'), dtype=str,
                 usecols=['snapshot', 'nct_id', 'study_first_posted_date', 'start_date', 'start_date_type', 'completion_date', 'completion_date_type',
                          'primary_completion_date', 'primary_completion_date_type', 'phase', 'enrollment', 'results_first_posted_date'])
AS = AS[AS.nct_id.isin(N2C)].copy(); AS['cik'] = AS.nct_id.map(N2C)
AS['snap'] = pd.to_datetime(AS.snapshot, format='%Y%m%d')
for c_ in ('study_first_posted_date', 'start_date', 'completion_date', 'primary_completion_date', 'results_first_posted_date'):
    AS[c_] = pd.to_datetime(AS[c_], errors='coerce')
AS = AS[AS.study_first_posted_date.notna() & (AS.study_first_posted_date <= AS.snap) & AS.start_date.notna()].copy()
AS['start_eom'] = AS.start_date + pd.offsets.MonthEnd(0)
ph = AS.phase.fillna('').str.upper().str.replace(' ', '')
AS['ph3'] = ph.str.contains('PHASE3'); AS['ph2'] = ph.str.contains('PHASE2') & ~AS.ph3; AS['ph1'] = ph.str.contains('PHASE1') & ~AS.ph2 & ~AS.ph3
AS['enr'] = pd.to_numeric(AS.enrollment, errors='coerce').fillna(0)
snaps = np.sort(AS.snap.unique())
cols = ['tr_active', 'tr_active_p3', 'tr_active_p2', 'tr_active_p1', 'tr_started_365', 'tr_pc_prev90', 'tr_results_prev180', 'tr_dsl_results', 'tr_enroll_active_p3', 'tr_snapshot_age_days']
R = {c_: np.full(N, np.nan) for c_ in cols}
dates = panel.date.to_numpy(); D1 = np.timedelta64(1, 'D')
snap_idx = np.searchsorted(snaps, dates, side='left') - 1          # latest snapshot strictly before day t
for cik, ix in panel.groupby('cik').indices.items():
    T_ = AS[AS.cik == cik]
    if T_.empty:
        for c_ in cols:
            if c_ != 'tr_dsl_results': R[c_][ix] = 0.0
        R['tr_snapshot_age_days'][ix] = np.where(snap_idx[ix] >= 0, (dates[ix] - snaps[np.maximum(snap_idx[ix], 0)]) / D1, np.nan)
        continue
    for si in np.unique(snap_idx[ix]):
        if si < 0: continue
        sel = ix[snap_idx[ix] == si]; dd = dates[sel]; t = T_[T_.snap == snaps[si]]
        R['tr_snapshot_age_days'][sel] = (dd - snaps[si]) / D1
        for nm, mk_ in (('tr_active', pd.Series(True, index=t.index)), ('tr_active_p3', t.ph3), ('tr_active_p2', t.ph2), ('tr_active_p1', t.ph1)):
            tt = t[mk_]; starts = np.sort(tt.start_eom.values); ends = np.sort(tt.completion_date[tt.completion_date.notna() & (tt.completion_date_type == 'ACTUAL')].values)   # a trial stays 'active' until the snapshot marks its completion ACTUAL
            R[nm][sel] = np.searchsorted(starts, dd, side='right') - np.searchsorted(ends, dd, side='right')
        s_ = np.sort(t.start_eom.values)
        R['tr_started_365'][sel] = np.searchsorted(s_, dd, side='right') - np.searchsorted(s_, dd - 365 * D1, side='right')
        pc = np.sort(t.primary_completion_date[(t.primary_completion_date_type == 'ACTUAL')].dropna().values)   # only completions marked actual in that snapshot
        R['tr_pc_prev90'][sel] = np.searchsorted(pc, dd, side='right') - np.searchsorted(pc, dd - 90 * D1, side='right')
        rs = np.sort(t.results_first_posted_date.dropna().values)
        R['tr_results_prev180'][sel] = np.searchsorted(rs, dd, side='left') - np.searchsorted(rs, dd - 180 * D1, side='left')   # posting dated t counts from t+1
        if len(rs):
            j = np.searchsorted(rs, dd, side='left') - 1
            R['tr_dsl_results'][sel] = np.where(j >= 0, (dd - rs[np.maximum(j, 0)]) / D1, np.nan)
        e3 = np.zeros(len(sel))
        for r_ in t[t.ph3].itertuples():
            endv = r_.completion_date if (pd.notna(r_.completion_date) and r_.completion_date_type == 'ACTUAL') else pd.Timestamp('2200-01-01')
            e3 += np.where((dd >= np.datetime64(r_.start_eom)) & (dd < np.datetime64(endv)), r_.enr, 0)
        R['tr_enroll_active_p3'][sel] = e3
TRD_DESC = {'tr_active': 'trials started and not yet completed, per the registry snapshot available that day', 'tr_active_p3': 'active phase 3 trials (snapshot)',
            'tr_active_p2': 'active phase 2 trials (snapshot)', 'tr_active_p1': 'active phase 1 trials (snapshot)', 'tr_started_365': 'trials started in last 365 days (snapshot)',
            'tr_pc_prev90': 'trials whose primary completion was marked ACTUAL within the last 90 days (snapshot)', 'tr_results_prev180': 'trials with results posted in last 180 days (snapshot)',
            'tr_dsl_results': 'days since last results posting (snapshot)', 'tr_enroll_active_p3': 'enrollment of active phase 3 trials as shown in the snapshot',
            'tr_snapshot_age_days': 'age of the registry snapshot used, in days (monthly snapshots, so 1 to about 35)'}
for c_ in cols:
    v = R[c_]
    code_ = np.where(~np.isnan(v), C_OK, np.where(snap_idx < 0, C_NOTYET, C_INAPP))
    add(c_, v, code_, 'trials', 'days' if ('dsl' in c_ or 'age' in c_) else 'count', TRD_DESC[c_] + ' [AACT monthly snapshots, point in time]')

# ------------------------------------------------------------------ PDUFA and FDA actions
log('regulatory block')
pf = pd.read_csv(os.path.join(RAW, 'pdufa_full.csv'), usecols=['cik', 'filing_date', 'pdufa_dates'])
pf = pf[pf.pdufa_dates.notna()].copy()
pairs = []
for r in pf.itertuples():
    for s in str(r.pdufa_dates).split('|'):
        dt = pd.to_datetime(s.strip(), errors='coerce')
        if pd.notna(dt): pairs.append((int(r.cik), pd.Timestamp(r.filing_date) + pd.Timedelta(days=1), dt))
pr = pd.DataFrame(pairs, columns=['cik', 'known_from', 'pdufa'])
ahead = np.full(N, np.nan); n180 = np.zeros(N)
for cik, ix in panel.groupby('cik').indices.items():
    p = pr[pr.cik == cik]
    if p.empty: continue
    dd = dates[ix]
    best = np.full(len(ix), np.inf); c180 = np.zeros(len(ix))
    for r in p.itertuples():
        dlt = (np.datetime64(r.pdufa) - dd) / D1
        ok = (dd >= np.datetime64(r.known_from)) & (dlt >= 0)
        best = np.where(ok & (dlt < best), dlt, best)
        c180 += (ok & (dlt <= 180)).astype(float)
    ahead[ix] = np.where(np.isinf(best), np.nan, best); n180[ix] = c180
add('reg_pdufa_days_ahead', ahead, block='regulatory', unit='days', desc='days to nearest FDA action date already mentioned in an earlier 8-K (regex, may include non-PDUFA dates)')
add('reg_pdufa_n180', n180, block='regulatory', unit='count', desc='known FDA action dates within next 180 days')
fa = pd.read_csv(os.path.join(RAW, 'fda_actions.csv'))
fa['cik'] = fa.ticker.map(T2C); fa = fa[fa.cik.notna()].copy(); fa['cik'] = fa.cik.astype(int)
fa['filing_date'] = pd.to_datetime(fa.status_date, errors='coerce'); fa = fa[fa.filing_date.notna()]
add_count('reg_fda_actions_365', roll_n(daily(fa), 365), 'regulatory', 'count', 'FDA approval records (openFDA) dated in last 365 days')

# ------------------------------------------------------------------ LABELS (separate file)
log('labels')
L = {}
def fwd(n): return ADJ.shift(-n) / ADJ - 1
xb = ADJ['XBI']
for n in (1, 5, 20):
    L[f'y_ret_cc{n}'] = at_t(fwd(n))
L['y_ret_gap1'] = at_t(ADJO.shift(-1) / ADJ - 1)
L['y_xs_cc1'] = at_t(fwd(1).sub(xb.shift(-1) / xb - 1, axis=0))
L['y_abs_cc1'] = np.abs(L['y_ret_cc1'])
L['y_abs_cc5'] = np.abs(L['y_ret_cc5'])
def evflag(cnt, k):
    w = cnt.reindex(cal).fillna(0)
    nxt = sum((w.shift(-i) > 0).astype(float) for i in range(1, k + 1))
    nxt = (nxt > 0).astype(float)
    nxt.iloc[-k:] = np.nan
    return at_c(nxt)
k8c = daily(ef[ef.g == 'k8'])
L['y_8k_next1_any'] = evflag(k8c, 1); L['y_8k_next5_any'] = evflag(k8c, 5)
for gname in ('trial', 'reg', 'offer', 'deal'):
    L[f'y_8k_next1_{gname}'] = evflag(EVD[gname], 1)
    L[f'y_8k_next5_{gname}'] = evflag(EVD[gname], 5)

# ------------------------------------------------------------------ WRITE
log('checkpoint')
_sp = os.path.join(OUT, '_stage.pkl')
pd.to_pickle((F, C, DOC, L, panel[['cik', 'date']], tmap, CODE_LEGEND), _sp + '.tmp'); os.replace(_sp + '.tmp', _sp)
if os.environ.get('STOP_AFTER_CHECKPOINT'):
    sys.exit(0)
log('writing')
key = pd.DataFrame({'cik': panel.cik, 'date': panel.date.dt.strftime('%Y%m%d').astype(int)})
X = pd.concat([key, pd.DataFrame(F)], axis=1)
MC = pd.concat([key, pd.DataFrame(C)], axis=1)
Y = pd.concat([key, pd.DataFrame(L)], axis=1)
assert X.select_dtypes(exclude=[np.number]).shape[1] == 0, 'non numeric column in matrix'
assert not X.duplicated(['cik', 'date']).any()
X.to_csv(os.path.join(OUT, 'fds_features.csv'), index=False, float_format='%.6g')
MC.to_csv(os.path.join(OUT, 'fds_missing.csv'), index=False)
Y.to_csv(os.path.join(OUT, 'fds_labels.csv'), index=False, float_format='%.6g')
tmap[tmap.cik.isin(panel.cik.unique())].sort_values('cik').to_csv(os.path.join(OUT, 'fds_lookup_cik_ticker.csv'), index=False)
pd.DataFrame([(k, v) for k, v in CODE_LEGEND.items()], columns=['code', 'meaning']).to_csv(os.path.join(OUT, 'fds_lookup_codes.csv'), index=False)
pd.DataFrame([(k, *v) for k, v in DOC.items()], columns=['column', 'block', 'unit', 'description']).to_csv(os.path.join(OUT, 'fds_dictionary.csv'), index=False)
log('done', X.shape, Y.shape)
