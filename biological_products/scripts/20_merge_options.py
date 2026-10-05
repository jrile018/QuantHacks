"""
20_merge_options.py - turn the event level options table (opt_events.csv) into time safe columns for the daily dataset.

Options were only sampled at 8-K events, so for each company and day we only know what earlier events showed:
how many earlier events had options listed / quoted, how wide the spreads were, how big the straddle was.
An event is usable from the day AFTER its filing date. Output joins to fds_features.csv on (cik, date).

Usage:  python 20_merge_options.py [--data C:\\path\\to\\data]
Writes (in <data>/fds): fds_options.csv, fds_options_missing.csv, fds_options_dictionary.csv
"""
import os, argparse
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
a = ap.parse_args()
fds = os.path.join(a.data, 'fds')

X = pd.read_csv(os.path.join(fds, 'fds_features.csv'), usecols=['cik', 'date'])
X['d'] = pd.to_datetime(X.date.astype(str))
o = pd.read_csv(os.path.join(fds, 'opt_events.csv'))
o['usable'] = pd.to_datetime(o.event_date.astype(str)) + pd.Timedelta(days=1)
o['spread'] = o[['near_call_spread_pct', 'near_put_spread_pct']].mean(axis=1)
q = o.status == 0
o['sp_q'] = o.spread.where(q); o['st_q'] = o.near_straddle_pct.where(q); o['mv_q'] = o.implied_event_move.where(q)
o['qdate'] = o.usable.where(q)
o = o.sort_values(['cik', 'usable']).reset_index(drop=True)
g = o.groupby('cik')
o['n_ev'] = g.cumcount() + 1
o['n_q'] = (o.status == 0).astype(int).groupby(o.cik).cumsum()
o['n_unl'] = (o.status == 1).astype(int).groupby(o.cik).cumsum()
o['med_sp'] = g.sp_q.transform(lambda s: s.expanding().median())
o['last_sp'] = g.sp_q.ffill(); o['last_st'] = g.st_q.ffill(); o['last_mv'] = g.mv_q.ffill(); o['last_qd'] = g.qdate.ffill()
cols = ['cik', 'usable', 'n_ev', 'n_q', 'n_unl', 'med_sp', 'last_sp', 'last_st', 'last_mv', 'last_qd']
X = X.sort_values('d')
m = pd.merge_asof(X, o[cols].sort_values('usable'), left_on='d', right_on='usable', by='cik', direction='backward')
m = m.sort_values(['cik', 'd']).reset_index(drop=True)

has_prior = m.n_ev.notna()
out = pd.DataFrame({'cik': m.cik, 'date': m.date})
out['opt_prior_events'] = m.n_ev.fillna(0)
out['opt_prior_quoted'] = m.n_q.fillna(0)
out['opt_prior_unlisted'] = m.n_unl.fillna(0)
out['opt_ever_listed'] = np.where(has_prior, (m.n_ev - m.n_unl > 0).astype(float), np.nan)
out['opt_last_spread_pct'] = m.last_sp
out['opt_med_spread_pct'] = m.med_sp
out['opt_last_straddle_pct'] = m.last_st
out['opt_last_implied_move'] = m.last_mv
out['opt_days_since_quote'] = (m.d - m.last_qd).dt.days

C = pd.DataFrame({'cik': m.cik, 'date': m.date})
for c in out.columns[2:]:
    if c in ('opt_prior_events', 'opt_prior_quoted', 'opt_prior_unlisted'):
        C[c] = 0
    else:
        # 5 = not collected (no earlier event sampled for this company), 6 = sampled but no usable quote
        C[c] = np.where(out[c].notna(), 0, np.where(has_prior, 6, 5))
C = C.astype({c: 'int8' for c in C.columns[2:]})

# time safety check: recount from the raw events for random rows
raw = pd.read_csv(os.path.join(fds, 'opt_events.csv'))
raw['ed'] = pd.to_datetime(raw.event_date.astype(str))
bad = 0
for r in out.sample(300, random_state=0).itertuples():
    dd = pd.Timestamp(str(r.date))
    sub = raw[(raw.cik == r.cik) & (raw.ed < dd)]
    if len(sub) != r.opt_prior_events or (sub.status == 0).sum() != r.opt_prior_quoted: bad += 1
print('time safety recount mismatches (of 300 random rows):', bad)
assert bad == 0

D = pd.DataFrame([
    ('opt_prior_events', 'options', 'count', 'earlier 8-K events (clinical, FDA, financing, deal, earnings) for which options were looked up; usable from the day after the filing date'),
    ('opt_prior_quoted', 'options', 'count', 'of those, events with a usable bid/ask on at least one at-the-money leg'),
    ('opt_prior_unlisted', 'options', 'count', 'of those, events where the company had no listed options in the window'),
    ('opt_ever_listed', 'options', 'flag', '1 if any earlier sampled event had listed options, 0 if none did; NaN = never sampled'),
    ('opt_last_spread_pct', 'options', 'fraction', 'bid-ask spread / mid of the at-the-money call and put at the last quoted earlier event (average of the two)'),
    ('opt_med_spread_pct', 'options', 'fraction', 'median of those spreads over all earlier quoted events'),
    ('opt_last_straddle_pct', 'options', 'fraction', 'near-month at-the-money straddle price / stock price at the last quoted earlier event'),
    ('opt_last_implied_move', 'options', 'fraction', 'implied event move estimate at the last quoted earlier event (crude)'),
    ('opt_days_since_quote', 'options', 'days', 'days since that last quoted event became usable'),
], columns=['column', 'block', 'unit', 'description'])

out.to_csv(os.path.join(fds, 'fds_options.csv'), index=False, float_format='%.6g')
C.to_csv(os.path.join(fds, 'fds_options_missing.csv'), index=False)
D.to_csv(os.path.join(fds, 'fds_options_dictionary.csv'), index=False)
print('rows', len(out), 'share of rows with at least one earlier sampled event:', round(has_prior.mean(), 3),
      '| with a quoted earlier event:', round((out.opt_prior_quoted > 0).mean(), 3))
print(out.describe().T[['count', 'mean', '50%', 'max']].round(3).to_string())
