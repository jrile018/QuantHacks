"""Frozen Databento pilot acquisition with durable reservations and no POST retries.

Metadata is free. --submit authorizes ONLY the seven frozen requests. Evidence
is written before each POST; an interrupted/unknown POST is never repeated.
Recover it using --status and provider job details matched to the frozen scope.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sys
import requests

PROJECT = Path(__file__).resolve().parents[2]
API = 'https://hist.databento.com/v0/'
EVIDENCE = PROJECT / 'data/raw/databento/multi-market-pilot'
SCOPE_FIELDS = ('dataset','schema','symbols','stype_in','start','end')
JOB_FIELDS = ('id','state','cost_usd','record_count','billed_size','actual_size','progress','ts_received','ts_process_done','ts_expiration')


def frozen_scopes():
    common={'start':'2024-01-01','end':'2026-01-01'}
    futures={'dataset':'GLBX.MDP3','symbols':'ES.v.0,MES.v.0,ZN.v.0,CL.v.0,GC.v.0','stype_in':'continuous',**common}
    return [dict(futures,schema=s) for s in ('statistics','definition','ohlcv-1d','bbo-1m')] + [
        {'dataset':'EQUS.MINI','symbols':'SPY,QQQ','schema':'ohlcv-1d','stype_in':'raw_symbol',**common},
        {'dataset':'EQUS.MINI','symbols':'SPY','schema':'bbo-1m','stype_in':'raw_symbol',**common},
        {'dataset':'EQUS.SUMMARY','symbols':'SPY,QQQ','schema':'ohlcv-1d','stype_in':'raw_symbol','start':'2024-07-01','end':'2026-01-01'}]


def money(value):
    try:
        result=Decimal(str(value))
    except (InvalidOperation,ValueError):
        raise ValueError('Missing or invalid financial amount') from None
    if not result.is_finite() or result<0:
        raise ValueError('Financial amounts must be finite and nonnegative')
    return result


def commitment(row):
    amounts=[money(row[k]) for k in ('actual_cost_usd','quoted_cost_usd') if row.get(k) is not None]
    if not amounts:
        raise ValueError('Purchase/reservation has no accountable cost')
    return max(amounts)


def same_purchase(a,b):
    # Distinct provider job IDs are two charges even when their scopes match.
    if a.get('job_id') and b.get('job_id'):
        return a['job_id']==b['job_id']
    return bool(a.get('scope_sha256') and a['scope_sha256']==b.get('scope_sha256'))


def financial_rows(rows):
    merged=[]
    for row in rows:
        cost=commitment(row)
        matches=[r for r in merged if same_purchase(row,r)]
        if len(matches)>1:
            raise ValueError('Ambiguous financial identity; reconcile ledger')
        if matches:
            old=matches[0]
            old['quoted_cost_usd']=float(max(commitment(old),cost))
            for key in ('job_id','scope_sha256'):
                if row.get(key):
                    old[key]=row[key]
        else:
            merged.append({**{k:row[k] for k in ('job_id','scope_sha256') if row.get(k)},'quoted_cost_usd':float(cost)})
    return merged


def check_budget(ledger, quotes, reservations):
    pilot=sum((money(q) for q in quotes),Decimal(0))
    if pilot>Decimal('10'):
        raise ValueError('Pilot exceeds $10 hard cap')
    purchases=financial_rows(ledger['purchases'])
    before=sum((commitment(p) for p in purchases),Decimal(0))
    after=sum((commitment(p) for p in financial_rows([*purchases,*reservations])),Decimal(0))
    # Keep the aggregate floor for unresolved ledger commitments, while charging
    # increases in local actual costs exactly once for the same provider order.
    total=max(before,money(ledger.get('actual_plus_quoted_usd',before)))+(after-before)+pilot
    if total>=min(money(ledger['budget_ceiling_usd']),Decimal('250')):
        raise ValueError('Aggregate acquisition ceiling exceeded')
    return float(total)


def check_remaining_pilot(ledger,quotes,records):
    pending=[]
    pilot=Decimal(0)
    for row in quotes:
        matching=[r for r in records if r.get('scope_sha256')==row['scope_sha256']]
        relevant=[r for r in ledger['purchases'] if r.get('scope_sha256')==row['scope_sha256']
                  or any(same_purchase(r,local) for local in matching)]
        exposure=max([money(row['quoted_cost_usd'])]+[commitment(r) for r in matching+relevant])
        pilot+=exposure
        if not matching and not relevant:
            pending.append(row['quoted_cost_usd'])
    if pilot>Decimal('10'):
        raise ValueError('Pilot actual-plus-reserved cost exceeds $10 hard cap')
    return check_budget(ledger,pending,records)


def canonical(scope):
    result={k:scope[k] for k in SCOPE_FIELDS}
    result['symbols']=','.join(sorted(set(str(result['symbols']).split(','))))
    for key in ('start','end'):
        value=str(result[key])
        if len(value)==10:
            value+='T00:00:00+00:00'
        result[key]=datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
    return result


def scope_hash(scope):
    return hashlib.sha256(json.dumps(canonical(scope),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def overlaps(a,b):
    a,b=canonical(a),canonical(b)
    return (all(a[k]==b[k] for k in ('dataset','schema','stype_in'))
        and bool(set(a['symbols'].split(',')) & set(b['symbols'].split(',')))
        and a['start']<b['end'] and b['start']<a['end'])


def ensure_disjoint(scopes,existing):
    seen=list(existing)
    for scope in scopes:
        if any(overlaps(scope,row) for row in seen):
            raise ValueError('Duplicate or overlapping paid scope')
        seen.append(scope)


def write_json(path,payload,exclusive=False,expected_bytes=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    if exclusive:
        with path.open('x',encoding='utf-8') as stream:
            json.dump(payload,stream,indent=2,allow_nan=False)
            stream.write('\n')
            stream.flush()
            import os
            os.fsync(stream.fileno())
    else:
        if expected_bytes is not None:
            import uuid
            temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        else:
            temp=path.with_suffix('.tmp')
        with temp.open('w',encoding='utf-8') as stream:
            json.dump(payload,stream,indent=2,allow_nan=False)
            stream.write('\n')
            stream.flush()
            import os
            os.fsync(stream.fileno())
        if expected_bytes is not None and path.read_bytes()!=expected_bytes:
            temp.unlink()
            raise RuntimeError('concurrent ledger change detected; reconciliation aborted')
        temp.replace(path)


def reconcile_ledger(path,records):
    snapshot=path.read_bytes()
    ledger=json.loads(snapshot)
    purchases=ledger['purchases']
    incoming_ids=set()
    for record in records:
        job_id=record.get('job_id')
        if not job_id or job_id in incoming_ids:
            raise ValueError('Missing or duplicate incoming provider job ID')
        incoming_ids.add(job_id)
        request=record['request']
        digest=scope_hash(request)
        if digest!=record['scope_sha256']:
            raise ValueError('Request scope hash mismatch')
        matches=[r for r in purchases if r.get('job_id')==job_id]
        if len(matches)>1:
            raise ValueError('Duplicate provider job ID in existing ledger')
        if matches:
            row=matches[0]
            if row.get('scope_sha256') and row['scope_sha256']!=digest:
                raise ValueError('Existing job ID has conflicting scope')
        else:
            row={'kind':'batch','job_id':job_id}
            purchases.append(row)
        row.update(status=record['status'],scope_sha256=digest,request=request,
                   **{k:request[k] for k in ('dataset','schema','symbols','stype_in','start','end')})
        row['quoted_cost_usd']=float(max(money(record['quoted_cost_usd']),money(row.get('quoted_cost_usd',0))))
        actual=record.get('actual_cost_usd',record.get('job',{}).get('cost_usd'))
        if actual is not None:
            row['actual_cost_usd']=float(max(money(actual),money(row.get('actual_cost_usd',0))))
        row['provider_job']={k:record['job'][k] for k in JOB_FIELDS if k in record.get('job',{})}
    total=sum((commitment(row) for row in purchases),Decimal(0))
    if total>=min(money(ledger['budget_ceiling_usd']),Decimal('250')):
        raise ValueError('Reconciled ledger violates strict aggregate ceiling')
    ledger['actual_plus_quoted_usd']=float(total)
    ledger['last_reconciled_utc']=datetime.now(timezone.utc).isoformat()
    # Write a complete temporary file, then reread the live ledger immediately
    # before atomic replacement. A changed snapshot aborts rather than overwrites.
    write_json(path,ledger,expected_bytes=snapshot)
    return {'purchase_count':len(purchases),'merged_job_ids':sorted(incoming_ids),
            'actual_plus_quoted_usd':float(total),'ledger_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def submit_once(scope,quote,evidence,submit):
    if money(quote)>Decimal('10'):
        raise ValueError('Single request exceeds $10 pilot hard cap')
    record={'request':scope,'scope_sha256':scope_hash(scope),'quoted_cost_usd':float(money(quote)),
        'status':'submitting','attempt_started_utc':datetime.now(timezone.utc).isoformat()}
    try:
        write_json(evidence,record,exclusive=True)
    except FileExistsError:
        raise RuntimeError('Request already reserved/submitted; inspect provider jobs, never retry') from None
    try:
        job=submit(scope)
        if not isinstance(job,dict) or not job.get('id'):
            raise ValueError('No durable job ID returned')
        record.update(status=job.get('state','queued'),job_id=job['id'],job={k:job[k] for k in JOB_FIELDS if k in job})
        if job.get('cost_usd') is not None:
            record['actual_cost_usd']=float(money(job['cost_usd']))
        write_json(evidence,record)
    except Exception as error:
        record['status']='unknown'
        record['error_type']=type(error).__name__
        write_json(evidence,record)
        raise RuntimeError('Submission outcome unknown; do not retry; list/query provider jobs') from None
    return record


class HTTP:
    def __init__(self):
        for line in (PROJECT/'.env').read_text(encoding='utf-8').splitlines():
            if line.startswith('DATABENTO_API_KEY='):
                key=line.partition('=')[2].strip().strip(chr(34)+chr(39))
                break
        else:
            raise RuntimeError('Project API credential missing')
        self.session=requests.Session()
        self.session.auth=(key,'')
    def get(self,method,params):
        response=self.session.get(API+method,params=params,timeout=(20,90))
        if response.status_code!=200:
            raise RuntimeError(f'{method}: HTTP {response.status_code}')
        return response.json()
    def submit(self,scope):
        params={**scope,'encoding':'csv','compression':'zstd','pretty_px':'false','pretty_ts':'false',
            'map_symbols':'true','split_symbols':'false','split_duration':'day','stype_out':'instrument_id','delivery':'download'}
        response=self.session.post(API+'batch.submit_job',data=params,timeout=(20,90))
        if response.status_code!=200:
            raise RuntimeError(f'batch.submit_job: HTTP {response.status_code}')
        return response.json()
    def jobs(self):
        jobs=self.get('batch.list_jobs',{'states':'queued,processing,done,expired','since':'1970-01-01T00:00:00Z','short':'false'})
        if isinstance(jobs,dict):
            jobs=jobs.get('jobs',jobs.get('data',[]))
        # API list may return short form; fetch full details before dedup.
        return [j if all(k in j for k in SCOPE_FIELDS) else self.get('batch.get_job_details',{'job_id':j['id']}) for j in jobs]


def current_reservations(exclude_paths=()):
    excluded={Path(p).resolve() for p in exclude_paths}
    records=[]
    reservation=EVIDENCE/'pilot_reservation.json'
    if reservation.exists() and reservation.resolve() not in excluded:
        payload=json.loads(reservation.read_text(encoding='utf-8'))
        records.append({'quoted_cost_usd':payload['pilot_quote_usd']})
    for path in EVIDENCE.glob('request-*.json'):
        if path.resolve() not in excluded:
            records.append(json.loads(path.read_text(encoding='utf-8')))
    return records


def refresh_status(http):
    jobs=http.jobs()
    sanitized=[]
    for job in jobs:
        if job.get('dataset') not in ('GLBX.MDP3','EQUS.MINI','EQUS.SUMMARY'):
            continue
        sanitized.append({k:job[k] for k in (*JOB_FIELDS,*SCOPE_FIELDS) if k in job})
    write_json(EVIDENCE/'provider_jobs.json',sanitized)
    for path in EVIDENCE.glob('request-*.json'):
        record=json.loads(path.read_text(encoding='utf-8'))
        matches=[j for j in jobs if all(k in j for k in SCOPE_FIELDS) and scope_hash(j)==record['scope_sha256']]
        if len(matches)==1:
            j=matches[0]
            record.update(job_id=j['id'],status=j['state'],job={k:j[k] for k in JOB_FIELDS if k in j})
            if j.get('cost_usd') is not None:
                record['actual_cost_usd']=float(money(j['cost_usd']))
            write_json(path,record)
        elif len(matches)>1:
            raise RuntimeError('Multiple provider jobs match frozen scope; manual reconciliation required')
    return jobs


def run(submit=False,status=False):
    http=HTTP()
    if status:
        refresh_status(http)
        print(json.dumps(current_reservations(),indent=2))
        return
    scopes=frozen_scopes()
    ensure_disjoint(scopes,[])
    quotes=[]
    for scope in scopes:
        row={'request':scope,'scope_sha256':scope_hash(scope),'quoted_utc':datetime.now(timezone.utc).isoformat()}
        for endpoint,label in [('metadata.get_cost','quoted_cost_usd'),('metadata.get_billable_size','billable_uncompressed_bytes'),('metadata.get_record_count','record_count')]:
            value=http.get(endpoint,scope)
            row[label]=float(money(value)) if label=='quoted_cost_usd' else int(money(value))
        quotes.append(row)
        print(json.dumps(row))
    ledger=json.loads((PROJECT/'data/raw/databento/acquisition_ledger.json').read_text(encoding='utf-8'))
    costs=[r['quoted_cost_usd'] for r in quotes]
    total=check_budget(ledger,costs,current_reservations())
    evidence={'retrieved_utc':datetime.now(timezone.utc).isoformat(),'quotes':quotes,'pilot_quote_usd':sum(costs),'aggregate_committed_usd':total,
        'docs':'https://databento.com/docs/api-reference-historical?historical=http',
        'units':'pretty_px=false (fixed-point 1e-9); pretty_ts=false (nanoseconds); CSV zstd; map_symbols=true; daily split',
        'metadata_size_endpoint':'get_billable_size is the current HTTP uncompressed size endpoint', 'paid_submit_authorized':submit}
    write_json(EVIDENCE/'live_quotes.json',evidence)
    if not submit:
        return
    jobs=http.jobs()
    ensure_disjoint(scopes,[j for j in jobs if all(k in j for k in SCOPE_FIELDS)])
    # Exclusive durable pilot reservation prevents concurrent or interrupted restart.
    write_json(EVIDENCE/'pilot_reservation.json',evidence,exclusive=True)
    for row in quotes:
        # Provider refresh must precede the final budget gate: an earlier job
        # can finalize above its quote while the shared ledger is still stale.
        jobs=refresh_status(http)
        ensure_disjoint([row['request']],[j for j in jobs if all(k in j for k in SCOPE_FIELDS)])
        ledger=json.loads((PROJECT/'data/raw/databento/acquisition_ledger.json').read_text(encoding='utf-8'))
        records=current_reservations([EVIDENCE/'pilot_reservation.json'])
        check_remaining_pilot(ledger,quotes,records)
        path=EVIDENCE/('request-'+row['scope_sha256']+'.json')
        result=submit_once(row['request'],row['quoted_cost_usd'],path,http.submit)
        print('SUBMITTED',result['job_id'],result['status'],row['quoted_cost_usd'],flush=True)
    refresh_status(http)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submit',action='store_true')
    parser.add_argument('--status',action='store_true')
    args=parser.parse_args()
    try:
        run(args.submit,args.status)
    except Exception as error:
        # Exception text from HTTP/auth may contain secrets; report only safe types.
        print('ACQUISITION_STOPPED',type(error).__name__,file=sys.stderr)
        sys.exit(1)
