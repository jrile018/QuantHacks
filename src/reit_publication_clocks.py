"""Evidence-bound producer sidecars, never a replacement canonical clock schema.

SEC acceptance is a replay proxy. It is never assigned to a public clock.
This module does not create decisions, calendars, features or outcomes.
"""
import copy
import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from functools import partial
from pathlib import Path, PureWindowsPath
from zoneinfo import ZoneInfo

from src.document_manifest import validate_sec_url


SCHEMA_VERSION = 'reit-publication-clock-evidence-v1'
_POLICY = {
    'name': 'sec_acceptance_plus_24h_or_date_upper_plus_24h_v1',
    'seconds': 86400,
    'date_rule': 'next_local_midnight_exclusive_upper_bound_plus_86400_seconds',
    'frozen_at_utc': '2026-10-04T05:17:19Z',
    'basis': 'assumed_sec_acceptance_proxy_not_actual_first_public',
    'cutoff_comparator': '<=',
    'scope': 'research_diagnostics_only_pending_canonical_consumer_acceptance',
    'provenance': [
        {'url': 'https://www.sec.gov/files/about/webmaster-faq.htm',
         'section': 'What is the lag time between filing acceptance and sec.gov availability?',
         'interpretation': 'Typical dissemination lag is not a guaranteed bound or exact public time.'},
        {'url': 'https://www.sec.gov/files/edgar-pds-new-subscriber-document.pdf',
         'section': 'EDGAR acceptance and dissemination',
         'interpretation': 'Acceptance, posting and dissemination are distinct operations.'},
        {'path': 'docs/coordination/architecture-contract.md',
         'section': 'Information clocks',
         'interpretation': 'Twenty-four hours is a frozen conservative research assumption, not an SEC guarantee.'},
    ],
}


def frozen_policy():
    """Return an isolated policy so callers cannot mutate the registered version."""
    return copy.deepcopy(_POLICY)


def _utc(value):
    if isinstance(value, str):
        if 'T' not in value and ' ' not in value:
            raise ValueError('clock requires time and explicit timezone')
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('clock requires aware timestamp; no timezone guessing')
    return value.astimezone(timezone.utc)


def _stamp(value):
    return _utc(value).isoformat().replace('+00:00', 'Z')


def _day_interval(day, zone):
    if not zone:
        raise ValueError('date-only clock requires timezone evidence')
    local_day, tz = date.fromisoformat(day), ZoneInfo(zone)
    return (_utc(datetime.combine(local_day, time.min, tz)),
            _utc(datetime.combine(local_day + timedelta(days=1), time.min, tz)))


def _bound(proof, digest):
    return isinstance(proof, dict) and proof.get('source_sha256') == digest and bool(proof.get('locator'))


def build_clock_record(evidence, *, review_at_utc, policy=None):
    """Validate one exact source version and retain independent clock bases."""
    policy = frozen_policy() if policy is None else copy.deepcopy(policy)
    if policy != _POLICY:
        raise ValueError('policy differs from its frozen version; register a new version')
    e, reasons = copy.deepcopy(evidence), list(evidence.get('exclusion_reasons', []))
    review = _utc(review_at_utc)
    cik = str(e.get('cik', '')).zfill(10)
    accession, digest = e.get('accession'), e.get('source_sha256')
    if not re.fullmatch(r'\d{10}', cik) or int(cik) == 0 or not re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession or ''):
        raise ValueError('invalid CIK/accession identity')
    if not re.fullmatch(r'[0-9a-f]{64}', digest or '') or not e.get('source_id'):
        raise ValueError('source identity and SHA256 are required')
    if e.get('selected_original_sha256') != digest:
        reasons.append('unselected_source_version')
    status = e.get('source_status')
    if status != 'eligible_as_primary':
        reasons.append('source_quarantined' if status in {'quarantined','quarantine'} else 'source_not_qualified')
    if e.get('source_conflict'):
        reasons.append('source_conflict')
    if e.get('identity_verified') is not True or e.get('integrity_verified') is not True:
        reasons.append('source_identity_or_integrity_unverified')
    if str(e.get('form', '')).upper().endswith('/A') or e.get('amends_accession'):
        reasons.append('amendment_not_original')
    lower = upper = None
    precision = None
    if e.get('sec_acceptance_at_utc'):
        lower = upper = _utc(e['sec_acceptance_at_utc'])
        precision = 'timestamp_as_reported'
    elif e.get('sec_acceptance_date'):
        lower, upper = _day_interval(e['sec_acceptance_date'], e.get('acceptance_timezone'))
        precision = 'date'
    else:
        reasons.append('acceptance_unknown')
    acceptance_proof = e.get('acceptance_evidence')
    if not (isinstance(acceptance_proof, dict) and acceptance_proof.get('locator')
            and re.fullmatch(r'[0-9a-f]{64}', acceptance_proof.get('source_sha256', ''))):
        reasons.append('acceptance_evidence_missing')
    if upper and upper > review:
        reasons.append('acceptance_after_review')
    retrieved = _utc(e['retrieved_at_utc']) if e.get('retrieved_at_utc') else None
    if retrieved is None:
        reasons.append('retrieval_unknown')
    elif retrieved > review:
        reasons.append('retrieval_after_review')
    elif lower and retrieved < lower:
        reasons.append('retrieval_before_acceptance')
    public_lower = public_upper = public = None
    if e.get('first_public_at_utc') or e.get('first_public_date'):
        if not _bound(e.get('first_public_evidence'), digest):
            reasons.append('unbound_public_evidence')
        elif e.get('first_public_date'):
            public_lower, public_upper = _day_interval(e['first_public_date'], e.get('public_timezone'))
        else:
            public = public_lower = public_upper = _utc(e['first_public_at_utc'])
    received = _utc(e['received_at_utc']) if e.get('received_at_utc') else None
    processed = _utc(e['processed_at_utc']) if e.get('processed_at_utc') else None
    if public_upper and public_upper > review:
        reasons.append('public_after_review')
    if received and received > review:
        reasons.append('receipt_after_review')
    if processed and processed > review:
        reasons.append('processing_after_review')
    if received and public_upper and received < public_upper:
        reasons.append('receipt_before_public_upper_bound')
    if processed and received and processed < received:
        reasons.append('processing_before_receipt')
    assumed = upper + timedelta(seconds=policy['seconds']) if upper and not reasons else None
    proposal_blockers = set(reasons) - {'source_not_qualified','source_identity_or_integrity_unverified'}
    proposed = (upper + timedelta(seconds=policy['seconds']) if upper and not proposal_blockers
                and e.get('integrity_verified') is True else None)
    row = {**e, 'schema_version': SCHEMA_VERSION, 'cik': cik,
           'effective_period': e.get('effective_period'),
           'effective_period_basis': 'represented_reporting_period_not_availability',
           'sec_acceptance_at_utc': _stamp(lower) if precision == 'timestamp_as_reported' else None,
           'acceptance_lower_utc': _stamp(lower) if lower else None,
           'acceptance_upper_utc': _stamp(upper) if upper else None,
           'acceptance_precision': precision,
           'first_public_at_utc': _stamp(public) if public else None,
           'first_public_lower_utc': _stamp(public_lower) if public_lower else None,
           'first_public_upper_utc': _stamp(public_upper) if public_upper else None,
           'first_public_status': 'exact_evidence_bound' if public else 'date_interval_evidence_bound' if public_upper else 'unknown',
           'received_at_utc': _stamp(received) if received else None,
           'processed_at_utc': _stamp(processed) if processed else None,
           'retrieved_at_utc': _stamp(retrieved) if retrieved else None,
           'review_at_utc': _stamp(review), 'review_basis': 'clock_packet_machine_validation_only',
           'assumed_available_at_utc': _stamp(assumed) if assumed else None,
           'proposed_assumed_available_at_utc': _stamp(proposed) if proposed else None,
           'assumed_clock_basis': policy['basis'], 'latency_assumption': policy,
           'exclusion_reasons': sorted(set(reasons)),
           'canonical_consumer_ready': False,
           'historical_trading_ready': False}
    return row


def cutoff_status(row, cutoff_at_utc, mode):
    """Producer qualification using canonical <=; replay proxy is diagnostic only."""
    cutoff, reasons = _utc(cutoff_at_utc), list(row['exclusion_reasons'])
    available = None
    if mode == 'historical_replay':
        available = row.get('assumed_available_at_utc')
        if not available:
            reasons.append('assumed_clock_unavailable')
    elif mode == 'observed':
        for key, reason in [('first_public_upper_utc', 'actual_public_unknown'),
                            ('received_at_utc', 'actual_receipt_unknown'),
                            ('processed_at_utc', 'actual_processing_unknown')]:
            if not row.get(key):
                reasons.append(reason)
        available = row.get('processed_at_utc')
    else:
        raise ValueError('mode must be observed or historical_replay')
    if available and _utc(available) > cutoff:
        reasons.append('source_after_cutoff')
    return {'eligible': not reasons, 'available_at_utc': available, 'mode': mode,
            'clock_basis': row['assumed_clock_basis'] if mode == 'historical_replay' else 'evidence_bound_actual_receipt_processing',
            'reasons': sorted(set(reasons)), 'canonical_consumer_ready': False}


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _path(value, root, *, origin_project_root=None):
    """Resolve within runtime root, optionally mapping one explicit Windows origin.

    Mapping is for I/O only: callers hash and retain the original JSON bytes.
    Without an origin declaration, preserve the existing native path behavior.
    """
    root = Path(root).resolve()
    if origin_project_root is not None:
        origin = PureWindowsPath(str(origin_project_root))
        if (not origin.is_absolute() or not re.fullmatch(r'[A-Za-z]:',origin.drive)
                or '..' in origin.parts):
            raise ValueError('origin project root must be an absolute Windows drive path without traversal')
        text = str(value)
        windows = PureWindowsPath(text)
        if not text or '\x00' in text or '..' in windows.parts:
            raise ValueError('unsafe project path traversal')
        native = Path(text.replace('\\','/'))
        # Explicit runtime paths remain usable on both Linux and Windows.
        if native.is_absolute():
            resolved = native.resolve()
            if resolved.is_relative_to(root):
                if any(':' in part for part in resolved.relative_to(root).parts):
                    raise ValueError('unsafe project path component')
                return resolved
        if windows.drive:
            if not windows.is_absolute():
                raise ValueError('drive-relative Windows paths are not supported')
            try:
                relative = windows.relative_to(origin)
            except ValueError as exc:
                raise ValueError('path is outside the explicitly declared origin project root') from exc
        elif windows.root:
            raise ValueError('absolute path is outside the runtime project root')
        else:
            relative = windows
        if any(part in {'..',''} or ':' in part for part in relative.parts):
            raise ValueError('unsafe project path component')
        path = root.joinpath(*relative.parts).resolve()
        if not path.is_relative_to(root):
            raise ValueError('mapped path or symlink escapes runtime project root')
        return path
    path = Path(value)
    path = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('evidence path escapes explicitly supplied root')
    return path


def build_packet(collection_manifest, snapshot_sources, output_dir, *, root, review_at_utc,
                 origin_project_root=None):
    """Small offline packet from frozen source classifications and retained receipts."""
    root = Path(root).resolve()
    resolve = partial(_path,root=root,origin_project_root=origin_project_root)
    collection_path, sources_path = resolve(collection_manifest), resolve(snapshot_sources)
    output = resolve(output_dir)
    if output.exists():
        raise FileExistsError('clock packet output is immutable; choose a new directory')
    collection = json.loads(collection_path.read_text(encoding='utf-8-sig'))
    documents = collection.get('documents', [])
    if len(documents) > 100:
        raise ValueError('small clock packet limited to 100 retained documents; use root remote runner for corpus')
    wanted_urls = {d['url'] for d in documents}
    source_by_url = {}
    with sources_path.open(encoding='utf-8-sig') as handle:
        for line in handle:
            s = json.loads(line)
            if s.get('url') in wanted_urls:
                source_by_url.setdefault(s['url'], []).append(s)
    inputs = [{'path':str(p.relative_to(root)), 'sha256':_hash(p)} for p in (collection_path,sources_path)]
    submissions = {}
    for company in collection.get('companies', []):
        cik = str(company['cik']).zfill(10)
        url = f'https://data.sec.gov/submissions/CIK{cik}.json'
        receipts = [r for r in company.get('metadata_receipts', []) if r.get('url') == url and r.get('cache_path')]
        if len(receipts) != 1:
            continue
        receipt = receipts[0]
        if receipt.get('http_status') != 200 or receipt.get('source') != 'http':
            continue  # Cached receipt with unknown original retrieval cannot acquire a fabricated clock.
        path = resolve(receipt['cache_path'])
        payload, digest = json.loads(path.read_text(encoding='utf-8-sig')), _hash(path)
        if str(payload.get('cik')).zfill(10) != cik:
            raise ValueError('Submissions issuer identity mismatch')
        submissions[cik] = (payload['filings']['recent'], digest, str(path.relative_to(root)))
        inputs.append({'path':str(path.relative_to(root)), 'sha256':digest, 'receipt':receipt})
    rows = []
    for d in documents:
        cik, accession = str(d['cik']).zfill(10), d['accession']
        validate_sec_url(d['url'], cik, accession)
        source_id = f'{accession}/{d["filename"]}'
        versions = source_by_url.get(d['url'], [])
        hash_matches = [s for s in versions if s.get('source_sha256') == d['sha256']]
        matching = [s for s in hash_matches if s.get('source_id') == source_id]
        source = matching[0] if len(matching) == 1 else {}
        reasons = []
        if any(s.get('source_id') != source_id for s in hash_matches):
            reasons.append('snapshot_source_identity_mismatch')
        if len(matching) != 1:
            reasons.append('snapshot_source_version_missing_or_duplicate')
        raw_path = resolve(d['source_path'])
        actual = _hash(raw_path)
        if actual != d['sha256']:
            reasons.append('source_bytes_mismatch')
        inputs.append({'path':str(raw_path.relative_to(root)), 'sha256':actual,
                       'declared_sha256':d['sha256']})
        acceptance = proof = None
        if cik in submissions:
            recent, digest, metadata_path = submissions[cik]
            indices = [i for i, value in enumerate(recent['accessionNumber']) if value == accession]
            if len(indices) == 1:
                i = indices[0]
                acceptance = recent['acceptanceDateTime'][i]
                proof = {'source_sha256':digest,'source_path':metadata_path,
                         'locator':f'/filings/recent/acceptanceDateTime/{i}',
                         'timezone_basis':'explicit_offset_as_retained_in_official_submissions',
                         'historical_capture':False}
                if (recent['form'][i] != d['form'] or recent['reportDate'][i] != d.get('reportDate', '')
                        or acceptance != d.get('acceptanceDateTime')):
                    reasons.append('submission_metadata_mismatch')
                if d.get('document_role') == 'primary' and recent['primaryDocument'][i] != d['filename']:
                    reasons.append('selected_primary_document_mismatch')
            else:
                reasons.append('submission_accession_missing_or_duplicate')
        else:
            reasons.append('official_submission_receipt_missing')
        axes = source.get('quality_axes', {})
        row = build_clock_record({
            'source_id':source_id,'cik':cik,'accession':accession,'source_sha256':d['sha256'],
            'selected_original_sha256':source.get('source_sha256'), 'source_path':str(raw_path.relative_to(root)),
            'source_url':d['url'], 'form':d['form'], 'document_role':d.get('document_role'),
            'effective_period':d.get('reportDate') or None, 'sec_acceptance_at_utc':acceptance,
            'acceptance_evidence':proof, 'retrieved_at_utc':collection.get('collected_at'),
            'retrieval_basis':'retained_http_collection_completion_upper_bound_not_exact_document_receipt',
            'source_status':source.get('eligibility'),
            'identity_verified':axes.get('content_identity', {}).get('state') == 'verified',
            'integrity_verified':axes.get('integrity', {}).get('state') == 'verified' and actual == d['sha256'],
            'source_conflict':len({s.get('source_sha256') for s in versions}) > 1 or any(
                s.get('eligibility') == 'quarantined' or 'source_conflict' in s.get('reasons', []) for s in versions),
            'exclusion_reasons':reasons}, review_at_utc=review_at_utc)
        rows.append(row)
    rows.sort(key=lambda r:(r['cik'], r['accession'], r['source_id']))
    counts = Counter(reason for row in rows for reason in row['exclusion_reasons'])
    manifest = {'schema_version':SCHEMA_VERSION, 'change_id':'reit-publication-clocks-20261004-v3',
                'producer':'Benchmark pt. 2 industry spec', 'consumer':'Post Benchmark',
                'status':'producer_diagnostic_packet_consumer_acceptance_pending',
                'review_at_utc':_stamp(review_at_utc), 'row_count':len(rows),
                'issuer_count':len({r['cik'] for r in rows}),
                'accession_count':len({(r['cik'], r['accession']) for r in rows}),
                'replay_proxy_candidate_count':sum(bool(r['assumed_available_at_utc']) for r in rows),
                'observed_ready_count':sum(cutoff_status(r,review_at_utc,'observed')['eligible'] for r in rows),
                'actual_first_public_known_count':sum(r['first_public_status'] != 'unknown' for r in rows),
                'exclusion_counts':dict(sorted(counts.items())), 'policy':frozen_policy(), 'inputs':inputs,
                'supported_mode':'historical_replay_acceptance_proxy_diagnostics_only',
                'canonical_consumer_ready':False, 'historical_trading_ready':False,
                'unresolved_gates':['canonical_adapter_policy_acceptance','actual_first_public_evidence',
                                    'actual_historical_receipt_and_processing','independent_financial_review',
                                    'dated_security_identity','registered_decision_calendar_and_outcomes'],
                'outputs':{}, 'code_sha256':_hash(Path(__file__))}
    if origin_project_root is not None:
        manifest['path_resolution'] = {'origin_project_root':str(origin_project_root),
            'runtime_project_root':str(root),'basis':'explicit_origin_mapping_for_io_only_original_bytes_retained'}
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.clock-packet-',dir=output.parent))
    try:
        data_path = stage/'publication_clocks.jsonl'
        data_path.write_text(''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows),encoding='utf-8')
        policy_path = stage/'latency_policy.json'
        policy_path.write_text(json.dumps(frozen_policy(),indent=2)+'\n',encoding='utf-8')
        for p in (data_path,policy_path):
            manifest['outputs'][p.name] = {'sha256':_hash(p), 'bytes':p.stat().st_size}
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest


def build_peer_packet(peer_manifest, broker_receipts, metadata_collection, output_dir, *, root,
                      review_at_utc, source_grades=None, origin_project_root=None):
    """Retained historical originals; independent grades are optional and explicit.

New originals never inherit a grade from the older immutable source snapshot.
Without an exact hash-bound grade, proposed clocks remain ineligible.
"""
    root = Path(root).resolve()
    resolve = partial(_path,root=root,origin_project_root=origin_project_root)
    peer_path, receipts_path, collection_path = [resolve(p) for p in
        (peer_manifest,broker_receipts,metadata_collection)]
    output = resolve(output_dir)
    if output.exists():
        raise FileExistsError('clock packet output is immutable; choose a new directory')
    peer, ledger, collection = [json.loads(p.read_text(encoding='utf-8-sig')) for p in
        (peer_path,receipts_path,collection_path)]
    if peer.get('broker_receipts_sha256') != _hash(receipts_path):
        raise ValueError('broker receipt ledger hash differs from peer manifest')
    if len(peer.get('documents',[])) > 100:
        raise ValueError('small clock packet limited to 100 retained documents')
    receipts = {r['receipt_id']:r for r in ledger['receipts']}
    if len(receipts) != len(ledger['receipts']):
        raise ValueError('duplicate receipt identity')
    inputs = [{'path':str(p.relative_to(root)),'sha256':_hash(p)} for p in
              (peer_path,receipts_path,collection_path)]
    metadata = {}
    for company in collection['companies']:
        cik = str(company['cik']).zfill(10)
        url = f'https://data.sec.gov/submissions/CIK{cik}.json'
        available = [r for r in company.get('metadata_receipts',[]) if r.get('url') == url
                     and r.get('source') == 'http' and r.get('http_status') == 200 and r.get('cache_path')]
        if len(available) != 1:
            continue
        path = resolve(available[0]['cache_path'])
        obj = json.loads(path.read_text(encoding='utf-8-sig'))
        if str(obj.get('cik')).zfill(10) != cik:
            raise ValueError('metadata issuer mismatch')
        metadata[cik] = (obj['filings']['recent'],_hash(path),str(path.relative_to(root)))
        inputs.append({'path':str(path.relative_to(root)),'sha256':_hash(path)})
    grades = {}
    if source_grades:
        grade_path = resolve(source_grades)
        inputs.append({'path':str(grade_path.relative_to(root)),'sha256':_hash(grade_path)})
        with grade_path.open(encoding='utf-8-sig') as handle:
            for line in handle:
                grade = json.loads(line)
                key = (grade['source_id'],grade['source_sha256'])
                if key in grades:
                    raise ValueError('duplicate source grade identity')
                grades[key] = grade
    rows = []
    for d in peer['documents']:
        cik, accession = str(d['cik']).zfill(10),d['accession']
        filename = d['primary_document']
        source_id = f'{accession}/{filename}'
        validate_sec_url(d['url'],cik,accession)
        source_reference = d['source_path']
        if origin_project_root is not None and PureWindowsPath(source_reference).anchor:
            raw_path = resolve(source_reference)
        else:
            raw_path = resolve(peer_path.parent/source_reference)
        actual = _hash(raw_path)
        inputs.append({'path':str(raw_path.relative_to(root)),'sha256':actual,'declared_sha256':d['sha256']})
        reasons = []
        if actual != d['sha256']:
            reasons.append('source_bytes_mismatch')
        receipt = d['receipt']
        if receipts.get(receipt.get('receipt_id')) != receipt:
            reasons.append('document_receipt_not_bound_to_ledger')
        if (receipt.get('status') != 200 or receipt.get('publicly_available') is not True
                or receipt.get('source_sha256') != d['sha256'] or receipt.get('response_sha256') != d['sha256']
                or receipt.get('final_url') != d['url'] or receipt.get('url') != d['url']):
            reasons.append('document_receipt_mismatch')
        official, proof, acceptance = d['official_metadata'],None,None
        if cik in metadata:
            recent,digest,metadata_path = metadata[cik]
            indices = [i for i,a in enumerate(recent['accessionNumber']) if a == accession]
            if len(indices) != 1:
                reasons.append('submission_accession_missing_or_duplicate')
            else:
                i = indices[0]
                acceptance = recent['acceptanceDateTime'][i]
                proof = {'source_sha256':digest,'source_path':metadata_path,
                         'locator':f'/filings/recent/acceptanceDateTime/{i}',
                         'timezone_basis':'explicit_offset_as_retained_in_official_submissions',
                         'historical_capture':False}
                if (official.get('metadata_source_sha256') != digest or official.get('accessionNumber') != accession
                        or recent['form'][i] != d['form'] or official.get('form') != d['form']
                        or recent['primaryDocument'][i] != filename or official.get('primaryDocument') != filename
                        or recent['reportDate'][i] != d['report_date'] or official.get('reportDate') != d['report_date']
                        or _utc(acceptance) != _utc(d['sec_acceptance_datetime'])
                        or acceptance != official.get('acceptanceDateTime')):
                    reasons.append('submission_metadata_mismatch')
        else:
            reasons.append('official_submission_receipt_missing')
        grade = grades.get((source_id,d['sha256']),{})
        axes = grade.get('quality_axes',{})
        row = build_clock_record({'source_id':source_id,'cik':cik,'accession':accession,
            'source_sha256':d['sha256'],'selected_original_sha256':d['sha256'],
            'source_path':str(raw_path.relative_to(root)),'source_url':d['url'],'form':d['form'],
            'document_role':'primary','effective_period':d['report_date'],
            'sec_acceptance_at_utc':acceptance,'acceptance_evidence':proof,
            'retrieved_at_utc':receipt.get('retrieved_at'),
            'retrieval_basis':'retained_2026_http_receipt_not_historical_capture',
            'present_public_observation':{'receipt_id':receipt.get('receipt_id'),
                'observed_at_utc':receipt.get('retrieved_at'),'source_sha256':receipt.get('source_sha256'),
                'basis':'available_by_current_receipt_not_earliest_public'},
            'source_status':grade.get('eligibility','needs_review'),
            'source_grade_basis':'exact_hash_bound_separate_grade_artifact' if grade else 'new_original_source_grade_pending',
            'identity_verified':axes.get('content_identity',{}).get('state') == 'verified',
            'integrity_verified':actual == d['sha256'],
            'source_conflict':grade.get('source_conflict') is True,
            'financial_eligible':False, 'exclusion_reasons':reasons},review_at_utc=review_at_utc)
        rows.append(row)
    rows.sort(key=lambda r:(r['cik'],r['accession'],r['source_id']))
    manifest = {'schema_version':SCHEMA_VERSION,'change_id':'reit-historical-publication-clocks-20261004-v3',
        'producer':'Benchmark pt. 2 industry spec','consumer':'Post Benchmark',
        'status':'producer_diagnostic_packet_source_grade_and_consumer_acceptance_gated',
        'review_at_utc':_stamp(review_at_utc),'row_count':len(rows),'issuer_count':len({r['cik'] for r in rows}),
        'accession_count':len({r['accession'] for r in rows}),
        'historical_accession_count':sum(_utc(r['sec_acceptance_at_utc']).year < 2026 for r in rows if r['sec_acceptance_at_utc']),
        'replay_proxy_candidate_count':sum(bool(r['assumed_available_at_utc']) for r in rows),
        'proposed_replay_clock_count':sum(bool(r['proposed_assumed_available_at_utc']) for r in rows),
        'observed_ready_count':sum(cutoff_status(r,review_at_utc,'observed')['eligible'] for r in rows),
        'actual_first_public_known_count':0,
        'exclusion_counts':dict(sorted(Counter(reason for r in rows for reason in r['exclusion_reasons']).items())),
        'policy':frozen_policy(),'inputs':inputs,'outputs':{},'code_sha256':_hash(Path(__file__)),
        'supported_mode':'historical_replay_acceptance_proxy_proposals_pending_source_grade_and_consumer_acceptance',
        'canonical_consumer_ready':False,'historical_trading_ready':False,
        'unresolved_gates':['exact_original_source_grade_approval','canonical_adapter_policy_acceptance',
            'actual_first_public_evidence','historical_receipt_processing','independent_financial_review',
            'dated_security_identity','registered_decision_calendar_and_outcomes']}
    if origin_project_root is not None:
        manifest['path_resolution'] = {'origin_project_root':str(origin_project_root),
            'runtime_project_root':str(root),'basis':'explicit_origin_mapping_for_io_only_original_bytes_retained'}
    output.parent.mkdir(parents=True,exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.clock-peer-',dir=output.parent))
    try:
        (stage/'publication_clocks.jsonl').write_text(''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows),encoding='utf-8')
        (stage/'latency_policy.json').write_text(json.dumps(frozen_policy(),indent=2)+'\n',encoding='utf-8')
        for name in ('publication_clocks.jsonl','latency_policy.json'):
            manifest['outputs'][name] = {'sha256':_hash(stage/name),'bytes':(stage/name).stat().st_size}
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest
