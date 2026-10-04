"""Evidence-bound financial observation histories; no inferred transactions.

All builders read retained files only. Financial observations remain nonadditive:
instant balances and overlapping reporting periods are never summed into flows.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from html import unescape
from pathlib import Path
import re


def _stable_id(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _timestamp(value, *, required=False):
    if value is None or value == '':
        if required:
            raise ValueError('as_of must be a timezone-aware timestamp')
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError('timezone required')
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        if required:
            raise ValueError('as_of must be a timezone-aware timestamp') from None
        return None


def _eligibility(issues, available_at, cutoff, *, candidate=False):
    available = _timestamp(available_at)
    pit = available is not None and (cutoff is None or available <= cutoff)
    reasons = list(issues)
    if available is None:
        reasons.append('availability_unknown_or_not_timezone_aware')
    elif cutoff is not None and available > cutoff:
        reasons.append('not_yet_available')
    if candidate:
        reasons.append('human_review_required')
    return {'source_eligible': not issues, 'pit_eligible': pit,
            'eligible': not issues and not candidate and (cutoff is None or pit),
            'reasons': sorted(set(reasons))}


def _document_id(document):
    if document.get('document_id'):
        return document['document_id']
    accession = document.get('accession')
    if accession:
        return accession if str(accession).startswith('local-') else str(accession) + '/' + str(document.get('filename'))
    return document.get('source_path') or document.get('sha256')


class _EvidenceIndex:
    """Cache hashes and text per retained document during one builder call."""
    def __init__(self, documents):
        self.documents = list(documents)
        self.cache = {}
        self.text_hash_cache = {}
        self.raw_cache = {}
        self.inline_cache = {}
        self.xml_cache = {}
        self.wanted_element_ids = defaultdict(set)

    def register(self, records):
        for row in records:
            for evidence in row.get('evidence', []):
                document = self.find(row, evidence)
                if document is not None and evidence.get('element_id'):
                    self.wanted_element_ids[id(document)].add(str(evidence['element_id']))

    def xml_quotes(self, document, element_id):
        key = id(document)
        if key not in self.xml_cache:
            raw = self.raw_cache.get(key)
            text = raw.decode('utf-8-sig', errors='replace') if raw else ''
            wanted = self.wanted_element_ids[key] or {str(element_id)}
            values, closings = {}, {}
            pattern = r"""<([\w:.-]+)\b[^>]*\bid\s*=\s*(["'])([^"']+)\2[^>]*>"""
            for match in re.finditer(pattern, text):
                if match.group(3) not in wanted:
                    continue
                tag = match.group(1)
                if tag not in closings:
                    closings[tag] = re.compile(r'</' + re.escape(tag) + r'\s*>')
                close = closings[tag].search(text, match.end())
                if close:
                    inner = text[match.end():close.start()]
                    values[match.group(3)] = unescape(re.sub(r'<[^>]+>', '', inner)).strip()
            self.xml_cache[key] = values
        return self.xml_cache[key].get(str(element_id))

    def find(self, item, evidence=None):
        evidence = evidence or {}
        identifier = evidence.get('document_id') or item.get('document_id')
        path = evidence.get('source_path') or item.get('source_path')
        digest = evidence.get('source_sha256') or item.get('source_sha256')
        accession = item.get('accession')
        if identifier:
            matches = [d for d in self.documents if _document_id(d) == identifier]
        elif path:
            matches = [d for d in self.documents if d.get('source_path') == path]
        else:
            matches = [d for d in self.documents if d.get('sha256', d.get('source_sha256')) == digest and (not accession or d.get('accession') == accession)]
        return matches[0] if len(matches) == 1 else None

    def content(self, document):
        key = id(document)
        if key in self.cache:
            return self.cache[key]
        issues, raw, pages = [], None, []
        expected = document.get('sha256') or document.get('source_sha256')
        try:
            if isinstance(document.get('raw_text'), str):
                raw = document['raw_text'].encode('utf-8')
            elif document.get('source_path'):
                raw = Path(document['source_path']).read_bytes()
        except (OSError, ValueError):
            issues.append('source_unreadable')
        if raw is None:
            issues.append('source_bytes_unavailable')
        elif not expected or sha256(raw).hexdigest() != expected:
            issues.append('source_hash_mismatch')
        self.raw_cache[key] = raw
        text_path = document.get('text_path') or document.get('text_artifact_path')
        if text_path:
            try:
                text_raw = Path(text_path).read_bytes()
                text_hashes = [document.get(field) for field in
                               ('extracted_text_sha256', 'text_artifact_sha256', 'text_sha256')
                               if document.get(field)]
                actual_text_hash = sha256(text_raw).hexdigest()
                if any(actual_text_hash != digest for digest in text_hashes):
                    issues.append('text_artifact_hash_mismatch')
                extracted = json.loads(text_raw.decode('utf-8-sig'))
                binding = extracted.get('sha256') or extracted.get('source_sha256') or extracted.get('extracted_raw_sha256')
                if binding != expected:
                    issues.append('extracted_source_hash_mismatch')
                else:
                    pages = extracted.get('pages', [])
            except (OSError, ValueError, TypeError):
                issues.append('cached_text_unreadable')
        elif document.get('pages'):
            # In-memory native text may share the raw UTF-8 text, otherwise an
            # explicit extraction/source binding is required.
            native_text = raw.decode('utf-8', errors='replace') if raw else ''
            supplied = document['pages']
            binding = document.get('extracted_raw_sha256') or document.get('text_source_sha256')
            if binding == expected or all(p.get('text', '') in native_text for p in supplied):
                pages = supplied
            else:
                issues.append('extracted_source_hash_unverified')
        texts = [p.get('text', '') for p in pages if isinstance(p.get('text'), str)]
        if raw is not None and not raw.lstrip().startswith(b'%PDF-'):
            texts.append(raw.decode('utf-8-sig', errors='replace'))
        result = (sorted(set(issues)), texts, pages, expected)
        self.cache[key] = result
        return result

    def verify(self, item, references):
        issues, documents = [], []
        if not references:
            return ['evidence_missing'], None
        for evidence in references:
            document = self.find(item, evidence)
            if document is None:
                issues.append('document_missing_or_ambiguous')
                continue
            documents.append(document)
            failures, texts, pages, expected = self.content(document)
            issues.extend(failures)
            digest = evidence.get('source_sha256') or item.get('source_sha256')
            if digest != expected or (item.get('source_sha256') and item['source_sha256'] != expected):
                issues.append('evidence_source_hash_mismatch')
            text_path = document.get('text_path') or document.get('text_artifact_path')
            # Record-level artifact hashes bind a quote to the actual retained
            # extraction, even when a manifest has no extraction hash field.
            evidence_text_hash = evidence.get('text_artifact_sha256') or item.get('text_artifact_sha256')
            if evidence_text_hash and text_path:
                try:
                    if text_path not in self.text_hash_cache:
                        self.text_hash_cache[text_path] = sha256(Path(text_path).read_bytes()).hexdigest()
                    if self.text_hash_cache[text_path] != evidence_text_hash:
                        issues.append('text_artifact_hash_mismatch')
                except OSError:
                    issues.append('cached_text_unreadable')
            quote = evidence.get('quote', evidence.get('quoted_text'))
            if not isinstance(quote, str) or not quote:
                issues.append('quote_missing')
            elif not any(quote in text for text in texts):
                issues.append('quote_not_found')
            if evidence.get('locator_type') == 'xml_element':
                element_id = evidence.get('element_id')
                bound_quote = None
                raw = self.raw_cache.get(id(document))
                if element_id:
                    bound_quote = self.xml_quotes(document, element_id)
                elif evidence.get('element_index') is not None and raw is not None:
                    if id(document) not in self.inline_cache:
                        from src.reit_inline_facts import extract_inline_facts
                        self.inline_cache[id(document)] = {f['evidence']['element_index']: f['evidence']['quoted_text'] for f in extract_inline_facts(raw)['facts']}
                    bound_quote = self.inline_cache[id(document)].get(evidence['element_index'])
                if not isinstance(quote, str) or bound_quote != quote:
                    issues.append('xml_locator_quote_mismatch')
            page_number = evidence.get('page_number')
            if page_number is not None:
                page = next((p for p in pages if p.get('number') == page_number), None)
                if page is None or not isinstance(quote, str) or quote not in page.get('text', ''):
                    issues.append('page_locator_quote_mismatch')
                elif evidence.get('char_start') is not None and evidence.get('char_end') is not None:
                    start, end = evidence['char_start'], evidence['char_end']
                    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or page['text'][start:end] != quote:
                        issues.append('character_locator_quote_mismatch')
            if not (evidence.get('locator') or evidence.get('locator_type')):
                issues.append('locator_missing')
        return sorted(set(issues)), documents[0] if documents else None


def _cik(value):
    text = str(value or '')
    return text.zfill(10) if text.isdigit() and len(text) <= 10 else None


def _available_record(row, document):
    values = [row.get('available_at'), row.get('acceptance_datetime'), row.get('first_public_at')]
    if document:
        values += [document.get('available_at'), document.get('acceptanceDateTime'),
                   document.get('acceptance_datetime'), document.get('accepted_at'), document.get('first_public_at')]
    aware = [parsed for value in values if (parsed := _timestamp(value)) is not None]
    # A later timestamp cannot be overwritten by an earlier metadata field.
    return max(aware).isoformat() if aware else None


def _series_key(row):
    return (row.get('issuer_cik'), row.get('entity_identifier'), row.get('metric'),
            row.get('amount_kind'), row.get('amount_basis'), row.get('currency'),
            row.get('period_type'), row.get('period_start'), row.get('period_end'), row.get('as_of_date'),
            json.dumps(row.get('dimensions', []), sort_keys=True))


def build_histories(records: list[dict], documents: list[dict], as_of: str | None = None) -> dict:
    """Return eligible source observations and explicit review/reconciliation.

    ``as_of`` is an inclusive UTC comparable availability cutoff. Unknown and
    naive availability timestamps are excluded from PIT views. Effective dates
    and filing calendar dates cannot supply a missing availability timestamp.
    """
    cutoff = _timestamp(as_of, required=True) if as_of is not None else None
    index = _EvidenceIndex(documents)
    index.register(records)
    prepared, groups, reconciliation = [], defaultdict(list), []
    classifications = {'balance': 'stock_balance', 'flow': 'period_flow',
                       'commitment': 'commitment', 'terms': 'terms',
                       'planned': 'planned_event', 'completed': 'completed_event'}
    for source in records:
        row = dict(source)
        references = source.get('evidence', [])
        issues, document = index.verify(source, references)
        issues += list(source.get('quality_flags', []))
        if document and _cik(document.get('cik')) and _cik(source.get('issuer_cik')) != _cik(document.get('cik')):
            issues.append('issuer_source_identity_mismatch')
        if source.get('source_kind') == 'companyfacts_comparison':
            issues.append('comparison_source_not_primary_history')
        kind = source.get('amount_kind')
        if kind not in classifications:
            issues.append('financial_meaning_unresolved')
        if source.get('status') != 'parsed':
            issues.append('record_requires_review')
        if kind in {'flow', 'balance'}:
            if source.get('period_type') != ('duration' if kind == 'flow' else 'instant'):
                issues.append('concept_period_mismatch')
            if kind == 'flow' and not (source.get('period_start') and source.get('period_end')):
                issues.append('period_unknown')
            if kind == 'balance' and not source.get('as_of_date'):
                issues.append('balance_date_unknown')
        try:
            value = Decimal(str(source.get('value')))
            if not value.is_finite():
                raise InvalidOperation
        except (InvalidOperation, TypeError, ValueError):
            issues.append('amount_unresolved')
        if not source.get('currency'):
            issues.append('currency_unresolved')
        if not source.get('metric'):
            issues.append('metric_unresolved')
        if source.get('source_kind') == 'filing_xbrl':
            if source.get('entity_scheme') != 'http://www.sec.gov/CIK' or _cik(source.get('entity_identifier')) != _cik(source.get('issuer_cik')):
                issues.append('context_entity_differs_from_issuer')
        available = _available_record(source, document)
        row.update(history_type=classifications.get(kind, 'unresolved'), available_at=available,
                   effective_at=source.get('as_of_date') or source.get('period_end') or source.get('effective_at'),
                   is_cash_movement=kind == 'flow' and source.get('amount_basis') == 'reported_cash_movement',
                   additive=False, issues=sorted(set(issues)))
        prepared.append(row)
        # Unknown/source-invalid inputs cannot poison a verified series.
        if not issues and (cutoff is None or _eligibility([], available, cutoff)['pit_eligible']):
            groups[_series_key(source)].append(row)
    for key, rows in groups.items():
        filings = defaultdict(list)
        for row in rows:
            filings[row.get('accession') or row.get('document_id') or row.get('source_sha256')].append(row)
        for accession, observations in filings.items():
            values = {Decimal(str(r['value'])) for r in observations}
            if len(values) > 1:
                reconciliation.append({'kind': 'same_filing_conflicting_values', 'accession': accession,
                                       'record_ids': [r.get('record_id') for r in observations],
                                       'values': sorted(str(v) for v in values), 'additive': False})
                for row in observations:
                    row['issues'].append('same_filing_conflicting_values')
            elif len(observations) > 1:
                reconciliation.append({'kind': 'same_filing_equivalent_observations',
                                       'record_ids': [r.get('record_id') for r in observations], 'additive': False})
        if len(filings) > 1:
            reconciliation.append({'kind': 'cross_filing_observations', 'series_id': _stable_id(key),
                                   'record_ids': [r.get('record_id') for r in rows],
                                   'revision_policy': 'retain_each_source_observation_no_sum', 'additive': False})
    history, review = [], []
    for row in prepared:
        row['eligibility'] = _eligibility(row['issues'], row['available_at'], cutoff)
        if row['eligibility']['eligible']:
            history.append(row)
        else:
            review.append(row)
    order = lambda row: (row.get('available_at') or '', row.get('effective_at') or '', row.get('record_id') or '')
    return {'schema_version': 1, 'as_of': as_of, 'financial_history': sorted(history, key=order),
            'review': sorted(review, key=order), 'reconciliation': reconciliation,
            'coverage': {'input_records': len(records), 'documents': len(documents),
                         'eligible_observations': len(history), 'review_observations': len(review),
                         'source_rejected': sum(bool(r['issues']) for r in prepared),
                         'pit_excluded': sum(not r['eligibility']['pit_eligible'] for r in prepared),
                         'complete': False, 'scope': 'retained_observations_only_no_cashflow_inference'}}
