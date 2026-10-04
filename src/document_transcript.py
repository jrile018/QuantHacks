"""Offline native extraction and a provenance-preserving OCR normalization boundary."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re

NORMALIZATION_VERSION = 'document_text_v1'
ADAPTER_REVISION = 'document_transcript_v2'


def _normalize(text: str) -> str:
    return text.replace('\r\n', '\n').replace('\r', '\n').replace('\u00a0', ' ')


def _record(document_id, source_hash, text, method, engine, settings, pages, tables, flags):
    if not text.strip():
        flags.append('incomplete_text')
    return {'schema_version': '1.0', 'document_id': document_id,
            'source_sha256': source_hash, 'text_sha256': sha256(text.encode('utf-8')).hexdigest(),
            'normalized_text': text, 'normalization_version': NORMALIZATION_VERSION,
            'extraction_method': method, 'engine_revision': engine,
            'adapter_revision': ADAPTER_REVISION, 'settings': settings,
            'page_records': pages, 'table_records': tables,
            'quality_flags': sorted(set(flags)),
            'processing_completed_at_utc': datetime.now(timezone.utc).isoformat()}


def _text_tables(text):
    """Retain candidate aligned rows without inferring units or numeric concepts."""
    rows = []
    cursor = 0
    for line in text.splitlines(keepends=True):
        value = line.rstrip('\r\n\f')
        cells = re.split(r'\t| {2,}', value)
        if len(cells) > 1 and value.strip():
            rows.append({'table_id': 'text_table_candidates', 'row_index': len(rows),
                         'char_start': cursor, 'char_end': cursor + len(value),
                         'quoted_text': value, 'cells': cells, 'labels': [],
                         'units': None, 'periods': [], 'evidence_references': [],
                         'structure_status': 'unresolved'})
        cursor += len(line)
    return rows


def normalize_ocr(payload: dict, document_id: str) -> dict:
    """Accept serialized OCR output; this does not run the declared backend.

    Confidence is backend-specific raw confidence, never semantic correctness.
    Page offsets refer to the newly stored transcript, preserving input order.
    """
    flags = ['unverified_reading_order', 'possible_negation_sign_unit_errors']
    pages = []
    parts = []
    cursor = 0
    raw_pages = payload.get('pages', [])
    if not isinstance(raw_pages, list):
        raw_pages = []
        flags.append('malformed_text')
    numbers = []
    for index, raw in enumerate(raw_pages):
        if not isinstance(raw, dict) or not isinstance(raw.get('text'), str):
            flags.append('malformed_text')
            raw = raw if isinstance(raw, dict) else {}
            text = ''
        else:
            text = _normalize(raw['text'])
        if index:
            parts.append('\n\f\n')
            cursor += 3
        number = raw.get('number', raw.get('page_number', index + 1))
        page_flags = raw.get('quality_flags') or []
        if not isinstance(page_flags, list) or any(not isinstance(f, str) for f in page_flags):
            page_flags = ['malformed_quality_flags']
        flags.extend(page_flags)
        if 'generation_token_limit_reached' in page_flags:
            flags.append('incomplete_text')
        numbers.append(number)
        pages.append({'page_number': number, 'text': text, 'char_start': cursor,
                      'char_end': cursor + len(text), 'confidence': raw.get('confidence'),
                      'confidence_semantics': 'backend_specific_uncalibrated',
                      'method': raw.get('method'), 'extraction_method': raw.get('method'),
                      'quality_flags': list(page_flags),
                      'bounding_box': raw.get('bounding_box')})
        parts.append(text)
        cursor += len(text)
    text = ''.join(parts)
    if not raw_pages:
        raw_text = payload.get('text', '')
        if not isinstance(raw_text, str):
            raw_text = ''
            flags.append('malformed_text')
        text = _normalize(raw_text)
        pages = [{'page_number': None, 'text': text, 'char_start': 0,
                  'char_end': len(text), 'confidence': None, 'bounding_box': None}]
    elif isinstance(payload.get('text'), str) and _normalize(payload['text']) != text:
        flags.append('document_page_text_mismatch')
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        flags.append('malformed_page_order')
    source_hash = payload.get('source_sha256', payload.get('sha256'))
    if not source_hash:
        flags.append('source_hash_unavailable')
    original = payload.get('source_path')
    if original and Path(original).is_file():
        if sha256(Path(original).read_bytes()).hexdigest() != source_hash:
            raise ValueError('OCR source hash does not match original source bytes')
    else:
        flags.append('source_hash_unverified')
    tables = _text_tables(text)
    if tables:
        flags.append('unresolved_table_structure')
    backend = payload.get('engine', payload.get('backend', 'unknown'))
    method = {'pdfium': 'native_pdf', 'mixed': 'mixed_pdf_native_ocr'}.get(backend, 'ocr_normalized')
    record = _record(document_id, source_hash, text, method,
                     payload.get('engine_version', payload.get('engine_revision')),
                     dict(payload.get('settings') or {}), pages, tables, flags)
    record['settings']['backend'] = backend
    record['original_artifact'] = payload
    return record


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0
        self.in_row = False
        self.cell_count = 0
        self.rows = []
        self.row_start = 0
        self.table_count = 0
        self.flags = []

    def _write(self, text):
        self.parts.append(text)

    def _break(self):
        if self.parts and not self.parts[-1].endswith('\n'):
            self._write('\n')

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if self.hidden:
            return
        if tag == 'table':
            self.table_count += 1
            self.flags.append('unresolved_table_structure')
        if tag == 'tr':
            self._break()
            self.row_start = sum(map(len, self.parts))
            self.in_row = True
            self.cell_count = 0
        elif tag in ('td', 'th') and self.in_row:
            if self.cell_count:
                self._write('\t')
            self.cell_count += 1
        elif tag in ('p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'li', 'section'):
            self._break()

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
            return
        if self.hidden:
            return
        if tag == 'tr' and self.in_row:
            end = sum(map(len, self.parts))
            value = ''.join(self.parts)[self.row_start:end]
            self.rows.append({'table_id': f'table_{self.table_count}', 'row_index': len(self.rows),
                              'char_start': self.row_start, 'char_end': end, 'quoted_text': value,
                              'cells': value.split('\t'), 'labels': [], 'units': None,
                              'periods': [], 'evidence_references': [], 'structure_status': 'unresolved'})
            self.in_row = False
            self._break()
        elif tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'li', 'section'):
            self._break()

    def handle_data(self, data):
        if not self.hidden:
            value = re.sub(r'\s+', ' ', _normalize(data))
            if value.strip() or (self.parts and not self.parts[-1].endswith((' ', '\n', '\t'))):
                self._write(value)


def extract_path(path, document_id: str, source_sha256: str | None = None) -> dict:
    """Extract a local HTML/text/PDF/image or adapt previously saved OCR JSON."""
    path = Path(path)
    data = path.read_bytes()
    digest = sha256(data).hexdigest()
    if path.suffix.lower() == '.json':
        payload = json.loads(data)
        record = normalize_ocr(payload, document_id)
        if source_sha256 is not None and source_sha256 != record['source_sha256']:
            raise ValueError('Supplied source hash does not match OCR provenance')
        record['ocr_artifact_sha256'] = digest
        return record
    if source_sha256 is not None and source_sha256 != digest:
        raise ValueError('Supplied source hash does not match actual source bytes')
    if path.suffix.lower() in {'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}:
        from src.document_ocr import extract_document
        return normalize_ocr(asdict(extract_document(path)), document_id)
    flags = []
    text = data.decode('utf-8-sig', errors='replace')
    if '\ufffd' in text:
        flags.append('malformed_text')
    text = _normalize(text)
    tables = []
    method = 'native_text'
    if path.suffix.lower() in {'.html', '.htm'}:
        parser = _HTMLText()
        parser.feed(text)
        parser.close()
        text = ''.join(parser.parts)
        tables = parser.rows
        flags.extend(parser.flags)
        if parser.hidden or parser.in_row:
            flags.append('malformed_text')
        method = 'native_html'
    else:
        tables = _text_tables(text)
        if tables:
            flags.append('unresolved_table_structure')
    pages = [{'page_number': None, 'char_start': 0, 'char_end': len(text), 'text': text,
              'confidence': None, 'bounding_box': None}]
    record = _record(document_id, digest, text, method, 'stdlib_v1', {}, pages, tables, flags)
    record['source_path'] = str(path.resolve())
    return record
