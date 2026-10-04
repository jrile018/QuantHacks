"""Analyze one explicit 8-K accession; offline by default, SEC fetch when requested."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.document_manifest import inventory_from_submission, SecFetcher, SECBlocked, atomic_json
from src.document_transcript import extract_path
from src.document_evidence import build_evidence
from src.document_language import DictionaryProvider, FinBertProvider, analyze_wording, compare_prior, utc_timestamp, has_public_evidence
from src.document_report import options_readiness, render_markdown


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def is_analysis_document(record):
    """Exclude SEC viewer assets, XBRL and encoded support files from wording."""
    if record['document_role'] == 'primary_filing':
        return True
    return (record.get('exhibit_type') or '').startswith('EX-99')


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def store_source(directory, data, suffix):
    digest = hashlib.sha256(data).hexdigest()
    path = Path(directory) / (digest + suffix)
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Immutable source cache hash mismatch')
    if not path.exists():
        atomic_bytes(path, data)
    return path.resolve()


def selected_row(args):
    row = {'cik': args.cik, 'accession': args.accession, 'form': '8-K', 'amends_accession': args.amends_accession}
    if args.catalog:
        with Path(args.catalog).open(encoding='utf-8-sig', newline='') as handle:
            matches = [r for r in csv.DictReader(handle)
                       if r.get('cik', '').lstrip('0') == args.cik.lstrip('0') and r.get('accession') == args.accession]
        if len(matches) != 1:
            raise ValueError('Expected exactly one CIK/accession in catalog')
        row.update(matches[0])
        row['amends_accession'] = args.amends_accession
    if not row.get('complete_text_url'):
        row['complete_text_url'] = f'https://www.sec.gov/Archives/edgar/data/{int(args.cik)}/{args.accession}.txt'
    return row


def comparison_metadata(inventory, latest=False):
    """All compared documents must have supported times; use conservative bounds."""
    if not inventory or any(not d.get('public_at_utc') or not has_public_evidence(d)
                            or d.get('identity_status') != 'verified' for d in inventory):
        return None
    ordered = sorted(inventory, key=lambda d: utc_timestamp(d['public_at_utc']))
    return ordered[-1] if latest else ordered[0]


def run(args):
    config = load_json(args.config)
    frozen = {'first_family': '2.02', 'administrative_items': ['9.01'],
              'target_rule_id': 'call_put_3to6m_5pct_next_session_v1',
              'expiry_days': {'minimum': 90, 'maximum': 180, 'target': 120},
              'call_spot_ratio': 1.05, 'put_spot_ratio': .95,
              'model_training_enabled': False, 'market_forecast_enabled': False}
    if any(config.get(key) != value for key, value in frozen.items()):
        raise ValueError('Frozen family/target settings differ from the implemented v1 rule')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:10]
    directory = Path(args.output_dir) / run_id
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {'schema_version': '1.0', 'run_id': run_id, 'status': 'started', 'cik': args.cik,
                'accession': args.accession, 'config': config, 'failures': []}
    atomic_json(directory / 'run.json', manifest)
    try:
        row = selected_row(args)
        # Validate identity before any source path or network use.
        inventory_from_submission(row, b'')
        if args.submission:
            payload = Path(args.submission).read_bytes()
            receipt = datetime.now(timezone.utc).isoformat()
            source_status = 'local_submission'
        else:
            fetcher = SecFetcher(args.raw_dir, os.environ.get('SEC_CONTACT_EMAIL'))
            fetched = fetcher.fetch(row['complete_text_url'], row['cik'], row['accession'])
            payload = Path(fetched['path']).read_bytes()
            receipt, source_status = fetched['receipt_at_utc'], 'contained_in_verified_submission'
        source_path = store_source(args.raw_dir, payload, '.submission.txt')
        manifest['submission_sha256'] = hashlib.sha256(payload).hexdigest()
        manifest['submission_path'] = str(source_path)
        inventory = inventory_from_submission(row, payload)
        metadata = load_json(args.public_metadata) if args.public_metadata else {}
        ocr_map = load_json(args.ocr_map) if args.ocr_map else {}
        transcripts, evidence, flags = [], [], []
        for record in inventory:
            record['run_id'] = run_id
            record['wording_selected'] = is_analysis_document(record)
            content = record.pop('content_bytes')
            record.pop('content', None)
            record['receipt_at_utc'] = receipt
            record['container_sha256'] = manifest['submission_sha256']
            if content is not None:
                record['url_status'] = source_status
            timing = metadata.get(record['filename'], {}) if record['filename'] else {}
            if timing.get('public_at_utc') and has_public_evidence(timing):
                record['public_at_utc'] = utc_timestamp(timing['public_at_utc']).isoformat()
                record['public_at_evidence'] = timing['public_at_evidence']
            if record['inventory_status'] != 'complete':
                flags.append(record['inventory_status'])
            if record.get('identity_status') != 'verified':
                flags.append('submission_identity_unverified')
            if content is None:
                continue
            try:
                suffix = Path(record['filename'] or 'document.txt').suffix.lower() or '.txt'
                path = store_source(args.raw_dir, content, suffix)
                record['source_path'] = str(path)
                if not record['wording_selected']:
                    record['analysis_status'] = 'not_selected_supporting_resource'
                    continue
                if record['filename'] in ocr_map:
                    ocr_path = Path(args.ocr_map).resolve().parent / ocr_map[record['filename']]
                    transcript = extract_path(ocr_path, record['document_id'], record['source_sha256'])
                    transcript['source_path'] = str(path)
                    store_source(args.raw_dir, ocr_path.read_bytes(), '.ocr.json')
                else:
                    transcript = extract_path(path, record['document_id'], record['source_sha256'])
                transcript['run_id'] = run_id
                for table in transcript['table_records']:
                    table['evidence_references'] = []
                items = build_evidence(transcript)
                for table in transcript['table_records']:
                    table['evidence_references'] = [e['evidence_id'] for e in items
                                                     if e['char_start'] < table['char_end'] and e['char_end'] > table['char_start']]
                transcripts.append(transcript)
                evidence.extend(items)
                flags.extend(transcript['quality_flags'])
                atomic_json(directory / 'transcripts' / (record['source_sha256'] + '-' + hashlib.sha256(record['document_id'].encode()).hexdigest()[:12] + '.json'), transcript)
            except (ValueError, RuntimeError, OSError, ImportError) as error:
                record['inventory_status'] = 'failed_extraction'
                record['extraction_error'] = type(error).__name__ + ': ' + str(error)
                flags.append('failed_extraction')
            # A durable checkpoint survives interruption after any completed document.
            atomic_json(directory / 'inventory.json', [
                {k: v for k, v in d.items() if k not in ('content', 'content_bytes')} for d in inventory])
        all_items = sorted({item for d in inventory for item in d['sec_items']})
        family = 'outside_first_family' if '2.02' not in all_items else 'mixed_event' if set(all_items) - {'2.02', '9.01'} else 'in_first_family'
        if family != 'in_first_family':
            flags.append(family)
        prior = load_json(args.prior_report) if args.prior_report else {}
        prior_evidence = prior.get('evidence', [])
        # Validate every prior span/hash before admitting its quotations.
        validated_prior = []
        for transcript in prior.get('transcripts', []):
            validated_prior.extend(build_evidence(transcript))
        if prior_evidence != validated_prior:
            prior_evidence = []
            flags.append('prior_evidence_unverified')
        analysis_evidence = evidence
        if args.mode == 'anticipation':
            cutoff = utc_timestamp(args.decision)
            eligible_ids = set()
            for record in inventory:
                transcript = next((t for t in transcripts if t['document_id'] == record['document_id']), {})
                public = utc_timestamp(record.get('public_at_utc'))
                received = utc_timestamp(record.get('receipt_at_utc'))
                processed = utc_timestamp(transcript.get('processing_completed_at_utc'))
                if (cutoff and args.target_accession and record['accession'] != args.target_accession
                        and record.get('identity_status') == 'verified'
                        and has_public_evidence(record) and public and public < cutoff
                        and received and received <= cutoff and processed and processed <= cutoff):
                    eligible_ids.add(record['document_id'])
            analysis_evidence = [e for e in evidence if e['document_id'] in eligible_ids]
            if len(analysis_evidence) != len(evidence):
                flags.append('anticipation_ineligible_evidence_excluded_from_wording')
        selected_inventory = [d for d in inventory if d['wording_selected']]
        comparison = compare_prior(analysis_evidence, prior_evidence, comparison_metadata(selected_inventory),
                                   comparison_metadata([d for d in prior.get('inventory', []) if is_analysis_document(d)], latest=True), args.decision)
        dictionary, finbert, errors = None, None, {}
        if args.dictionary:
            try:
                dictionary = DictionaryProvider(args.dictionary, args.dictionary_revision)
            except (ValueError, OSError) as error:
                errors['dictionary'] = type(error).__name__ + ': ' + str(error)
        if args.finbert_model:
            try:
                finbert = FinBertProvider(args.finbert_model, args.finbert_revision, args.device)
            except (ValueError, OSError, ImportError, RuntimeError) as error:
                errors['finbert'] = type(error).__name__ + ': ' + str(error)
        wording = analyze_wording(analysis_evidence, dictionary, finbert, comparison, errors)
        market = load_json(args.market_metadata) if args.market_metadata else None
        readiness = options_readiness(selected_inventory, transcripts, mode=args.mode, decision=args.decision,
                                      target_accession=args.target_accession, market=market, settings=config['eligibility'])
        # No document-derived output is eligible as an anticipation feature yet.
        # This tool is a document audit; the as-of dataset builder is a later stage.
        report = {'schema_version': '1.0', 'run_id': run_id, 'cik': row['cik'], 'accession': row['accession'],
                  'family_status': family, 'sec_items': all_items, 'inventory': inventory,
                  'transcripts': transcripts, 'evidence': evidence, 'wording': wording,
                  'options': readiness, 'quality_flags': sorted(set(flags)),
                  'feature_export_eligible': False,
                  'analysis_purpose': 'document_audit; not a point-in-time feature dataset'}
        atomic_json(directory / 'inventory.json', inventory)
        atomic_json(directory / 'report.json', report)
        atomic_bytes(directory / 'report.md', render_markdown(report).encode('utf-8'))
        manifest['status'] = 'completed_with_gaps' if flags or errors else 'completed'
        manifest['report_path'] = str((directory / 'report.json').resolve())
        manifest['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
        atomic_json(directory / 'run.json', manifest)
        return (directory / 'report.json').resolve()
    except Exception as error:
        manifest['status'] = 'blocked' if isinstance(error, SECBlocked) else 'failed'
        manifest['failures'].append({'type': type(error).__name__, 'detail': str(error)})
        atomic_json(directory / 'run.json', manifest)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cik', required=True)
    parser.add_argument('--accession', required=True)
    parser.add_argument('--catalog', help='Existing SEC URL catalog CSV')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--submission', help='Local complete SEC SGML submission')
    source.add_argument('--fetch', action='store_true', help='Fetch this complete submission from SEC')
    parser.add_argument('--amends-accession')
    parser.add_argument('--config', default=str(ROOT / 'configs/8k_document_analysis.json'))
    parser.add_argument('--output-dir', default=str(ROOT / 'data/processed/8k_document_analysis'))
    parser.add_argument('--raw-dir', default=str(ROOT / 'data/raw/8k_documents'))
    parser.add_argument('--ocr-map', help='JSON filename -> saved OCR JSON path, relative to map')
    parser.add_argument('--public-metadata', help='JSON filename -> supported public timestamp and evidence')
    parser.add_argument('--prior-report', help='Explicit earlier comparable report.json')
    parser.add_argument('--dictionary')
    parser.add_argument('--dictionary-revision')
    parser.add_argument('--finbert-model', help='Local frozen model directory (safetensors)')
    parser.add_argument('--finbert-revision')
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--market-metadata', help='Optional diagnostic records, never proof of validated coverage')
    parser.add_argument('--mode', choices=('post_release', 'anticipation'), default='post_release')
    parser.add_argument('--decision', help='As-of ISO timestamp with timezone')
    parser.add_argument('--target-accession', help='Future target accession to exclude in anticipation')
    args = parser.parse_args()
    try:
        print(run(args))
    except Exception as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
