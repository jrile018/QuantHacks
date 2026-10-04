"""Frozen language features and explicitly supplied, dated comparisons."""
from __future__ import annotations

import csv
import hashlib
import math
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path


def utc_timestamp(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return parsed.astimezone(timezone.utc)


def has_public_evidence(record):
    evidence = record.get('public_at_evidence')
    return isinstance(evidence, str) and evidence.strip().lower() not in {
        '', 'unverified', 'unknown', 'none', 'null', 'n/a', 'true', 'false', 'verified'}


class DictionaryProvider:
    """Counts only. Category memberships are from the supplied frozen CSV."""
    CATEGORIES = ('negative', 'positive', 'uncertainty', 'litigious',
                  'strong_modal', 'weak_modal', 'constraining')

    def __init__(self, path, revision):
        if not revision:
            raise ValueError('Dictionary revision is required')
        raw = Path(path).read_bytes()
        self.metadata = {'revision': revision, 'sha256': hashlib.sha256(raw).hexdigest(),
                         'membership_rule': 'category value > 0 in supplied frozen CSV'}
        self.words = {}
        reader = csv.DictReader(raw.decode('utf-8-sig').splitlines())
        columns = {k.lower().replace(' ', '_'): k for k in (reader.fieldnames or [])}
        if 'word' not in columns or not any(k in columns for k in self.CATEGORIES):
            raise ValueError('Dictionary requires Word and at least one recognized category column')
        for row in reader:
            word = row[columns['word']].upper()
            self.words[word] = {cat for cat in self.CATEGORIES
                               if cat in columns and float(row[columns[cat]] or 0) > 0}

    def score(self, text):
        words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text.upper())
        counts = {cat: sum(cat in self.words.get(w, ()) for w in words) for cat in self.CATEGORIES}
        return {'counts': counts, 'word_count': len(words),
                'rates': {cat: n / len(words) if words else None for cat, n in counts.items()}}


class FinBertProvider:
    """Local frozen classifier; no weight download, remote code or training."""
    def __init__(self, path, revision, device='cpu'):
        if not revision or not Path(path).is_dir():
            raise ValueError('FinBERT requires a local model directory and explicit revision')
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            path, local_files_only=True, trust_remote_code=False, use_safetensors=True)
        self.model.to(device).eval()
        self.device = device
        self.labels = {int(k): str(v).lower() for k, v in self.model.config.id2label.items()}
        if set(self.labels.values()) != {'positive', 'negative', 'neutral'}:
            raise ValueError('FinBERT config must explicitly map positive, negative, neutral labels')
        self.metadata = {'revision': revision, 'label_mapping': self.labels,
                         'config_sha256': hashlib.sha256((Path(path) / 'config.json').read_bytes()).hexdigest(),
                         'truncation': 'reported per evidence', 'device': device}

    def score(self, text):
        import torch
        limit = min(self.tokenizer.model_max_length, self.model.config.max_position_embeddings)
        token_count = len(self.tokenizer.encode(text, add_special_tokens=True, truncation=False))
        encoded = self.tokenizer(text, return_tensors='pt', truncation=True, max_length=limit).to(self.device)
        with torch.inference_mode():
            probabilities = self.model(**encoded).logits.softmax(dim=-1)[0].cpu().tolist()
        if not all(math.isfinite(p) for p in probabilities):
            raise ValueError('Non-finite model output')
        return {'probabilities': {self.labels[i]: p for i, p in enumerate(probabilities)},
                'label': self.labels[max(range(len(probabilities)), key=probabilities.__getitem__)],
                'token_count': token_count, 'truncated': token_count > limit}


def compare_prior(current, prior, current_metadata, prior_metadata, decision=None):
    unavailable = {'status': 'comparison_unavailable', 'statements': [],
                   'reason': 'eligible_dated_prior_missing'}
    if not current_metadata or not prior_metadata or not prior:
        return unavailable
    try:
        a, b = (utc_timestamp(m.get('public_at_utc')) for m in (current_metadata, prior_metadata))
        cutoff = utc_timestamp(decision) if decision else a
        same_issuer = int(current_metadata['cik']) == int(prior_metadata['cik'])
        verified = all(has_public_evidence(m) for m in (current_metadata, prior_metadata))
        if not (same_issuer and verified and a and b and cutoff and b < a and b <= cutoff):
            return unavailable
    except (ValueError, TypeError, KeyError):
        return unavailable
    statements = []
    for item in current:
        text = ' '.join(item['quoted_text'].split())
        candidates = [p for p in prior if p.get('sec_item') == item.get('sec_item')]
        best, similarity = None, 0.0
        for candidate in candidates:
            score = SequenceMatcher(None, text, ' '.join(candidate['quoted_text'].split()), autojunk=False).ratio()
            if score > similarity:
                best, similarity = candidate, score
        novelty = 'unchanged' if similarity == 1 else ('changed' if similarity >= .65 else 'new_statement')
        statements.append({'evidence_id': item['evidence_id'], 'novelty': novelty,
                           'prior_evidence_id': best['evidence_id'] if similarity >= .65 else None,
                           'prior_quoted_text': best['quoted_text'] if similarity >= .65 else None,
                           'similarity': similarity})
    return {'status': 'available', 'method': 'case-sensitive whitespace-normalized SequenceMatcher; changed >= 0.65 within item',
            'limitation': 'Lexical comparison with supplied prior only; not economic or consensus surprise.',
            'statements': statements}


def analyze_wording(evidence, dictionary=None, finbert=None, comparison=None, provider_errors=None):
    assessments, sections = [], {}
    for item in evidence:
        counts = dictionary.score(item['quoted_text']) if dictionary else None
        sentiment = finbert.score(item['quoted_text']) if finbert else None
        assessments.append({'evidence_id': item['evidence_id'], 'quoted_text': item['quoted_text'],
                            'dictionary': counts, 'financial_sentiment': sentiment,
                            'rhetorical_tone': None, 'numeric_changes': None})
        if counts:
            section = sections.setdefault(item['section_id'], {'word_count': 0, 'counts': {k: 0 for k in counts['counts']}})
            section['word_count'] += counts['word_count']
            for k, v in counts['counts'].items():
                section['counts'][k] += v
    for section in sections.values():
        section['rates'] = {k: v / section['word_count'] if section['word_count'] else None for k, v in section['counts'].items()}
    return {'status': 'available' if dictionary and finbert else ('partial' if dictionary or finbert else 'providers_unavailable'),
            'provider_revisions': {'dictionary': dictionary.metadata if dictionary else None,
                                   'finbert': finbert.metadata if finbert else None},
            'provider_errors': provider_errors or {}, 'evidence_assessments': assessments,
            'section_features': sections, 'annotation_status': 'machine_unreviewed',
            'novelty_comparison': comparison or {'status': 'comparison_unavailable', 'statements': []},
            'limitations': ['Dictionary counts do not handle negation or imply market direction.',
                           'Semantic tone and numeric changes require separate reviewed labels.',
                           'Financial sentiment is not an option-price forecast.']}
