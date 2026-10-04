"""Collect exact peer-requested SEC primary originals into an isolated export."""
import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.reit_acquisition import FetchBroker, RunState, AcquisitionBlocked, transaction


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False), encoding='utf-8')
    temp.replace(path)
    return sha256(path.read_bytes()).hexdigest()


def validate_binding(row):
    cik, accession, filename = row['cik'], row['accession'], row['primary_document']
    if not re.fullmatch(r'\d{10}', cik) or not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession):
        raise ValueError('Invalid exact issuer/accession identity')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.html?', filename):
        raise ValueError('Primary filename must be a single HTML filename')
    expected = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{filename}'
    if row['source_url'] != expected:
        raise ValueError('SEC Archives exact path/issuer/accession/filename mismatch')
    if row['form'] not in {'10-K', '10-Q', '10-K/A', '10-Q/A', '8-K', '8-K/A'}:
        raise ValueError('Unsupported primary form')
    return (row['source_url'], cik, accession)


def prepare(queues, metadata_path, collection_path, output):
    rows, inputs, failures = {}, [], []
    for number, path in enumerate(queues):
        raw = path.read_bytes()
        staged = output/'inputs'/f'queue-{number}.csv'
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(raw)
        inputs.append({'path': str(path), 'staged_path': str(staged.relative_to(output)), 'sha256': sha256(raw).hexdigest()})
        for row in csv.DictReader(raw.decode('utf-8-sig').splitlines()):
            try:
                key = validate_binding(row)
                if key in rows and any(rows[key][k] != row[k] for k in ('primary_document', 'form', 'report_date', 'sec_acceptance_datetime')):
                    raise ValueError('Conflicting queue metadata for exact binding')
                rows.setdefault(key, row)
            except Exception as exc:
                failures.append({'row': row, 'error': str(exc)})
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))['metadata']
    official = {}
    for item in metadata:
        if item['cik'] not in {key[1] for key in rows}:
            continue
        if str(item['submissions']['cik']).zfill(10) != item['cik']:
            raise ValueError('Submissions issuer mismatch')
        arrays = [(item['submissions']['filings']['recent'], item)] + [(p['data'], p) for p in item.get('historical_pages', [])]
        for data, source in arrays:
            count = len(data.get('accessionNumber', []))
            if any(len(v) != count for v in data.values() if isinstance(v, list)):
                raise ValueError('Unequal official submissions arrays')
            for i, accession in enumerate(data.get('accessionNumber', [])):
                record = {k: v[i] for k, v in data.items() if isinstance(v, list)}
                key = (item['cik'], accession)
                if key in official and any(official[key][k] != record.get(k) for k in ('primaryDocument', 'form', 'reportDate')):
                    raise ValueError('Conflicting official submissions identity')
                official[key] = {**record, 'metadata_source_sha256': source.get('source_sha256'), 'metadata_source_url': source.get('source_url')}
    retained = json.loads(collection_path.read_text(encoding='utf-8'))['documents']
    ready = []
    for key, row in rows.items():
        try:
            record = official[(row['cik'], row['accession'])]
            for queue_key, official_key in [('primary_document','primaryDocument'), ('form','form'), ('report_date','reportDate')]:
                if row[queue_key] != (record.get(official_key) or ''):
                    raise ValueError('Queue differs from official primary submissions: '+queue_key)
            if not record['metadata_source_sha256']:
                raise ValueError('Official metadata lacks retained source hash')
            matches = [d for d in retained if d['url'] == row['source_url'] and d['cik'] == row['cik'] and d['accession'] == row['accession'] and d.get('document_role') == 'primary' and d.get('primaryDocument') == row['primary_document']]
            ready.append({**row, 'official_metadata': record, 'retained': matches[0] if matches else None})
        except Exception as exc:
            failures.append({'row': row, 'error': str(exc)})
    ready.sort(key=lambda r: (r['accession'] != '0001500217-26-000032', r['cik'], r['accession']))
    result = {'schema_version': 1, 'queues': inputs, 'metadata_sha256': sha256(metadata_path.read_bytes()).hexdigest(), 'collection_sha256': sha256(collection_path.read_bytes()).hexdigest(), 'requests': ready, 'schema_failures': failures}
    save(output/'request_manifest.json', result)
    return result


class NativeText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in {'script','style'}: self.skip += 1
        elif tag in {'p','div','tr','br','li'}: self.parts.append('\n')
        elif tag in {'td','th'}: self.parts.append('\t')
    def handle_endtag(self, tag):
        if tag in {'script','style'} and self.skip: self.skip -= 1
        elif tag in {'p','div','tr','li'}: self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)


def aware_timestamp(value):
    if not isinstance(value,str):
        raise ValueError('Receipt timestamp is missing')
    stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Receipt timestamp must specify timezone')
    return stamp


def offline_source(output, row, source, receipts):
    """Validate bounded bytes and acquisition evidence before native parsing."""
    if not source or source.get('error'):
        raise AcquisitionBlocked((source or {}).get('error','Original acquisition unavailable'))
    url = row['source_url']
    if source.get('url') != url:
        raise ValueError('Acquired source URL differs from exact request')
    path_text = source.get('path','').replace('\\','/')
    if not path_text or Path(path_text).is_absolute() or re.match(r'^[A-Za-z]:',path_text) or '..' in Path(path_text).parts:
        raise ValueError('Offline source path must be relative and bounded')
    path = (output/path_text).resolve()
    if not path.is_relative_to(output.resolve()):
        raise ValueError('Offline source resolves outside output')
    digest = sha256(path.read_bytes()).hexdigest()
    if source.get('sha256') != digest:
        raise ValueError('Offline source bytes differ from acquired hash')
    receipt = source.get('receipt') or {}
    if receipt.get('url') != url or receipt.get('source_sha256') != digest or not receipt.get('receipt_id'):
        raise ValueError('Receipt exact URL/source hash/identity mismatch')
    if receipts.get(receipt['receipt_id']) != receipt:
        raise ValueError('Acquired receipt does not match durable broker ledger identity')
    if receipt.get('kind') == 'http':
        if receipt.get('status') != 200 or receipt.get('final_url') != url or receipt.get('response_sha256') != digest or receipt.get('publicly_available') is not True:
            raise ValueError('HTTP receipt does not bind successful exact response')
        if aware_timestamp(receipt.get('started_at')) > aware_timestamp(receipt.get('retrieved_at')):
            raise ValueError('HTTP receipt retrieval precedes request')
    elif receipt.get('kind') == 'retained_cache_import':
        retained = row.get('retained') or {}
        if (retained.get('url') != url or retained.get('cik') != row['cik'] or retained.get('accession') != row['accession']
                or retained.get('primaryDocument') != row['primary_document'] or retained.get('document_role') != 'primary' or retained.get('sha256') != digest):
            raise ValueError('Import lacks exact hash-bound retained primary evidence')
        if any(receipt.get(k) is not None for k in ('status','retrieved_at','publicly_available','response_sha256','final_url','started_at')):
            raise ValueError('Import receipt contains forged live response evidence')
        aware_timestamp(receipt.get('imported_at'))
    else:
        raise ValueError('Unsupported acquisition receipt kind')
    return {**source,'path':str(path)}


def validate_completed_result(output, row, source, document):
    """A terminal extraction belongs to one exact source version and receipt."""
    if document.get('sha256') != source['sha256'] or document.get('receipt') != source['receipt']:
        raise ValueError('Completed source version changed; retained prior result requires explicit rebuild')
    if any(document.get(key) != value for key,value in row.items() if key != 'retained') or document.get('url') != row['source_url']:
        raise ValueError('Completed result differs from exact current request identity')
    for key in ('source_path','text_path'):
        value = document.get(key,'').replace('\\','/')
        if not value or Path(value).is_absolute() or re.match(r'^[A-Za-z]:',value) or '..' in Path(value).parts:
            raise ValueError('Completed artifact path must be bounded and relative')
        if not (output/value).resolve().is_relative_to(output.resolve()):
            raise ValueError('Completed artifact resolves outside output')
    raw = (output/document['source_path'].replace('\\','/')).read_bytes()
    if sha256(raw).hexdigest() != source['sha256']:
        raise ValueError('Completed source version differs from retained raw artifact')
    text_raw = (output/document['text_path'].replace('\\','/')).read_bytes()
    if sha256(text_raw).hexdigest() != document.get('text_sha256'):
        raise ValueError('Completed extraction hash differs from retained text artifact')
    text = json.loads(text_raw)
    if any(text.get(key) != row[key] for key in ('source_url','cik','accession')) or text.get('sha256') != source['sha256']:
        raise ValueError('Completed extraction quote identity differs from current source version')
    parser = NativeText()
    parser.feed(raw.decode('utf-8',errors='replace'))
    expected_pages = [{'number':1,'text':''.join(parser.parts),'method':'html_native_text','confidence':None}]
    if text.get('pages') != expected_pages or text.get('source_method') != 'html_native_text' or document.get('source_method') != 'html_native_text' or document.get('page_count') != 1:
        raise ValueError('Completed native extraction differs from current exact source bytes')


def collect(output, broker_root, retained_root=None, acquire_only=False, offline=False, retry_network_denied=False):
    request_path = output/'request_manifest.json'
    request = json.loads(request_path.read_text(encoding='utf-8'))
    broker = None if offline else FetchBroker(broker_root, contact_email='john.p.riley00@gmail.com', rate=2)
    acquired = json.loads((output/'acquired.json').read_text()) if offline else {}
    ledger = {}
    if offline:
        for receipt in json.loads((output/'broker_receipts.json').read_text())['receipts']:
            identity = receipt.get('receipt_id')
            if not identity or (identity in ledger and ledger[identity] != receipt):
                raise ValueError('Broker ledger contains missing or conflicting receipt identity')
            ledger[identity] = receipt
    state = RunState(output/('acquisition_tasks.sqlite' if acquire_only else 'tasks.sqlite'))
    if retry_network_denied:
        with transaction(state.path) as db:
            db.execute("UPDATE tasks SET status='pending',retry_at=0 WHERE status='blocked' AND error LIKE '%WinError 10013%'")
    current = {}
    bindings = set()
    for i, row in enumerate(request['requests']):
        binding = validate_binding(row)
        if binding in bindings:
            raise ValueError('Duplicate exact request identity')
        bindings.add(binding)
        task_id = f'{i:03d}-'+sha256(row['source_url'].encode()).hexdigest()
        current[task_id] = row
        state.enqueue(task_id, row)
    owner = 'peer-primary'
    while task := state.claim(owner, lease_seconds=300):
        row = task['payload']
        try:
            if task['task_id'] not in current:
                raise ValueError('Obsolete task is outside current request set')
            validate_binding(row)
            retained = row.get('retained')
            if offline:
                result = offline_source(output,row,acquired.get(row['source_url']),ledger)
            elif retained:
                path = Path(retained['source_path'])
                if retained_root:
                    normalized = retained['source_path'].replace('\\','/')
                    path = retained_root / normalized.split('/QuantHaxs/',1)[1]
                result = broker.import_cached(row['source_url'], path, retained['sha256'], content_type=retained.get('content_type'))
            else:
                result = broker.fetch(row['source_url'])
            raw = Path(result['path']).read_bytes()
            if sha256(raw).hexdigest() != result['sha256']:
                raise ValueError('Exact source hash mismatch')
            if b'<html' not in raw[:20000].lower() and b'<?xml' not in raw[:20000].lower():
                raise ValueError('Primary response is not native HTML')
            raw_path = output/'raw'/row['cik']/row['accession']/row['primary_document']
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(raw)
            if acquire_only:
                state.finish(task['task_id'],owner,{'url':row['source_url'],'path':raw_path.relative_to(output).as_posix(),'sha256':result['sha256'],'receipt':result['receipt']})
                continue
            parser = NativeText()
            parser.feed(raw.decode('utf-8', errors='replace'))
            text_path = output/'text'/row['cik']/row['accession']/(row['primary_document']+'.json')
            text_sha = save(text_path, {'source_url': row['source_url'], 'cik': row['cik'], 'accession': row['accession'], 'sha256': result['sha256'], 'source_method': 'html_native_text', 'pages': [{'number':1,'text':''.join(parser.parts),'method':'html_native_text','confidence':None}]})
            doc = {**row, 'url': row['source_url'], 'document_role':'primary', 'source_path':raw_path.relative_to(output).as_posix(), 'text_path':text_path.relative_to(output).as_posix(), 'sha256':result['sha256'], 'text_sha256':text_sha, 'source_method':'html_native_text', 'page_count':1, 'receipt':result['receipt'], 'acquisition_evidence_kind':result['receipt']['kind'], 'retained_source_reused':bool(retained), 'first_public_at':None, 'availability_status':'retrospective_current_receipt_only', 'financial_eligible':False, 'out_of_sample_eligible':False}
            doc.pop('retained',None)
            state.finish(task['task_id'],owner,doc)
        except Exception as exc:
            # Every request receives a durable explicit terminal failure; no retry burst.
            state.fail(task['task_id'],owner,type(exc).__name__+': '+str(exc),blocked=True)
    summary = state.summary()
    tasks = [t for t in summary['tasks'] if t['task_id'] in current]
    if len(tasks) != len(current):
        raise ValueError('Current requests do not have exactly one durable task')
    # Revalidate completed offline inputs too; RunState completion cannot bypass
    # changed or forged evidence in a reused output directory.
    if offline:
        for task in tasks:
            if task['status'] == 'complete':
                try:
                    row = current[task['task_id']]
                    source = offline_source(output,row,acquired.get(row['source_url']),ledger)
                    validate_completed_result(output,row,source,json.loads(task['result']))
                except Exception as exc:
                    task.update(status='blocked',result=None,error=type(exc).__name__+': '+str(exc))
    if any(t['status'] not in {'complete','blocked','failed'} for t in tasks):
        raise ValueError('Current request lacks a terminal result')
    counts = {}
    for task in tasks:
        counts[task['status']] = counts.get(task['status'],0)+1
    summary['counts'] = counts
    if acquire_only:
        acquisitions = {json.loads(t['payload'])['source_url']:json.loads(t['result']) if t['status']=='complete' else {'error':t['error']} for t in tasks}
        save(output/'acquired.json',acquisitions)
        requested_urls = {r['source_url'] for r in request['requests']}
        save(output/'broker_receipts.json',{'receipts':[r for r in broker.receipts() if r['url'] in requested_urls]})
        print(json.dumps({'acquisition_counts':summary['counts']}),flush=True)
        return acquisitions
    receipts = json.loads((output/'broker_receipts.json').read_text())['receipts'] if offline else broker.receipts()
    requested_urls = {r['source_url'] for r in request['requests']}
    receipts_sha = save(output/'broker_receipts.json', {'receipts':[r for r in receipts if r['url'] in requested_urls]})
    manifest = {'schema_version':1,'produced_at':datetime.now(timezone.utc).isoformat(), 'request_manifest_sha256':sha256(request_path.read_bytes()).hexdigest(), 'broker_receipts_sha256':receipts_sha, 'documents':[json.loads(t['result']) for t in tasks if t['status']=='complete'], 'failures':[{'task_id':t['task_id'],'request':json.loads(t['payload']),'status':t['status'],'error':t['error']} for t in tasks if t['status']!='complete'], 'schema_failures':request['schema_failures'], 'counts':summary['counts'], 'first_public_at':None,'financial_eligible':False,'out_of_sample_eligible':False}
    digest = save(output/'manifest.json',manifest)
    save(output/'producer_hashes.json', {'manifest_sha256':digest,'broker_receipts_sha256':receipts_sha})
    print(json.dumps({'manifest_sha256':digest,'broker_receipts_sha256':receipts_sha,'counts':summary['counts'],'schema_failures':len(request['schema_failures'])}),flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--queue',type=Path,action='append')
    parser.add_argument('--metadata',type=Path)
    parser.add_argument('--collection-manifest',type=Path)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--broker-root',type=Path)
    parser.add_argument('--retained-root',type=Path)
    parser.add_argument('--acquire-only',action='store_true')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--retry-network-denied',action='store_true')
    args=parser.parse_args()
    if args.queue:
        result=prepare(args.queue,args.metadata,args.collection_manifest,args.output)
        print(json.dumps({'requests':len(result['requests']), 'retained':sum(bool(r['retained']) for r in result['requests']), 'schema_failures':len(result['schema_failures'])}))
    if not args.prepare_only:
        if not args.broker_root and not args.offline: parser.error('--broker-root is required for acquisition')
        collect(args.output,args.broker_root,args.retained_root,args.acquire_only,args.offline,args.retry_network_denied)


if __name__ == '__main__': main()
