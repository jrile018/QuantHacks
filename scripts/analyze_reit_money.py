"""Organize a retained REIT collection locally; never fetch or run OCR/models."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import reit_inline_facts, reit_money_records, reit_tables, reit_pdf_money
from src.reit_cash_facts import cash_flow_rows
from src.reit_money_records import (ANALYZER_REVISION, build_document_records,
                                   companyfacts_records, consolidate_records)


def _serialized(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _hash(value):
    return sha256(_serialized(value)).hexdigest()


def _atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _inside(root, value):
    if not isinstance(value, str) or not value:
        raise ValueError('Missing source path')
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError('Source path is outside collection directory')
    return path


def _implementation_hash():
    paths = [Path(__file__), Path(reit_inline_facts.__file__), Path(reit_money_records.__file__),
             Path(reit_tables.__file__), Path(reit_pdf_money.__file__), Path(cash_flow_rows.__code__.co_filename)]
    return sha256(b''.join(p.read_bytes() for p in paths)).hexdigest()


def _load_document(root, document):
    original = _inside(root, document.get('source_path'))
    text_path = _inside(root, document.get('text_path'))
    if original.stat().st_size > reit_inline_facts.MAX_BYTES:
        raise ValueError('Original source exceeds 25 MiB parsing limit')
    raw = original.read_bytes()
    if sha256(raw).hexdigest() != document.get('sha256'):
        raise ValueError('Original source hash mismatch')
    if text_path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError('Cached extracted text exceeds 50 MiB limit')
    text_raw = text_path.read_bytes()
    extracted = json.loads(text_raw)
    if not isinstance(extracted, dict) or not isinstance(extracted.get('pages'), list):
        raise ValueError('Malformed cached text artifact')
    expected = {'sha256': document.get('sha256'), 'accession': document.get('accession'),
                'source_url': document.get('url')}
    if any(extracted.get(key) != value for key, value in expected.items()):
        raise ValueError('Cached text provenance mismatch')
    if _inside(root, extracted.get('source_path')) != original:
        raise ValueError('Cached text source path mismatch')
    if any(not isinstance(page, dict) or not isinstance(page.get('text'), str) for page in extracted['pages']):
        raise ValueError('Malformed cached page text')
    return raw, extracted, sha256(text_raw).hexdigest()


def analyze_collection(collection_dir: Path, output_dir: Path | None = None, *, max_candidates_per_document: int = 100) -> dict:
    """Analyze hash-checked retained documents; incomplete inputs stay visible.

    Each output is atomic and the summary is published last with output hashes.
    Consumers must verify those hashes to detect an interrupted mixed snapshot.
    """
    if max_candidates_per_document < 1 or max_candidates_per_document > 10000:
        raise ValueError('max_candidates_per_document must be between 1 and 10000')
    root = Path(collection_dir).resolve()
    output = Path(output_dir).resolve() if output_dir else root / 'money_analysis'
    inventory_bytes = (root / 'manifest.json').read_bytes()
    inventory = json.loads(inventory_bytes)
    if not isinstance(inventory, dict) or not isinstance(inventory.get('documents'), list):
        raise ValueError('Malformed collection manifest')
    records, candidates, comparisons, summaries, errors, warnings = [], [], [], [], [], []
    if inventory.get('run_status') != 'complete':
        warnings.append('Input collection did not complete; analysis covers retained documents only')
    if not inventory['documents']:
        warnings.append('No retained documents to analyze')
    implementation = _implementation_hash()
    for document in inventory['documents']:
        if not isinstance(document, dict):
            errors.append({'stage': 'document', 'message': 'Malformed document metadata'})
            continue
        summary = {'cik': document.get('cik'), 'accession': document.get('accession'),
                   'source_url': document.get('url'), 'status': 'error', 'reused': False}
        summaries.append(summary)
        try:
            raw, extracted, text_hash = _load_document(root, document)
            analyzed_document = {**document, 'source_path': str(_inside(root, document.get('source_path'))),
                                 'text_path': str(_inside(root, document.get('text_path'))), 'extracted_text_sha256': text_hash}
            stable_metadata = {key: analyzed_document.get(key) for key in ('cik', 'accession', 'filename', 'url', 'source_path', 'text_path', 'sha256', 'form', 'filed', 'reportDate', 'acceptanceDateTime')}
            fingerprint = _hash({'revision': ANALYZER_REVISION, 'implementation_sha256': implementation,
                                 'document': stable_metadata, 'extracted_text_sha256': text_hash,
                                 'max_candidates': max_candidates_per_document})
            cache_name = _hash([document.get('cik'), document.get('accession'), document.get('url')])
            cache = output / 'cache' / (cache_name + '.json')
            result = None
            if cache.is_file():
                try:
                    saved = json.loads(cache.read_bytes())
                    previous = saved.get('result')
                    if (saved.get('fingerprint') == fingerprint and isinstance(previous, dict)
                            and isinstance(previous.get('records'), list) and isinstance(previous.get('candidates'), list)
                            and isinstance(previous.get('coverage'), dict) and saved.get('result_sha256') == _hash(previous)):
                        result = previous
                        summary['reused'] = True
                except (ValueError, OSError, AttributeError):
                    pass
            if result is None:
                result = build_document_records(raw, analyzed_document, extracted, max_candidates=max_candidates_per_document)
                _atomic(cache, _serialized({'fingerprint': fingerprint, 'result_sha256': _hash(result), 'result': result}) + b'\n')
            records.extend(result['records'])
            candidates.extend(result['candidates'])
            summary.update(status='analyzed', coverage=result['coverage'], extracted_text_sha256=text_hash)
            if result['coverage'].get('incomplete'):
                warnings.append(f"Incomplete parsing/candidate coverage for {document.get('url')}")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            errors.append({'stage': 'document', 'cik': document.get('cik'), 'source_url': document.get('url'),
                           'error_type': type(exc).__name__, 'message': str(exc)})
    for company in inventory.get('companies', []):
        try:
            cik = str(company['cik'])
            if not cik.isdigit() or len(cik) > 10:
                raise ValueError('Invalid company CIK')
            coverage = company.get('coverage', {})
            if coverage.get('companyfacts') != 'available':
                warnings.append(f'CompanyFacts unavailable for {cik}')
                continue
            path = _inside(root, str(root / 'cache' / cik / 'companyfacts.json'))
            data = path.read_bytes()
            digest = sha256(data).hexdigest()
            if digest != coverage.get('companyfacts_sha256'):
                raise ValueError('CompanyFacts response hash mismatch')
            payload = json.loads(data)
            if str(payload.get('cik', '')).zfill(10) != cik.zfill(10):
                raise ValueError('CompanyFacts entity mismatch')
            accessions = {d.get('accession') for d in inventory['documents'] if isinstance(d, dict) and str(d.get('cik')) == cik}
            rows = [r for r in cash_flow_rows(cik, payload) if r['accession'] in accessions]
            for row in rows:
                row.update(data_sha256=digest, data_path=str(path))
            comparisons.extend(companyfacts_records(rows))
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append({'stage': 'companyfacts', 'message': str(exc), 'error_type': type(exc).__name__})
    records = consolidate_records(records)
    output_hashes = {}
    for filename, rows in [('money_records.jsonl', records), ('review_candidates.jsonl', candidates), ('comparison_facts.jsonl', comparisons)]:
        data = b''.join(_serialized(row) + b'\n' for row in rows)
        _atomic(output / filename, data)
        output_hashes[filename] = sha256(data).hexdigest()
    result = {'schema_version': '1.0', 'analyzer_revision': ANALYZER_REVISION,
              'implementation_sha256': implementation, 'analyzed_at_utc': datetime.now(timezone.utc).isoformat(),
              'collection_dir': str(root), 'collection_manifest_sha256': sha256(inventory_bytes).hexdigest(),
              'run_status': 'partial' if errors or warnings else 'complete',
              'document_count': len(inventory['documents']), 'analyzed_document_count': sum(s['status'] == 'analyzed' for s in summaries),
              'reused_document_count': sum(s['reused'] for s in summaries), 'record_count': len(records),
              'parsed_record_count': sum(r['status'] == 'parsed' for r in records),
              'review_record_count': sum(r['status'] == 'review_required' for r in records),
              'candidate_count': len(candidates), 'comparison_fact_count': len(comparisons),
              'output_sha256': output_hashes, 'documents': summaries, 'errors': errors,
              'coverage_warnings': warnings, 'settings': {'max_candidates_per_document': max_candidates_per_document},
              'interpretation': 'Reported observations and unresolved candidates; not a transaction ledger or verified loan database'}
    _atomic(output / 'analysis_manifest.json', _serialized(result) + b'\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection-dir', type=Path, default=Path('data/processed/reit_financials'))
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--max-candidates-per-document', type=int, default=100)
    args = parser.parse_args(argv)
    try:
        result = analyze_collection(args.collection_dir, args.output_dir, max_candidates_per_document=args.max_candidates_per_document)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Analysis stopped: {exc}\n')
    print(f"Analyzed {result['analyzed_document_count']} documents: {result['parsed_record_count']} parsed records, "
          f"{result['review_record_count']} records and {result['candidate_count']} candidates needing review")
    return 0 if result['run_status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
