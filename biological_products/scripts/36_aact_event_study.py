"""
36_aact_event_study.py - does the stock move AFTER a quiet change in a trial record?

Events: data/raw/aact_changes.csv (script 35), our 139 biologics only (group A).
Trade clock: the change was posted on day E. We act at the OPEN of the first market day after E and measure to the close
5, 20 and 60 market days later. Abnormal return = stock minus XBI over the same window (negative = the stock fell).

HONEST TESTING: events are split by time.
  design  = events up to --design_end (default 2025-06-30). We may look at these as much as we like to choose a rule.
  holdout = later events. By default this script prints only how many there are, never their returns.
  To test ONE chosen rule on the holdout, run for example:
     python 36_aact_event_study.py --rule "types=to_terminated,to_suspended,to_withdrawn;hold=20;no8k=1"
  Every holdout run is appended to data/fds/ct_holdout_log.csv so we cannot quietly try many rules.
Usage: python 36_aact_event_study.py
"""
import os, argparse, datetime as dt
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--min_adv', type=float, default=1.0)
ap.add_argument('--min_px', type=float, default=1.0)
ap.add_argument('--design_end', default='2025-06-30')
ap.add_argument('--rule', default='', help='types=a,b;hold=5|20|60;no8k=0|1;extra=pandas query on the event table (optional)')
a = ap.parse_args()
RAW = os.path.join(a.data, 'raw'); FDS = os.path.join(a.data, 'fds')
rng = np.random.default_rng(0)
HOLDS = {5: 'ab5', 20: 'ab20', 60: 'ab60'}

E = pd.read_csv(os.path.join(RAW, 'aact_changes.csv'), dtype={'event_date': str, 'usable_date': str, 'pc_cur': str, 'pc_prev': str, 'phase': str})
E = E[E.group == 'A'].copy()
E['ed'] = pd.to_datetime(E.event_date, errors='coerce'); E['ud'] = pd.to_datetime(E.usable_date, errors='coerce')
E['pc_cur'] = E.pc_cur.fillna('').astype(str); E['phase'] = E.phase.fillna('').astype(str)
E = E[E.ed.notna()].copy()
lk = pd.read_csv(os.path.join(FDS, 'fds_lookup_cik_ticker.csv')); t2c = dict(zip(lk.ticker, lk.cik.astype(int)))
E['cik'] = E.ticker.map(t2c); E = E[E.cik.notna()].copy(); E['cik'] = E.cik.astype(int)

# one event per company, day and change type (companies often update several records at once)
def big(s): return s.loc[s.abs().idxmax()] if s.notna().any() else np.nan
agg = E.groupby(['ticker', 'cik', 'ed', 'ud', 'change_type']).agg(
    n_trials=('nct_id', 'nunique'), days_shifted=('days_shifted', big), pct_change=('pct_change', 'mean'),
    late_phase=('phase', lambda s: int(s.str.contains('3').any())), mid_phase=('phase', lambda s: int(s.str.contains('2').any())),
    prior_slips=('prior_slips', 'max'), pc_cur=('pc_cur', 'max'), exact=('exact_date', 'min')).reset_index()
piv = E.assign(v=1).pivot_table(index=['ticker', 'ed'], columns='change_type', values='v', aggfunc='max', fill_value=0)
agg = agg.merge(piv.add_prefix('same_').reset_index(), on=['ticker', 'ed'], how='left')
agg['n_records_same_day'] = agg.groupby(['ticker', 'ed']).n_trials.transform('max')

P = pd.read_csv(os.path.join(RAW, 'prices.csv'), usecols=['ticker', 'date', 'open', 'close']); P['date'] = pd.to_datetime(P.date)
O = P.pivot(index='date', columns='ticker', values='open'); C = P.pivot(index='date', columns='ticker', values='close')
cal = O.index[O['XBI'].notna()]; O = O.loc[cal]; C = C.loc[cal]
n_cal = len(cal)

def rets(tk, i):
    """i = index of the entry day. abnormal return for 5, 20, 60 market days, and for the 5 days before entry"""
    out = [np.nan] * 4
    if tk not in O.columns or i < 6 or i >= n_cal: return out
    o, xo = O[tk].iat[i], O['XBI'].iat[i]
    if not (o > 0): return out
    for k, h in enumerate((4, 19, 59)):
        if i + h < n_cal:
            c, xc = C[tk].iat[i + h], C['XBI'].iat[i + h]
            if c > 0: out[k] = (c / o - 1) - (xc / xo - 1)
    c0, c1 = C[tk].iat[i - 6], C[tk].iat[i - 1]; x0, x1 = C['XBI'].iat[i - 6], C['XBI'].iat[i - 1]
    if c0 > 0 and c1 > 0: out[3] = (c1 / c0 - 1) - (x1 / x0 - 1)
    return out

agg = agg[agg.ud >= pd.Timestamp('2024-01-02')].copy()
agg['i'] = np.searchsorted(cal.values, agg.ud.values)            # first market day on or after the usable date
agg = agg[agg.i < n_cal - 5].copy()
R = np.array([rets(t, i) for t, i in zip(agg.ticker, agg.i)])
agg['ab5'], agg['ab20'], agg['ab60'], agg['pre5'] = R[:, 0], R[:, 1], R[:, 2], R[:, 3]
lo = int(np.searchsorted(cal.values, np.datetime64('2024-01-02')))
ri = rng.integers(lo, n_cal - 61, size=len(agg))                 # control: a random entry day for the same company
Rc = np.array([rets(t, i) for t, i in zip(agg.ticker, ri)])
agg['c5'], agg['c20'], agg['c60'] = Rc[:, 0], Rc[:, 1], Rc[:, 2]

# company situation on the event day (last feature row on or before the event date: no look ahead)
F = pd.read_csv(os.path.join(FDS, 'fds_features.csv'), usecols=['cik', 'date', 'px_adv20_usd_m', 'px_close_real', 'fin_runway_q', 'fin_mktcap_m', 'tr_active'])
F['fd'] = pd.to_datetime(F.date.astype(str)); F = F.sort_values('fd').drop(columns='date')
agg = pd.merge_asof(agg.sort_values('ed'), F, left_on='ed', right_on='fd', by='cik', direction='backward', tolerance=pd.Timedelta(days=10))
agg['liquid'] = (agg.px_adv20_usd_m >= a.min_adv) & (agg.px_close_real >= a.min_px)
K = pd.read_csv(os.path.join(RAW, 'events_8k.csv'), usecols=['cik', 'filing_date']); K['kd'] = pd.to_datetime(K.filing_date)
kset = {int(c): np.sort(g.kd.values.astype('int64')) for c, g in K.groupby('cik')}
def near8k(c, e, days=2):
    v = kset.get(c)
    if v is None: return 0
    lo_, hi_ = (e - pd.Timedelta(days=days)).value, (e + pd.Timedelta(days=days)).value
    j = np.searchsorted(v, lo_); return int(j < len(v) and v[j] <= hi_)
agg['k8_near'] = [near8k(c, e) for c, e in zip(agg.cik, agg.ed)]
def next8k(c, e):
    v = kset.get(c)
    if v is None: return np.nan
    j = np.searchsorted(v, e.value, side='right')
    return (v[j] - e.value) / 86400e9 if j < len(v) else np.nan
agg['days_to_next_8k'] = [next8k(c, e) for c, e in zip(agg.cik, agg.ed)]
agg['pc_new'] = pd.to_datetime(agg.pc_cur, errors='coerce')
cash_end = agg.ed + pd.to_timedelta((agg.fin_runway_q * 91).clip(upper=4000).fillna(0), unit='D')
agg['past_cash'] = np.where(agg.fin_runway_q.notna() & agg.pc_new.notna(), (agg.pc_new > cash_end).astype(float), np.nan)
agg['m'] = agg.ed.dt.to_period('M').astype(str)
agg['cutover'] = agg.ed.between('2024-06-01', '2024-09-15').astype(int)      # registry changed its systems here; treat as suspect
agg['set'] = np.where(agg.ed <= pd.Timestamp(a.design_end), 'design', 'holdout')
agg['stopped'] = agg.change_type.isin(['to_terminated', 'to_suspended', 'to_withdrawn']).astype(int)
agg.to_csv(os.path.join(FDS, 'ct_event_study.csv'), index=False)

def stat(h, col):
    v = h[col].dropna()
    if len(v) < 8: return f'n {len(v):4d}  too few'
    b = h.dropna(subset=[col]).groupby(['ticker', 'm'])[col].mean()
    t = b.mean() / (b.std() / np.sqrt(len(b))) if len(b) > 2 and b.std() > 0 else np.nan
    return f'n {len(v):4d} cos {h.dropna(subset=[col]).ticker.nunique():3d}  mean {v.mean()*100:+6.2f}%  median {v.median()*100:+6.2f}%  pos {(v>0).mean():.2f}  t {t:+5.2f}'

L = agg[agg.liquid].copy()
Dn = L[L.set == 'design']; Hn = L[L.set == 'holdout']
print(f'group A company-day events: {len(agg)} | liquid: {len(L)} | companies: {L.ticker.nunique()} | {L.ed.min().date()} to {L.ed.max().date()}')
print(f'design (to {a.design_end}): {len(Dn)} events | holdout: {len(Hn)} events (returns hidden)')
print(f'share of events with an 8-K within 2 days: {L.k8_near.mean():.2f} | median days until the next 8-K: {L.days_to_next_8k.median():.0f}')
print(f'events on days when the company updated 5+ records at once: {(L.n_records_same_day >= 5).mean():.2f}')
print('\nevent counts (liquid) by type:   design / holdout')
ct = L.groupby(['change_type', 'set']).size().unstack(fill_value=0)
print(ct.to_string())

if a.rule:
    kv = dict(x.split('=', 1) for x in a.rule.split(';') if '=' in x)
    types = kv.get('types', '').split(','); hold = int(kv.get('hold', 20)); no8k = int(kv.get('no8k', 0)); extra = kv.get('extra', '')
    col = HOLDS[hold]
    def pick(df):
        q = df[df.change_type.isin(types)]
        if no8k: q = q[q.k8_near == 0]
        if extra: q = q.query(extra)
        return q.sort_values('ed').drop_duplicates(['ticker', 'ed'])
    print(f'\n=== RULE: {a.rule} ===  (abnormal return of the stock; a short gains when this is negative)')
    print('design :', stat(pick(Dn), col)); print('HOLDOUT:', stat(pick(Hn), col))
    q = pick(Hn)[col].dropna()
    if len(q) >= 8:
        bs = np.array([rng.choice(q.values, len(q)).mean() for _ in range(2000)])
        print(f'holdout mean {q.mean()*100:+.2f}%  90% bootstrap interval {np.percentile(bs,5)*100:+.2f}% to {np.percentile(bs,95)*100:+.2f}%')
    logp = os.path.join(FDS, 'ct_holdout_log.csv'); new = not os.path.exists(logp)
    with open(logp, 'a') as fh:
        if new: fh.write('run_at,rule,n_holdout,mean_holdout\n')
        fh.write(f'{dt.datetime.now().isoformat(timespec="seconds")},"{a.rule}",{len(q)},{q.mean() if len(q) else float("nan")}\n')
    print('holdout runs so far:', sum(1 for _ in open(logp)) - 1)
    raise SystemExit

print('\n================ DESIGN SET ONLY ================')
print('control (random days, same companies):')
for h, c in ((5, 'c5'), (20, 'c20'), (60, 'c60')): print(f'   {h:2d}d', stat(Dn, c))
def block(name, h):
    print(f'\n{name}')
    for lab, q in (('all', h), ('no 8-K within 2d', h[h.k8_near == 0]), ('8-K within 2d', h[h.k8_near == 1])):
        print(f'   {lab:17s}  5d ', stat(q, 'ab5')); print(f'   {"":17s} 20d ', stat(q, 'ab20')); print(f'   {"":17s} 60d ', stat(q, 'ab60'))
    print(f'   {"all, 5d BEFORE":17s}     ', stat(h, 'pre5'))
block('STOPPED (terminated + suspended + withdrawn)', Dn[Dn.stopped == 1])
for ct_, h in sorted(Dn.groupby('change_type'), key=lambda x: -len(x[1])): block(ct_, h)

print('\n=== context splits for pc_slip, design set, 20 day abnormal return (and 60 day) ===')
S = Dn[Dn.change_type == 'pc_slip']
def split(name, groups):
    print(f'\n{name}')
    for lab, mk in groups: print(f'   {lab:34s}', stat(S[mk], 'ab20'), '| 60d', stat(S[mk], 'ab60'))
split('1. new data date vs cash runway', [('after cash runs out', S.past_cash == 1), ('before cash runs out', S.past_cash == 0)])
split('2. importance', [('includes a phase 3 trial', S.late_phase == 1), ('no phase 3 trial', S.late_phase == 0),
                        ('company has <= 2 active trials', S.tr_active <= 2), ('company has > 2 active trials', S.tr_active > 2)])
split('3. size of the delay', [('28 to 180 days', S.days_shifted.between(28, 180)), ('181 to 365 days', S.days_shifted.between(181, 365)), ('over 365 days', S.days_shifted > 365)])
split('4. repeat', [('first slip of this trial', S.prior_slips == 0), ('second or later slip', S.prior_slips >= 1)])
z = pd.Series(0, index=S.index)
up = S.get('same_enroll_target_up', z) == 1; dn = S.get('same_enroll_target_down', z) == 1; oe = S.get('same_primary_outcome_edit', z) == 1
split('5. what else changed the same day', [('enrollment target raised', up), ('enrollment target cut', dn), ('primary outcome edited', oe), ('nothing else', ~(up | dn | oe))])
split('6. company size', [('market cap under $300M', S.fin_mktcap_m < 300), ('market cap $300M or more', S.fin_mktcap_m >= 300)])
split('7. data quality', [('outside the 2024 system change', S.cutover == 0), ('inside it (Jun to mid Sep 2024)', S.cutover == 1),
                          ('company updated < 5 records that day', S.n_records_same_day < 5), ('5+ records that day (bulk update)', S.n_records_same_day >= 5)])
print('\nnote: many groups are shown. With this many, a few will look good by luck. Pick ONE rule, then test it once with --rule.')
