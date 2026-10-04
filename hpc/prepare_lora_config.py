"""Generate the official GLM-OCR LLaMA-Factory LoRA recipe for reviewed data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_document_batch import digest
from scripts.export_ocr_training_pairs import export_pairs
from src.document_manifest import atomic_json
from src.glm_document_ocr import GLMConfig, MODEL_ID
from hpc.setup_model_cache import resolve_model_snapshot


def prepare_config(manifest, dataset_dir, output_dir, model_revision, model_cache, dtype='bfloat16'):
    output = Path(output_dir).resolve()
    if output.exists():
        raise ValueError('LoRA requires a fresh output directory; existing output cannot be resumed or overwritten')
    GLMConfig(model_revision, model_cache, dtype=dtype)
    dataset = Path(dataset_dir).resolve()
    provenance = json.loads((dataset / 'provenance.json').read_text(encoding='utf8'))
    if provenance['manifest_sha256'] != digest(manifest):
        raise ValueError('Reviewed dataset differs from the supplied input manifest')
    # Re-run all provenance/split checks before training; never trust a modified export.
    import tempfile
    with tempfile.TemporaryDirectory() as scratch:
        export_pairs(manifest, scratch)
        for name in ('train.json', 'validation.json', 'dataset_info.json', 'provenance.json'):
            expected = json.loads((Path(scratch) / name).read_text(encoding='utf8'))
            actual = json.loads((dataset / name).read_text(encoding='utf8'))
            if expected != actual:
                raise ValueError('Training artifact differs from reviewed export: ' + name)
    for row in provenance['records']:
        if digest(dataset / row['export_image_path']) != row['image_sha256']:
            raise ValueError('Exported training image hash mismatch')
    snapshot = resolve_model_snapshot(MODEL_ID, model_revision, model_cache)
    # Atomic directory creation also rejects a concurrent preparation of this run.
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ValueError('LoRA requires a fresh output directory') from exc
    config = {'model_name_or_path': snapshot, 'trust_remote_code': False, 'stage': 'sft',
              'do_train': True, 'do_eval': True, 'finetuning_type': 'lora', 'lora_rank': 8,
              'lora_target': 'all', 'dataset_dir': str(dataset), 'dataset': 'reviewed_ocr_train',
              'eval_dataset': 'reviewed_ocr_validation', 'template': 'glm_ocr', 'cutoff_len': 4096,
              'preprocessing_num_workers': 2, 'dataloader_num_workers': 2,
              'output_dir': str(output / 'adapter'), 'logging_steps': 1, 'save_steps': 100,
              'overwrite_output_dir': False, 'save_only_model': False, 'report_to': 'none',
              'per_device_train_batch_size': 1, 'per_device_eval_batch_size': 1,
              'gradient_accumulation_steps': 4, 'learning_rate': 1e-4, 'num_train_epochs': 3,
              'lr_scheduler_type': 'cosine', 'warmup_ratio': .1,
              'bf16': dtype == 'bfloat16', 'fp16': dtype == 'float16', 'seed': 42}
    # JSON is valid YAML; the .yaml extension selects the factory's working loader.
    atomic_json(output / 'lora-config.yaml', config)
    atomic_json(output / 'training-provenance.json', {'model_id': MODEL_ID, 'model_revision': model_revision,
                'dataset_manifest_sha256': provenance['manifest_sha256'], 'dataset_provenance': provenance,
                'training_config': config, 'status': 'prepared_not_trained'})
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('manifest', 'dataset-dir', 'output-dir', 'model-revision', 'model-cache'):
        parser.add_argument('--' + key, required=True)
    parser.add_argument('--dtype', choices=('bfloat16', 'float16'), default='bfloat16')
    args = parser.parse_args(argv)
    prepare_config(**vars(args))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
