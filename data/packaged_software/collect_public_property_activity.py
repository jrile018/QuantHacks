"""Keyless public property evidence. Candidates are not verified ownership or spending."""
import argparse
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import pandas as pd
from extract_infrastructure_evidence import HERE, BASE, ROOT
from extract_company_metrics import HTML_TAG, HIDDEN_BLOCK, next_day

OUT=BASE/'property_activity'
START='2022-01-01'
OBSERVED=datetime.now(timezone.utc).date().isoformat()
END=OBSERVED
SJ='https://geo.sanjoseca.gov/server/rest/services/PLN/PLN_PermitsAndComplaints/MapServer'
DEQ='https://www.deq.virginia.gov/news-info/shortcuts/permits/air/issued-air-permits-for-data-centers'
PROPERTY=re.compile(r'\b(?:data\s*cent(?:er|re)s?|real estate|real property|land|buildings?|campus|facilit(?:y|ies)|warehouse|ground lease|colocation)\b',re.I)
ACTION=re.compile(r'\b(?:purchas\w*|acquir\w*|construction|construct\w*|develop\w*|expan\w*|lease\w*|sold|sale|open\w*|permit\w*)\b',re.I)


def write_csv(name,rows,columns=None):
    pd.DataFrame(rows,columns=columns).to_csv(OUT/name,index=False)


def alias(name):
    name=re.sub(r'\s+(?:Class [AB].*|Common Stock.*)$','',name,flags=re.I)
    name=re.sub(r'[,\s]+(?:incorporated|inc\.?|corporation|corp\.?|limited|ltd\.?|plc|n\.v\.|llc)\s*$','',name,flags=re.I)
    name=' '.join(name.upper().split())
    return name if len(name)>=5 else ''


def sql_quote(text):
    return "'"+text.replace("'","''")+"'"


def fetch(url,params=None):
    if params: url+='?'+urllib.parse.urlencode(params)
    key=hashlib.sha256(url.encode()).hexdigest()
    path=OUT/'raw'/f'{key}.bin'
    meta=path.with_suffix('.json')
    if path.exists():
        body=path.read_bytes()
        saved=json.loads(meta.read_text())
        if hashlib.sha256(body).hexdigest()!=saved['sha256']: raise ValueError('Cached public source hash mismatch')
    else:
        req=urllib.request.Request(url,headers={'User-Agent':'public-property-research/1.0','Accept':'application/json,text/html'})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req,timeout=45) as response: body=response.read()
                break
            except Exception:
                if attempt==2: raise
                time.sleep(2*(attempt+1))
        saved={'source_url':url,'fetched_at_utc':datetime.now(timezone.utc).isoformat(),
               'sha256':hashlib.sha256(body).hexdigest()}
        path.write_bytes(body); meta.write_text(json.dumps(saved,indent=2),encoding='utf-8')
        time.sleep(.3)
    return body,{**saved,'local_path':path.relative_to(ROOT).as_posix()}


def json_fetch(url,params=None):
    body,meta=fetch(url,params)
    data=json.loads(body)
    if isinstance(data,dict) and 'error' in data: raise ValueError(str(data['error']))
    return data,meta


def target_matches(value,companies):
    value=' '.join(str(value).upper().split())
    return [c for c in companies if c['search_alias'] and re.search(r'(?<!\w)'+re.escape(c['search_alias'])+r'(?!\w)',value)]


def sec_candidates(companies):
    index=pd.read_csv(BASE/'sec/filings_index.csv',dtype=str).fillna('')
    index=index[index.form.isin(['10-K','10-Q','8-K']) & index.filing_date.ge(START) & index.filing_date.le(END)]
    known={c['ticker']:c for c in companies}; rows=[]; missing=[]; scanned=0
    for i,r in enumerate(index.to_dict('records'),1):
        path=ROOT/r['local_path']
        if not path.exists(): missing.append(r); continue
        raw=path.read_bytes(); scanned+=1
        if i%1500==0: print(f'SEC property search: {i}/{len(index)} documents',flush=True)
        # Cheap prefilter; the cleaned source is authoritative for the extracted context.
        if not re.search(rb'data\s*cent[er]{2}|real\s+(?:estate|property)|ground\s+lease|\bland\b|\bcampus\b',raw,re.I): continue
        text=' '.join(html.unescape(HTML_TAG.sub(' ',HIDDEN_BLOCK.sub(' ',raw.decode('utf-8',errors='replace')))).split())
        digest=hashlib.sha256(raw).hexdigest()
        positions=[]
        for match in PROPERTY.finditer(text):
            context=text[max(0,match.start()-300):match.end()+600]
            if not ACTION.search(context): continue
            if positions and match.start()-positions[-1]<450: continue
            positions.append(match.start())
            company=known[r['ticker']]
            datacenter=bool(re.search(r'data\s*cent(?:er|re)|colocation',context,re.I))
            rows.append({'cik':company['cik'],'ticker':r['ticker'],'name':company['name'],
                         'filing_date':r['filing_date'],'available_date_conservative':next_day(r['filing_date']),
                         'event_type_candidate':'data_center_activity' if datacenter else 'property_activity',
                         'form':r['form'],'accession':r['accession'],'document_role':r['document_role'],
                         'source_url':f"https://www.sec.gov/Archives/edgar/data/{int(r['cik'])}/{r['accession'].replace('-','')}/{path.name}",
                         'local_path':r['local_path'],'source_sha256':digest,
                         'context':context,'status':'narrative_candidate_subject_event_and_amount_require_review',
                         'confirmed_purchase_price_usd':'','record_id':hashlib.sha256((r['local_path']+'|'+str(match.start())).encode()).hexdigest()[:24]})
    write_csv('sec_property_activity_candidates.csv',rows)
    write_csv('sec_unavailable_documents.csv',missing,list(index.columns))
    return {'indexed_documents_in_scope':len(index),'cached_documents_scanned':scanned,'unavailable_documents':len(missing),
            'candidate_records':len(rows),'candidate_companies':len({r['ticker'] for r in rows}),
            'data_center_candidate_records':sum(r['event_type_candidate']=='data_center_activity' for r in rows)}


def san_jose(companies):
    rows=[]; runs=[]
    for layer in [7,8,9,23]:
        metadata,_=json_fetch(f'{SJ}/{layer}',{'f':'json'})
        fields=[f['name'] for f in metadata['fields'] if f['type']=='esriFieldTypeString' and re.search('APPLICANT|OWNER|WORKDESC|DESCRIPTION|NOTES|SUBDESC',f['name'],re.I)]
        if not fields: raise ValueError('No searchable permit fields')
        terms=[c['search_alias'] for c in companies if c['search_alias']]+['DATA CENTER','DATACENTER','DATA CENTRE','COLOCATION']
        conditions=[f'UPPER({field}) LIKE {sql_quote("%"+term+"%")}' for field in fields for term in terms]
        seen=set(); total=0
        for start in range(0,len(conditions),80):
            where=' OR '.join(conditions[start:start+80]); offset=0
            while True:
                data,meta=json_fetch(f'{SJ}/{layer}/query',{'where':where,'outFields':'*','returnGeometry':'false','f':'json',
                                                          'resultOffset':offset,'resultRecordCount':1000,'orderByFields':'OBJECTID'})
                features=data.get('features',[])
                for feature in features:
                    a=feature['attributes']; oid=a['OBJECTID']
                    if oid in seen: continue
                    seen.add(oid); total+=1
                    matches=target_matches(' '.join(str(a.get(f) or '') for f in fields),companies)
                    dc=bool(re.search(r'data\s*cent(?:er|re)|colocation',' '.join(str(v) for v in a.values()),re.I))
                    for c in matches or [{'cik':'','ticker':'','name':''}]:
                        rows.append({**{k:c[k] for k in ['cik','ticker','name']},'layer':layer,'layer_name':metadata['name'],
                                     'permit_object_id':oid,'is_data_center_text':dc,'attributes_json':json.dumps(a,ensure_ascii=False),
                                     'source_url':meta['source_url'],'local_path':meta['local_path'],'source_sha256':meta['sha256'],
                                     'observed_date':OBSERVED,'available_date_conservative':next_day(OBSERVED),
                                     'status':'permit_snapshot_name_match_requires_review' if matches else 'unattributed_data_center_candidate',
                                     'declared_permit_value_not_spending':a.get('PERMITVALUE',''),
                                     'permit_issue_date':datetime.fromtimestamp(a['ISSUEDATEUTC']/1000,timezone.utc).date().isoformat() if a.get('ISSUEDATEUTC') else '',
                                     'confirmed_purchase_price_usd':''})
                if not data.get('exceededTransferLimit'): break
                if not features: raise ValueError('Pagination returned no records with transfer limit set')
                offset+=len(features)
        runs.append({'layer':layer,'name':metadata['name'],'distinct_features':total,'query_complete':True})
        print('San Jose permit layer',layer,':',total,'features',flush=True)
    write_csv('san_jose_permit_candidates.csv',rows)
    return {'layers':runs,'candidate_rows':len(rows),'matched_target_companies':len({r['ticker'] for r in rows if r['ticker']}),
            'history_limit':'Current active/expired/planning snapshots; not a complete historical permit database or historical availability archive.'}


def acris(companies):
    # Only parent-name searches in this pass. Subsidiary names require an ownership/date review first.
    parties=[]; docs=set(); runs=[]
    for start in range(0,len(companies),20):
        group=companies[start:start+20]
        # Prefixes avoid pathological substring hits (AWARE inside DELAWARE).
        # This is explicitly a parent-prefix search, not exhaustive subsidiary discovery.
        terms=[f'(upper(name) = {sql_quote(c["search_alias"])} OR upper(name) like {sql_quote(c["search_alias"]+" %")} OR upper(name) like {sql_quote(c["search_alias"]+",%")})' for c in group if c['search_alias']]
        if not terms: continue
        offset=0
        while True:
            data,meta=json_fetch('https://data.cityofnewyork.us/resource/636b-3b5g.json',{'$where':' OR '.join(terms),'$limit':1000,'$offset':offset,'$order':'document_id,name,party_type'})
            for p in data:
                matches=target_matches(p.get('name',''),group)
                for c in matches:
                    parties.append({**{k:c[k] for k in ['cik','ticker','name']},**p,'matched_legal_party_name':p.get('name',''),
                                    'source_url':meta['source_url'],'local_path':meta['local_path'],'source_sha256':meta['sha256']})
                    docs.add(p['document_id'])
            offset+=len(data)
            if len(data)<1000: break
        runs.append({'company_group_start':start,'returned_party_records':offset,'pagination_complete':True})
        print('ACRIS company search:',min(start+20,len(companies)),'/',len(companies),flush=True)
    masters=[]; legals=[]
    doclist=sorted(docs)
    for start in range(0,len(doclist),70):
        where='document_id in ('+','.join(sql_quote(x) for x in doclist[start:start+70])+')'
        data,meta=json_fetch('https://data.cityofnewyork.us/resource/bnx9-e6tj.json',{'$where':where+f" AND recorded_datetime >= '{START}T00:00:00' AND recorded_datetime < '{END}T23:59:59'",'$limit':1000})
        for r in data: masters.append({**r,'master_source_url':meta['source_url'],'master_local_path':meta['local_path'],'master_source_sha256':meta['sha256']})
        ids=[r['document_id'] for r in data]
        if ids:
            where='document_id in ('+','.join(sql_quote(x) for x in ids)+')'
            data,meta=json_fetch('https://data.cityofnewyork.us/resource/8h5j-fqxa.json',{'$where':where,'$limit':5000})
            if len(data)==5000: raise ValueError('ACRIS parcel response requires further pagination')
            for r in data: legals.append({**r,'source_url':meta['source_url'],'local_path':meta['local_path'],'source_sha256':meta['sha256']})
    active={r['document_id']:r for r in masters}; joined=[]
    for p in parties:
        if p['document_id'] not in active: continue
        m=active[p['document_id']]
        joined.append({**p,**m,'observed_date':OBSERVED,'available_date_conservative':next_day(OBSERVED),
                       'status':'recorded_document_candidate_party_role_transaction_type_and_parent_link_require_review',
                       'confirmed_purchase_price_usd':'','data_center_use_confirmed':False})
    write_csv('nyc_acris_recorded_document_candidates_since_2022.csv',joined)
    write_csv('nyc_acris_parcel_records.csv',legals)
    write_csv('nyc_acris_parent_name_search_log.csv',runs)
    return {'all_date_parent_name_party_matches':len(parties),'since_2022_document_party_candidates':len(joined),
            'recorded_documents_since_2022':len(masters),'parcel_rows':len(legals),
            'matched_target_companies':len({r['ticker'] for r in joined}),
            'limit':'NYC parent-name prefixes only; subsidiary buyers, embedded names and other jurisdictions not comprehensively searched. Current extract is not historical availability proof.'}


class TableReader(HTMLParser):
    def __init__(self): super().__init__(); self.rows=[]; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr': self.row=[]
        if tag in ['td','th'] and self.row is not None: self.cell=[]
    def handle_data(self,data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ['td','th'] and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split())); self.cell=None
        if tag=='tr' and self.row is not None:
            if self.row: self.rows.append(self.row)
            self.row=None


def deed_support(companies):
    codes,meta=json_fetch('https://data.cityofnewyork.us/resource/7isb-wh4c.json',{'$limit':1000})
    write_csv('nyc_document_control_codes.csv',[{**r,**meta} for r in codes])
    parties,party_meta=json_fetch('https://data.cityofnewyork.us/resource/636b-3b5g.json',
                                 {'$where':"document_id='2025121600382004'",'$limit':1000})
    write_csv('reviewed_deed_supporting_parties.csv',[{**r,**party_meta} for r in parties])
    return {'document_control_code_rows':len(codes),'supporting_parties_for_TTWO_named_deed':len(parties),
            'purchase_price_or_data_center_use_confirmed':False}


def deq(companies):
    body,meta=fetch(DEQ); parser=TableReader(); parser.feed(body.decode('utf-8',errors='replace'))
    rows=[]
    for cells in parser.rows:
        if len(cells)<5 or 'Permit Issuance Date' in ' '.join(cells): continue
        try: issued=pd.Timestamp(cells[2]).date().isoformat()
        except (ValueError,TypeError): continue
        matches=target_matches(cells[0],companies)
        rows.append({'site_name':cells[0],'registration_application_number':cells[1],'permit_issuance_date':issued,
                     'program_type':cells[3],'city_county':cells[4],'regional_office':cells[5] if len(cells)>5 else '',
                     'candidate_parent_tickers':';'.join(c['ticker'] for c in matches),
                     'observed_date':OBSERVED,'available_date_conservative':next_day(OBSERVED),
                     **meta,'status':'public_data_center_permit_inventory_operator_parent_link_requires_review',
                     'purchase_price_usd':''})
    if not rows: raise ValueError('No permit rows parsed; page format or access must be reviewed')
    write_csv('virginia_data_center_air_permits_all_dates.csv',rows)
    recent=[r for r in rows if START<=r['permit_issuance_date']<=END]
    write_csv('virginia_data_center_air_permits_since_2022.csv',recent)
    return {'inventory_rows_all_dates':len(rows),'permit_rows_since_2022':len(recent),'target_parent_name_matches':sum(bool(r['candidate_parent_tickers']) for r in recent),
            'limit':'Permits are not property purchases, operating dates or independent proof of parent ownership.'}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--source',choices=['sec','public','support','all'],default='all'); args=ap.parse_args()
    OUT.mkdir(exist_ok=True); (OUT/'raw').mkdir(exist_ok=True)
    companies=pd.read_csv(HERE/'packaged_software_companies.csv',dtype=str).to_dict('records')
    for c in companies: c['search_alias']=alias(c['name'])
    write_csv('parent_search_aliases.csv',companies)
    manifest_path=OUT/'collection_manifest.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    allowed={'sec':{'sec'},'public':{'san_jose','nyc_acris','virginia_deq'},'support':{'nyc_deed_support'},'all':{'sec','san_jose','nyc_acris','virginia_deq','nyc_deed_support'}}[args.source]
    for name,fn in [('sec',sec_candidates),('san_jose',san_jose),('nyc_acris',acris),('virginia_deq',deq),('nyc_deed_support',deed_support)]:
        if name not in allowed: continue
        try: manifest[name]={'status':'collected',**fn(companies)}
        except Exception as exc: manifest[name]={'status':'failed','error':f'{type(exc).__name__}: {exc}'}
        manifest.update({'target_companies':168,'period_start':START,'observed_date':OBSERVED,'api_keys_used':False})
        (OUT/(name+'_collection_result.json')).write_text(json.dumps(manifest[name],indent=2),encoding='utf-8')
        for result_path in OUT.glob('*_collection_result.json'):
            manifest[result_path.name.replace('_collection_result.json','')]=json.loads(result_path.read_text())
        manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__': main()
