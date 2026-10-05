"""
26_merge_finra.py - turn the raw FINRA short files into time safe columns for the daily dataset.

Daily short sale volume: published after the close, so the value for market day d only uses days BEFORE d (lag 1 market day).
Short interest: settlement date S, published about 7 business days later. We treat it as usable 14 calendar days after S (safe side).
Joins to fds_features.csv on (cik, date). Writes fds_short.csv, fds_short_missing.csv, fds_short_dictionary.csv in <data>/fds.
Usage: python 26_merge_finra.py [--data C:\\path\\to\\data]
"""
import os, argparse
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
a = ap.parse_args()
FDS = os.path.join(a.data, 'fds'); RAW = os.path.join(a.data, 'raw')
LAG_SI = 14

X = pd.read_csv(os.path.join(FDS, 'fds_features.csv'), usecols=['cik', 'date'])
X['d'] = pd.to_datetime(X.date.astype(str))
lk = pd.read_csv(os.path.join(FDS, 'fds_lookup_cik_ticker.csv')); c2t = dict(zip(lk.cik.astype(int), lk.ticker.astype(str).str.upper()))
X['ticker'] = X.cik.map(c2t)

# market calendar (SPY days)
P = pd.read_csv(os.path.join(RAW, 'prices.csv'), usecols=['ticker', 'date'])
cal = pd.DatetimeIndex(sorted(pd.to_datetime(P[P.ticker == 'SPY'].date).unique()))

# ---------- daily short volume ----------
sv = pd.read_csv(os.path.join(RAW, 'finra_shortvol.csv'))
sv['d'] = pd.to_datetime(sv.date.astype(str))
SV = sv.pivot(index='d', columns='ticker', values='short_vol').reindex(cal)
TV = sv.pivot(index='d', columns='ticker', values='total_vol').reindex(cal)
EX = sv.pivot(index='d', columns='ticker', values='short_exempt_vol').reindex(cal)
has = TV.notna()
def roll(df, n): return df.fillna(0).rolling(n, min_periods=1).sum()
r1 = (SV / TV.where(TV > 0))
r5 = roll(SV, 5) / roll(TV, 5).where(roll(TV, 5) > 0)
r20 = roll(SV, 20) / roll(TV, 20).where(roll(TV, 20) > 0)
ex20 = roll(EX, 20) / roll(TV, 20).where(roll(TV, 20) > 0)
mu60, sd60 = r1.rolling(60, min_periods=30).mean(), r1.rolling(60, min_periods=30).std()
z5 = (r5 - mu60) / sd60.where(sd60 > 0)
days_print_20 = has.astype(float).rolling(20, min_periods=1).sum()
def lag1(df): return df.shift(1)          # value known at the close of d uses days up to d-1
mats = {'sv_ratio_1d': lag1(r1), 'sv_ratio_5d': lag1(r5), 'sv_ratio_20d': lag1(r20), 'sv_ratio_z60': lag1(z5),
        'sv_exempt_share_20d': lag1(ex20), 'sv_days_with_print_20d': lag1(days_print_20)}
out = X[['cik', 'date']].copy()
mi = pd.MultiIndex.from_arrays([X.d, X.ticker])
for k, m in mats.items():
    s = m.stack(dropna=False)
    out[k] = s.reindex(mi).values
first_sv = sv.groupby('ticker').d.min()
X['sv_first'] = X.ticker.map(first_sv)

# ---------- short interest ----------
si = pd.read_csv(os.path.join(RAW, 'finra_shortint.csv'))
si['settle_d'] = pd.to_datetime(si.settle.astype(str)); si['usable'] = si.settle_d + pd.Timedelta(days=LAG_SI)
si['si_chg'] = si.short_int / si.prev_short_int.where(si.prev_short_int > 0) - 1
si = si.sort_values('usable')
m = pd.merge_asof(X.sort_values('d')[['cik', 'date', 'd', 'ticker']], si[['ticker', 'usable', 'settle_d', 'short_int', 'days_to_cover', 'si_chg', 'avg_daily_vol']],
                  left_on='d', right_on='usable', by='ticker', direction='backward')
m = m.set_index(['cik', 'date']).reindex(pd.MultiIndex.from_frame(out[['cik', 'date']]))
out['si_days_to_cover'] = m.days_to_cover.values
out['si_chg_pct'] = m.si_chg.clip(-1, 5).values
out['si_shares_m'] = (m.short_int / 1e6).values
out['si_age_days'] = (X.d.reset_index(drop=True) - pd.Series(m.settle_d.values)).dt.days.values.astype(float)

# ---------- missing codes ----------
C = out[['cik', 'date']].copy()
has_ticker = X.ticker.notna().values
for col in out.columns[2:]:
    ok = out[col].notna().values
    if col.startswith('sv_'):
        code = np.where(ok, 0, np.where(~has_ticker, 5, np.where(X.d.values < X.sv_first.values, 1, 6)))
    else:
        age_ok = out['si_age_days'].fillna(0).values <= 200
        code = np.where(ok & age_ok, 0, np.where(ok, 3, np.where(~has_ticker, 5, 1)))
    C[col] = code
C = C.astype({c: 'int8' for c in C.columns[2:]})

# ---------- time safety recount ----------
bad = 0
rs = out.sample(300, random_state=0)
for r in rs.itertuples():
    tk = c2t.get(int(r.cik)); dd = pd.Timestamp(str(r.date))
    i = cal.searchsorted(dd)                       # index of dd in the calendar
    prev5 = cal[max(0, i - 5):i]                   # the 5 market days BEFORE dd
    s = sv[(sv.ticker == tk) & sv.d.isin(prev5)]
    exp = s.short_vol.sum() / s.total_vol.sum() if s.total_vol.sum() > 0 else np.nan
    got = r.sv_ratio_5d
    if not ((np.isnan(exp) and np.isnan(got)) or (not np.isnan(exp) and not np.isnan(got) and abs(exp - got) < 1e-9)): bad += 1
    q = si[(si.ticker == tk) & (si.usable <= dd)].sort_values('settle_d')
    expd = q.days_to_cover.iloc[-1] if len(q) else np.nan
    gotd = r.si_days_to_cover
    if not ((np.isnan(expd) and np.isnan(gotd)) or (not np.isnan(expd) and not np.isnan(gotd) and abs(expd - gotd) < 1e-9)): bad += 1
print('time safety recount mismatches (300 random rows, 2 checks each):', bad)
assert bad == 0

D = pd.DataFrame([
    ('sv_ratio_1d', 'short', 'fraction', 'short sale volume / total volume on the previous market day (FINRA, all venues)'),
    ('sv_ratio_5d', 'short', 'fraction', 'same ratio summed over the previous 5 market days'),
    ('sv_ratio_20d', 'short', 'fraction', 'same ratio summed over the previous 20 market days'),
    ('sv_ratio_z60', 'short', 'z score', '5 day ratio compared with the 60 day average of the daily ratio, in standard deviations'),
    ('sv_exempt_share_20d', 'short', 'fraction', 'short exempt volume / total volume over the previous 20 market days'),
    ('sv_days_with_print_20d', 'short', 'days', 'days in the previous 20 market days with a FINRA short volume print for this ticker'),
    ('si_days_to_cover', 'short', 'days', 'FINRA reported days to cover (short interest / average daily volume), latest settlement usable 14 days after it'),
    ('si_chg_pct', 'short', 'fraction', 'change of short interest from the previous settlement date to the latest one (clipped to -1 .. 5)'),
    ('si_shares_m', 'short', 'shares_m', 'shares sold short at the latest usable settlement date, in millions, as reported then (not split adjusted)'),
    ('si_age_days', 'short', 'days', 'days between the latest usable settlement date and this row date'),
], columns=['column', 'block', 'unit', 'description'])
out.to_csv(os.path.join(FDS, 'fds_short.csv'), index=False, float_format='%.6g')
C.to_csv(os.path.join(FDS, 'fds_short_missing.csv'), index=False)
D.to_csv(os.path.join(FDS, 'fds_short_dictionary.csv'), index=False)
print('rows', len(out), '| share of rows with ticker', round(has_ticker.mean(), 3))
print(out.describe().T[['count', 'mean', '50%', 'max']].round(3).to_string())
