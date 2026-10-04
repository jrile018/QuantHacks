"""Resumable official REIT discovery, validation and historical document batches."""
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import csv
import json
from pathlib import Path
import re
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.reit_acquisition import FetchBroker, RunState, AcquisitionBlocked, CacheCorrupt
from src.reit_discovery import reitwatch_candidates, resolve_candidates, filing_eligibility_evidence
from src.reit_universe import parse_sec_exchange_map, parse_nareit_ticker_table, build_universe
from src.reit_inventory import build_inventory
from src.document_ocr import _native_pdf_texts
from scripts.collect_reit_financials import document_text, select_exhibits


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    tmp.replace(path)


def retained_candidates(documents,exchange):
    """Seed known retained issuer CIKs; current listings remain candidates."""
    by_cik={}
    for item in exchange:
        by_cik.setdefault(item['cik'],[]).append(item)
    rows=[]
    for doc in documents:
        cik=str(doc.get('cik','')).zfill(10)
        if not cik.isdigit() or int(cik)==0:
            continue
        path=Path(doc['source_path'])
        if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=doc['sha256']:
            raise CacheCorrupt('Retained discovery document changed')
        for listing in by_cik.get(cik,[]):
            rows.append(dict(listing,security_id=cik+':'+listing['ticker']+':common_candidate',
                source_url=doc['url'],source_path=str(path),source_sha256=doc['sha256'],
                discovery_status='candidate_only',resolution='retained_issuer_cik_current_listing',
                limitation='Retained issuer identity seeds discovery; no REIT status or historical ticker proof.'))
    return rows


def exhibit_document(filing,exhibit):
    doc={**filing,**exhibit,'document_role':'exhibit'}
    for key in ('source_path','text_path','sha256','text_sha256'):
        doc.pop(key,None)
    return doc


def discovery(output):
    sources=load(output/'discovery_source_receipts.json')['sources']
    integrity_path=output/'discovery_integrity.json'
    integrity=load(integrity_path) if integrity_path.exists() else {}
    for source in sources:
        raw=Path(source['source_path']).read_bytes()
        if sha256(raw).hexdigest()!=source['sha256']:
            raise CacheCorrupt('Discovery source changed from its HTTP receipt')
    sec=next(s for s in sources if s['source_id']=='sec-exchange-map')
    exchange=parse_sec_exchange_map(load(sec['source_path']))
    candidates=[]
    for source in sources:
        if source['source_id']=='nareit-ticker-table':
            candidates+=parse_nareit_ticker_table(Path(source['source_path']).read_bytes(),retrieved_at=source['retrieved_at'])
        elif source['source_id'].startswith('reitwatch-'):
            text_path=output/'discovery_text'/(source['sha256']+'.json')
            if not text_path.exists():
                texts=_native_pdf_texts(Path(source['source_path']))
                save(text_path,{'source_sha256':source['sha256'],'source_url':source['url'],
                                'pages':[{'number':i+1,'text':text or ''} for i,text in enumerate(texts)]})
            extracted=load(text_path)
            text_hash=sha256(text_path.read_bytes()).hexdigest()
            if extracted['source_sha256']!=source['sha256'] or extracted.get('source_url')!=source['url']:
                raise CacheCorrupt('Discovery text source hash mismatch')
            if source['sha256'] in integrity and integrity[source['sha256']]['text_sha256']!=text_hash:
                raise CacheCorrupt('Cached discovery text was modified')
            if source['sha256'] not in integrity:
                fresh=_native_pdf_texts(Path(source['source_path']))
                if extracted['pages']!=[{'number':i+1,'text':text or ''} for i,text in enumerate(fresh)]:
                    raise CacheCorrupt('Unbound discovery cache differs from retained native text')
            integrity[source['sha256']]={'source_sha256':source['sha256'],'source_url':source['url'],'text_sha256':text_hash}
            candidates+=reitwatch_candidates(extracted['pages'],source_url=source['url'],source_sha256=source['sha256'],retrieved_at=source['retrieved_at'])
    candidates=resolve_candidates(candidates,exchange)
    for manifest_path in (
        ROOT/'data/processed/reit_financials/20261003-meaning-pilot/manifest.json',
        ROOT/'data/processed/reit_filing_pilot/realty_income_2025_meaning_v2/manifest.json',
    ):
        if manifest_path.exists():
            candidates+=retained_candidates(load(manifest_path).get('documents',[]),exchange)
    sectors=ROOT/'data/processed/tiger_8k_company_sectors.csv'
    if sectors.exists():
        by_cik={r['cik']:r for r in exchange}
        with sectors.open(encoding='utf-8-sig',newline='') as stream:
            for row in csv.DictReader(stream):
                if str(row.get('sic'))!='6798':
                    continue
                cik=str(row['cik']).zfill(10)
                listings=[r for r in exchange if r['cik']==cik]
                if not listings:
                    candidates.append({'cik':cik,'ticker':row.get('tickers',''),'name':row.get('company_name',''),
                                       'source_path':str(sectors),'discovery_status':'candidate_only','resolution':'local_sic_candidate'})
                for item in listings:
                    candidates.append(dict(item,security_id=cik+':'+item['ticker']+':common_candidate',
                                           source_path=str(sectors),discovery_status='candidate_only',resolution='local_sic_candidate'))
    # Preserve every source assertion; build_universe deduplicates security identities.
    save(output/'discovery_candidates.json',{'candidates':candidates,'coverage':{'assertions':len(candidates),
         'resolved_ciks':len({r['cik'] for r in candidates if r.get('cik')}),
         'unresolved_names':sorted({r['name'] for r in candidates if not r.get('cik')}),
         'complete_historical_universe':False}})
    save(integrity_path,integrity)
    return candidates


def retained_results(queue):
    results=[]
    for task in queue.summary()['tasks']:
        if task['status']!='complete':
            continue
        row=json.loads(task['result'])
        path=Path(row.get('source_path') or row['path'])
        if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=row.get('sha256'):
            raise CacheCorrupt('Completed task raw source is missing or modified')
        if row.get('text_path'):
            text_path=Path(row['text_path'])
            extracted=load(text_path)
            if extracted.get('sha256')!=row['sha256'] or extracted.get('source_url')!=row['url'] or extracted.get('accession')!=row['accession']:
                raise CacheCorrupt('Completed task extracted text identity mismatch')
            digest=sha256(text_path.read_bytes()).hexdigest()
            if row.get('text_sha256') and digest!=row['text_sha256']:
                raise CacheCorrupt('Completed task extracted text was modified')
            if not row.get('text_sha256'):
                if extracted!=document_text(path,row['url'],row['accession']):
                    raise CacheCorrupt('Legacy extraction differs from fresh retained native text')
                row['text_sha256']=digest
        results.append(row)
    return results


def annual_tasks(inventory,ciks):
    tasks=[]
    for cik in ciks:
        annual=[r for r in inventory['selected'] if r['cik']==cik and r['form']=='10-K']
        if annual:
            filing=max(annual,key=lambda r:(r['filing_date'],r['accession']))
            tasks.append({'task_id':'annual-'+cik,'url':filing['url'],'filing':filing})
    return tasks


def fetch_tasks(tasks,queue,broker,*,limit=None,callback=None):
    for task in tasks:
        queue.enqueue(task['task_id'],task)
    owner=uuid4().hex
    completed=0
    while limit is None or completed<limit:
        task=queue.claim(owner,lease_seconds=120)
        if task is None:
            break
        payload=task['payload']
        try:
            result=broker.fetch(payload['url'])
            value={**payload,**result}
            if callback:
                value=callback(value)
            queue.finish(task['task_id'],owner,value)
            completed+=1
            if completed%10==0:
                print(json.dumps({'completed':completed,'last':payload['task_id']}),flush=True)
        except Exception as exc:
            blocked=isinstance(exc,(AcquisitionBlocked,CacheCorrupt))
            queue.fail(task['task_id'],owner,type(exc).__name__+': '+str(exc),blocked=blocked)
            print(json.dumps({'task':payload['task_id'],'error':type(exc).__name__+': '+str(exc)}),flush=True)
            completed+=1
            if blocked:
                break
    return retained_results(queue)


def metadata_stage(candidates,output,broker,limit):
    ciks=sorted({r['cik'] for r in candidates if r.get('cik')})
    queue=RunState(output/'metadata_tasks.sqlite')
    def check(value):
        payload=load(value['path'])
        if str(payload.get('cik','')).zfill(10)!=value['cik']:
            raise ValueError('SEC submissions CIK mismatch')
        return value
    rows=fetch_tasks([{'task_id':'submissions-'+cik,'cik':cik,'url':f'https://data.sec.gov/submissions/CIK{cik}.json'} for cik in ciks],queue,broker,limit=limit,callback=check)
    metadata=[]
    history_tasks=[]
    for row in rows:
        data=load(row['path'])
        metadata.append({'cik':row['cik'],'submissions':data,'source_url':row['url'],'source_path':row['path'],
                         'source_sha256':row['sha256'],'retrieved_at':row['receipt']['retrieved_at'],'historical_pages':[]})
        for ref in data.get('filings',{}).get('files',[]):
            if ref.get('filingTo','')>='2022-01-01':
                name=ref['name']
                if '/' in name or '\\' in name or '..' in name or not name.startswith('CIK'+row['cik']+'-submissions-'):
                    raise ValueError('Unsafe historical submissions filename')
                history_tasks.append({'task_id':'history-'+name,'cik':row['cik'],'name':name,'url':'https://data.sec.gov/submissions/'+name})
    pages=fetch_tasks(history_tasks,RunState(output/'historical_metadata_tasks.sqlite'),broker,limit=limit)
    by_cik={r['cik']:r for r in metadata}
    for row in pages:
        if row['cik'] in by_cik:
            by_cik[row['cik']]['historical_pages'].append({'name':row['name'],'data':load(row['path']),
                'source_url':row['url'],'source_path':row['path'],'source_sha256':row['sha256'],'retrieved_at':row['receipt']['retrieved_at']})
    save(output/'metadata.json',{'metadata':metadata,'scope':'2024 onward plus available 2022/2023 opening context; older references are explicit gaps'})
    return metadata


def store_document(value,collection):
    filing=value['filing']
    filename=filing.get('filename') or filing['primaryDocument']
    path=collection/'cache'/filing['cik']/filing['accession']/filename
    if path.resolve().is_relative_to(collection.resolve()) is False:
        raise ValueError('Document path escaped collection')
    path.parent.mkdir(parents=True,exist_ok=True)
    body=Path(value['path']).read_bytes()
    if sha256(body).hexdigest()!=value['sha256']:
        raise CacheCorrupt('Broker source changed before collection copy')
    if path.exists() and path.read_bytes()!=body:
        raise CacheCorrupt('Frozen collection document conflicts with new bytes')
    path.write_bytes(body)
    text_path=collection/'text'/filing['cik']/filing['accession']/(filename+'.json')
    text=document_text(path,filing['url'],filing['accession'])
    save(text_path,text)
    metadata=dict(filing)
    if 'size' in metadata:
        original_size=metadata.pop('size')
        sec_submissions=any(re.fullmatch(r'https://data\.sec\.gov/submissions/CIK\d{10}(?:-submissions-\d+)?\.json',source.get('url',''))
                            and source.get('source_sha256') for source in metadata.get('metadata_sources',[]))
        size_field='filing_metadata_size' if sec_submissions else 'legacy_metadata_size'
        if size_field in metadata and metadata[size_field]!=original_size:
            raise ValueError('Conflicting original size metadata')
        metadata[size_field]=original_size
        metadata['size_metadata_provenance']={'original_field':'size','scope':'sec_submissions_filing_metadata' if sec_submissions else 'legacy_metadata_unknown_scope'}
    return {**metadata,'source_byte_count':len(body),'filename':filename,'filed':filing['filing_date'],'reportDate':filing.get('report_date'),
        'acceptanceDateTime':filing.get('accepted_at'),'source_path':str(path.resolve()),'text_path':str(text_path.resolve()),
        'sha256':value['sha256'],'source_method':text['source_method'],'page_count':text['page_count'],
        'text_sha256':sha256(text_path.read_bytes()).hexdigest(),
        'content_type':value['receipt'].get('content_type'),'retrieved_at':value['receipt']['retrieved_at'],
        'first_public_at':None,'document_role':filing.get('document_role','primary')}


def validate_stage(candidates,metadata,output,broker,limit):
    collection=output/'collection'
    inventory=build_inventory({'ciks':[r['cik'] for r in metadata],'start_date':'2024-01-01','end_date':'2026-10-03'},metadata)
    tasks=annual_tasks(inventory,[m['cik'] for m in metadata])
    docs=fetch_tasks(tasks,RunState(output/'validation_tasks.sqlite'),broker,limit=limit,callback=lambda v:store_document(v,collection))
    allowed={r['url'] for r in tasks}
    docs=[r for r in docs if r['url'] in allowed]
    candidates=list({(r.get('cik'),r.get('ticker'),r.get('security_id')):r for r in candidates}.values())
    by_cik={m['cik']:m for m in metadata}
    proof=[]
    for doc in docs:
        for candidate in candidates:
            if candidate.get('cik')!=doc['cik']:
                continue
            enriched=dict(doc,ticker=candidate['ticker'],security_id=candidate.get('security_id',doc['cik']+':'+candidate['ticker']+':common_candidate'),
                          issuer=by_cik[doc['cik']]['submissions']['name'])
            proof+=filing_eligibility_evidence(enriched,Path(doc['source_path']).read_text(encoding='utf-8',errors='replace'))
    # Repeated discovery assertions do not create duplicate proof rows.
    proof=list({sha256(json.dumps(r,sort_keys=True).encode()).hexdigest():r for r in proof}.values())
    universe=build_universe(candidates,proof,datetime.now(timezone.utc).isoformat())
    save(output/'universe.json',universe)
    save(output/'universe_evidence.json',{'evidence':proof})
    companies=[{'cik':m['cik'],'company_name':m['submissions']['name'],'coverage':{'companyfacts':'not_attempted'}} for m in metadata]
    save(collection/'manifest.json',{'run_status':'partial','companies':companies,'documents':docs,
         'scope':'Latest annual reports for discovery validation; historical collection is separate',
         'coverage':universe['coverage']})
    print(json.dumps({'validated':len(universe['validated']),'candidates':len(universe['candidates']),'documents':len(docs)}),flush=True)
    return universe


def history_stage(metadata,universe,output,broker,limit,*,requested=None,batch_size=10,batch_index=1,max_exhibits=8):
    ciks=sorted(set(requested or [r['cik'] for r in universe['validated']]))
    if requested is None:
        ciks=ciks[(batch_index-1)*batch_size:batch_index*batch_size]
    if not ciks:
        raise ValueError('No issuers in this history batch')
    if set(ciks)-{r['cik'] for r in metadata}:
        raise ValueError('Requested history issuer lacks retained submissions')
    scope={'ciks':ciks,'start_date':'2024-01-01','end_date':'2026-10-03','opening_context':True}
    inventory=build_inventory(scope,metadata)
    batch_id='batch-'+str(batch_index)+'-'+sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()[:12]
    batch_dir=output/'batches'/batch_id
    batch_dir.mkdir(parents=True,exist_ok=True)
    save(batch_dir/'inventory.json',inventory)
    collection=output/'collection'
    queue=RunState(batch_dir/'document_tasks.sqlite')
    tasks=[{'task_id':'filing-'+sha256(f['url'].encode()).hexdigest(),'url':f['url'],'filing':f} for f in inventory['selected']]
    docs=fetch_tasks(tasks,queue,broker,limit=limit,callback=lambda v:store_document(v,collection))
    # File lists are retained even when only a bounded set of relevant exhibits
    # is selected. Omitted agreements remain visible for later targeted follow-up.
    index_tasks=[]
    for doc in docs:
        base=doc['url'].rsplit('/',1)[0]+'/'
        url=base+doc['accession']+'-index.html'
        index_tasks.append({'task_id':'index-'+sha256(url.encode()).hexdigest(),'url':url,'filing':doc})
    indices=fetch_tasks(index_tasks,RunState(batch_dir/'index_tasks.sqlite'),broker,limit=limit)
    exhibit_tasks=[]
    omitted=[]
    for item in indices:
        filing=item['filing']
        exhibits=select_exhibits(filing,Path(item['path']).read_bytes(),10000)
        selected=exhibits[:max_exhibits]
        omitted.extend({'cik':filing['cik'],'accession':filing['accession'],**e,'reason':'bounded_exhibit_selection'} for e in exhibits[max_exhibits:])
        for exhibit in selected:
            doc=exhibit_document(filing,exhibit)
            exhibit_tasks.append({'task_id':'exhibit-'+sha256(doc['url'].encode()).hexdigest(),'url':doc['url'],'filing':doc})
    exhibits=fetch_tasks(exhibit_tasks,RunState(batch_dir/'exhibit_tasks.sqlite'),broker,limit=limit,callback=lambda v:store_document(v,collection))
    manifest_path=collection/'manifest.json'
    previous=load(manifest_path) if manifest_path.exists() else {'documents':[],'companies':[]}
    merged={d['url']:d for d in previous['documents']}
    merged.update({d['url']:d for d in docs+exhibits})
    stages={name:RunState(batch_dir/(name+'_tasks.sqlite')).summary()['counts'] for name in ('document','index','exhibit')}
    complete=all(not any(status!='complete' and count for status,count in counts.items()) for counts in stages.values())
    batch={'batch_id':batch_id,'scope':scope,'primary_documents':len(docs),'exhibits':len(exhibits),'omitted_exhibits':omitted,
           'completed_document_urls':sorted(d['url'] for d in docs),
           'completed_exhibit_urls':sorted(d['url'] for d in exhibits),
           'stage_counts':stages,'selected_collection_complete':complete,'history_complete':False,
           'inventory_coverage':inventory['coverage'],'limitation':'Selected filings/exhibits only; no assertion of undisclosed transfers, complete loan lineage or exhaustive historical membership.'}
    save(batch_dir/'batch_manifest.json',batch)
    previous.update(documents=list(merged.values()),run_status='partial',scope='Current validation reports plus explicit historical batches; coverage below',
                    history_batches=sorted(str(p) for p in (output/'batches').glob('*/batch_manifest.json')))
    save(manifest_path,previous)
    save(output/'broker_receipts.json',{'receipts':broker.receipts()})
    print(json.dumps({k:batch[k] for k in ('batch_id','primary_documents','exhibits','selected_collection_complete','history_complete')}),flush=True)
    return batch


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'data/processed/reit_build/20261003')
    parser.add_argument('--broker-root',type=Path,default=ROOT/'data/raw/reit_broker')
    parser.add_argument('--stage',choices=['discovery','metadata','validate','history','all'],default='discovery')
    parser.add_argument('--universe-path',type=Path,help='Fresh validated universe from the integrated build for historical batching')
    parser.add_argument('--max-tasks',type=int)
    parser.add_argument('--ciks',help='Explicit comma-separated documented cohort; otherwise take validated issuers in stable batches')
    parser.add_argument('--batch-size',type=int,default=10)
    parser.add_argument('--batch-index',type=int,default=1)
    parser.add_argument('--max-exhibits',type=int,default=8)
    args=parser.parse_args(argv)
    if args.max_tasks is not None and args.max_tasks<1:
        parser.error('--max-tasks must be positive')
    if args.batch_size<1 or args.batch_index<1 or args.max_exhibits<0:
        parser.error('Batch size/index must be positive and exhibit cap nonnegative')
    broker=FetchBroker(args.broker_root,contact_email='john.p.riley00@gmail.com')
    candidates=discovery(args.output)
    if args.stage=='discovery':
        return 0
    metadata=metadata_stage(candidates,args.output,broker,args.max_tasks) if args.stage in {'metadata','all'} else load(args.output/'metadata.json')['metadata']
    if args.stage=='metadata':
        return 0
    universe=validate_stage(candidates,metadata,args.output,broker,args.max_tasks) if args.stage in {'validate','all'} else load(args.universe_path or args.output/'universe.json')
    if args.stage in {'history','all'}:
        requested=[c.strip().zfill(10) for c in args.ciks.split(',')] if args.ciks else None
        history_stage(metadata,universe,args.output,broker,args.max_tasks,requested=requested,
                      batch_size=args.batch_size,batch_index=args.batch_index,max_exhibits=args.max_exhibits)
    save(args.output/'broker_receipts.json',{'receipts':broker.receipts()})
    return 0


if __name__=='__main__':
    raise SystemExit(main())
