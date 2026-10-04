"""Bounded Slurm-only OCR diagnostics; no training or evaluation claims."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-cache', required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--filings')
    args = parser.parse_args()
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('GPU diagnostic requires Slurm allocation')
    import torch
    from PIL import Image, ImageStat
    from transformers import AutoProcessor
    from src.glm_document_ocr import GLMConfig, GLMOCRProvider, MODEL_ID, VERIFIED_MODEL_REVISION
    rows = [json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
    row = next(row for row in rows if str(row['source_path']).endswith('.png'))
    path = args.manifest.parent / row['source_path']
    if hashlib.sha256(path.read_bytes()).hexdigest() != row['source_sha256']:
        raise ValueError('Diagnostic source hash mismatch')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    provider = GLMOCRProvider(GLMConfig(VERIFIED_MODEL_REVISION, args.model_cache))
    provider._load()
    image = Image.open(path).convert('RGB')
    result = {'job_id': os.environ['SLURM_JOB_ID'], 'source_sha256': row['source_sha256'],
              'image_size': image.size, 'image_stddev': ImageStat.Stat(image).stddev,
              'is_encoder_decoder': provider._model.config.is_encoder_decoder, 'cases': []}
    for name in ('current', 'explicit_images', 'slow_processor', 'top_half'):
        processor = provider._processor
        if name == 'slow_processor':
            processor = AutoProcessor.from_pretrained(MODEL_ID, revision=VERIFIED_MODEL_REVISION,
                cache_dir=args.model_cache, local_files_only=True, trust_remote_code=False, use_fast=False)
        source_image = image.crop((0, 0, image.width, image.height // 2)) if name == 'top_half' else image
        messages = [{'role': 'user', 'content': [{'type': 'image', 'image': source_image},
                    {'type': 'text', 'text': 'Text Recognition:'}]}]
        if name == 'explicit_images':
            prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=[prompt], images=[source_image], return_tensors='pt')
        else:
            inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                return_dict=True, return_tensors='pt')
        inputs = inputs.to('cuda:0')
        record = {'name': name, 'processor': type(processor.image_processor).__name__,
                  'input_shapes': {key: list(value.shape) for key, value in inputs.items()},
                  'prompt': processor.decode(inputs['input_ids'][0], skip_special_tokens=False)}
        if 'pixel_values' in inputs:
            pixels = inputs['pixel_values'].float()
            record['pixel_stats'] = {'min': pixels.min().item(), 'max': pixels.max().item(), 'std': pixels.std().item()}
        with torch.inference_mode():
            output = provider._model.generate(**inputs, max_new_tokens=2048, do_sample=False)
        prefix = inputs['input_ids'].shape[-1]
        record.update(input_tokens=prefix, output_tokens=output.shape[-1],
            prefix_matches=bool(torch.equal(output[0, :prefix], inputs['input_ids'][0])),
            decoded_full=processor.decode(output[0], skip_special_tokens=True),
            decoded_generated=processor.decode(output[0, prefix:], skip_special_tokens=True))
        result['cases'].append(record)
        (args.output_dir / 'diagnostics.json').write_text(json.dumps(result, indent=2))
        print(json.dumps({'case': name, 'generated_chars': len(record['decoded_generated']),
                          'input_shapes': record['input_shapes']}), flush=True)
        if source_image is not image:
            source_image.close()
    image.close()


if __name__ == '__main__':
    main()
