"""Process only an explicit finite JSONL manifest, checkpointing each record."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.document_manifest import atomic_json
from src.document_transcript import extract_path, normalize_ocr, ADAPTER_REVISION, NORMALIZATION_VERSION

BATCH_REVISION = 'document_batch_v2'


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def read_manifest(path, *, unique_documents=True):
    path = Path(path).resolve()
    rows = []
    with path.open(encoding='utf-8-sig') as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f'Malformed input manifest line {number}') from exc
            if not isinstance(row, dict) or not isinstance(row.get('document_id'), str) or not row['document_id'] or not isinstance(row.get('source_path'), str) or not row['source_path']:
                raise ValueError(f'Manifest line {number} requires document_id and source_path')
            source = Path(row['source_path'])
            row['source_path'] = str((path.parent / source).resolve() if not source.is_absolute() else source.resolve())
            rows.append(row)
    if not rows:
        raise ValueError('Input manifest is empty')
    if unique_documents and len({r['document_id'] for r in rows}) != len(rows):
        raise ValueError('Manifest document_id values must be unique')
    return rows


def read_journal(path):
    if not path.exists():
        return []
    rows = []
    with path.open(encoding='utf8') as handle:
        for number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or row.get('status') not in ('completed', 'failed'):
                    raise ValueError('Invalid record')
                rows.append(row)
            except (ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f'Output journal is damaged at line {number}; preserve it and repair before resuming') from exc
    return rows


def append_record(path, record):
    with path.open('a', encoding='utf8', newline='\n') as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def run_batch(manifest, output_dir, config):
    rows = read_manifest(manifest)
    # argparse uses Path objects; checkpoints must contain portable JSON values.
    config = json.loads(json.dumps(dict(config), default=str))
    runtime_versions = {}
    for dependency in ('Pillow', 'pypdfium2', 'pytesseract', 'transformers', 'torch'):
        try:
            runtime_versions[dependency] = version(dependency)
        except PackageNotFoundError:
            runtime_versions[dependency] = None
    config['runtime_versions'] = runtime_versions
    config['transcript_adapter_revision'] = ADAPTER_REVISION
    config['normalization_version'] = NORMALIZATION_VERSION
    engine = config.get('engine', 'native')
    if engine not in ('native', 'tesseract', 'glm'):
        raise ValueError('engine must be native, tesseract or glm')
    provider = None
    if engine == 'glm':
        from src.glm_document_ocr import GLMConfig, GLMOCRProvider
        provider = GLMOCRProvider(GLMConfig(
            model_revision=config['model_revision'], cache_dir=config['model_cache'],
            device=config.get('device', 'cuda:0'), dtype=config.get('dtype', 'bfloat16'),
            allow_download=config.get('allow_download', False), max_new_tokens=config.get('max_new_tokens', 4096)))
        config['provider'] = provider.config.provenance()
    fingerprint = hashlib.sha256(json.dumps({'batch_revision': BATCH_REVISION, 'config': config},
                                            sort_keys=True, default=str).encode()).hexdigest()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    journal = output / 'manifest.jsonl'
    # A process lock prevents racing resumes and interleaved journal writes.
    lock = output / '.batch.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError('Batch output is locked; verify no worker is alive before removing .batch.lock') from exc
    os.close(fd)
    counts = {'completed': 0, 'failed': 0, 'skipped': 0, 'records': len(rows)}
    try:
        completed = {r['resume_key']: r for r in read_journal(journal) if r['status'] == 'completed'}
        for row in rows:
            record = {'document_id': row['document_id'], 'source_path': row['source_path'],
                      'config_fingerprint': fingerprint, 'config': config,
                      'batch_revision': BATCH_REVISION, 'input_record': row}
            try:
                source = Path(row['source_path'])
                source_hash = digest(source)
                record['source_sha256'] = source_hash
                if row.get('source_sha256') and source_hash != row['source_sha256']:
                    raise ValueError('Source hash differs from explicit manifest')
                input_record_hash = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                record['input_record_sha256'] = input_record_hash
                key = hashlib.sha256(json.dumps([row['document_id'], source_hash, fingerprint, input_record_hash]).encode()).hexdigest()
                record['resume_key'] = key
                if key in completed:
                    prior = completed[key]
                    if digest(prior['output_path']) != prior['output_sha256']:
                        raise ValueError('Completed output changed; immutable artifact verification failed')
                    if prior.get('ocr_path') and digest(prior['ocr_path']) != prior['ocr_sha256']:
                        raise ValueError('Completed OCR output changed')
                    counts['skipped'] += 1
                    continue
                suffix = source.suffix.lower()
                if suffix in ('.pdf', '.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp', '.webp'):
                    if engine == 'glm':
                        from src.glm_document_ocr import extract_document
                        raw = asdict(extract_document(source, provider=provider, dpi=config.get('dpi', 300),
                                                     force_ocr=config.get('force_ocr', False)))
                    elif engine == 'tesseract':
                        from src.document_ocr import extract_document
                        raw = asdict(extract_document(source, dpi=config.get('dpi', 300), force_ocr=config.get('force_ocr', False)))
                    elif suffix == '.pdf':
                        from src.document_ocr import _native_pdf_texts
                        texts = _native_pdf_texts(source)
                        if not texts or any(t is None for t in texts):
                            raise ValueError('native engine requires OCR for this PDF; choose tesseract or glm explicitly')
                        raw = {'sha256': source_hash, 'engine': 'pdfium', 'engine_version': 'native_pdfium',
                               'pages': [{'number': i, 'text': text, 'confidence': None,
                                          'method': 'native_pdf_text'} for i, text in enumerate(texts, 1)]}
                    else:
                        raise ValueError('Image input requires explicitly selected OCR engine')
                    ocr_path = output / (key + '.ocr.json')
                    atomic_json(ocr_path, raw)
                    record.update(ocr_path=str(ocr_path), ocr_sha256=digest(ocr_path))
                    transcript = normalize_ocr(raw, row['document_id'])
                else:
                    transcript = extract_path(source, row['document_id'], source_hash)
                if digest(source) != source_hash:
                    raise ValueError('Source changed during extraction')
                artifact = output / (key + '.transcript.json')
                atomic_json(artifact, transcript)
                record.update(status='completed', output_path=str(artifact), output_sha256=digest(artifact))
                counts['completed'] += 1
            except Exception as exc:
                record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
                counts['failed'] += 1
            record['processing_completed_at_utc'] = datetime.now(timezone.utc).isoformat()
            append_record(journal, record)
        return counts
    finally:
        lock.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--engine', choices=('native', 'tesseract', 'glm'), default='native')
    parser.add_argument('--model-revision')
    parser.add_argument('--model-cache', type=Path)
    parser.add_argument('--device', default='cuda:0')
    parser.add_argument('--dtype', choices=('bfloat16', 'float16'), default='bfloat16')
    parser.add_argument('--max-new-tokens', type=int, default=4096)
    parser.add_argument('--dpi', type=int, default=300)
    parser.add_argument('--force-ocr', action='store_true')
    parser.add_argument('--allow-download', action='store_true')
    args = parser.parse_args(argv)
    config = vars(args).copy()
    config.pop('manifest')
    config.pop('output_dir')
    if args.engine == 'glm' and (not args.model_revision or not args.model_cache):
        parser.error('glm requires --model-revision and --model-cache')
    result = run_batch(args.manifest, args.output_dir, config)
    print(json.dumps(result))
    return 1 if result['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
