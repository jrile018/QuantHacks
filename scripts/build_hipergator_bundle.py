"""Stage an explicit portable code/document bundle; never include secrets or full data."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import io

ROOT = Path(__file__).resolve().parents[1]


def build(output, manifest):
    manifest = Path(manifest).resolve()
    paths = [Path('src/__init__.py'), Path('requirements-ocr.txt'), Path('requirements-gpu-ocr.txt'), Path('requirements-training.txt')]
    for pattern in ('src/document_*.py', 'src/glm_document_ocr.py', 'src/options_learning.py',
                    'scripts/analyze_8k_documents.py', 'scripts/run_document_batch.py',
                    'scripts/export_ocr_training_pairs.py', 'scripts/train_options_model.py',
                    'hpc/*.py', 'hpc/*.sbatch', 'configs/8k_document_analysis.json',
                    'configs/options_learning.json', 'configs/hipergator.example.json'):
        paths.extend(p.relative_to(ROOT) for p in ROOT.glob(pattern))
    files = {str(p).replace('\\', '/'): (ROOT / p).read_bytes() for p in sorted(set(paths)) if (ROOT / p).is_file()}
    records = []
    for line in Path(manifest).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        path = Path(row['source_path'])
        if not path.is_absolute():
            path = manifest.parent / path
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != row['source_sha256']:
            raise ValueError('Pilot source hash mismatch')
        relative = 'pilot/documents/' + digest + path.suffix
        files[relative] = data
        row['source_path'] = 'documents/' + digest + path.suffix
        # Local receipt is source provenance; deployment does not backdate it.
        records.append(row)
    files['pilot/documents.jsonl'] = ''.join(json.dumps(r) + '\n' for r in records).encode()
    selection_path = Path(manifest).parent / 'selection.json'
    filings = []
    if selection_path.is_file():
        for filing in json.loads(selection_path.read_text())['filings']:
            if not filing.get('submission_path'):
                continue
            source = Path(filing['submission_path'])
            if not source.is_absolute():
                source = selection_path.parent / source
            raw = source.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != filing['submission_sha256']:
                raise ValueError('Submission source hash mismatch')
            name = 'pilot/submissions/' + digest + '.txt'
            files[name] = raw
            filings.append({'cik': filing['cik'], 'accession': filing['accession'],
                            'submission_path': 'submissions/' + digest + '.txt', 'source_sha256': digest})
    files['pilot/filings.json'] = json.dumps(filings, indent=2).encode()
    metadata = {'schema_version': '1.0', 'documents': len(records),
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
                'excluded': ['.env', '.ssh', '.git', 'model weights', 'unselected data', 'API credentials']}
    files['bundle-manifest.json'] = json.dumps(metadata, indent=2).encode()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz') as archive:
        for name, data in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o644
            archive.addfile(entry, io.BytesIO(data))
    return {'bundle': str(output.resolve()), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'bytes': output.stat().st_size, 'files': len(files), 'documents': len(records)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/processed/document_pilot/documents.jsonl')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/processed/hipergator/quanthaxs-pilot.tar.gz')
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.manifest), indent=2))


if __name__ == '__main__':
    main()
