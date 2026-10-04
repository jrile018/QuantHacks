"""Explicit CUDA GLM-OCR inference; native PDF extraction stays model-free."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.metadata import version, PackageNotFoundError
import itertools
from pathlib import Path
import re

from src import document_ocr as ocr

ADAPTER_REVISION = 'glm_document_ocr_v3_local_processor'
MODEL_ID = 'zai-org/GLM-OCR'
VERIFIED_MODEL_REVISION = '2e85a62840ccac27daa451df36c736c4636b8628'
INFERENCE_FILE_PATTERNS = ['*.json', '*.safetensors', '*.jinja', '*.txt', '*.model']


def resolve_model_snapshot(model_id, revision, cache_dir, *, allow_download=False):
    """Resolve a pinned inference snapshot with matching online/offline scope."""
    from huggingface_hub import snapshot_download
    return snapshot_download(model_id, revision=revision, cache_dir=str(cache_dir),
                             local_files_only=not allow_download,
                             allow_patterns=INFERENCE_FILE_PATTERNS)


@dataclass(frozen=True)
class GLMConfig:
    model_revision: str
    cache_dir: str | Path
    device: str = 'cuda:0'
    dtype: str = 'bfloat16'
    allow_download: bool = False
    max_new_tokens: int = 4096

    def __post_init__(self):
        if not re.fullmatch(r'[0-9a-f]{40}', self.model_revision):
            raise ValueError('model_revision must be a full immutable Hugging Face commit SHA')
        if not re.fullmatch(r'cuda(?::\d+)?', self.device):
            raise ValueError('GLM OCR requires an explicitly selected CUDA device')
        if self.dtype not in ('bfloat16', 'float16'):
            raise ValueError('dtype must be bfloat16 or float16')
        if not self.cache_dir or self.max_new_tokens <= 0:
            raise ValueError('cache_dir and positive max_new_tokens are required')

    def provenance(self):
        result = asdict(self)
        result['cache_dir'] = str(self.cache_dir)
        result.update(model_id=MODEL_ID, adapter_revision=ADAPTER_REVISION,
                      prompt='Text Recognition:', do_sample=False,
                      processor_class='Glm46VProcessor', processor_use_fast=True,
                      loading='pinned_local_snapshot')
        return result


class GLMOCRProvider:
    def __init__(self, config: GLMConfig):
        self.config = config
        self._model = self._processor = self._torch = None

    def _load(self):
        if self._model is not None:
            return
        try:
            import torch
            from transformers import Glm46VProcessor, GlmOcrForConditionalGeneration
        except ImportError as exc:
            raise RuntimeError('Install requirements-gpu-ocr.txt in the allocated GPU environment') from exc
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA is unavailable; run GLM OCR on an allocated Slurm GPU node')
        if self.config.dtype == 'bfloat16' and not torch.cuda.is_bf16_supported():
            raise RuntimeError('Allocated GPU does not support bfloat16; explicitly select float16')
        snapshot = resolve_model_snapshot(MODEL_ID, self.config.model_revision,
                                          self.config.cache_dir, allow_download=self.config.allow_download)
        if not (Path(snapshot) / 'processor_config.json').is_file():
            raise RuntimeError('Pinned OCR snapshot lacks processor_config.json; repair the cache before inference')
        options = dict(local_files_only=True, trust_remote_code=False)
        processor = Glm46VProcessor.from_pretrained(snapshot, **options, use_fast=True)
        model = GlmOcrForConditionalGeneration.from_pretrained(
            snapshot, **options, dtype=getattr(torch, self.config.dtype),
            attn_implementation='sdpa')
        model.to(self.config.device)
        model.eval()
        self._model, self._processor, self._torch = model, processor, torch

    def recognize(self, image):
        self._load()
        messages = [{'role': 'user', 'content': [
            {'type': 'image', 'image': image}, {'type': 'text', 'text': 'Text Recognition:'}]}]
        inputs = self._processor.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            return_dict=True, return_tensors='pt').to(self.config.device)
        for key in ('pixel_values', 'image_grid_thw'):
            value = inputs.get(key)
            if value is None or value.numel() == 0:
                raise RuntimeError('OCR processor omitted image data (' + key +
                                   '); verify the pinned processor configuration before inference')
        with self._torch.inference_mode():
            output = self._model.generate(**inputs, max_new_tokens=self.config.max_new_tokens,
                                          do_sample=False)
        # GLM is decoder-only: the returned sequence contains the prompt tokens.
        tokens = output[0, inputs['input_ids'].shape[-1]:]
        flags = []
        if len(tokens) >= self.config.max_new_tokens:
            flags.append('generation_token_limit_reached')
        return self._processor.decode(tokens, skip_special_tokens=True), flags


def extract_document(path, *, provider: GLMOCRProvider, dpi=300, force_ocr=False):
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() not in ocr.SUPPORTED_SUFFIXES:
        raise ValueError('Unsupported document type: ' + source.suffix)
    if dpi <= 0:
        raise ValueError('dpi must be positive')
    source_hash = ocr._sha256(source)
    diagnostics = []
    native = ocr._native_pdf_texts(source, diagnostics=diagnostics, force_ocr=force_ocr) if source.suffix.lower() == '.pdf' else []
    needed = {i for i, value in enumerate(native, 1) if value is None}
    images = iter(ocr._page_images(source, dpi, needed if native else None)) if needed or not native else iter(())
    pages, rendered = [], []
    try:
        for number in range(1, len(native) + 1) if native else itertools.count(1):
            if native and native[number - 1] is not None:
                pages.append(ocr.OCRPage(number, native[number - 1], None, 'native_pdf_text',
                                         ['native_text_completeness_unverified'], native_text=native[number - 1]))
                continue
            try:
                image = next(images)
            except StopIteration:
                if native:
                    raise ValueError(f'PDF page {number} could not be rendered')
                break
            try:
                # The shared renderer bounds PDF/image dimensions before inference.
                ocr._prepare_image(image, False)
                text, flags = provider.recognize(image)
                rendered.append({'page': number, 'width': image.size[0], 'height': image.size[1]})
                flags = list(flags) + ['machine_unreviewed', 'unverified_table_or_reading_order']
                if not text.strip():
                    flags.append('empty_text')
                native_text = diagnostics[number - 1].get('native_text') if diagnostics else None
                pages.append(ocr.OCRPage(number, text, None, 'glm_ocr', flags, native_text=native_text))
            finally:
                image.close()
    finally:
        if hasattr(images, 'close'):
            images.close()
    if not pages:
        raise ValueError('Document contains no pages')
    if ocr._sha256(source) != source_hash:
        raise RuntimeError('Source changed during extraction')
    settings = provider.config.provenance()
    settings.update(dpi=dpi, force_ocr=force_ocr, renderer_pages=rendered,
                    max_image_dimension=ocr.MAX_OCR_DIMENSION, pdf_page_diagnostics=diagnostics)
    try:
        settings['transformers_version'] = version('transformers') if rendered else None
    except PackageNotFoundError:
        settings['transformers_version'] = None
    try:
        settings['pdfium_version'] = version('pypdfium2') if native else None
    except PackageNotFoundError:
        settings['pdfium_version'] = None
    engine = 'mixed' if rendered and any(p.method == 'native_pdf_text' for p in pages) else 'glm_ocr' if rendered else 'pdfium'
    return ocr.OCRDocument(str(source), source_hash, engine,
                           provider.config.model_revision if rendered else settings['pdfium_version'] or 'version_unavailable',
                           settings, len(pages), '\n\f\n'.join(p.text for p in pages), pages)
