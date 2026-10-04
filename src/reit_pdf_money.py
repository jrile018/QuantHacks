"""Interpret explicitly supported PDF money statements from retained page text.

Rules bind amounts to a row/year or a grammatical facility statement. They do
not read evaluation labels, infer transfers, or attach nearby loan terms.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, localcontext
import re


REVISION = 'pdf-money-2'
MAX_PAGE_CHARS = 250_000
MAX_RECORDS = 5000
NUMBER = r'(?:\([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?\)|-?[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?|—|–|-)'
CELL = re.compile(r'(?:\$\s*)?' + NUMBER)
MONEY = r'\$\s*[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?\s+(?:million|billion)'
NAMESPACE = 'urn:quanthaxs:reported-pdf-money:1'

# Explicit row meanings, not an arbitrary financial-keyword classifier.
ROWS = {
    'net cash provided by operating activities': ('cash_operating', 'issuer', 'signed_net'),
    'net cash used in operating activities': ('cash_operating', 'issuer', 'signed_net'),
    'investment in loans and preferred equity': ('loan_preferred_equity_investments', 'mixed_asset_investor', 'outflow'),
    'borrowings on revolving credit facilities and commercial paper programs': ('revolver_commercial_paper_borrowings', 'borrower', 'inflow'),
    'payments on revolving credit facilities and commercial paper programs': ('revolver_commercial_paper_payments', 'borrower', 'outflow'),
    'proceeds from term loan': ('term_loan_proceeds', 'borrower', 'inflow'),
    'principal payment on term loans': ('term_loan_principal_payments', 'borrower', 'outflow'),
    'proceeds from notes payable issued': ('notes_issued_proceeds', 'borrower', 'inflow'),
    'principal payment on notes payable': ('notes_principal_payments', 'borrower', 'outflow'),
    'principal payments on mortgages payable': ('mortgage_principal_payments', 'borrower', 'outflow'),
    'cash distributions to common stockholders': ('common_cash_distributions', 'issuer', 'outflow'),
    'net cash used in investing activities': ('cash_investing', 'issuer', 'signed_net'),
    'net cash provided by investing activities': ('cash_investing', 'issuer', 'signed_net'),
    'net cash provided by (used in) financing activities': ('cash_financing', 'issuer', 'signed_net'),
    'net cash provided by financing activities': ('cash_financing', 'issuer', 'signed_net'),
    'net cash used in financing activities': ('cash_financing', 'issuer', 'signed_net'),
}


def _flat(text: str, offset: int = 0) -> tuple[str, list[int]]:
    words, positions = [], []
    for match in re.finditer(r'\S+', text):
        if words:
            words.append(' ')
            positions.append(offset + match.start() - 1)
        words.append(match.group())
        positions.extend(range(offset + match.start(), offset + match.end()))
    return ''.join(words), positions


def _span(positions: list[int], start: int, end: int) -> tuple[int, int]:
    return positions[start], positions[end - 1] + 1


def _evidence(page: dict, start: int, end: int, role: str, **extra) -> dict:
    return {'locator_type': 'cached_page_character_span', 'page_number': page['number'],
            'char_start': start, 'char_end': end, 'quoted_text': page['text'][start:end],
            'evidence_role': role, **extra}


def _currency(pages: list[dict]) -> tuple[str | None, list[dict], list[str]]:
    declarations = []
    for page in pages:
        text = page.get('text', '')
        if not isinstance(text, str) or len(text) > MAX_PAGE_CHARS:
            continue
        flat, positions = _flat(text)
        for match in re.finditer(r'all dollar amounts are expressed in (USD|CAD|AUD|NZD|HKD|SGD)\b', flat, re.I):
            start, end = _span(positions, match.start(), match.end())
            declarations.append((match.group(1).upper(), _evidence(page, start, end, 'currency')))
    codes = {code for code, _ in declarations}
    if len(codes) == 1:
        return next(iter(codes)), [item for _, item in declarations], []
    return None, [], ['reporting_currency_conflict' if codes else 'reporting_currency_unresolved']


def _value(raw: str, scale: int) -> tuple[str | None, str | None]:
    token = raw.replace('$', '').replace(' ', '').replace(',', '')
    if token in {'—', '–', '-'}:
        return None, None
    if len(token) > 40:
        raise ValueError('numeric_size_limit')
    negative = token.startswith('(') and token.endswith(')')
    token = token[1:-1] if negative else token
    with localcontext() as ctx:
        ctx.prec = 60
        number = Decimal(token) * (Decimal(10) ** scale)
        if negative:
            number = -number
    decimals = len(token.split('.')[1]) if '.' in token else 0
    return format(number, 'f').split('.')[0] if number == number.to_integral() else format(number, 'f'), str(decimals - scale)


def _money(raw: str) -> tuple[str, str]:
    match = re.fullmatch(r'\$\s*([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s+(million|billion)', raw, re.I)
    if not match:
        raise ValueError('unsupported_currency_amount')
    value, decimals = _value(match.group(1), 6 if match.group(2).lower() == 'million' else 9)
    return value, decimals


def _record(document, metric, value, decimals, currency, flags, evidence, *,
            relationship, kind, basis, direction, period_start=None, period_end=None,
            as_of_date=None, facility=None, entity_scope='issuer', rule_id):
    entity = document.get('cik') if entity_scope == 'issuer' else entity_scope
    return {'issuer_cik': document.get('cik'), 'metric': metric,
            'concept_namespace': NAMESPACE, 'concept_local_name': metric,
            'entity_scheme': 'http://www.sec.gov/CIK' if entity_scope == 'issuer' else 'document_entity_label',
            'entity_identifier': entity, 'entity_scope': entity_scope,
            'dimensions': [{'axis': 'entity_scope', 'member': entity_scope}] +
                          ([{'axis': 'facility', 'member': facility}] if facility else []),
            'period_type': 'duration' if kind == 'flow' else 'instant',
            'period_start': period_start, 'period_end': period_end, 'as_of_date': as_of_date,
            'value': value, 'decimals': decimals, 'currency': currency,
            'unit_measure': '{http://www.xbrl.org/2003/iso4217}' + currency if currency else None,
            'amount_kind': kind, 'amount_basis': basis, 'relationship': relationship,
            'cash_direction': direction, 'cash_basis': None, 'source_kind': 'pdf_money_rule',
            'rule_id': rule_id, 'quality_flags': sorted(set(flags)),
            'status': 'review_required' if flags or value is None else 'parsed', 'evidence': evidence}


def _cash_rows(page, document, currency, currency_evidence, currency_flags):
    text = page['text']
    titles = list(re.finditer(r'(?im)^(?:CONSOLIDATED[ \t]+)?STATEMENTS? OF CASH FLOWS[ \t\r]*$', text))
    records, issues = [], []
    for title in titles:
        # Each table owns its header. A subsequent financial statement closes it.
        boundary = re.search(r'(?im)^(?:CONSOLIDATED[ \t]+)?(?:STATEMENTS? OF [A-Z &]+|BALANCE SHEETS?)[ \t\r]*$',
                             text[title.end():])
        table_end = title.end() + boundary.start() if boundary else len(text)
        rows, warnings = _cash_table(page, document, currency, currency_evidence, currency_flags,
                                    title.start(), table_end)
        records.extend(rows)
        issues.extend(warnings)
    return records, issues


def _cash_table(page, document, currency, currency_evidence, currency_flags, table_start, table_end):
    text = page['text']
    head = text[table_start:min(table_start + 1000, table_end)]
    scale_match = re.search(r'\(in (thousands|millions)\)', head, re.I)
    period = re.search(r'Years ended December 31,?\s*[\r\n]+(?P<years>20\d{2}(?:\s+20\d{2}){1,3})\s*[\r\n]', head, re.I)
    if not scale_match or not period:
        return [], ['cash_table_header_unresolved']
    years = period.group('years').split()
    if len(set(years)) != len(years):
        return [], ['cash_table_year_conflict']
    scale = 3 if scale_match.group(1).lower() == 'thousands' else 6
    rows_start = table_start + period.end()
    header = _evidence(page, table_start, rows_start, 'table_header')
    # Repeated/unsupported period or unit headers cannot silently reuse this one.
    boundary = re.search(r'(?im)^[ \t]*(?:Years? ended|(?:Three|Six|Nine|Twelve) months? ended|\(in (?:thousands|millions)\))',
                         text[rows_start:table_end])
    if boundary:
        table_end = rows_start + boundary.start()
    records, issues = [], []
    for line in re.finditer(r'[^\r\n]+', text[rows_start:table_end]):
        row_text, _ = _flat(line.group())
        for label, (metric, relation, direction) in ROWS.items():
            if not row_text.casefold().startswith(label + ' '):
                continue
            tail = row_text[len(label):].strip()
            tokens = list(CELL.finditer(tail))
            cursor, valid = 0, True
            for token in tokens:
                if tail[cursor:token.start()].strip():
                    valid = False
                cursor = token.end()
            if tail[cursor:].strip() or len(tokens) != len(years) or not valid:
                issues.append('cash_table_column_count_or_numeric_format_unresolved')
                continue
            start, end = rows_start + line.start(), rows_start + line.end()
            for year, token in zip(years, tokens):
                flags = list(currency_flags)
                try:
                    value, decimals = _value(token.group(), scale)
                except ValueError:
                    issues.append('numeric_size_limit')
                    continue
                if value is None:
                    flags.append('unreported_dash_value')
                elif ((direction == 'outflow' and Decimal(value) > 0) or
                      (direction == 'inflow' and Decimal(value) < 0)):
                    flags.append('cash_direction_sign_conflict')
                amount = _evidence(page, start, end, 'amount', selected_amount_text=token.group(),
                                   row_label=row_text[:len(label)], column_year=year, table_scale=scale)
                row = _record(document, metric, value, decimals, currency, flags,
                              [amount, header, *currency_evidence], relationship=relation,
                              kind='flow', basis='reported_cash_movement', direction=direction,
                              period_start=year + '-01-01', period_end=year + '-12-31',
                              rule_id=REVISION + ':annual_cash_flow')
                row['raw_text'] = token.group()
                records.append(row)
    return records, issues


def _date(value):
    try:
        return datetime.strptime(value, '%B %d, %Y').date().isoformat()
    except ValueError:
        return None


def _facility_rows(page, document, currency, currency_evidence, currency_flags):
    text = page['text']
    headings = list(re.finditer(r'(?m)^(?:[A-Z]\.\s*)?(?P<facility>[A-Za-z][A-Za-z0-9 &\x27’-]{0,65} Credit Facilit(?:y|ies))\s*$', text))
    records, issues = [], []
    for heading in headings[:20]:
        next_heading = re.search(r'(?m)^[A-Z]\.\s+[A-Za-z]', text[heading.end():])
        end = heading.end() + next_heading.start() if next_heading else len(text)
        if end - heading.end() > 15000:
            issues.append('facility_section_size_limit')
            continue
        facility = heading.group('facility').strip()
        flat, positions = _flat(text[heading.end():end], heading.end())
        facility_re = re.escape(facility)
        available_re = (r'As of (?P<date>[A-Za-z]+ \d{1,2}, \d{4}), we had a borrowing capacity of '
                        r'(?P<available>' + MONEY + r') available on our ' + facility_re +
                        r'\s*(?:\(subject to customary conditions to borrowing\))?\s*and an outstanding balance of '
                        r'(?P<outstanding>' + MONEY + r')')
        availability = list(re.finditer(available_re, flat, re.I))
        commitment_re = (r'(?P<actor>we|the Fund|Fund) entered into (?:new|a newly-established|a new) '
                         r'(?P<amount>' + MONEY + r')\s+(?P<description>[A-Za-z -]{0,100}credit facilit(?:y|ies))')
        commitments = list(re.finditer(commitment_re, flat, re.I))
        # A section heading alone cannot disambiguate two separate arrangements.
        association_flags = ['facility_association_unresolved'] if len(commitments) > 1 else []
        fund = facility.casefold() == 'fund credit facilities'
        scope_proven = any(('fund' in match.group('actor').casefold()) == fund for match in commitments)
        scope = 'Fund' if fund else 'issuer'
        relation = 'fund_borrower' if fund else 'borrower'
        scope_flags = [] if scope_proven else ['borrower_scope_unresolved']
        current = [match for match in availability if _date(match.group('date')) == document.get('reportDate')]
        capacity_date = document.get('reportDate') if current else None
        date_flags = [] if capacity_date else ['capacity_reporting_date_unresolved']
        section = _evidence(page, heading.start(), heading.end(), 'facility_section')

        def make(match, group, metric, kind, basis, date, flags, context=()):
            value, decimals = _money(match.group(group))
            start, finish = _span(positions, match.start(), match.end())
            amount = _evidence(page, start, finish, 'amount', selected_amount_text=match.group(group), facility=facility)
            return _record(document, metric, value, decimals, currency,
                           [*currency_flags, *scope_flags, *flags],
                           [amount, section, *context, *currency_evidence], relationship=relation,
                           kind=kind, basis=basis, direction='balance' if kind == 'balance' else 'none',
                           as_of_date=date, facility=facility, entity_scope=scope,
                           rule_id=REVISION + ':credit_note')

        date_evidence = []
        if current:
            start, finish = _span(positions, current[0].start(), current[0].end())
            date_evidence = [_evidence(page, start, finish, 'reporting_date')]
        for match in commitments:
            if ('fund' in match.group('actor').casefold()) != fund:
                continue
            flags = [*date_flags, *association_flags]
            sentence_end = re.search(r'\.(?:\s|$)', flat[match.end():])
            suffix = flat[match.end():match.end() + sentence_end.end()] if sentence_end else flat[match.end():]
            if re.search(r'\b(?:subsidiar(?:y|ies)|affiliate|joint venture|on behalf of)\b', suffix, re.I):
                flags.append('facility_association_unresolved')
            if _subsequent_capacity_change(flat[match.end():]):
                flags.append('capacity_current_state_unresolved')
            if current and any(not _capacity_agrees(match.group('amount'), dated) for dated in current):
                flags.extend(('capacity_current_state_unresolved', 'capacity_reconciliation_conflict'))
            records.append(make(match, 'amount', 'facility_commitment', 'capacity', 'facility_commitment',
                                capacity_date, flags, date_evidence))
        conditional_re = (r'The aggregate (?:capacity|amount) (?:of|under) (?:the|our) ' + facility_re +
                          r' can be increased to up to (?P<amount>' + MONEY +
                          r') pursuant to an accordion expansion feature, which is subject to obtaining lender commitments')
        for match in re.finditer(conditional_re, flat, re.I):
            flags = list(date_flags)
            if _subsequent_capacity_change(flat[match.end():]):
                flags.append('capacity_current_state_unresolved')
            records.append(make(match, 'amount', 'facility_conditional_capacity', 'conditional_capacity',
                                'subject_to_lender_commitments', capacity_date, flags, date_evidence))
        for match in availability:
            date = _date(match.group('date'))
            flags = [] if date else ['statement_date_unresolved']
            records.append(make(match, 'available', 'facility_available_capacity', 'capacity',
                                'undrawn_available', date, flags))
            records.append(make(match, 'outstanding', 'facility_outstanding_debt', 'balance',
                                'reported_debt_balance', date, flags))
    if len(headings) > 20:
        issues.append('facility_section_count_limit')
    return records, issues


def _subsequent_capacity_change(text):
    # Completed modifications invalidate carrying an original commitment forward.
    # Conditional wording ("can be increased") is intentionally outside this rule.
    return bool(re.search(r'\b(?:was|were|has been|have been|we|the fund) (?:subsequently )?'
                          r'(?:reduced|increased|amended|restated|terminated|cancelled|canceled)\b|'
                          r'\b(?:commitments?|capacity|facilit(?:y|ies)|agreements?) '
                          r'(?:subsequently )?(?:decreased|fell|expired|terminated|changed)\b', text, re.I))


def _capacity_agrees(commitment, dated):
    """A consistency guard, not an inferred commitment or accounting identity."""
    amounts = [_money(raw) for raw in (commitment, dated.group('available'), dated.group('outstanding'))]
    with localcontext() as ctx:
        ctx.prec = 60
        capacity, available, outstanding = (Decimal(value) for value, _ in amounts)
        # Each disclosed amount can be rounded by half its displayed increment.
        tolerance = sum(Decimal('0.5') * Decimal(10) ** -int(decimals) for _, decimals in amounts)
        return abs(capacity - available - outstanding) <= tolerance


def extract_pdf_money(pages: list[dict], document: dict) -> dict:
    currency, currency_evidence, currency_flags = _currency(pages)
    records, issues = [], []
    for page in pages:
        text = page.get('text')
        if not isinstance(text, str) or not isinstance(page.get('number'), int):
            issues.append('malformed_money_page')
            continue
        if len(text) > MAX_PAGE_CHARS:
            issues.append('money_page_size_limit')
            continue
        for adapter in (_cash_rows, _facility_rows):
            rows, warnings = adapter(page, document, currency, currency_evidence, currency_flags)
            records.extend(rows)
            issues.extend(warnings)
        if len(records) > MAX_RECORDS:
            records = records[:MAX_RECORDS]
            issues.append('money_record_limit')
            break
    for row in records:
        for reference in row['evidence']:
            reference.update(source_url=document.get('url'), source_sha256=document.get('sha256'),
                             text_artifact_path=document.get('text_path'),
                             text_artifact_sha256=document.get('extracted_text_sha256'))
    if records:
        issues.extend(currency_flags)
    return {'records': records, 'issues': sorted(set(issues))}
