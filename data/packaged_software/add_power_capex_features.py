"""Append public power/capex features without changing existing rows or labels.

Snapshots make this rerunnable. CSV, dictionary and SQLite modelling views are
updated additively; source/provenance/coverage tables remain reviewable separately.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path

import pandas as pd

from collect_power_capex import HERE, OUT, read, write, sha, next_day, pick, observation

TARGETS = [HERE/'final/feature_matrix_backtest.csv', HERE/'output/feature_matrix_backtest.csv',
           HERE/'feature_matrix_backtest.csv', HERE/'output/feature_matrix_extended.csv',
           HERE/'output/feature_matrix_wide.csv']
TEXT_FEATURES = {'capex_guidance_candidate_sentences','datacenter_capex_candidate_sentences','ppa_disclosure_candidate_sentences'}
MACRO = {'pjm_rto_capacity_price_usd_mw_day':('price_usd_mw_day','USD/MW-day'),
         'pjm_rto_capacity_price_change_vs_previous_auction':('price_change_vs_previous_auction','fraction'),
         'pjm_rto_capacity_price_cap_hit':('price_cap_hit','flag'),
         'pjm_rto_capacity_shortfall_mw':('shortfall_mw','MW')}
GUIDANCE = {'capex_guidance_annual_low_usd','capex_guidance_annual_high_usd',
            'capex_guidance_remaining_year_low_usd','capex_guidance_remaining_year_high_usd',
            'capex_guidance_next_12_months_upper_bound_usd'}


def ranks(values):
    v=pd.to_numeric(values,errors='coerce')
    result=pd.Series(float('nan'),index=v.index)
    n=v.notna().sum()
    if n>=5:
        result.loc[v.notna()] = 2*(v.dropna().rank(method='average')-1)/(n-1)-1
    return result


def verified_guidance():
    path=OUT/'reviewed_capex_guidance.csv'
    if not path.exists():
        return []
    candidates={r['evidence_id']:r for r in read(OUT/'filing_candidates.csv')}
    result=[]
    for reviewed in read(path):
        source=candidates[reviewed['evidence_id']]
        if sha(Path(source['local_path']).read_bytes())!=source['source_sha256']:
            raise ValueError('Changed guidance source')
        # Exact reviewed snippet/amount/horizon are pinned; never guess hardware scope.
        if reviewed['source_sha256']!=source['source_sha256'] or reviewed['source_clause'] not in source['excerpt']:
            raise ValueError('Guidance evidence mismatch')
        for bound in ('low','high','upper_bound'):
            value=reviewed.get(bound+'_usd','')
            if not value:
                continue
            feature='capex_guidance_'+reviewed['horizon_type']+'_'+bound+'_usd'
            row=observation(source['cik'],feature,float(value),source['filed_date'],source['available_date'],source['evidence_id'])
            row.update(source_url=source['source_url'],source_sha256=source['source_sha256'],
                       local_path=source['local_path'],quality_status='source_clause_amount_and_horizon_reviewed_not_PPE_only',
                       scope=reviewed['scope'],valid_until=reviewed['horizon_end'],source_clause=reviewed['source_clause'])
            result.append(row)
    return result


def load_observations():
    observations=[]
    for name in ('sec_observations.csv','filing_observations.csv'):
        observations.extend(read(OUT/name))
    observations.extend(verified_guidance())
    # Only public filing metadata has a usable historical publication date.
    # Counts are search candidates, not verified agreements or load expansion.
    grouped=defaultdict(list)
    coverage={r['cik']:r for r in read(OUT/'ferc_search_coverage.csv')}
    for r in read(OUT/'ferc_search_candidates.csv'):
        if r['availability_code']!='P' or not r['posted_date'] or not coverage[r['cik']]['status'].startswith('completed_'):
            continue
        published=dt.datetime.strptime(r['posted_date'],'%m/%d/%Y').date().isoformat()
        available=next_day(published)
        quarter=str(pd.Timestamp(available).to_period('Q'))
        grouped[(r['cik'],quarter)].append(dict(r,available_date=available,published_date=published))
    for (cik,q),rows in grouped.items():
        row=observation(cik,'ferc_power_search_candidate_count',len({r['accession'] for r in rows}),
                        max(r['published_date'] for r in rows),max(r['available_date'] for r in rows),
                        ';'.join(sorted({r['accession'] for r in rows})))
        row.update(unit='search_candidates',scope=coverage[cik]['status'],
                   quality_status='public_metadata_search_matches_not_confirmed_company_projects',
                   source_url=rows[0]['source_url'],source_sha256=rows[0]['metadata_sha256'],
                   local_path=rows[0]['cache_path'],quarter=q)
        observations.append(row)
    for r in read(OUT/'pjm_auctions.csv'):
        if sha((HERE/r['local_path']).read_bytes())!=r['source_sha256']:
            raise ValueError('Changed PJM source')
        for feature,(column,unit) in MACRO.items():
            if r[column]=='':
                continue
            row=observation('*',feature,float(r[column]),r['published_date'],r['available_date'],r['delivery_year'])
            row.update(unit=unit,scope='PJM regional macro context; issuer exposure unmeasured',
                       source_url=r['source_url'],source_sha256=r['source_sha256'],local_path=r['local_path'],
                       quality_status='official_capacity_auction_not_company_cost',source_clause=r['source_clause'],
                       date_source_url=r.get('date_source_url',''),date_source_sha256=r.get('date_source_sha256',''))
            observations.append(row)
    # Validate lineage, all clocks and finite numerical values before changing outputs.
    for r in observations:
        r['value']=float(r['value'])
        if not pd.notna(r['value']) or abs(r['value'])==float('inf'):
            raise ValueError('Nonfinite value')
        if r['available_date']<r['period_end']:
            raise ValueError('Availability before economic/source period')
        dt.date.fromisoformat(r['period_end'])
        dt.date.fromisoformat(r['available_date'])
    return observations


def select(rows,cutoff,feature,quarter):
    rows=[r for r in rows if r['available_date']<=cutoff]
    if feature in GUIDANCE:
        rows=[r for r in rows if r.get('valid_until','')>=cutoff and str(pd.Timestamp(r['available_date']).to_period('Q'))==quarter]
    if feature=='ferc_power_search_candidate_count':
        rows=[r for r in rows if r['quarter']==quarter]
    if feature in MACRO:
        return max(rows,key=lambda r:r['available_date']) if rows else None
    return pick(rows,cutoff)


def additions(base,observations,definitions):
    groups=defaultdict(list)
    for r in observations:
        groups[(r['cik'],r['feature'])].append(r)
    added,ledger=[],[]
    for original in base.to_dict('records'):
        quarter=original.get('quarter') or original['period_end']
        cutoff=str(pd.Period(quarter,freq='Q').end_time.date())
        row={}
        for feature in sorted(definitions):
            candidates=groups.get(('*' if feature in MACRO else original['cik'],feature),[])
            choice=select(candidates,cutoff,feature,quarter)
            row[feature]=choice['value'] if choice else float('nan')
            reason='' if choice else ('no_reviewed_guidance_for_this_disclosure_quarter_and_horizon' if feature in GUIDANCE
                                     else 'no_public_search_candidate_in_quarter_not_evidence_of_zero_projects' if feature.startswith('ferc_')
                                     else 'no_available_source_observation_within_400_days')
            ledger.append(dict(cik=original['cik'],quarter=quarter,decision_date=cutoff,feature=feature,
                               missing_reason=reason,**({k:v for k,v in choice.items() if k not in {'cik','quarter','feature'}} if choice else {})))
        added.append(row)
    data=pd.DataFrame(added,index=base.index)
    quarters=base['quarter'] if 'quarter' in base else base['period_end']
    companions={}
    for feature in sorted(definitions):
        companions[feature+'__present']=data[feature].notna().astype(int)
        companions[feature+'__rank']=data[feature].groupby(quarters).transform(ranks)
    return pd.concat([data,pd.DataFrame(companions,index=base.index)],axis=1),ledger


def sync_database(path,matrix,ledger,definitions):
    if not path.exists():
        return
    con=sqlite3.connect(path)
    try:
        with con:
            tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'fact_feature_matrix' in tables:
                columns={r[1] for r in con.execute('PRAGMA table_info(fact_feature_matrix)')}
                for feature in sorted(definitions):
                    for column in [feature,feature+'__present',feature+'__rank']:
                        if column not in columns:
                            con.execute(f'ALTER TABLE fact_feature_matrix ADD COLUMN "{column}" REAL')
                newcols=[c for c in matrix if c.removesuffix('__present').removesuffix('__rank') in definitions]
                statement='UPDATE fact_feature_matrix SET '+','.join(f'"{c}"=?' for c in newcols)+' WHERE cik=? AND quarter=?'
                con.executemany(statement, [[None if pd.isna(r[c]) or r[c]=='' else r[c] for c in newcols]+[r['cik'],r['quarter']]
                                           for r in matrix.to_dict('records')])
            if 'fact_panel' in tables:
                for feature in definitions:
                    con.execute('DELETE FROM fact_panel WHERE feature=?',(feature,))
                columns=['cik','period_end','feature','value','unit','source_file','as_of','missing_reason','evidence_ref']
                records=[(r['cik'],r['quarter'],r['feature'],r.get('value',''),definitions[r['feature']]['unit'],
                          'extracts/power_capex/matrix_feature_provenance.csv',r.get('available_date',''),r['missing_reason'],r.get('evidence_ref',''))
                         for r in ledger]
                con.executemany('INSERT INTO fact_panel ('+','.join(columns)+') VALUES (?,?,?,?,?,?,?,?,?)',records)
    finally:
        con.close()


def main():
    observations=load_observations()
    definitions={r['feature']:dict(unit=r['unit'],description=r['quality_status'],scope=r['scope']) for r in observations}
    for feature in GUIDANCE:
        definitions.setdefault(feature,dict(unit='USD',description='Reviewed disclosed CapEx guidance; horizon retained; not necessarily PP&E only',scope='issuer guidance'))
    definitions.setdefault('ferc_power_search_candidate_count',dict(unit='search_candidates',description='Public FERC full-text matches; not direct company PPA or interconnection amounts',scope='unverified search attribution'))
    for feature,(column,unit) in MACRO.items():
        definitions.setdefault(feature,dict(unit=unit,description='Latest published PJM regional auction result',scope='regional macro; company exposure unmeasured'))
    snapshot=OUT/'matrix_before_power_capex'
    snapshot.mkdir(exist_ok=True)
    results=[]
    final_ledger=[]
    final_matrix=None
    for target in TARGETS:
        if not target.exists():
            continue
        baseline=snapshot/(str(target.relative_to(HERE)).replace('\\','__').replace('/','__'))
        if not baseline.exists():
            shutil.copy2(target,baseline)
        base=pd.read_csv(baseline,dtype=str,keep_default_na=False)
        current=pd.read_csv(target,dtype=str,keep_default_na=False)
        if any(c not in current for c in base) or not current[list(base)].equals(base):
            raise ValueError('Existing matrix changed since this extension snapshot; preserve and review the newer base before rebuilding')
        if base.duplicated(['cik','quarter' if 'quarter' in base else 'period_end']).any():
            raise ValueError('Duplicate matrix issuer/quarter')
        added,ledger=additions(base,observations,definitions)
        overlap=set(base)&set(added)
        if overlap:
            raise ValueError('New feature collides with existing column: '+str(overlap))
        updated=pd.concat([base,added],axis=1)
        if not updated[list(base)].equals(base):
            raise ValueError('Existing cells changed')
        temporary=target.with_suffix('.power_capex.tmp')
        updated.to_csv(temporary,index=False)
        reloaded=pd.read_csv(temporary,dtype=str,keep_default_na=False)
        if not reloaded[list(base)].equals(base):
            raise ValueError('CSV export changed existing cells')
        temporary.replace(target)
        results.append(dict(path=str(target.relative_to(HERE)),rows=len(updated),columns=updated.shape[1],
                            original_sha256=sha(baseline.read_bytes()),output_sha256=sha(target.read_bytes())))
        if target.parent.name=='final':
            final_ledger,final_matrix=ledger,updated
    if final_matrix is None:
        raise ValueError('No final matrix')
    write(OUT/'matrix_feature_provenance.csv',final_ledger)
    write(OUT/'all_observations.csv',observations)
    coverage=[dict(feature=f,rows_present=int(final_matrix[f].notna().sum()),
                   companies_with_values=int((final_matrix.groupby('cik')[f].count()>0).sum()),
                   total_rows=len(final_matrix),**definitions[f]) for f in sorted(definitions)]
    write(OUT/'matrix_feature_coverage.csv',coverage)
    # Extend dictionaries at both published locations, preserving original descriptions.
    for path in [HERE/'final/FEATURE_MATRIX_DICTIONARY.csv',HERE/'FEATURE_MATRIX_DICTIONARY.csv']:
        rows=read(path)
        rows=[r for r in rows if r['column'].removesuffix('__present').removesuffix('__rank') not in definitions]
        for feature in sorted(definitions):
            for suffix,role in [('', 'feature'),('__present','presence'),('__rank','rank')]:
                rows.append(dict(column=feature+suffix,role=role,description=json.dumps(definitions[feature]) if not suffix else
                                 '1 means observed, 0 missing; not proof of economic applicability' if role=='presence' else
                                 'Within-quarter average tied rank in [-1,1]; macro constants rank zero; fewer than 5 observed values remain blank'))
        write(path,rows,['column','role','description'])
    for database in [HERE/'output/dataset.sqlite',HERE/'final/dataset.sqlite']:
        sync_database(database,final_matrix,final_ledger,definitions)
    summary=dict(version='power-capex-additive-v1',raw_features_added=len(definitions),companies=final_matrix.cik.nunique(),
                 rows=len(final_matrix),all_existing_values_and_labels_preserved=True,updated_files=results,
                 source_sha256={p.name:sha(p.read_bytes()) for p in OUT.glob('*.csv') if not p.name.startswith('matrix_')})
    (OUT/'matrix_update_manifest.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    note='\n\n## Public CapEx, leases and power features\n\n'+f'Added {len(definitions)} raw features with presence flags and ranks. The final matrix has {len(final_matrix)} rows and {final_matrix.shape[1]} columns.\n\n'+README
    for path in [HERE/'final/FEATURE_MATRIX_README.md',HERE/'FEATURE_MATRIX_README.md']:
        original=path.read_text(encoding='utf-8').split('\n\n## Public CapEx, leases and power features')[0]
        path.write_text(original+note,encoding='utf-8')
    (OUT/'REPORT.md').write_text(README+'\n\n'+json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    manifest_path=HERE/'final/feature_matrix_manifest.json'
    if manifest_path.exists():
        manifest_archive=snapshot/'final__feature_matrix_manifest.json'
        if not manifest_archive.exists():
            shutil.copy2(manifest_path,manifest_archive)
        manifest=json.loads(manifest_archive.read_text(encoding='utf-8'))
        manifest['base_build_output_sha256']=manifest.get('output_sha256',{})
        manifest['output_sha256']=dict(manifest.get('output_sha256',{}),
                                      **{name:sha((HERE/'final'/name).read_bytes()) for name in ['feature_matrix_backtest.csv','FEATURE_MATRIX_DICTIONARY.csv']})
        manifest['power_capex_extension']=dict(raw_features_added=len(definitions),rows=len(final_matrix),columns=final_matrix.shape[1],
                                              manifest='extracts/power_capex/matrix_update_manifest.json',
                                              provenance='extracts/power_capex/matrix_feature_provenance.csv',
                                              coverage='extracts/power_capex/matrix_feature_coverage.csv')
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='source_sha256'},indent=2))


README='''The additive collector is `collect_power_capex.py`; integration is
`add_power_capex_features.py`. Existing matrix values, rows and outcome labels are
preserved. New source/provenance/coverage files are in `extracts/power_capex/`.

SEC standard USD tags provide lease liabilities (a reported total, or current plus
noncurrent from the SAME accession and economic period), ROU assets, undiscounted
lease payments and reported noncash additions. Liability changes are changes in
balances, not new lease additions: payments, FX, acquisitions and discounting can
affect them. Nothing establishes data-center-specific lease scope by itself.
Missing current/noncurrent components and inconsistent totals remain missing.
Quarter and annual noncash additions are separate; annual values are not divided
into quarters. Actual physical CapEx and intensity use the existing conservative
financial-quality layer and retain its eligibility/lineage restrictions.

Daily availability is the filing/publication date plus one day. Company features
select the latest economic period publicly available at quarter-end, then its
latest available version; conflicts are withheld. Financial values expire after
400 days. YoY/QoQ changes only use compatible economic periods and earlier facts
available at the current disclosure date. A zero prior value has no growth ratio.

CapEx/PPA/data-center text counts are CANDIDATES from the latest scanned annual or
quarterly filing. They are not verified guidance amounts, hardware spend, PPAs or
data-center expansion. Reviewed numeric guidance is sparse, with an exact clause,
source hash, horizon and scope. Annual, remaining-year and next-12-month amounts
are separate and used only in their disclosure quarter, before the horizon ends.
Guidance including software or offices is not relabeled PP&E-only or data-center
CapEx. Unreviewed dollar mentions never enter numeric guidance features.

FERC searches use public eLibrary full-text metadata. Search candidates can refer
to testimony, software/vendor mentions or policy proceedings. Candidate counts
are positive public metadata matches by posting quarter, not confirmed company
projects, PPAs, MW or expenditures. Failed/truncated searches and absence of
candidates never become zero interconnection demand. No confidential/CEII contents
are downloaded. `ferc_search_coverage.csv` retains errors, truncation and queries.
Unverified project MW/contract prices are not fabricated into model inputs.

PJM prices are USD per MW-day of capacity, not energy prices (USD/MWh). These are
regional macro values shared by all issuers, not company exposure or costs.
Identical macro values receive a tied rank of zero; raw values retain the time
series. Auction announcement dates are distinct from future delivery years.
Price changes can reflect supply, demand, accreditation and price caps; they do
not isolate AI/data-center demand. Shortfalls remain missing unless explicitly
reported. Other RTO/ISO auction formats are not assumed comparable to PJM.

`matrix_feature_provenance.csv` records selection, clocks, scope and missing
reasons; `matrix_feature_coverage.csv` gives observed company/row counts. Original
matrices are archived in `matrix_before_power_capex/`. CSV modelling views retain
their individual original row grids and labels; the reviewed final grid can differ
from legacy copies. New SQLite columns match new CSV values for shared keys;
legacy SQLite rows/labels are not replaced by the reviewed final CSV. Original legacy
quality, survivorship and label limitations remain. These data do not establish
an executable strategy or a historical intraday information clock.

Reproduce with the project venv: run `collect_power_capex.py --asof YYYY-MM-DD`,
then `add_power_capex_features.py`. Public reports need `pypdf` and `requests`.
'''


if __name__=='__main__':
    main()
