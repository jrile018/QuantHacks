"""Exact sentence and item evidence into immutable normalized transcript text."""
from hashlib import sha256
import re

ITEM = re.compile(r'\bItem\s+(\d{1,2}\.\d{2})\b', re.IGNORECASE)


def build_evidence(transcript: dict) -> list[dict]:
    text = transcript['normalized_text']
    digest = sha256(text.encode('utf-8')).hexdigest()
    if digest != transcript['text_sha256']:
        raise ValueError('Transcript text hash mismatch')
    result = []
    item = None
    section = f"{transcript['document_id']}:document"
    # Newlines preserve headings/rows; punctuation separates sentences except decimals.
    boundaries = re.compile(r'\n|\f|(?<!\d)[.!?](?=\s|$)|(?<=\d)[.!?](?=\s|$)')
    start = 0
    spans = []
    for match in boundaries.finditer(text):
        end = match.start() if match.group() in ('\n', '\f') else match.end()
        spans.append((start, end))
        start = match.end()
    spans.append((start, len(text)))
    for start, end in spans:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end <= start:
            continue
        quote = text[start:end]
        heading = ITEM.search(quote)
        if heading:
            item = heading.group(1)
            section = f"{transcript['document_id']}:item_{item}_{start}"
        page = next((p.get('page_number') for p in transcript['page_records']
                     if p['char_start'] <= start and end <= p['char_end']), None)
        identity = f"{transcript['document_id']}:{digest}:{start}:{end}"
        result.append({'evidence_id': sha256(identity.encode()).hexdigest(),
                       'document_id': transcript['document_id'], 'text_sha256': digest,
                       'section_id': section, 'sec_item': item, 'page_number': page,
                       'char_start': start, 'char_end': end, 'quoted_text': quote,
                       'bounding_box': None, 'record_type': 'item_heading' if heading else 'statement'})
    return result
