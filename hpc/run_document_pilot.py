"""Run the staged native/OCR and frozen FinBERT pilot on a Slurm GPU node."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.document_manifest import atomic_json
from hpc.setup_model_cache import FINBERT_ID, FINBERT_REVISION, resolve_model_snapshot
from src.glm_document_ocr import VERIFIED_MODEL_REVISION
from scripts.run_document_batch import read_journal, read_manifest, digest
from src.document_ocr import SUPPORTED_SUFFIXES


FENCE_LINE = re.compile(r'^\s*(?:`{3,}|~{3,})(?:[A-Za-z0-9_+.-]+)?\s*(?:`{3,}|~{3,})?\s*$')


def has_ocr_content(text):
    """Fence labels, empty HTML tags and Markdown separators are not OCR text."""
    content = '\n'.join(line for line in text.splitlines() if not FENCE_LINE.fullmatch(line))
    content = html.unescape(re.sub(r'<[^>]*>', '', content))
    return any(character.isalnum() for character in content)


def validate_ocr_batch(input_manifest, batch_dir):
    """Accept this pilot's selected nonblank PDF/image sources, bound to artifacts.

    This is a pilot acceptance check, not an OCR policy for arbitrary blank PDFs.
    Native HTML/text rows are covered by the accession report checks instead.
    """
    selected = [row for row in read_manifest(input_manifest)
                if Path(row['source_path']).suffix.lower() in SUPPORTED_SUFFIXES]
    journal = read_journal(Path(batch_dir) / 'manifest.jsonl')
    for source in selected:
        document_id = source['document_id']
        matches = [row for row in journal if row.get('document_id') == document_id]
        if len(matches) != 1:
            raise RuntimeError('Missing or ambiguous selected OCR result: ' + document_id)
        row = matches[0]
        if row['status'] != 'completed':
            raise RuntimeError('Selected OCR extraction failed: ' + document_id)
        source_hash = digest(source['source_path'])
        if (source.get('source_sha256') and source['source_sha256'] != source_hash
                or row.get('source_sha256') != source_hash):
            raise ValueError('Selected OCR original source hash mismatch: ' + document_id)
        if not row.get('ocr_path') or not row.get('ocr_sha256'):
            raise RuntimeError('Missing selected OCR artifact: ' + document_id)
        artifact = Path(row['ocr_path'])
        if not artifact.is_absolute():
            artifact = Path(batch_dir) / artifact
        if digest(artifact) != row['ocr_sha256']:
            raise ValueError('Selected OCR artifact hash mismatch: ' + document_id)
        payload = json.loads(artifact.read_text(encoding='utf-8-sig'))
        if not isinstance(payload, dict) or payload.get('sha256') != source_hash:
            raise ValueError('Selected OCR payload original source hash mismatch: ' + document_id)
        pages = payload.get('pages')
        if not isinstance(pages, list) or any(not isinstance(page, dict) or not isinstance(page.get('text'), str) for page in pages):
            raise ValueError('Malformed selected OCR pages: ' + document_id)
        if not any(has_ocr_content(page['text']) for page in pages):
            raise RuntimeError('Empty or formatting-only selected OCR output: ' + document_id)
    return {'status': 'passed', 'checked_documents': len(selected)}


def read_filings(path):
    filings = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(filings, list) or not filings:
        raise ValueError('Combined OCR/wording pilot requires at least one filing')
    for filing in filings:
        if not all(filing.get(key) for key in ('cik', 'accession', 'submission_path', 'source_sha256')):
            raise ValueError('Incomplete filing identity or source provenance')
    return filings


def filing_ocr_map(batch_dir, filing):
    mapping = {}
    for row in read_journal(Path(batch_dir) / 'manifest.jsonl'):
        metadata = row.get('input_record', {})
        if (str(metadata.get('cik', '')).lstrip('0') != str(filing['cik']).lstrip('0')
                or metadata.get('accession') != filing['accession']):
            continue
        if row['status'] != 'completed':
            raise RuntimeError('Filing document extraction failed in GPU batch')
        if not row.get('ocr_path'):
            continue
        artifact = Path(row['ocr_path']).resolve()
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != row['ocr_sha256']:
            raise ValueError('Batch OCR artifact hash mismatch')
        filename = metadata.get('filename')
        if not filename or filename in mapping:
            raise ValueError('Missing or duplicate filing filename in OCR map')
        mapping[filename] = str(artifact)
    return mapping


def validate_report(report):
    if not report['wording']['provider_revisions'].get('finbert'):
        raise RuntimeError('FinBERT provider unavailable in produced report')
    selected = [row for row in report['inventory'] if row.get('wording_selected')]
    if not selected or any(row['inventory_status'] != 'complete' for row in selected):
        raise RuntimeError('Selected filing document extraction is incomplete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-cache', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'pilot/documents.jsonl')
    parser.add_argument('--filings', type=Path, default=ROOT / 'pilot/filings.json')
    args = parser.parse_args()
    filings = read_filings(args.filings)
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('Run the actual model pilot through Slurm on an allocated GPU node')
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError('Allocated GPU is unavailable')
    dtype = 'bfloat16' if torch.cuda.is_bf16_supported() else 'float16'
    finbert = resolve_model_snapshot(FINBERT_ID, FINBERT_REVISION, args.model_cache)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {'job_id': os.environ['SLURM_JOB_ID'], 'status': 'started',
                'gpu': torch.cuda.get_device_name(0), 'reports': [], 'failures': [],
                'started_at_utc': datetime.now(timezone.utc).isoformat()}
    atomic_json(args.output_dir / 'pilot-run.json', manifest)
    batch = [sys.executable, str(ROOT / 'scripts/run_document_batch.py'), '--manifest', str(args.manifest),
             '--output-dir', str(args.output_dir / 'transcripts'), '--engine', 'glm',
             '--model-revision', VERIFIED_MODEL_REVISION, '--model-cache', str(args.model_cache), '--dtype', dtype]
    try:
        # The native filing reports can still succeed when a separate calibration
        # row fails; retain those reports before failing overall pilot acceptance.
        batch_result = subprocess.run(batch, check=False)
        manifest['batch_exit_code'] = batch_result.returncode
        ocr_error = None
        try:
            manifest['ocr_acceptance'] = validate_ocr_batch(args.manifest, args.output_dir / 'transcripts')
        except Exception as error:
            ocr_error = error
            manifest['ocr_acceptance'] = {'status': 'failed', 'error': type(error).__name__ + ': ' + str(error)}
        atomic_json(args.output_dir / 'pilot-run.json', manifest)
        for index, filing in enumerate(filings):
            source = args.filings.parent / filing['submission_path']
            if hashlib.sha256(source.read_bytes()).hexdigest() != filing['source_sha256']:
                raise ValueError('Staged submission hash mismatch')
            ocr_map = args.output_dir / f'filing-{index}-ocr-map.json'
            atomic_json(ocr_map, filing_ocr_map(args.output_dir / 'transcripts', filing))
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/analyze_8k_documents.py'),
                                     '--cik', filing['cik'], '--accession', filing['accession'],
                                     '--submission', str(source), '--output-dir', str(args.output_dir / 'reports'),
                                     '--ocr-map', str(ocr_map),
                                     '--raw-dir', str(args.output_dir / 'sources'), '--finbert-model', finbert,
                                     '--finbert-revision', FINBERT_REVISION, '--device', 'cuda:0'],
                                    check=True, text=True, capture_output=True)
            report_path = Path(result.stdout.strip())
            report = json.loads(report_path.read_text())
            validate_report(report)
            manifest['reports'].append(str(report_path))
            atomic_json(args.output_dir / 'pilot-run.json', manifest)
        if ocr_error is not None:
            raise ocr_error
        if batch_result.returncode:
            raise RuntimeError('Document batch failed with exit code ' + str(batch_result.returncode))
        manifest['status'] = 'completed'
    except Exception as error:
        manifest['status'] = 'failed'
        manifest['failures'].append({'type': type(error).__name__, 'detail': str(error)})
        raise
    finally:
        manifest['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        atomic_json(args.output_dir / 'pilot-run.json', manifest)
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
