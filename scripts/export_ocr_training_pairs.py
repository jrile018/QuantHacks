"""Export reviewed OCR image/transcript pairs to official LLaMA-Factory format."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_document_batch import read_manifest, digest
from src.document_manifest import atomic_json


def export_pairs(manifest, output_dir):
    rows = read_manifest(manifest, unique_documents=False)
    root = Path(manifest).resolve().parent
    validated = []
    for row in rows:
        required = ('image_path', 'source_sha256', 'transcript', 'annotator', 'rubric_revision',
                    'company_id', 'public_at_utc', 'split', 'page_number')
        if any(not row.get(k) for k in required):
            raise ValueError('Reviewed pair is missing required provenance fields')
        if row.get('annotation_status') not in ('human_reviewed', 'adjudicated'):
            raise ValueError('OCR training requires human_reviewed or adjudicated transcripts')
        if row['split'] not in ('train', 'validation'):
            raise ValueError('split must be train or validation')
        if not isinstance(row['transcript'], str) or not row['transcript'].strip():
            raise ValueError('Reviewed transcript must be nonempty text')
        if not isinstance(row['page_number'], int) or row['page_number'] < 1:
            raise ValueError('page_number must be positive')
        image = Path(row['image_path'])
        image = (root / image).resolve() if not image.is_absolute() else image.resolve()
        if image.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.webp', '.bmp'):
            raise ValueError('Training image must be a supported image file')
        image_hash = digest(image)
        if row.get('image_sha256') and row['image_sha256'] != image_hash:
            raise ValueError('Training image hash mismatch')
        if digest(row['source_path']) != row['source_sha256']:
            raise ValueError('Original source hash mismatch')
        raw_time = row['public_at_utc']
        try:
            time = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
        except (ValueError, TypeError) as exc:
            raise ValueError('public_at_utc must be an ISO timestamp') from exc
        if time.tzinfo is None:
            raise ValueError('public_at_utc requires a timezone')
        validated.append((row, image, image_hash, time.astimezone(timezone.utc)))
    split_rows = {split: [r for r in validated if r[0]['split'] == split] for split in ('train', 'validation')}
    if any(not rows for rows in split_rows.values()):
        raise ValueError('Both explicit train and validation splits are required')
    for field in ('document_id', 'company_id', 'source_sha256'):
        if {r[0][field] for r in split_rows['train']} & {r[0][field] for r in split_rows['validation']}:
            raise ValueError(f'{field} leakage across train/validation')
    if {r[2] for r in split_rows['train']} & {r[2] for r in split_rows['validation']}:
        raise ValueError('Image hash leakage across train/validation')
    if max(r[3] for r in split_rows['train']) >= min(r[3] for r in split_rows['validation']):
        raise ValueError('Training must strictly precede validation in time')
    output = Path(output_dir).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Training output directory must be new or empty')
    output.mkdir(parents=True, exist_ok=True)
    image_dir = output / 'images'
    image_dir.mkdir(exist_ok=True)
    datasets = {'train': [], 'validation': []}
    provenance = []
    for row, image, image_hash, time in validated:
        name = image_hash + image.suffix.lower()
        copied = image_dir / name
        shutil.copyfile(image, copied)
        if digest(copied) != image_hash or digest(image) != image_hash or digest(row['source_path']) != row['source_sha256']:
            raise ValueError('Training source changed during export')
        datasets[row['split']].append({'messages': [
            {'role': 'user', 'content': '<image>Text Recognition:'},
            {'role': 'assistant', 'content': row['transcript']}],
            'images': ['images/' + name]})
        provenance.append({**row, 'image_sha256': image_hash,
                           'transcript_sha256': __import__('hashlib').sha256(row['transcript'].encode()).hexdigest(),
                           'export_image_path': 'images/' + name, 'public_at_utc': time.isoformat()})
    info = {}
    for split, dataset in datasets.items():
        atomic_json(output / (split + '.json'), dataset)
        info['reviewed_ocr_' + split] = {
            'file_name': split + '.json', 'formatting': 'sharegpt',
            'columns': {'messages': 'messages', 'images': 'images'},
            'tags': {'role_tag': 'role', 'content_tag': 'content', 'user_tag': 'user', 'assistant_tag': 'assistant'}}
    atomic_json(output / 'dataset_info.json', info)
    report = {'schema_version': '1.0', 'manifest_sha256': digest(manifest),
              'counts': {k: len(v) for k, v in datasets.items()}, 'records': provenance,
              'split_policy': 'document_source_image_company_disjoint_train_strictly_before_validation'}
    atomic_json(output / 'provenance.json', report)
    return {'counts': report['counts'], 'output_dir': str(output)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(export_pairs(args.manifest, args.output_dir)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
