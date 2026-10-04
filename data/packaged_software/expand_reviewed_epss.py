"""Add reviewed Airship/Gen brand mappings using actual dated FIRST scores."""
import json
import hashlib
import urllib.parse
from pathlib import Path
import pandas as pd
from extract_epss import Client, api_key, vendor_cves, summary

HERE=Path(__file__).resolve().parent
BASE=HERE/'extracts'
OUT=BASE/'company_coverage'
CACHE=BASE/'_cache/epss'
MERGER='https://newsroom.gendigital.com/2022-09-12-NortonLifeLock-Completes-Merger-with-Avast'
OWNERSHIP=[
    ('AISP','airship.ai','2022-01-01','https://raw.githubusercontent.com/cisagov/CSAF/develop/csaf_files/IT/white/2025/va-25-265-01.json'),
    ('GEN','avira','2022-01-01','https://investor.gendigital.com/news/news-details/2021/NortonLifeLocks-Q3-Growth-Momentum-Fueled-by-Cyber-Safety-Adoption/default.aspx'),
    ('GEN','avast','2022-09-12',MERGER),
    ('GEN','avg','2022-09-12',MERGER+';https://blog.avast.com/avast-and-avg-become-one'),
    ('GEN','piriform','2022-09-12',MERGER+';https://blog.avast.com/welcome-piriform-to-avast')]
DIRECT={'FATN':[f'CVE-2021-278{i}' for i in range(55,61)],
        'DOCU':['CVE-2024-52276','CVE-2024-52269']}


def checked_scores(data, date, wanted, strict_cves=False):
    if data.get('status') != 'OK':
        raise ValueError('FIRST did not return OK')
    scores = {}
    for r in data.get('data', []):
        if r.get('date') != date:
            raise ValueError('FIRST row date mismatch')
        if r['cve'] not in wanted:
            if strict_cves:
                raise ValueError('FIRST CVE mismatch')
            continue
        score, percentile = float(r['epss']), float(r['percentile'])
        if not 0 <= score <= 1 or not 0 <= percentile <= 1:
            raise ValueError('Probability outside [0,1]')
        scores[r['cve']] = (score, percentile)
    return scores


def main():
    OUT.mkdir(exist_ok=True)
    pd.DataFrame(OWNERSHIP,columns=['ticker','cpe_vendor','ownership_start_used','evidence_url']).to_csv(OUT/'reviewed_epss_brand_ownership.csv',index=False)
    client=Client(api_key()); records={}
    for ticker,vendor,start,evidence in OWNERSHIP:
        print(f'NVD reviewed vendor: {ticker} {vendor}',flush=True)
        records[vendor]=vendor_cves(client,vendor,CACHE)['cves']
    companies=pd.read_csv(HERE/'packaged_software_companies.csv',dtype=str).set_index('ticker')
    direct={}
    direct_sources=[]
    for ticker,cves in DIRECT.items():
        cik=companies.loc[ticker,'cik']
        raw=json.loads((OUT/'nvd_company_search_cache'/cik/'0.json').read_text())
        source={r['cve']['id']:r['cve'] for r in raw['vulnerabilities']}
        direct[ticker]=[]
        for cve_id in cves:
            c=source[cve_id]
            if ticker=='DOCU':
                url=f'https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2024/52xxx/{cve_id}.json'
                file=OUT/f'{cve_id}_primary_record.json'
                d=json.loads(file.read_text()) if file.exists() else json.loads(client.get(url))
                if not any(a.get('vendor','').lower()=='docusign' for a in d['containers']['cna']['affected']):
                    raise ValueError('Primary CVE record does not attribute product to DocuSign')
                file.write_text(json.dumps(d),encoding='utf-8')
            else:
                url=f'https://nvd.nist.gov/vuln/detail/{cve_id}'
                if 'cpe:2.3:o:fatpipeinc:' not in json.dumps(c.get('configurations',[])):
                    raise ValueError('FatPipe firmware vendor missing from NVD configurations')
            direct[ticker].append({'cve':cve_id,'published':c['published'],'vendors':['fatpipeinc'] if ticker=='FATN' else []})
            direct_sources.append({'ticker':ticker,'cve':cve_id,'evidence_url':url,
                                   'attribution':'reviewed_firmware_CPE_vendor' if ticker=='FATN' else 'reviewed_primary_CVE_named_vendor_no_CPE_required'})
    pd.DataFrame(direct_sources).to_csv(OUT/'reviewed_direct_cve_attribution.csv',index=False)
    targets=['AISP','GEN']+list(DIRECT)
    history=pd.read_csv(BASE/'epss_monthly/company_epss_history.csv',dtype=str).fillna('')
    cache=OUT/'epss_reviewed_cache'; cache.mkdir(exist_ok=True)
    errors=[]; supplements=[]
    for date in sorted(history.score_date.unique()):
        eligible={}
        for ticker in targets:
            merged={}
            for owner,vendor,start,evidence in OWNERSHIP:
                if owner!=ticker or date<start: continue
                for c in records[vendor]:
                    if c['published'][:10]<=date:
                        merged.setdefault(c['cve'],{**c,'vendors':[]})['vendors'].append(vendor)
            eligible[ticker]=list(merged.values())
            if ticker in direct:
                eligible[ticker]=[c for c in direct[ticker] if c['published'][:10]<=date]
        wanted=sorted({c['cve'] for values in eligible.values() for c in values}); scores={}
        failed=False
        try:
            for file in sorted(cache.glob(f'{date}_*.json')):
                data=json.loads(file.read_text())
                scores.update(checked_scores(data, date, wanted))
            missing=[c for c in wanted if c not in scores]
            for start in range(0,len(missing),100):
                batch=missing[start:start+100]
                qs=urllib.parse.urlencode({'cve':','.join(batch),'date':date,'limit':100})
                url=f'https://api.first.org/data/v1/epss?{qs}'
                fingerprint=hashlib.sha256(','.join(batch).encode()).hexdigest()[:16]
                file=cache/f'{date}_{fingerprint}.json'
                data=json.loads(file.read_text()) if file.exists() else json.loads(client.get(url))
                scores.update(checked_scores(data, date, batch, strict_cves=True))
                file.write_text(json.dumps(data),encoding='utf-8')
        except Exception as e:
            failed=True; errors.append({'date':date,'error':type(e).__name__,'http_status':getattr(e,'code',None)})
        for ticker in targets:
            company=companies.loc[ticker].to_dict(); company['ticker']=ticker
            mapping={'cpe_vendors':';'.join(v for owner,v,start,_ in OWNERSHIP if owner==ticker and date>=start),
                     'mapping_status':'reviewed_named_brand_subset_ownership_dates_checked'}
            if ticker in DIRECT:
                mapping={'cpe_vendors':'fatpipeinc' if ticker=='FATN' else 'direct_named_vendor_CVE',
                         'mapping_status':'reviewed_firmware_CPE' if ticker=='FATN' else 'reviewed_primary_CVE_named_vendor_no_CPE_assignment'}
            row=summary(company,mapping,eligible[ticker],scores,date,'unavailable_from_dated_API',.10,failed)
            if ticker=='DOCU': row['cpe_vendors']=''
            if failed: row['coverage_status']='epss_snapshot_fetch_failed'
            row['historical_mapping_limitation']='ownership_start_dates_checked_current_NVD_inventory_retrospective_not_full_vintage;brand_subset_not_full_company_risk'
            supplements.append(row)
        print(f'FIRST {date}: {len(scores)}/{len(wanted)} CVEs returned',flush=True)
    revised=pd.concat([history[~history.ticker.isin(targets)],pd.DataFrame(supplements)],ignore_index=True)
    revised.sort_values(['score_date','ticker']).to_csv(OUT/'company_epss_history_expanded.csv',index=False)
    (OUT/'epss_expansion_manifest.json').write_text(json.dumps({'companies_updated':targets,
                                                              'vendors':{v:len(c) for v,c in records.items()},'errors':errors,
                                                              'limitation':'Named owned-brand subset, not comprehensive company risk; model versions unavailable from dated API.'},indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
