"""Read public Companies House account filings for reviewed registry numbers.

Reads COMPANIES_HOUSE_API_KEY from .env. Never prints credentials or signed URLs.
Downloaded subsidiary accounts remain separate from consolidated parent metrics.
"""
import base64
import hashlib
import json
import re
import time
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
import pandas as pd
from sec_common import env_value
from extract_infrastructure_evidence import HERE, OUT


class StripAuthorizationRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(newurl).scheme!='https':
            raise ValueError('Refusing non-HTTPS document redirect')
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if redirected is not None:
            redirected.remove_header('Authorization')
        return redirected


def main():
    registry=json.loads((HERE/'infrastructure_review_registry.json').read_text())['registry_matches']
    key=env_value('COMPANIES_HOUSE_API_KEY')
    target=OUT/'companies_house'; target.mkdir(exist_ok=True)
    if not key:
        result={'status':'missing_COMPANIES_HOUSE_API_KEY','requests_made':0,'registry_candidates':len(registry),
                'accounts_downloaded':0,'numeric_metrics_extracted':0}
        (target/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2)); return
    opener=urllib.request.build_opener(StripAuthorizationRedirect())
    token=base64.b64encode((key+':').encode()).decode()
    requests=0; records=[]; errors=[]
    def get(url,accept='application/json'):
        nonlocal requests
        if urlparse(url).hostname not in {'api.company-information.service.gov.uk','document-api.company-information.service.gov.uk'}:
            raise ValueError('Unexpected API host')
        time.sleep(.6)
        requests+=1
        req=urllib.request.Request(url,headers={'Authorization':'Basic '+token,'Accept':accept,'User-Agent':'QuantHacks public accounts research'})
        with opener.open(req,timeout=60) as response:
            return response.read(32*1024*1024)
    norm=lambda s:re.sub(r'[^a-z0-9]','',s.lower())
    for entity in registry:
        number=entity['company_number']; folder=target/number; folder.mkdir(exist_ok=True)
        try:
            profile_file=folder/'profile.json'
            profile=json.loads(profile_file.read_text()) if profile_file.exists() else json.loads(get(f'https://api.company-information.service.gov.uk/company/{number}'))
            if norm(profile['company_name'])!=norm(entity['subsidiary_name']): raise ValueError('Registry legal name mismatch')
            profile_file.write_text(json.dumps(profile),encoding='utf-8')
            start=0
            while True:
                page_file=folder/f'accounts_{start}.json'
                page=json.loads(page_file.read_text()) if page_file.exists() else json.loads(get(f'https://api.company-information.service.gov.uk/company/{number}/filing-history?category=accounts&items_per_page=100&start_index={start}'))
                page_file.write_text(json.dumps(page),encoding='utf-8')
                items=page.get('items',[])
                for item in items:
                    if not '2022-01-01'<=item['date']<='2026-10-03': continue
                    metadata_url=item.get('links',{}).get('document_metadata')
                    if not metadata_url: continue
                    doc_id=metadata_url.rsplit('/',1)[-1]
                    pdf=folder/(doc_id+'.pdf')
                    content=pdf.read_bytes() if pdf.exists() else get(metadata_url+'/content','application/pdf')
                    if not content.startswith(b'%PDF-'): raise ValueError('Expected PDF account document')
                    pdf.write_bytes(content)
                    records.append({**entity,'filed_date':item['date'],'document_id':doc_id,'account_description':item.get('description',''),
                                    'period_end':item.get('description_values',{}).get('made_up_date',''),
                                    'document_source_url':metadata_url+'/content','local_path':str(pdf),
                                    'sha256':hashlib.sha256(content).hexdigest(),'status':'downloaded_subsidiary_accounts_numeric_review_pending'})
                if start+len(items)>=page.get('total_count',0): break
                if not items: raise ValueError('Empty filing-history page before total_count')
                start+=len(items)
        except Exception as exc:
            errors.append({'company_number':number,'error':type(exc).__name__,'http_status':getattr(exc,'code',None)})
    pd.DataFrame(records).to_csv(target/'account_documents.csv',index=False)
    result={'status':'collection_completed_with_review_pending' if not errors else 'collection_incomplete',
            'requests_made':requests,'accounts_downloaded':len(records),'numeric_metrics_extracted':0,'errors':errors}
    (target/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
