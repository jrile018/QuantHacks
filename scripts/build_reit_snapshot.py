"""Offline integration of retained REIT sources into an immutable snapshot.

The preparation step can be CPU intensive and belongs on the remote compute
host. Publication alone verifies prepared inputs without redoing extraction.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))

from src.reit_dataset import publish_snapshot
from src.reit_discovery import filing_eligibility_evidence
from src.reit_histories import build_histories, _document_id
from src.reit_relationships import build_relationships, normalize_assertions, discover_relationship_candidates
from src.reit_source_quality import audit_source, _status
from src.reit_universe import build_universe

DEFAULT_BUILD = 'data/processed/reit_build/20261003'
DEFAULT_RETAINED = ('data/processed/reit_financials/20261003-meaning-pilot',
                    'data/processed/reit_filing_pilot/realty_income_2025_meaning_v2')
PATH_KEYS = {'source_path', 'text_path', 'text_artifact_path', 'data_path',
             'cache_path', 'path', 'collection_dir', 'derived_path'}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _hash_file(path):
    digest = sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (_json(value) + '\n').encode('utf-8')
    if path.exists() and path.read_bytes() == raw:
        return
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)


def resolve_input_path(value, project_root=ROOT, collection_root=None, *, must_exist=True):
    """Resolve saved Windows/project/collection paths inside the current project.

    Relocation is anchored at the exact data/ project subtree, never a filename
    search. Parent traversal and paths outside the supplied project are rejected.
    """
    root = Path(project_root).resolve()
    if not isinstance(value, str) or not value:
        raise ValueError('Cannot resolve missing input path')
    normalized = value.replace('\\', '/')
    if '..' in normalized.split('/'):
        raise ValueError('Input path outside project: ' + value)
    candidates = []
    native = Path(normalized)
    if native.is_absolute():
        candidates.append(native)
    # A Windows drive path is not absolute to pathlib on Linux.
    match = re.search(r'(?:^|/)data/', normalized)
    if match:
        candidates.append(root / normalized[match.start():].lstrip('/'))
    if not native.is_absolute() and not re.match(r'^[A-Za-z]:/', normalized):
        candidates.append(root / normalized)
        if collection_root is not None:
            candidates.append(Path(collection_root) / normalized)
    allowed = []
    for candidate in candidates:
        path = candidate.resolve()
        if not path.is_relative_to(root):
            continue
        allowed.append(path)
        if path.exists():
            return path
    if allowed and not must_exist:
        return allowed[-1] if collection_root is not None and not match else allowed[0]
    raise ValueError('Cannot resolve input inside project: ' + value)


def _remap(value, root, collection, mapping):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in PATH_KEYS and isinstance(child, str) and child:
                path = resolve_input_path(child, root, collection, must_exist=False)
                relative = path.relative_to(root).as_posix()
                mapping[child] = relative
                value[key] = str(path)
            else:
                _remap(child, root, collection, mapping)
    elif isinstance(value, list):
        for child in value:
            _remap(child, root, collection, mapping)


def _portable(value, root):
    """Create project-relative JSON for moving prepared inputs between hosts."""
    value = deepcopy(value)
    def walk(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if key in PATH_KEYS and isinstance(child, str) and child:
                    path = Path(child)
                    if path.is_absolute() and path.resolve().is_relative_to(root):
                        item[key] = path.resolve().relative_to(root).as_posix()
                else:
                    walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
    walk(value)
    return value


def _relocate_extraction(document, root, work, mapping, derivations):
    path = Path(document['text_path'])
    original_hash = _hash_file(path)
    anchored = any(document.get(field) for field in ('text_sha256', 'extracted_text_sha256', 'text_artifact_sha256'))
    for field in ('text_sha256', 'extracted_text_sha256', 'text_artifact_sha256'):
        if document.get(field) and document[field] != original_hash:
            raise ValueError('Extracted text hash mismatch: ' + str(path))
    extracted = _load(path)
    if not isinstance(extracted, dict) or not isinstance(extracted.get('pages'), list):
        raise ValueError('Malformed extracted pages: ' + str(path))
    binding = extracted.get('sha256') or extracted.get('source_sha256') or extracted.get('extracted_raw_sha256')
    if binding != document['sha256']:
        raise ValueError('Extracted raw source hash mismatch: ' + str(path))
    if extracted.get('source_url') and extracted['source_url'] != document['url']:
        raise ValueError('Extracted URL identity mismatch: ' + str(path))
    if extracted.get('accession') and extracted['accession'] != document.get('accession'):
        raise ValueError('Extracted accession identity mismatch: ' + str(path))
    if extracted.get('source_path'):
        bound = resolve_input_path(extracted['source_path'], root, path.parent)
        if bound != Path(document['source_path']):
            raise ValueError('Extracted path identity mismatch: ' + str(path))
    # Omit the host-specific field in this derived copy. Binding remains exact
    # through raw SHA256, URL and accession. Original bytes remain untouched.
    derived = deepcopy(extracted)
    derived.pop('source_path', None)
    derived['original_extraction_sha256'] = original_hash
    derived_path = work / 'extractions' / (sha256(_json(derived).encode()).hexdigest() + '.json')
    _save(derived_path, derived)
    new_hash = _hash_file(derived_path)
    derivations.append({'original_path': path.relative_to(root).as_posix(),
                        'original_sha256': original_hash, 'derived_path': str(derived_path),
                        'derived_sha256': new_hash, 'original_extraction_digest_anchored': anchored,
                        'method': 'remove_host_specific_source_path_only'})
    mapping[str(path)] = derived_path.relative_to(root).as_posix()
    document.update(text_path=str(derived_path), extracted_text_sha256=new_hash,
                    original_extracted_text_sha256=original_hash,
                    original_extraction_digest_unanchored=not anchored,
                    extraction_integrity_basis='declared_input_digest' if anchored else 'unanchored_legacy_cache')
    document.pop('text_sha256', None)
    document.pop('text_artifact_sha256', None)
    return derived


def _analysis_paths(collection):
    preferred = [collection / 'money_analysis_v2/analysis_manifest.json',
                 collection / 'analysis_100/analysis_manifest.json']
    for path in preferred:
        if path.is_file():
            return path
    return None


def _history_batches(build, root, inputs):
    """Read explicit completed URLs without claiming the selected batch is done."""
    batches, urls = [], set()
    for path in sorted((build / 'batches').glob('*/batch_manifest.json')):
        batch = _load(path)
        batches.append(batch)
        inputs.append({'kind': 'history_batch', 'input_path': path.relative_to(root).as_posix(), 'input_sha256': _hash_file(path)})
        for label, queue_name in [('completed_document_urls', 'document'), ('completed_exhibit_urls', 'exhibit')]:
            if label in batch:
                urls.update(batch[label])
                continue
            queue_path = path.parent / (queue_name + '_tasks.sqlite')
            if not queue_path.exists():
                continue
            connection = sqlite3.connect(queue_path.resolve().as_uri() + '?mode=ro', uri=True)
            try:
                for (result,) in connection.execute("SELECT result FROM tasks WHERE status='complete'"):
                    row = json.loads(result)
                    if row.get('url'):
                        urls.add(row['url'])
            finally:
                connection.close()
            inputs.append({'kind': 'completed_history_task_queue', 'input_path': queue_path.relative_to(root).as_posix(), 'input_sha256': _hash_file(queue_path)})
    return batches, urls


def _official_sec_archive_url(url):
    """Require the exact official archive shape observed in retained receipts."""
    try:
        parts = urlsplit(url)
        return (parts.scheme == 'https' and parts.netloc in {'www.sec.gov', 'sec.gov'}
                and not parts.query and not parts.fragment
                and re.fullmatch(r'/Archives/edgar/data/\d+/\d{18}/[A-Za-z0-9_.-]+', parts.path) is not None)
    except (TypeError, ValueError):
        return False


def _trailing_empty_script(path, source_url):
    """Compare the narrow observed SEC injection shape, preserving raw IDs.

    This is an inference about the retained wrapper pattern, not a claim of
    general rendered equivalence. External, encoded, ordinary asset, query, and
    protocol-relative src values do not qualify.
    """
    if not _official_sec_archive_url(source_url):
        return None
    raw = Path(path).read_bytes()
    pattern = (rb'<script[ \t]+type="text/javascript"[ \t]+src="/[A-Za-z0-9]+(?:/[A-Za-z0-9]+){5,11}"'
               rb'[ \t]*>[ \t]*</script>(?=</body></html>[ \t\r\n]*$)')
    match = re.search(pattern, raw)
    if match is None:
        return None
    remainder = raw[:match.start()] + raw[match.end():]
    return {'comparison_sha256': sha256(remainder).hexdigest(), 'comparison_bytes': len(remainder),
            'removed_tag': raw[match.start():match.end()].decode('utf-8', errors='replace'),
            'removed_char_start': match.start(), 'removed_char_end': match.end(),
            'scope': 'exact_bytes_except_observed_SEC_empty_final_injection_pattern',
            'interpretation': 'narrow_observed_pattern_inference_not_general_rendered_equivalence'}


def _bind_records(rows, documents):
    """Rebind derivative text hashes while retaining the original evidence hash."""
    by_id = {_document_id(d): d for d in documents}
    by_path = {d['source_path']: d for d in documents}
    by_hash = {}
    for document in documents:
        by_hash.setdefault(document['sha256'], []).append(document)
    def walk(item, inherited=None):
        if isinstance(item, dict):
            document = by_id.get(item.get('document_id')) or by_path.get(item.get('source_path')) or inherited
            digest = item.get('source_sha256')
            if document is None and digest and len(by_hash.get(digest, [])) == 1:
                document = by_hash[digest][0]
            if document is not None and (not digest or digest == document['sha256']):
                if item.get('text_artifact_sha256'):
                    item['original_text_artifact_sha256'] = item['text_artifact_sha256']
                    item['text_artifact_sha256'] = document['extracted_text_sha256']
                if item.get('text_artifact_path'):
                    item['text_artifact_path'] = document['text_path']
                    item['original_extraction_digest_unanchored'] = document['original_extraction_digest_unanchored']
                if item.get('text_path'):
                    item['text_path'] = document['text_path']
                    item['original_extraction_digest_unanchored'] = document['original_extraction_digest_unanchored']
                if item.get('source_path'):
                    item['source_path'] = document['source_path']
            for child in item.values():
                if isinstance(child, (dict, list)):
                    walk(child, document)
        elif isinstance(item, list):
            for child in item:
                walk(child, inherited)
    walk(rows)
    return rows


def build_snapshot(build_root=DEFAULT_BUILD, *, project_root=ROOT, retained_roots=None,
                   output_root=None, as_of=None, prepare_only=False, max_candidates=100,
                   financial_scope='history_batches'):
    """Integrate retained collection manifests; no requests, OCR, or models."""
    root = Path(project_root).resolve()
    build = resolve_input_path(str(build_root), root)
    output = (resolve_input_path(str(output_root), root, must_exist=False)
              if output_root else build / 'integrated')
    work = output / 'prepared'
    as_of = as_of or datetime.now(timezone.utc).isoformat()
    retained_roots = DEFAULT_RETAINED if retained_roots is None else retained_roots
    collections = [resolve_input_path(str(path), root) for path in retained_roots]
    collections.append(build / 'collection')
    mapping, derivations, inputs, docs, records, candidate_review = {}, [], [], [], [], []
    analysis_coverage, seen_docs = [], {}
    representation_variants, conflicted_urls = [], set()
    if financial_scope not in {'history_batches', 'all'}:
        raise ValueError('financial_scope must be history_batches or all')
    batches, financial_urls = _history_batches(build, root, inputs)
    for collection in collections:
        manifest_path = collection / 'manifest.json'
        manifest = _load(manifest_path)
        manifest_hash = _hash_file(manifest_path)
        inputs.append({'kind': 'collection_manifest', 'input_path': manifest_path.relative_to(root).as_posix(), 'input_sha256': manifest_hash})
        names = {str(c['cik']).zfill(10): c.get('company_name') for c in manifest.get('companies', [])}
        analysis_path = _analysis_paths(collection)
        analysis = _load(analysis_path) if analysis_path else None
        if analysis:
            if analysis.get('collection_manifest_sha256') != manifest_hash:
                raise ValueError('Analysis collection manifest hash mismatch: ' + str(analysis_path))
            text_hashes = {d['source_url']: d.get('extracted_text_sha256') for d in analysis.get('documents', [])}
            inputs.append({'kind': 'analysis_manifest', 'input_path': analysis_path.relative_to(root).as_posix(), 'input_sha256': _hash_file(analysis_path),
                           'analyzer_revision': analysis.get('analyzer_revision'), 'implementation_sha256': analysis.get('implementation_sha256')})
            analysis_coverage.append({'input_path': analysis_path.relative_to(root).as_posix(),
                                     'coverage_warnings': analysis.get('coverage_warnings', []), 'errors': analysis.get('errors', []),
                                     'documents': analysis.get('documents', [])})
            for filename in ('money_records.jsonl', 'review_candidates.jsonl'):
                path = analysis_path.parent / filename
                expected = analysis.get('output_sha256', {}).get(filename)
                if not expected or _hash_file(path) != expected:
                    raise ValueError('Analysis output hash mismatch: ' + str(path))
                rows = [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
                _remap(rows, root, collection, mapping)
                inputs.append({'kind': 'analysis_output', 'input_path': path.relative_to(root).as_posix(), 'input_sha256': expected})
                if filename == 'money_records.jsonl':
                    records.extend(rows)
                else:
                    candidate_review.extend({'item_type': 'money_candidate', 'candidate': row, 'issues': ['human_review_required']} for row in rows)
        else:
            text_hashes = {}
        for original in manifest.get('documents', []):
            document = deepcopy(original)
            _remap(document, root, collection, mapping)
            document['source_path'] = str(resolve_input_path(original['source_path'], root, collection))
            document['text_path'] = str(resolve_input_path(original['text_path'], root, collection))
            if _hash_file(document['source_path']) != document.get('sha256'):
                raise ValueError('Raw source hash mismatch: ' + document['source_path'])
            # SEC submissions size is filing metadata, not a measurement of this
            # individual retained document. Clarify only this derived copy.
            if 'size' in document:
                original_size = document.pop('size')
                sec_submissions = any(re.fullmatch(r'https://data\.sec\.gov/submissions/CIK\d{10}(?:-submissions-\d+)?\.json', source.get('url', ''))
                                      and source.get('source_sha256') for source in document.get('metadata_sources', []))
                size_field = 'filing_metadata_size' if sec_submissions else 'legacy_metadata_size'
                if size_field in document and document[size_field] != original_size:
                    raise ValueError('Conflicting original size metadata')
                document[size_field] = original_size
                document['size_metadata_provenance'] = {'original_field': 'size', 'scope': 'sec_submissions_filing_metadata' if sec_submissions else 'legacy_metadata_unknown_scope'}
            document['source_byte_count'] = Path(document['source_path']).stat().st_size
            if text_hashes.get(document['url']):
                document['extracted_text_sha256'] = text_hashes[document['url']]
            document['document_id'] = _document_id(document)
            document['company_name'] = document.get('company_name') or names.get(str(document.get('cik')).zfill(10))
            document['report_date'] = document.get('report_date') or document.get('reportDate')
            document['issuer_name'] = document.get('issuer_name') or document['company_name']
            document['analysis_bound_representation'] = bool(analysis)
            # Retrieval establishes a current observation, never publication.
            document['retrieved_at'] = document.get('retrieved_at') or manifest.get('collected_at')
            extracted = _relocate_extraction(document, root, work, mapping, derivations)
            identifier = document['document_id']
            if identifier in seen_docs:
                preferred = seen_docs[identifier]
                comparison = None
                if preferred['url'] != document['url']:
                    classification = 'conflicting_retained_source_urls'
                elif preferred['sha256'] == document['sha256']:
                    classification = 'identical_raw_bytes_distinct_retained_chains'
                else:
                    left = _trailing_empty_script(preferred['source_path'], preferred['url'])
                    right = _trailing_empty_script(document['source_path'], document['url'])
                    comparison = {'preferred': left, 'auxiliary': right}
                    classification = ('identical_except_trailing_empty_external_script'
                                      if left and right and left['comparison_sha256'] == right['comparison_sha256']
                                      and left['comparison_bytes'] == right['comparison_bytes']
                                      else 'substantive_retained_content_conflict')
                token = sha256(_json([document['sha256'], Path(document['source_path']).relative_to(root).as_posix(),
                                      document['extracted_text_sha256'], document.get('form'), document.get('document_role')]).encode()).hexdigest()[:24]
                document['document_id'] = identifier + '#representation-' + token
                document['source_local_document_id'] = identifier
                document['auxiliary_representation'] = True
                document['financial_representation_policy'] = 'prefer_first_analysis_bound_retained_chain_no_duplicate_parse'
                changed = {key: {'preferred': preferred.get(key), 'auxiliary': document.get(key)}
                           for key in ('cik', 'form', 'report_date', 'document_role')
                           if preferred.get(key) != document.get(key)}
                variant = {'document_id': identifier, 'auxiliary_document_id': document['document_id'],
                           'classification': classification, 'meaning_metadata_differences': changed,
                           'preferred_representation': deepcopy(preferred), 'auxiliary_representation': deepcopy(document),
                           'comparison': comparison}
                representation_variants.append(variant)
                if classification in {'substantive_retained_content_conflict', 'conflicting_retained_source_urls'}:
                    conflicted_urls.update((preferred['url'], document['url']))
                if changed:
                    candidate_review.append({'item_type': 'document_meaning_metadata_difference', 'issues': ['human_review_required'],
                                             'document_id': identifier, 'auxiliary_document_id': document['document_id'], 'differences': changed})
            else:
                seen_docs[identifier] = document
            docs.append(document)
            if not analysis and not document.get('auxiliary_representation') and (financial_scope == 'all' or document['url'] in financial_urls):
                from src.reit_money_records import build_document_records
                generated = build_document_records(Path(document['source_path']).read_bytes(), document, extracted, max_candidates=max_candidates)
                records.extend(generated['records'])
                candidate_review.extend({'item_type': 'money_candidate', 'candidate': row, 'issues': ['human_review_required']} for row in generated['candidates'])
                analysis_coverage.append({'document_id': identifier, 'analysis_origin': 'fresh_retained_document', 'coverage': generated['coverage']})
            elif not analysis:
                analysis_coverage.append({'document_id': identifier, 'analysis_origin': 'discovery_validation_collection',
                                          'status': 'skipped_auxiliary_representation' if document.get('auxiliary_representation') else 'skipped_outside_completed_history_batch',
                                          'financial_coverage_complete': False})
    for document in docs:
        document['source_issues'] = ['retained_content_conflict'] if document['url'] in conflicted_urls else []
    conflict_docs = {d['source_path'] for d in docs if d['source_issues']}
    conflict_hashes = {d['sha256'] for d in docs if d['source_issues']}
    for row in records:
        if row.get('source_path') in conflict_docs or row.get('source_sha256') in conflict_hashes:
            row['quality_flags'] = sorted(set(row.get('quality_flags', []) + ['retained_content_conflict']))
    candidate_review.extend({'item_type': 'retained_source_conflict', 'issues': ['retained_content_conflict'], 'variant': variant}
                            for variant in representation_variants if variant['classification'] in {'substantive_retained_content_conflict', 'conflicting_retained_source_urls'})
    records = _bind_records(records, docs)
    candidate_review = _bind_records(candidate_review, docs)
    # Retain independent source observations and deduplicate identical rows only.
    records = list({_json(row): row for row in records}.values())
    candidates_path = build / 'discovery_candidates.json'
    candidates = _load(candidates_path)['candidates']
    _remap(candidates, root, build, mapping)
    inputs.append({'kind': 'discovery_candidates', 'input_path': candidates_path.relative_to(root).as_posix(), 'input_sha256': _hash_file(candidates_path)})
    evidence = []
    by_cik = {}
    for candidate in candidates:
        if candidate.get('cik'):
            key = (candidate.get('ticker'), candidate.get('security_id'))
            by_cik.setdefault(str(candidate['cik']).zfill(10), {})[key] = candidate
    annual_dates = {}
    for document in docs:
        if not document.get('auxiliary_representation') and not document['source_issues'] and document.get('form') in {'10-K', '10-K/A'} and document.get('document_role') != 'exhibit' and document.get('report_date'):
            annual_dates.setdefault(str(document.get('cik')).zfill(10), set()).add(document['report_date'])
    for document in docs:
        if document.get('auxiliary_representation') or document['source_issues'] or document.get('form') not in {'10-K', '10-K/A'} or document.get('document_role') == 'exhibit':
            continue
        raw = Path(document['source_path']).read_bytes()
        if raw.lstrip().startswith(b'%PDF-'):
            continue  # PDF layout is not converted to an HTML cover-table claim.
        for candidate in by_cik.get(str(document.get('cik')).zfill(10), {}).values():
            context = dict(document, ticker=candidate['ticker'],
                           security_id=candidate.get('security_id') or str(document['cik']).zfill(10) + ':' + candidate['ticker'] + ':common_candidate',
                           issuer=document.get('company_name') or document.get('issuer_name'))
            proof = filing_eligibility_evidence(context, raw.decode('utf-8-sig', errors='replace'))
            newer = sorted(day for day in annual_dates.get(str(document.get('cik')).zfill(10), []) if day > document.get('report_date', ''))
            if newer:
                for row in proof:
                    row['valid_to'] = newer[0]
                    row['interval_basis'] = 'next_retained_annual_report_date_not_verified_continuity'
            evidence.extend(proof)
    evidence = list({_json(row): row for row in evidence}.values())
    universe = build_universe(candidates, evidence, as_of)
    receipts_path = build / 'broker_receipts.json'
    receipts = _load(receipts_path).get('receipts', []) if receipts_path.exists() else []
    if receipts_path.exists():
        inputs.append({'kind': 'broker_receipts', 'input_path': receipts_path.relative_to(root).as_posix(), 'input_sha256': _hash_file(receipts_path)})
    by_url = defaultdict(list)
    for receipt in receipts:
        by_url[receipt.get('url')].append(receipt)
    quality_rows, duplicate_indices = [], defaultdict(list)
    for document in docs:
        extracted = _load(document['text_path'])
        issuer = document.get('company_name') or document.get('issuer_name')
        if not issuer and document.get('cik') == '0000726728':
            issuer = 'Realty Income Corporation'
        source = dict(document, issuer=issuer, period=document.get('report_date'), source_id=document['document_id'],
                      extracted_raw_sha256=document['sha256'],
                      content_text='\n'.join(p.get('text', '') for p in extracted['pages']),
                      expected={'cik': document.get('cik'), 'issuer': issuer, 'period': document.get('report_date'),
                                'accession': document.get('accession'), 'document': document.get('filename')})
        observations = by_url.get(source['url'], [])
        if observations:
            source['availability_history'] = observations
            if source.get('http_status') is None and _status(observations[-1]) is not None:
                source['http_status'] = _status(observations[-1])
        audited = audit_source(source, Path(document['source_path']).read_bytes(), source['expected'])
        if document['source_issues']:
            audited.update(eligibility='quarantine')
            audited['reasons'] = sorted(set(audited['reasons'] + document['source_issues']))
            audited['coverage']['source_grade'] = 'quarantine'
        audited.update(source_id=document['document_id'], source_path=document['source_path'], source_sha256=document['sha256'],
                      document_id=document['document_id'], text_path=document['text_path'],
                      extracted_text_sha256=document['extracted_text_sha256'],
                      original_extraction_digest_unanchored=document['original_extraction_digest_unanchored'])
        duplicate_indices[document['sha256']].append(len(quality_rows))
        quality_rows.append(audited)
    quality = {'schema_version': '1.0', 'sources': quality_rows,
               'duplicate_groups': [{'raw_sha256': digest, 'source_indices': indices, 'lineage': 'same_retained_bytes'}
                                    for digest, indices in duplicate_indices.items() if len(indices) > 1],
               'conflicts': [row for row in representation_variants if row['classification'] in {'substantive_retained_content_conflict', 'conflicting_retained_source_urls'}],
               'eligibility_counts': dict(Counter(row['eligibility'] for row in quality_rows)),
               'coverage': {'source_count': len(quality_rows), 'receipt_count': len(receipts), 'universe_completeness': 'unknown',
                            'financial_accuracy': 'not_assessed', 'audit_memory_policy': 'one_raw_document_at_a_time',
                            'limitation': 'Source axes audited independently; observation comparison requires supplied comparable financial evidence.'}}
    histories = build_histories(records, docs)
    histories['review'].extend(candidate_review)
    assertions_path = build / 'relationship_seed_assertions.json'
    seed = _load(assertions_path) if assertions_path.exists() else {'assertions': []}
    if assertions_path.exists():
        inputs.append({'kind': 'relationship_seed', 'input_path': assertions_path.relative_to(root).as_posix(), 'input_sha256': _hash_file(assertions_path)})
    assertions = deepcopy(seed.get('assertions', []))
    _remap(assertions, root, build, mapping)
    _bind_records(assertions, docs)
    from src.reit_histories import _timestamp
    by_doc = {_document_id(d): d for d in docs}
    conflicted_assertions = [a for a in assertions if (by_doc.get((a.get('evidence') or {}).get('document_id')) or {}).get('source_issues')]
    assertions = [a for a in assertions if a not in conflicted_assertions]
    for assertion in assertions:
        document = by_doc.get((assertion.get('evidence') or {}).get('document_id'))
        if document:
            clocks = [document.get(key) for key in ('available_at', 'acceptanceDateTime', 'acceptance_datetime', 'accepted_at')]
            source_clocks = [stamp for value in clocks if (stamp := _timestamp(value)) is not None]
            original = assertion.get('available_at')
            assertion_clock = _timestamp(original)
            # A supplied seed clock cannot override later filing acceptance.
            if source_clocks and assertion_clock:
                latest = max([assertion_clock, *source_clocks]).isoformat()
                if _timestamp(latest) != assertion_clock:
                    assertion['original_available_at'] = original
                    assertion['available_at'] = latest
                    assertion['availability_adjustment'] = 'max_asserted_and_retained_accepted_timestamp'
            elif assertion_clock and not source_clocks:
                assertion['original_available_at'] = original
                assertion['available_at'] = None
                assertion['availability_adjustment'] = 'retained_source_availability_unknown'
    normalized = normalize_assertions(assertions, docs)
    network = build_relationships(normalized['assertions'], docs)
    network['review'].extend({'item_type': 'retained_source_conflict', 'assertion': assertion,
                              'issues': ['retained_content_conflict']} for assertion in conflicted_assertions)
    network['review'].extend({'item_type': 'normalization', **row} for row in normalized['review'])
    network['review'].extend({'item_type': 'seed_review', **row} for row in seed.get('review_items', []))
    native_candidate_count, native_skipped, native_issues = 0, 0, []
    for document in docs:
        if document.get('auxiliary_representation') or document['source_issues']:
            native_skipped += 1
            continue
        discovered = discover_relationship_candidates([document])
        native_candidate_count += len(discovered['candidates'])
        native_skipped += discovered['coverage']['skipped_documents']
        native_issues.extend(discovered['coverage']['issues'])
        network['review'].extend({'item_type': 'native_relationship_candidate', 'candidate': row,
                                  'issues': ['human_review_required'], 'eligibility': row['eligibility']}
                                 for row in discovered['candidates'])
    network['coverage']['native_relationship_discovery'] = {'candidate_count': native_candidate_count,
        'skipped_documents': native_skipped, 'issues': native_issues, 'complete': False,
        'scope': 'retained_native_agreement_passages_no_adjudicated_roles'}
    coverage = {'scope': 'retained_sources_and_explicit_batches', 'documents': len(docs), 'money_records': len(records),
                'history_batches': batches, 'analysis': analysis_coverage,
                'financial_scope': financial_scope,
                'completed_history_source_urls': len(financial_urls),
                'fresh_money_documents': sum(row.get('analysis_origin') == 'fresh_retained_document' for row in analysis_coverage),
                'money_skipped_documents': sum(row.get('status') == 'skipped_outside_completed_history_batch' for row in analysis_coverage),
                'auxiliary_money_skipped_documents': sum(row.get('status') == 'skipped_auxiliary_representation' for row in analysis_coverage),
                'source_representation_variant_count': len(representation_variants),
                'quarantined_source_url_count': len(conflicted_urls), 'quarantined_source_urls': sorted(conflicted_urls),
                'native_relationship_candidate_count': native_candidate_count,
                'universe_complete': False, 'collection_complete': False, 'history_complete': False,
                'point_in_time_ready': False, 'trading_ready': False,
                'availability_policy': 'retrieval_is_not_publication; missing_first_public_time_remains_unknown',
                'native_pdf_extraction': 'retained_cache_only_no_OCR_audit',
                'eligibility_policy': 'fresh_contextual_annual_HTML_evidence; old_universe_proof_not_imported'}
    coverage['extraction_integrity_gaps'] = [
        {'kind': 'original_extraction_digest_unanchored', 'document_id': d['document_id'],
         'original_extracted_text_sha256': d['original_extracted_text_sha256']}
        for d in docs if d['original_extraction_digest_unanchored']]
    histories['coverage']['analysis_coverage'] = analysis_coverage
    inventory = {'selected': deepcopy(docs), 'coverage': {'scope': 'collected_documents_only', 'collection_complete': False, 'history_batches': batches}}
    provenance = {'runner_sha256': _hash_file(__file__), 'as_of': as_of, 'input_artifacts': inputs,
                  'path_mapping': mapping, 'extraction_derivations': _portable(derivations, root),
                  'eligibility_evidence': evidence, 'normalization': normalized, 'coverage': coverage}
    provenance['representation_variants'] = representation_variants
    prepared = dict(universe=universe, inventory=inventory, quality=quality, histories=histories,
                    network=network, documents=docs, provenance=provenance)
    prepared_path = work / 'prepared_inputs.json'
    _save(prepared_path, _portable(prepared, root))
    _save(work / 'coverage.json', _portable(coverage, root))
    current_universe = deepcopy(universe)
    current_universe['proof_scope'] = 'fresh_retained_annual_claims_current_retrieval_clock; historical_membership_not_exhaustive'
    current_universe.update(historical_ready=False, trading_ready=False, collection_complete=False)
    _save(work / 'universe_current.json', _portable(current_universe, root))
    validated_ciks = sorted({row['cik'] for row in universe['validated']})
    issuer_proof = []
    for cik in validated_ciks:
        securities = [row for row in universe['validated'] if row['cik'] == cik]
        issuer_proof.append({'cik': cik, 'security_ids': [row['security_id'] for row in securities],
                             'evidence': list({_json(ev): ev for row in securities for ev in row['evidence']}.values()),
                             'eligibility_intervals': [interval for row in securities for interval in row['eligibility_intervals']]})
    history_plan = {'schema_version': 1, 'as_of': as_of, 'batch_size': 10,
                    'universe_input': 'universe_current.json', 'validated_issuer_ciks': validated_ciks,
                    'validated_issuer_proof': issuer_proof,
                    'batches': [{'batch_index': index // 10 + 1, 'ciks': validated_ciks[index:index + 10],
                                'status': 'planned_not_collected', 'history_complete': False}
                               for index in range(0, len(validated_ciks), 10)],
                    'existing_history_batches': batches,
                    'coverage': {'validated_issuer_count': len(validated_ciks), 'batch_count': (len(validated_ciks) + 9) // 10,
                                 'candidate_security_count': len(universe['candidates']), 'excluded_security_count': len(universe['exclusions']),
                                 'unresolved_candidate_security_count': sum(not row.get('cik') for row in universe['candidates']),
                                 'quarantined_source_urls': sorted(conflicted_urls), 'evidence_errors': universe['coverage']['evidence_errors'],
                                 'collection_complete': False, 'historical_membership_complete': False},
                    'proof_scope': current_universe['proof_scope'],
                    'limitation': 'Plan only; no HTTP jobs launched. Current validated claims do not establish exhaustive historical membership.'}
    _save(work / 'history_batch_plan.json', _portable(history_plan, root))
    result = {'prepared_inputs': str(prepared_path), 'universe': universe, 'network': network,
              'coverage': coverage, 'eligibility_evidence': evidence, 'path_mapping': mapping,
              'extraction_derivations': derivations}
    if not prepare_only:
        result['snapshot'] = publish_snapshot(output / 'snapshots', source_root=root, **prepared)
    return result


def publish_prepared(prepared_path, *, project_root=ROOT, output_root=None):
    """Relocate portable prepared inputs and publish without financial parsing."""
    root = Path(project_root).resolve()
    path = resolve_input_path(str(prepared_path), root)
    prepared = _load(path)
    mapping = {}
    # Prepared extraction copies have no source_path field; no rewriting needed.
    _remap(prepared, root, path.parent, mapping)
    for reference in prepared['provenance'].get('input_artifacts', []):
        original = resolve_input_path(reference['input_path'], root)
        if _hash_file(original) != reference['input_sha256']:
            raise ValueError('Prepared input artifact hash mismatch: ' + str(original))
    output = resolve_input_path(str(output_root), root, must_exist=False) if output_root else path.parent.parent / 'snapshots'
    return publish_snapshot(output, source_root=root, **prepared)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=ROOT)
    parser.add_argument('--build-root', default=DEFAULT_BUILD)
    parser.add_argument('--retained-root', action='append', help='Repeat for retained pilot collections; defaults to two documented pilots')
    parser.add_argument('--output-root')
    parser.add_argument('--as-of', help='Aware current universe knowledge cutoff; does not establish historical availability')
    parser.add_argument('--max-candidates', type=int, default=100)
    parser.add_argument('--financial-scope', choices=['history_batches', 'all'], default='history_batches',
                        help='Fresh money parsing scope; retained pilot analyses are reused in both modes')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--prepare-inputs', action='store_true')
    mode.add_argument('--publish-only', metavar='PREPARED_JSON')
    args = parser.parse_args(argv)
    if args.max_candidates < 0:
        parser.error('--max-candidates must be nonnegative')
    if args.publish_only:
        snapshot = publish_prepared(args.publish_only, project_root=args.project_root, output_root=args.output_root)
        print(_json({'snapshot_dir': snapshot['snapshot_dir'], 'verified': snapshot['verified'], 'counts': snapshot['counts']}), flush=True)
    else:
        result = build_snapshot(args.build_root, project_root=args.project_root, retained_roots=args.retained_root,
                                output_root=args.output_root, as_of=args.as_of,
                                prepare_only=args.prepare_inputs, max_candidates=args.max_candidates,
                                financial_scope=args.financial_scope)
        print(_json({'prepared_inputs': result['prepared_inputs'],
                     'snapshot_dir': result.get('snapshot', {}).get('snapshot_dir'),
                     'validated_current_candidates': result['universe']['coverage']['validated_count'],
                     'documents': result['coverage']['documents'],
                     'collection_complete': False, 'trading_ready': False}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
