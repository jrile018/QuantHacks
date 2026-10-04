"""Source-backed REIT observations and explicitly unresolved review candidates.

Records are reported observations, not individual inferred bank transactions.
Curated standard concepts and explicit supported PDF statements receive
automatic financial classification.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
import json
import re

from src.reit_cash_facts import TAGS, BALANCE_TAGS, CASH_BASIS, BRIDGE
from src.reit_inline_facts import extract_inline_facts, MAX_BYTES
from src.reit_tables import extract_html_tables
from src.reit_pdf_money import extract_pdf_money

ANALYZER_REVISION = 'reit-money-2'
MAX_TABLE_QUOTE_CHARS = 4000
MAX_QUOTED_BYTES_PER_DOCUMENT = 256 * 1024
MONETARY = re.compile(r'^\{http://www.xbrl.org/2003/iso4217\}([A-Z]{3})$')
FINANCIAL = re.compile(r'loan|borrow|credit\s*facilit|repurchase|debt|principal|book\s*value|cash|dividend|proceeds|repay|collateral|notional|interest|matur|SOFR|commitment', re.I)
STANDARD = re.compile(r'^http://fasb\.org/us-gaap/20\d{2}(?:-\d{2}-\d{2})?$')


def _id(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _classification(namespace, concept):
    if not namespace or not STANDARD.fullmatch(namespace):
        return {'metric': None, 'amount_kind': 'unknown', 'amount_basis': 'unknown', 'relationship': 'unknown', 'cash_direction': 'unknown', 'cash_basis': None}
    balance = concept in BALANCE_TAGS
    metric = {**TAGS, **BALANCE_TAGS}.get(concept)
    if metric is None:
        return _classification(None, concept)
    direction = 'balance' if balance else 'signed_net' if metric in BRIDGE or 'FromRepaymentsOf' in concept else 'outflow' if concept.startswith(('Payments', 'Repayments')) else 'inflow'
    relation = 'borrower' if re.search(r'Debt|Borrowings', concept) else 'lender_or_loan_investor' if re.search(r'Loans', concept) else 'unknown'
    basis = 'reported_cash_balance' if balance and 'cash' in metric else 'reported_debt_balance' if balance else 'reported_cash_movement'
    return {'metric': metric, 'amount_kind': 'balance' if balance else 'flow', 'amount_basis': basis,
            'relationship': relation, 'cash_direction': direction, 'cash_basis': CASH_BASIS.get(concept)}


def _identity(row):
    return (row.get('issuer_cik'), row.get('accession'), row.get('concept_namespace'),
            row.get('concept_local_name'), row.get('entity_scheme'), row.get('entity_identifier'),
            row.get('period_type'), row.get('period_start'), row.get('period_end'), row.get('as_of_date'),
            json.dumps(row.get('dimensions', []), sort_keys=True), row.get('unit_measure'), row.get('source_kind'))


def _precision(value):
    if value == 'INF':
        return Decimal(0), 1000
    if value is not None and re.fullmatch(r'[+-]?\d{1,2}', str(value)) and -20 <= int(value) <= 20:
        d = int(value)
        return Decimal('0.5') * Decimal(10) ** -d, d
    return None, -1000


def consolidate_records(records: list[dict]) -> list[dict]:
    """Consolidate same-filing equivalent observations, retaining all evidence.

    Differing values require known overlapping rounding intervals and cannot
    disagree at the same precision. Unknown precision is never invented.
    """
    groups = defaultdict(list)
    for row in records:
        base = {key: value for key, value in row.items() if key not in {
            'observations', 'duplicate_values', 'duplicate_count', 'duplicate_status', 'record_id', 'status'}}
        observations = row.get('observations')
        if observations:
            for observation in observations:
                groups[_identity(row)].append({**base, **observation})
        else:
            groups[_identity(row)].append(base)
    result = []
    for identity, items in groups.items():
        flags = sorted({flag for item in items for flag in item.get('quality_flags', [])})
        unique_values = {None if item.get('value') is None else Decimal(item['value']) for item in items}
        consistent = len(unique_values) == 1
        if not consistent and None not in unique_values:
            lows, highs, by_precision = [], [], defaultdict(set)
            with localcontext() as ctx:
                ctx.prec = 280
                for item in items:
                    bound, decimals = _precision(item.get('decimals'))
                    if bound is None:
                        break
                    value = Decimal(item['value'])
                    lows.append(value - bound)
                    highs.append(value + bound)
                    by_precision[decimals].add(value)
                else:
                    consistent = max(lows) <= min(highs) and all(len(values) == 1 for values in by_precision.values())
        chosen = max(items, key=lambda item: _precision(item.get('decimals'))[1])
        row = dict(chosen)
        evidence, seen = [], set()
        for item in items:
            for reference in item.get('evidence', []):
                key = _id(reference)
                if key not in seen:
                    evidence.append(reference)
                    seen.add(key)
        row['evidence'] = evidence
        row['observations'] = [{key: item.get(key) for key in ('value', 'decimals', 'raw_text', 'is_nil', 'quality_flags', 'evidence')} for item in items]
        row['duplicate_count'] = len(items)
        row['duplicate_status'] = 'single' if len(items) == 1 else 'identical' if len(unique_values) == 1 else 'consistent_rounded' if consistent else 'inconsistent'
        if not consistent:
            row['value'] = None
            row['duplicate_values'] = [{'value': item.get('value'), 'decimals': item.get('decimals'), 'evidence': item.get('evidence', [])} for item in items]
            flags.append('inconsistent_duplicate_facts')
        row['quality_flags'] = sorted(set(flags))
        row['status'] = 'review_required' if flags or row.get('value') is None else 'parsed'
        row['record_id'] = _id(identity)
        result.append(row)
    return sorted(result, key=lambda r: r['record_id'])


def _metadata(document):
    return {'issuer_cik': document.get('cik'), 'accession': document.get('accession'),
            'form': document.get('form'), 'filing_date': document.get('filed'),
            'report_date': document.get('reportDate'), 'acceptance_datetime': document.get('acceptanceDateTime'),
            'source_url': document.get('url'), 'source_path': document.get('source_path'),
            'source_sha256': document.get('sha256'), 'text_artifact_path': document.get('text_path'),
            'text_artifact_sha256': document.get('extracted_text_sha256')}


def _candidate(metadata, kind, evidence, flags, **extra):
    value = {**metadata, 'candidate_type': kind, 'status': 'review_required', 'amount_kind': 'unknown',
             'amount_basis': 'unknown', 'relationship': 'unknown', 'currency': None,
             'value': None, 'evidence': evidence, 'quality_flags': sorted(set(flags)), **extra}
    value['candidate_id'] = _id([metadata, kind, evidence])
    return value


def build_document_records(raw: bytes, document: dict, extracted: dict, *, max_candidates: int = 100) -> dict:
    if max_candidates < 1:
        raise ValueError('max_candidates must be positive')
    if sha256(raw).hexdigest() != document.get('sha256'):
        raise ValueError('Original source hash mismatch')
    metadata = _metadata(document)
    records, candidates, issues = [], [], []
    candidate_count, table_count, quoted_bytes = 0, 0, 0

    def add(value):
        nonlocal candidate_count
        candidate_count += 1
        if len(candidates) < max_candidates:
            candidates.append(value)

    def quote_evidence(text, start, end, **locator):
        nonlocal quoted_bytes
        available = max(0, MAX_QUOTED_BYTES_PER_DOCUMENT - quoted_bytes)
        quote = text[start:min(end, start + MAX_TABLE_QUOTE_CHARS)].encode('utf-8')[:available].decode('utf-8', errors='ignore')
        quoted_bytes += len(quote.encode('utf-8'))
        reference = {'char_start': start, 'char_end': start + len(quote), 'quoted_text': quote, **locator}
        if start + len(quote) < end:
            reference.update(full_span_char_start=start, full_span_char_end=end, quote_truncated=True)
            issues.append('evidence_quote_limit')
        return reference

    if len(raw) > MAX_BYTES:
        return {'records': [], 'candidates': [], 'coverage': {'issues': ['source_size_limit'], 'incomplete': True, 'candidates_omitted': 0}}
    filename = str(document.get('filename') or document.get('source_path') or '').lower()
    if filename.endswith(('.htm', '.html', '.xml')):
        parsed = extract_inline_facts(raw)
        issues.extend(parsed['issues'])
        for fact in parsed['facts']:
            concept = fact.get('concept_local_name') or ''
            known = fact.get('concept_namespace') and STANDARD.fullmatch(fact['concept_namespace']) and concept in {**TAGS, **BALANCE_TAGS}
            if not known and not FINANCIAL.search(concept):
                continue
            measure = fact.get('unit_measure') or ''
            money = MONETARY.fullmatch(measure)
            if not money and measure:
                continue
            classified = _classification(fact.get('concept_namespace'), concept)
            flags = list(fact.get('quality_flags', []))
            if classified['amount_kind'] == 'unknown':
                flags.append('financial_meaning_unresolved')
            elif fact.get('period_type') != ('instant' if classified['amount_kind'] == 'balance' else 'duration'):
                flags.append('concept_period_mismatch')
            if not money:
                flags.append('currency_unresolved')
            if fact.get('entity_scheme') != 'http://www.sec.gov/CIK':
                flags.append('entity_scheme_unverified')
            entity = str(fact.get('entity_identifier') or '')
            if not entity.isdigit() or entity.zfill(10) != str(document.get('cik') or '').zfill(10):
                flags.append('context_entity_differs_from_issuer')
            evidence = {**fact['evidence'], 'source_url': metadata['source_url'],
                        'source_path': metadata['source_path'], 'source_sha256': metadata['source_sha256']}
            row = {**fact, **metadata, **classified, 'source_kind': 'filing_xbrl', 'currency': money.group(1) if money else None,
                   'quality_flags': sorted(set(flags)), 'evidence': [evidence]}
            records.append(row)
        if filename.endswith(('.html', '.htm')):
            text = raw.decode('utf-8-sig', errors='replace')
            for table in extract_html_tables(text):
                issues.extend('html_parser:' + flag for flag in table['quality_flags'] if flag.endswith('_limit'))
                search = table.get('caption', '') + ' ' + table.get('context', '') + ' ' + ' '.join(c['text'] for r in table['rows'] for c in r['cells'])
                if not FINANCIAL.search(search):
                    continue
                table_count += 1
                start, end = table['char_start'], table['char_end']
                flags = ['table_financial_semantics_unresolved', *table['quality_flags']]
                if '\ufffd' in text:
                    flags.append('source_text_decode_loss')
                evidence = [quote_evidence(text, start, end, locator_type='html_character_span',
                                           table_id=table['table_id'], source_sha256=metadata['source_sha256'])]
                if evidence[0].get('quote_truncated'):
                    flags.append('evidence_quote_limit')
                add(_candidate(metadata, 'html_table', evidence, flags, table=table))
    if filename.endswith('.pdf'):
        interpreted = extract_pdf_money(extracted.get('pages', []), document)
        issues.extend(interpreted['issues'])
        records.extend({**row, **metadata} for row in interpreted['records'])
    # Cached text also retains unresolved review candidates. This never runs
    # OCR or attaches nearby interest rates/maturities to a loan.
    for page in extracted.get('pages', []):
        text = page.get('text')
        if not isinstance(text, str):
            issues.append('malformed_cached_page')
            continue
        lines = list(re.finditer(r'[^\n\r]+', text))
        for match in lines:
            quote = match.group()
            if len(quote) > 4000:
                if FINANCIAL.search(quote):
                    issues.append('long_text_candidate_requires_layout')
                continue
            if FINANCIAL.search(quote) and re.search(r'[0-9$€£]', quote):
                evidence = [quote_evidence(text, match.start(), match.end(), locator_type='cached_page_character_span',
                                           page_number=page.get('number'), source_sha256=metadata['source_sha256'],
                                           text_artifact_path=metadata['text_artifact_path'], text_artifact_sha256=metadata['text_artifact_sha256'])]
                flags = ['text_financial_semantics_unresolved', *page.get('quality_flags', [])]
                if evidence[0].get('quote_truncated'):
                    flags.append('evidence_quote_limit')
                add(_candidate(metadata, 'text_excerpt', evidence, flags))
        # Keep a two-line span when a currency amount is separated from its
        # magnitude or the financial noun by a PDF line wrap. It is still a
        # review candidate: joining adjacent text does not establish meaning.
        for first, second in zip(lines, lines[1:]):
            left, right = first.group(), second.group()
            if not re.search(r'[$€£]\s*\d[\d,.]*', left):
                continue
            split_magnitude = bool(re.search(r'[$€£]\s*\d[\d,.]*\s*$', left)
                                   and re.match(r'\s*(?:million|billion)\b', right, re.I))
            split_financial_noun = not FINANCIAL.search(left) and bool(FINANCIAL.search(right))
            continued_facility = bool(re.match(r'\s*(?:(?:unsecured|secured)\s+)?credit\s+facilit', right, re.I))
            if not (split_magnitude or split_financial_noun or continued_facility):
                continue
            if second.end() - first.start() > 4000:
                issues.append('long_text_candidate_requires_layout')
                continue
            evidence = [quote_evidence(text, first.start(), second.end(),
                                       locator_type='cached_page_character_span',
                                       page_number=page.get('number'), source_sha256=metadata['source_sha256'],
                                       text_artifact_path=metadata['text_artifact_path'],
                                       text_artifact_sha256=metadata['text_artifact_sha256'])]
            flags = ['text_financial_semantics_unresolved', 'line_wrap_joined',
                     *page.get('quality_flags', [])]
            if evidence[0].get('quote_truncated'):
                flags.append('evidence_quote_limit')
            add(_candidate(metadata, 'text_excerpt_window', evidence, flags))
    records = consolidate_records(records)
    omitted = max(0, candidate_count - len(candidates))
    return {'records': records, 'candidates': candidates,
            'coverage': {'inline_records': sum(r['source_kind'] == 'filing_xbrl' for r in records),
                         'pdf_rule_records': sum(r['source_kind'] == 'pdf_money_rule' for r in records),
                         'parsed_records': sum(r['status'] == 'parsed' for r in records),
                         'review_records': sum(r['status'] == 'review_required' for r in records),
                         'relevant_tables': table_count, 'candidate_count': len(candidates), 'candidates_omitted': omitted,
                         'issues': sorted(set(issues)), 'incomplete': bool(issues or omitted)}}


def companyfacts_records(rows: list[dict]) -> list[dict]:
    """Preserve existing normalized API values as separate comparison facts."""
    records = []
    for item in rows:
        try:
            value = Decimal(str(item['value']))
            if not value.is_finite():
                continue
        except (KeyError, InvalidOperation):
            continue
        concept = item.get('tag')
        classified = _classification('http://fasb.org/us-gaap/2025', concept)
        row = {**classified, 'issuer_cik': item.get('cik'), 'accession': item.get('accession'),
               'concept_namespace': 'us-gaap', 'concept_local_name': concept,
               'entity_scheme': 'http://www.sec.gov/CIK', 'entity_identifier': item.get('cik'), 'dimensions': [],
               'period_type': 'instant' if classified['amount_kind'] == 'balance' else 'duration',
               'period_start': item.get('period_start') or None,
               'period_end': item.get('period_end') if classified['amount_kind'] != 'balance' else None,
               'as_of_date': item.get('period_end') if classified['amount_kind'] == 'balance' else None,
               'value': format(value, 'f'), 'decimals': item.get('decimals') or None,
               'currency': item.get('unit'), 'unit_measure': '{http://www.xbrl.org/2003/iso4217}' + str(item.get('unit')),
               'source_kind': 'companyfacts_comparison', 'filing_date': item.get('filed'), 'form': item.get('form'),
               'source_url': item.get('data_url'), 'source_path': item.get('data_path'), 'source_sha256': item.get('data_sha256'),
               'quality_flags': [], 'evidence': [{'locator_type': 'companyfacts_context', 'concept': concept,
                                               'unit': item.get('unit'), 'accession': item.get('accession'),
                                               'period_start': item.get('period_start'), 'period_end': item.get('period_end'),
                                               'source_sha256': item.get('data_sha256')}]}
        records.append(row)
    return consolidate_records(records)
