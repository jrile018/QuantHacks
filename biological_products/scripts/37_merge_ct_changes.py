"""
37_merge_ct_changes.py - daily, time safe "trial record change" block for the shared dataset.

Two kinds of columns, all numbers, one row per (cik, date), same rows and order as fds_features.csv:
  A) change counts: how many of the company's trial records changed in the last N days (date slips, status moves, enrollment, results...).
     A change posted on day E is usable from E + 1.
  B) state: what the registry said about the company's trials on that day, from the latest monthly snapshot taken BEFORE that day
     (number of active trials, how many expect data in the next 90 / 180 days as known then).
Inputs : data/raw/aact_changes.csv (script 35), data/raw/aact_snapshots.csv (script 34), data/raw/trials.csv
Outputs: data/fds/fds_trialchg.csv, fds_trialchg_missing.csv, fds_trialchg_dictionary.csv
Usage  : python 37_merge_ct_changes.py
"""
import os, argparse
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
a = ap.parse_args()
RAW = os.path.join(a.data, 'raw'); FDS = os.path.join(a.data, 'fds')

X = pd.read_csv(os.path.join(FDS, 'fds_features.csv'), usecols=['cik', 'date'])
X['d'] = pd.to_datetime(X.date.astype(str))
lk = pd.read_csv(os.path.join(FDS, 'fds_lookup_cik_ticker.csv')); t2c = dict(zip(lk.ticker, lk.cik.astype(int)))
T = pd.read_csv(os.path.join(RAW, 'trials.csv'), usecols=['ticker', 'nct_id']).drop_duplicates()
T['cik'] = T.ticker.map(t2c); T = T[T.cik.notna()].copy(); T['cik'] = T.cik.astype(int)
has_trials = X.cik.isin(set(T.cik)).values

E = pd.read_csv(os.path.join(RAW, 'aact_changes.csv'), dtype={'usable_date': str, 'event_date': str})
E = E[E.group == 'A'].copy(); E['cik'] = E.ticker.map(t2c); E = E[E.cik.notna() & E.usable_date.notna()].copy()
E['cik'] = E.cik.astype(int); E['ud'] = pd.to_datetime(E.usable_date)
S = pd.read_csv(os.path.join(RAW, 'aact_snapshots.csv'), dtype=str)
S['snap'] = pd.to_datetime(S.snapshot, format='%Y%m%d')
first_snap = S.snap.min()
days = pd.date_range(first_snap, X.d.max(), freq='D')
ciks = sorted(X.cik.unique())

def daily(mask, val=None):
    """company x calendar day matrix of counts (or sums of val) of changes that became usable that day"""
    e = E[mask]
    v = e.assign(v=1.0 if val is None else e[val].astype(float))
    m = v.pivot_table(index='ud', columns='cik', values='v', aggfunc='sum')
    return m.reindex(index=days, columns=ciks).fillna(0.0)

kinds = {'slip': E.change_type == 'pc_slip', 'pull_in': E.change_type == 'pc_pull_in', 'pc_reached': E.change_type == 'pc_reached',
         'to_anr': E.change_type == 'to_active_not_recruiting', 'stopped': E.change_type.isin(['to_terminated', 'to_suspended', 'to_withdrawn']),
         'completed': E.change_type == 'to_completed', 'results': E.change_type == 'results_posted',
         'enroll_up': E.change_type == 'enroll_target_up', 'enroll_down': E.change_type == 'enroll_target_down',
         'outcome_edit': E.change_type == 'primary_outcome_edit', 'registered': E.change_type == 'registered',
         'any': pd.Series(True, index=E.index)}
spec = [('ch_n_slip_30', 'slip', 30), ('ch_n_slip_90', 'slip', 90), ('ch_n_slip_365', 'slip', 365), ('ch_n_pull_in_180', 'pull_in', 180),
        ('ch_n_pc_reached_180', 'pc_reached', 180), ('ch_n_to_anr_180', 'to_anr', 180), ('ch_n_stopped_180', 'stopped', 180),
        ('ch_n_completed_180', 'completed', 180), ('ch_n_results_180', 'results', 180), ('ch_n_enroll_up_180', 'enroll_up', 180),
        ('ch_n_enroll_down_180', 'enroll_down', 180), ('ch_n_outcome_edit_365', 'outcome_edit', 365), ('ch_n_registered_180', 'registered', 180),
        ('ch_n_any_30', 'any', 30), ('ch_n_any_90', 'any', 90)]
mi = pd.MultiIndex.from_arrays([X.d, X.cik])
out = X[['cik', 'date']].copy(); win = {}
D = {k: daily(m) for k, m in kinds.items()}
for col, k, n in spec:
    out[col] = D[k].rolling(n, min_periods=1).sum().stack().reindex(mi).values; win[col] = n
slipdays = daily(kinds['slip'], 'days_shifted')
out['ch_slip_days_sum_180'] = slipdays.rolling(180, min_periods=1).sum().stack().reindex(mi).values; win['ch_slip_days_sum_180'] = 180
def dsl(m):
    idx = pd.Series(np.arange(len(days)), index=days)
    last = m.gt(0).mul(idx, axis=0).where(m.gt(0)).ffill()
    return (-last).add(idx, axis=0)
out['ch_dsl_any'] = dsl(D['any']).stack(dropna=False).reindex(mi).values
out['ch_dsl_slip'] = dsl(D['slip']).stack(dropna=False).reindex(mi).values

# ---------- state from the latest snapshot before the row date ----------
norm = lambda s: s.fillna('').str.upper().str.replace(r'[^A-Z0-9]+', '_', regex=True).str.strip('_')
S = S.merge(T[['nct_id', 'cik']], on='nct_id')
S['status'] = norm(S.overall_status); S['pct'] = norm(S.primary_completion_date_type).replace({'ANTICIPATED': 'ESTIMATED'})
S['pc'] = pd.to_datetime(S.primary_completion_date, errors='coerce'); S['rfp'] = pd.to_datetime(S.results_first_posted_date, errors='coerce')
S['ph3'] = S.phase.fillna('').str.contains('3'); S['active'] = S.status.isin(['RECRUITING', 'ACTIVE_NOT_RECRUITING', 'ENROLLING_BY_INVITATION', 'NOT_YET_RECRUITING'])
snaps = np.sort(S.snap.unique())
X['si'] = np.searchsorted(snaps, X.d.values, side='left') - 1          # latest snapshot strictly before the row date
st = {c: np.full(len(X), np.nan) for c in ('ch_n_active_known', 'ch_n_ph3_active', 'ch_n_pc_next90', 'ch_n_pc_next180', 'ch_days_to_next_pc', 'ch_n_results_overdue', 'ch_snapshot_age_days')}
grp = {k: g for k, g in S.groupby(['snap', 'cik'])}
for (si, cik), rows in X[X.si >= 0].groupby(['si', 'cik']):
    g = grp.get((pd.Timestamp(snaps[si]), cik))
    ix = rows.index.values; dd = rows.d.values
    st['ch_snapshot_age_days'][ix] = (dd - snaps[si]).astype('timedelta64[D]').astype(float)
    if g is None:
        for c in ('ch_n_active_known', 'ch_n_ph3_active', 'ch_n_pc_next90', 'ch_n_pc_next180', 'ch_n_results_overdue'): st[c][ix] = 0
        continue
    act = g[g.active]
    st['ch_n_active_known'][ix] = len(act); st['ch_n_ph3_active'][ix] = int(act.ph3.sum())
    pcs = np.sort(act[(act.pct == 'ESTIMATED') & act.pc.notna()].pc.values)
    lo = np.searchsorted(pcs, dd, side='right')
    st['ch_n_pc_next90'][ix] = np.searchsorted(pcs, dd + np.timedelta64(90, 'D'), side='right') - lo
    st['ch_n_pc_next180'][ix] = np.searchsorted(pcs, dd + np.timedelta64(180, 'D'), side='right') - lo
    if len(pcs): st['ch_days_to_next_pc'][ix] = np.where(lo < len(pcs), (pcs[np.minimum(lo, len(pcs) - 1)] - dd).astype('timedelta64[D]').astype(float), np.nan)
    od = g[(g.pct == 'ACTUAL') & g.pc.notna() & g.rfp.isna()].pc.values
    st['ch_n_results_overdue'][ix] = (od[None, :] < (dd[:, None] - np.timedelta64(365, 'D'))).sum(axis=1) if len(od) else 0
for c, v in st.items(): out[c] = v

# ---------- missing codes ----------
C = out[['cik', 'date']].copy()
age = (X.d - first_snap).dt.days.values
for col in out.columns[2:]:
    v = out[col].values
    code = np.zeros(len(out), dtype='int8')
    if col in win:
        short = age < win[col]                                   # window reaches back before our first snapshot
        out.loc[short, col] = np.nan; code[short] = 4
    code[np.isnan(out[col].values) & (code == 0)] = 6             # no such change yet / no next date
    out.loc[~has_trials, col] = np.nan; code[~has_trials] = 6     # company has no registered trials in our list
    code[(X.si.values < 0) & (code == 0) & np.isnan(out[col].values)] = 1
    C[col] = code

# ---------- time safety recount ----------
bad = 0
chk = out[has_trials & (age >= 90)].sample(300, random_state=0)
for r in chk.itertuples():
    dd = pd.Timestamp(str(r.date))
    e = E[(E.cik == r.cik) & (E.change_type == 'pc_slip') & (E.ud <= dd) & (E.ud > dd - pd.Timedelta(days=90))]
    if abs(len(e) - r.ch_n_slip_90) > 1e-9: bad += 1
print('time safety recount mismatches (300 random rows):', bad); assert bad == 0

desc = {'ch_n_slip_30': 'trial records whose expected primary completion date was pushed back 30+ days, posted in the last 30 days',
        'ch_n_slip_90': 'same, last 90 days', 'ch_n_slip_365': 'same, last 365 days', 'ch_n_pull_in_180': 'expected data date moved earlier by 30+ days, last 180 days',
        'ch_n_pc_reached_180': 'trials that reported reaching primary completion (estimated became actual), last 180 days',
        'ch_n_to_anr_180': 'trials that moved from recruiting to active not recruiting (enrollment finished), last 180 days',
        'ch_n_stopped_180': 'trials moved to terminated, suspended or withdrawn, last 180 days', 'ch_n_completed_180': 'trials moved to completed, last 180 days',
        'ch_n_results_180': 'trials with results first posted, last 180 days', 'ch_n_enroll_up_180': 'enrollment target raised 10%+, last 180 days',
        'ch_n_enroll_down_180': 'enrollment target cut 10%+, last 180 days', 'ch_n_outcome_edit_365': 'primary outcome text or count edited after the trial started, last 365 days',
        'ch_n_registered_180': 'new trials first posted, last 180 days', 'ch_n_any_30': 'any detected record change, last 30 days', 'ch_n_any_90': 'any detected record change, last 90 days',
        'ch_slip_days_sum_180': 'total days of delay added by slips, last 180 days', 'ch_dsl_any': 'days since the last detected record change',
        'ch_dsl_slip': 'days since the last slip', 'ch_n_active_known': 'active trials per the latest monthly registry snapshot before this day',
        'ch_n_ph3_active': 'of those, phase 3', 'ch_n_pc_next90': 'active trials whose expected primary completion date, as known then, is in the next 90 days',
        'ch_n_pc_next180': 'same, next 180 days', 'ch_days_to_next_pc': 'days to the nearest expected primary completion date as known then',
        'ch_n_results_overdue': 'trials past primary completion by 12+ months with no results posted, as known then',
        'ch_snapshot_age_days': 'age in days of the registry snapshot used for the state columns'}
unit = lambda c: 'days' if ('dsl' in c or 'days' in c) else 'count'
pd.DataFrame([(c, 'trialchg', unit(c), desc[c]) for c in out.columns[2:]], columns=['column', 'block', 'unit', 'description']).to_csv(os.path.join(FDS, 'fds_trialchg_dictionary.csv'), index=False)
out.to_csv(os.path.join(FDS, 'fds_trialchg.csv'), index=False, float_format='%.6g')
C.to_csv(os.path.join(FDS, 'fds_trialchg_missing.csv'), index=False)
print('rows', len(out), '| companies with trials', int(X[has_trials].cik.nunique()), 'of', X.cik.nunique())
print(out.describe().T[['count', 'mean', '50%', 'max']].round(3).to_string())
