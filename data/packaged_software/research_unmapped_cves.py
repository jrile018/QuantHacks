"""Search public NVD records for every unmapped company; never guess ownership.

An empty company-name search does not establish absence of vulnerabilities.
Matches are candidates requiring product/issuer ownership review.
"""
import argparse
import csv
import json
import re
import urllib.parse
from pathlib import Path
from extract_epss import Client, api_key, read_csv, write_json

HERE=Path(__file__).resolve().parent
OUT=HERE/'extracts/company_coverage'


def search_name(name):
    name=re.split(r'\b(?:Common Stock|Ordinary Shares|Class [A-Z]|American Depositary)\b',name,flags=re.I)[0]
    name=re.sub(r'\b(?:Inc\.?|Corporation|Corp\.?|Ltd\.?|plc|Holdings?|Limited|Company)\b',' ',name,flags=re.I)
    return ' '.join(name.replace(',',' ').replace('.',' ').split()).strip()


def application_vendors(value):
    result=set()
    if isinstance(value,dict):
        if value.get('vulnerable') and str(value.get('criteria','')).startswith('cpe:2.3:a:'):
            result.add(value['criteria'].split(':')[3])
        for v in value.values():
            result.update(application_vendors(v))
    elif isinstance(value,list):
        for v in value:
            result.update(application_vendors(v))
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--limit',type=int)
    ap.add_argument('--include-empty-vendors',action='store_true',help='Also research mapped vendors that returned no CVEs')
    args=ap.parse_args()
    companies=read_csv(HERE/'epss_company_mapping.csv')
    empty=set()
    if args.include_empty_vendors:
        empty={r['cik'] for r in read_csv(HERE/'extracts/epss_monthly/mapping_coverage.csv') if r['current_matching_cve_count']=='0'}
    missing=[r for r in companies if not r['cpe_vendors'].strip() or r['cik'] in empty]
    if args.limit:
        missing=missing[:args.limit]
    OUT.mkdir(parents=True,exist_ok=True)
    cache=OUT/'nvd_company_search_cache'
    client=Client(api_key())
    coverage=[]
    candidates=[]
    for index,company in enumerate(missing,1):
        query=search_name(company['name'])
        records=[]
        start=0
        error=''
        urls=[]
        try:
            while True:
                parameters=urllib.parse.urlencode({'keywordSearch':query,'resultsPerPage':2000,'startIndex':start})+'&keywordExactMatch'
                url=f'https://services.nvd.nist.gov/rest/json/cves/2.0?{parameters}'
                urls.append(url)
                file=cache/company['cik']/f'{start}.json'
                data=json.loads(file.read_text()) if file.exists() else json.loads(client.get(url,nvd=True))
                if 'totalResults' not in data or 'vulnerabilities' not in data:
                    raise ValueError('Unexpected NVD response')
                write_json(file,data)
                records.extend(data['vulnerabilities'])
                if start+len(data['vulnerabilities'])>=data['totalResults']:
                    break
                if not data['vulnerabilities']:
                    raise ValueError('Empty incomplete page')
                start+=len(data['vulnerabilities'])
        except Exception as exc:
            error=f'{type(exc).__name__}:{getattr(exc,"code","")}'
        for record in records:
            c=record['cve']
            if c.get('vulnStatus')=='Rejected':
                continue
            vendors=application_vendors(c.get('configurations',[]))
            candidates.append({'cik':company['cik'],'ticker':company['ticker'],'name':company['name'],
                               'query':query,'cve':c['id'],'published':c.get('published',''),
                               'candidate_application_vendors':';'.join(sorted(vendors)),
                               'description':' '.join(d['value'] for d in c.get('descriptions',[]) if d.get('lang')=='en'),
                               'references':';'.join(r['url'] for r in c.get('references',[])),
                               'source_url':f"https://nvd.nist.gov/vuln/detail/{c['id']}",
                               'review_status':'company_name_match_product_ownership_unverified'})
        coverage.append({'cik':company['cik'],'ticker':company['ticker'],'name':company['name'],
                         'query':query,'matching_records':len(records),
                         'status':'query_failed' if error else 'candidates_require_ownership_review' if records else 'no_records_for_this_name_search_not_zero_risk',
                         'error':error,'source_urls':';'.join(urls)})
        for filename,rows in [('unmapped_cve_search_coverage.csv',coverage),('cve_ownership_candidates.csv',candidates)]:
            fields=list(rows[0]) if rows else ['cik','ticker','name','query','cve','review_status']
            with (OUT/filename).open('w',newline='',encoding='utf-8') as f:
                w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
        print(f"{index}/{len(missing)} {company['ticker']}: {coverage[-1]['status']} ({len(records)} records)",flush=True)
    write_json(OUT/'nvd_search_manifest.json',{'companies_queried':len(coverage),'candidate_records':len(candidates),
                                            'failures':sum(bool(r['error']) for r in coverage),
                                            'limitations':['Company-name search is not exhaustive product search.','No candidates automatically assigned to issuer or converted to EPSS company scores.']})


if __name__=='__main__':
    main()
