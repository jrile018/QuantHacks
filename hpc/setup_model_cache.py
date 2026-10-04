"""Explicitly populate pinned GLM/FinBERT caches, without running inference."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.glm_document_ocr import (MODEL_ID, VERIFIED_MODEL_REVISION, GLMConfig,
                                  INFERENCE_FILE_PATTERNS, resolve_model_snapshot)

FINBERT_ID = 'ProsusAI/finbert'
FINBERT_REVISION = 'db38d3727cbaed87c9aed72df7b3519e2ba5cca1'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--model', choices=('glm', 'finbert', 'both'), default='glm')
    parser.add_argument('--glm-revision', default=VERIFIED_MODEL_REVISION)
    parser.add_argument('--download', action='store_true', help='explicitly authorize checkpoint downloads')
    args = parser.parse_args(argv)
    GLMConfig(args.glm_revision, args.cache_dir)
    models = []
    if args.model in ('glm', 'both'):
        models.append((MODEL_ID, args.glm_revision))
    if args.model in ('finbert', 'both'):
        models.append((FINBERT_ID, FINBERT_REVISION))
    results = []
    for model_id, revision in models:
        # Native safetensors only: legacy pickle files are not needed by this pipeline.
        path = resolve_model_snapshot(model_id, revision, args.cache_dir, allow_download=args.download)
        results.append({'model_id': model_id, 'revision': revision, 'snapshot_path': path})
    print(json.dumps(results, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
