"""Scan newly indexed exhibits and previously excluded registration statements."""
import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import pandas as pd
import extract_company_metrics as m

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE=HERE/'extracts'
OUT=BASE/'company_coverage'
REGISTRATION={'S-1','S-1/A','F-1','F-1/A','S-4','S-4/A','F-4','F-4/A'}


def main():
    companies=pd.read_csv(HERE/'packaged_software_companies.csv',dtype=str).set_index('cik')
    prior=pd.read_csv(BASE/'gap_recovery/filings_index_before_retry.csv',dtype=str)
    index=pd.read_csv(BASE/'sec/filings_index.csv',dtype=str)
    key=lambda r:(r.cik,r.accession,r.primary_document,r.document_role)
    previously_scanned={key(r) for r in prior.itertuples() if r.form in m.FORMS-REGISTRATION and '2022-01-01'<=r.filing_date<='2026-10-03'}
    eligible=index[index.form.isin(m.FORMS)&index.filing_date.between('2022-01-01','2026-10-03')]
    records=eligible.to_dict('records')
    valid=[]; missing=[]
    for r in records:
        path=(ROOT/r['local_path']).resolve()
        if not path.is_relative_to((BASE/'sec').resolve()) or not path.exists():
            missing.append(r)
        elif (r['cik'],r['accession'],r['primary_document'],r['document_role']) not in previously_scanned:
            valid.append(r)
    events=pd.read_csv(BASE/'company_metrics_recovered/disclosure_evidence.csv',dtype=str).fillna('').to_dict('records')
    tagged=pd.read_csv(BASE/'company_metrics_recovered/filing_tagged_asset_and_cloud_facts.csv',dtype=str).fillna('').to_dict('records')
    seen={r['evidence_id']:r for r in events}; inline_seen=set()
    for r in tagged:
        inline_seen.add((r['cik'],r['accession'],r['tag'],r['context_id'],r['raw_value']))
    errors=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,(filing,result) in enumerate(zip(valid,m.bounded_scan(pool,valid,4)),1):
            facts,text,error=result
            if error:
                errors.append({'ticker':filing['ticker'],'accession':filing['accession'],'error':error})
                continue
            company=companies.loc[filing['cik']].to_dict(); company['cik']=filing['cik']
            url=f"https://www.sec.gov/Archives/edgar/data/{int(filing['cik'])}/{filing['accession'].replace('-','')}/{filing['primary_document']}"
            for f in facts:
                if not f['period_end'] or not '2022-01-01'<=f['period_end']<='2026-10-03': continue
                k=(filing['cik'],filing['accession'],f['tag'],f['context_id'],f['raw_value'])
                if k in inline_seen: continue
                inline_seen.add(k)
                tagged.append({**{k:company[k] for k in m.ID},**f,'form':filing['form'],'accession':filing['accession'],
                               'filed_date':filing['filing_date'],'available_date_conservative':m.next_day(filing['filing_date']),'source_url':url})
            for category,classification,snippet in m.evidence(text):
                norm=re.sub(r'\s+',' ',snippet).strip().lower()
                eid=hashlib.sha256((filing['cik']+classification+norm).encode()).hexdigest()[:24]
                if eid in seen and seen[eid]['filed_date']<=filing['filing_date']: continue
                seen[eid]={**{k:company[k] for k in m.ID},'evidence_id':eid,'category':category,'classification':classification,
                           'review_status':'unreviewed_text_candidate','form':filing['form'],'accession':filing['accession'],
                           'filed_date':filing['filing_date'],'available_date_conservative':m.next_day(filing['filing_date']),
                           'source_url':url,'local_path':filing['local_path'],'excerpt':snippet,
                           'vendors_mentioned':';'.join(sorted(set(x.group() for x in m.VENDORS.finditer(snippet)))),
                           'numeric_mentions_unvalidated':';'.join(m.NUMBER.findall(snippet)),'amount_usd':'','employee_seats':'',
                           'first_seen_in_scanned_filings':True}
            if i==1 or i%100==0: print(f'Additional filing scan {i}/{len(valid)}',flush=True)
    m.write_csv(OUT/'disclosure_evidence_expanded.csv',m.EVIDENCE_FIELDS,list(seen.values()))
    m.write_csv(OUT/'tagged_asset_cloud_facts_expanded.csv',m.INLINE_FIELDS,tagged)
    pd.DataFrame(missing).to_csv(OUT/'unavailable_filing_documents.csv',index=False)
    manifest={'eligible_index_documents':len(eligible),'baseline_keys':len(previously_scanned),'additional_documents_scanned':len(valid)-len(errors),
              'missing_documents':len(missing),'errors':errors,'disclosure_candidates':len(seen),'tagged_fact_rows':len(tagged),
              'scope':'indexed_eligible_SEC_documents_through_2026_10_03_not_all_public_announcements',
              'interpretation':'Unreviewed candidates; no inferred spending or adoption amounts.'}
    (OUT/'disclosure_expansion_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    main()
