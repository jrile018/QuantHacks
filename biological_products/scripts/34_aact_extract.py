"""
34_aact_extract.py - read the monthly AACT snapshots (zips in data/raw/aact) and keep only our trials.

AACT (aact.ctti-clinicaltrials.org, run by CTTI: Duke + FDA) stores a full copy of ClinicalTrials.gov on the first of each month.
Comparing a trial across snapshots shows when its record changed. This script only EXTRACTS; script 35 builds the change events.

For every zip it writes one small csv in data/raw/aact_extract/ (so a rerun skips finished zips):
  one row per trial: snapshot date, status, dates, enrollment, number of sites, number of primary outcomes and a hash of their text.
Usage:  python 34_aact_extract.py [--max_seconds 150]     (stops cleanly when time is up; run again to continue)
"""
import os, re, io, sys, glob, time, zipfile, hashlib, argparse
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('--data', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ap.add_argument('--max_seconds', type=float, default=0)
a = ap.parse_args()
RAW = os.path.join(a.data, 'raw'); SRC = os.path.join(RAW, 'aact'); OUT = os.path.join(RAW, 'aact_extract')
os.makedirs(OUT, exist_ok=True)
t0 = time.time()

# our trials: group A (139 biologics, has ticker) and, if present, the wider research set (group B = big pharma, for base rates)
A = pd.read_csv(os.path.join(RAW, 'trials.csv'), usecols=['ticker', 'nct_id']).drop_duplicates('nct_id')
keep = set(A.nct_id)
p = os.path.join(RAW, 'research', 'trials_all.csv')
if os.path.exists(p):
    keep |= set(pd.read_csv(p, usecols=['nct_id']).nct_id)
print('trials to keep:', len(keep), '(group A', len(A), ')', flush=True)

COLS = ['nct_id', 'nlm_download_date_description', 'study_first_submitted_date', 'study_first_posted_date', 'results_first_posted_date',
        'last_update_submitted_date', 'last_update_posted_date', 'start_date', 'start_date_type', 'completion_date', 'completion_date_type',
        'primary_completion_date', 'primary_completion_date_type', 'overall_status', 'phase', 'enrollment', 'enrollment_type',
        'number_of_arms', 'why_stopped', 'source']

def read_member(z, name, usecols):
    names = {os.path.basename(n): n for n in z.namelist()}
    if name not in names: return None
    parts = []
    with z.open(names[name]) as h:
        for ch in pd.read_csv(h, sep='|', dtype=str, usecols=lambda c: c in usecols, chunksize=200000, on_bad_lines='skip', low_memory=False):
            parts.append(ch[ch.nct_id.isin(keep)])
    return pd.concat(parts) if parts else None

def snap_date(desc, s):
    m = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})', str(desc))
    if m:
        try: return pd.to_datetime(m.group(1))
        except Exception: pass
    return pd.to_datetime(s.last_update_posted_date, errors='coerce').max()

zips = sorted(glob.glob(os.path.join(SRC, '*.zip')))
print('zips found:', len(zips), flush=True)
done_n = 0
for zp in zips:
    tag = os.path.splitext(os.path.basename(zp))[0]
    outp = os.path.join(OUT, tag + '.csv')
    if os.path.exists(outp): done_n += 1; continue
    if a.max_seconds and time.time() - t0 > a.max_seconds:
        print('time is up, run again to continue'); break
    t1 = time.time()
    try:
        z = zipfile.ZipFile(zp)
        s = read_member(z, 'studies.txt', set(COLS))
    except Exception as ex:
        print('SKIP (unreadable, maybe still downloading):', tag, repr(ex)[:80], flush=True); continue
    if s is None or len(s) == 0: print('SKIP no studies.txt:', tag); continue
    sd = snap_date(s.nlm_download_date_description.iloc[0], s)
    s = s.drop(columns=['nlm_download_date_description'])
    s.insert(0, 'snapshot', int(sd.strftime('%Y%m%d')))
    s['has_why_stopped'] = s.why_stopped.notna().astype(int)
    s = s.drop(columns=['why_stopped'])
    # number of sites
    cv = read_member(z, 'calculated_values.txt', {'nct_id', 'number_of_facilities'})
    if cv is not None: s = s.merge(cv.drop_duplicates('nct_id'), on='nct_id', how='left')
    # primary outcomes: count and a short hash of the text, so an edit is visible without storing the words
    do = read_member(z, 'design_outcomes.txt', {'nct_id', 'outcome_type', 'measure', 'time_frame'})
    if do is not None and len(do):
        do = do[do.outcome_type.str.lower() == 'primary']
        do['t'] = do.measure.fillna('').str.lower().str.strip() + '#' + do.time_frame.fillna('').str.lower().str.strip()
        g = do.groupby('nct_id').t.agg(lambda v: hashlib.md5('||'.join(sorted(v)).encode()).hexdigest()[:10]).rename('primary_outcome_hash')
        n = do.groupby('nct_id').size().rename('n_primary_outcomes')
        s = s.merge(pd.concat([g, n], axis=1).reset_index(), on='nct_id', how='left')
    tmp = outp + '.tmp'
    s.to_csv(tmp, index=False); os.replace(tmp, outp); done_n += 1
    print(f'{tag}: snapshot {sd.date()} rows {len(s)} in {time.time()-t1:.0f}s', flush=True)

print('extracted', done_n, 'of', len(zips), 'zips')
if done_n:
    allp = sorted(glob.glob(os.path.join(OUT, '*.csv')))
    d = pd.concat([pd.read_csv(f, dtype=str) for f in allp])
    d = d.drop_duplicates(['snapshot', 'nct_id']).sort_values(['nct_id', 'snapshot'])
    d.to_csv(os.path.join(RAW, 'aact_snapshots.csv'), index=False)
    print('aact_snapshots.csv rows', len(d), 'snapshots', sorted(d.snapshot.unique()))
