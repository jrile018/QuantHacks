"""
35_aact_events.py - turn the monthly AACT snapshots into dated "the trial record changed" events.

Rule: a change only counts when a NEW VERSION of the record was posted between two snapshots
(last_update_posted_date moved forward). The event date is that posted date, which is when the public could first see it.
This also removes fake changes caused by the registry changing its text format.
Usable date = event date + 1 day (same lag as SEC filings).

Input : data/raw/aact_snapshots.csv (from script 34), data/raw/trials.csv (ticker for our companies)
Output: data/raw/aact_changes.csv  (one row per change; group A = our 139 biologics, B = big pharma for base rates)
Usage : python 35_aact_events.py
"""
import os, argparse
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
a = ap.parse_args()
RAW = os.path.join(a.data, 'raw')

d = pd.read_csv(os.path.join(RAW, 'aact_snapshots.csv'), dtype=str)
norm = lambda s: s.fillna('').str.upper().str.replace(r'[^A-Z0-9]+', '_', regex=True).str.strip('_')
d['status'] = norm(d.overall_status)
d['pc_type'] = norm(d.primary_completion_date_type).replace({'ANTICIPATED': 'ESTIMATED'})
d['en_type'] = norm(d.enrollment_type).replace({'ANTICIPATED': 'ESTIMATED'})
d['ph'] = d.phase.fillna('').str.findall(r'\d').str.join('/')            # '2', '1/2', '2/3', '3', '' (none)
for c, n in (('snapshot', 'snap'), ('primary_completion_date', 'pc'), ('completion_date', 'cd'), ('last_update_posted_date', 'lup'),
             ('results_first_posted_date', 'rfp'), ('study_first_posted_date', 'sfp'), ('start_date', 'st')):
    d[n] = pd.to_datetime(d[c], errors='coerce', format='%Y%m%d' if c == 'snapshot' else None)
for c in ('enrollment', 'number_of_facilities', 'n_primary_outcomes', 'has_why_stopped'):
    d[c] = pd.to_numeric(d[c], errors='coerce')
d = d.sort_values(['nct_id', 'snap']).reset_index(drop=True)
snaps = sorted(d.snap.unique())
print('snapshots:', len(snaps), str(snaps[0])[:10], 'to', str(snaps[-1])[:10], '| trials:', d.nct_id.nunique())

g = d.groupby('nct_id')
P = g.shift(1)                                   # previous snapshot of the same trial
has_prev = P.snap.notna()
consecutive = has_prev                            # gaps are allowed; the posted date still dates the change
newver = has_prev & d.lup.notna() & P.lup.notna() & (d.lup > P.lup) & (d.lup <= d.snap + pd.Timedelta(days=2))

base = pd.DataFrame({'nct_id': d.nct_id, 'event_date': d.lup, 'snap_prev': P.snap, 'snap_cur': d.snap, 'phase': d.ph,
                     'status_prev': P.status, 'status_cur': d.status, 'pc_prev': P.pc, 'pc_cur': d.pc,
                     'enroll_prev': P.enrollment, 'enroll_cur': d.enrollment, 'sites_cur': d.number_of_facilities})
ev = []
def add(mask, kind, days=None, pct=None):
    e = base[mask & newver].copy(); e['change_type'] = kind
    e['days_shifted'] = days[mask & newver] if days is not None else np.nan
    e['pct_change'] = pct[mask & newver] if pct is not None else np.nan
    ev.append(e)

dpc = (d.pc - P.pc).dt.days
both = d.pc.notna() & P.pc.notna()
add(both & (d.pc_type == 'ESTIMATED') & (dpc >= 28), 'pc_slip', dpc)
add(both & (d.pc_type == 'ESTIMATED') & (dpc <= -28), 'pc_pull_in', dpc)
add((P.pc_type == 'ESTIMATED') & (d.pc_type == 'ACTUAL'), 'pc_reached', dpc)
dcd = (d.cd - P.cd).dt.days
st_ch = (d.status != P.status) & (d.status != '') & (P.status != '')
enrolling = P.status.isin(['RECRUITING', 'ENROLLING_BY_INVITATION'])
add(st_ch & (d.status == 'ACTIVE_NOT_RECRUITING') & enrolling, 'to_active_not_recruiting')
add(st_ch & (d.status == 'RECRUITING') & (P.status == 'NOT_YET_RECRUITING'), 'to_recruiting')
add(st_ch & (d.status == 'COMPLETED'), 'to_completed')
add(st_ch & (d.status == 'TERMINATED'), 'to_terminated')
add(st_ch & (d.status == 'SUSPENDED'), 'to_suspended')
add(st_ch & (d.status == 'WITHDRAWN'), 'to_withdrawn')
add(st_ch & (P.status == 'SUSPENDED') & (d.status == 'RECRUITING'), 'resumed')
epct = d.enrollment / P.enrollment.where(P.enrollment > 0) - 1
est = (d.en_type == 'ESTIMATED') & (P.en_type == 'ESTIMATED')
add(est & (epct >= 0.10), 'enroll_target_up', pct=epct)
add(est & (epct <= -0.10), 'enroll_target_down', pct=epct)
add((P.en_type == 'ESTIMATED') & (d.en_type == 'ACTUAL') & epct.notna(), 'enroll_actual', pct=epct)
add(d.rfp.notna() & P.rfp.isna(), 'results_posted')
started = ~P.status.isin(['NOT_YET_RECRUITING', 'WITHDRAWN', ''])
add(started & d.primary_outcome_hash.notna() & P.primary_outcome_hash.notna() & (d.primary_outcome_hash != P.primary_outcome_hash), 'primary_outcome_edit')
spct = d.number_of_facilities / P.number_of_facilities.where(P.number_of_facilities > 0) - 1
add((spct.abs() >= 0.2) & ((d.number_of_facilities - P.number_of_facilities).abs() >= 2) & (spct > 0), 'sites_up', pct=spct)
add((spct.abs() >= 0.2) & ((d.number_of_facilities - P.number_of_facilities).abs() >= 2) & (spct < 0), 'sites_down', pct=spct)
E = pd.concat(ev, ignore_index=True)
# results posted has its own exact date
m = E.change_type == 'results_posted'
rfp = d.set_index(['nct_id', 'snap']).rfp
E.loc[m, 'event_date'] = pd.MultiIndex.from_arrays([E.nct_id[m], E.snap_cur[m]]).map(rfp).values
# new registrations (first time we see the trial, after the first snapshot)
first = d[~has_prev & (d.snap > snaps[0]) & d.sfp.notna()]
R = pd.DataFrame({'nct_id': first.nct_id, 'event_date': first.sfp, 'snap_prev': pd.NaT, 'snap_cur': first.snap, 'phase': first.ph,
                  'status_prev': '', 'status_cur': first.status, 'pc_prev': pd.NaT, 'pc_cur': first.pc, 'enroll_prev': np.nan,
                  'enroll_cur': first.enrollment, 'sites_cur': first.number_of_facilities, 'change_type': 'registered',
                  'days_shifted': np.nan, 'pct_change': np.nan})
E = pd.concat([E, R], ignore_index=True)
E['exact_date'] = (E.snap_prev.isna() | (E.event_date > E.snap_prev)).astype(int)
E['usable_date'] = E.event_date + pd.Timedelta(days=1)
E['n_changes_same_update'] = E.groupby(['nct_id', 'event_date']).change_type.transform('size')

A = pd.read_csv(os.path.join(RAW, 'trials.csv'), usecols=['ticker', 'nct_id']).drop_duplicates()
E = E.merge(A, on='nct_id', how='left')
E['group'] = np.where(E.ticker.notna(), 'A', 'B')
# how many times this trial slipped before (in our window)
E = E.sort_values(['nct_id', 'event_date'])
E['prior_slips'] = E.assign(s=(E.change_type == 'pc_slip').astype(int)).groupby('nct_id').s.cumsum() - (E.change_type == 'pc_slip').astype(int)
for c in ('event_date', 'usable_date', 'snap_prev', 'snap_cur', 'pc_prev', 'pc_cur'):
    E[c] = E[c].dt.strftime('%Y%m%d')
cols = ['nct_id', 'ticker', 'group', 'event_date', 'usable_date', 'change_type', 'days_shifted', 'pct_change', 'phase', 'status_prev', 'status_cur',
        'pc_prev', 'pc_cur', 'enroll_prev', 'enroll_cur', 'sites_cur', 'prior_slips', 'n_changes_same_update', 'exact_date', 'snap_prev', 'snap_cur']
E[cols].to_csv(os.path.join(RAW, 'aact_changes.csv'), index=False)

print('\nrows', len(E), '| new versions seen', int(newver.sum()))
print('\nevents by type and group:'); print(E.groupby(['change_type', 'group']).size().unstack(fill_value=0).to_string())
print('\nshare with an exact posted date:', round(E.exact_date.mean(), 3))
s = E[(E.change_type == 'pc_slip')]
print('slip size in days (all groups): median', s.days_shifted.median(), ' 25/75 pct', s.days_shifted.quantile(.25), s.days_shifted.quantile(.75))
print('\naudit, 12 random group A events:')
print(E[E.group == 'A'].sample(min(12, (E.group == 'A').sum()), random_state=1)[['ticker', 'nct_id', 'event_date', 'change_type', 'days_shifted', 'pct_change', 'phase', 'status_prev', 'status_cur', 'pc_prev', 'pc_cur']].to_string(index=False))
