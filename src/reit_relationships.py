"""Retained-evidence REIT role assertions and conservative intersections.

Roles are instrument-specific, and source support is separate from entity
identity resolution. Name-only parties never acquire invented identifiers.
"""
from __future__ import annotations

from collections import defaultdict
import re

from src.reit_histories import (_EvidenceIndex, _available_record, _cik, _document_id,
                                _eligibility, _stable_id, _timestamp)


RELATION_ROLES = {
    'borrower_under': 'borrower', 'issuer_under_indenture': 'issuer',
    'trustee_under_supplemental_indenture': 'trustee',
    'series_established_under_indenture': 'issuer',
    'completed_debt_issuance': 'issuer', 'completed_secured_note_issuance': 'issuer',
    'aggregate_completed_equity_sale_reported': 'issuer',
    'entered_sales_agreements_authorizing_equity_offering': 'issuer',
    'entered_revolving_credit_facilities': 'borrower',
    'facility_terms_and_balance_snapshot': 'borrower',
    'planned_use_of_proceeds': 'planned_user_of_proceeds',
    'lender_under': 'lender', 'administrative_agent_under': 'administrative_agent',
    'arranger_under': 'arranger', 'guarantor_under': 'guarantor',
    'sales_agent_under': 'sales_agent', 'collateral_agent_under': 'collateral_agent',
}
COUNTERPARTY_ROLES = {'trustee', 'collateral_agent', 'administrative_agent',
                      'arranger', 'lender', 'guarantor', 'sales_agent'}
HISTORY_TYPES = {
    'completed_debt_issuance': 'completed_event',
    'completed_secured_note_issuance': 'completed_event',
    'aggregate_completed_equity_sale_reported': 'completed_event',
    'planned_use_of_proceeds': 'planned_event',
    'facility_terms_and_balance_snapshot': 'terms',
    'entered_revolving_credit_facilities': 'commitment',
    'entered_sales_agreements_authorizing_equity_offering': 'authorization',
    'borrower_under': 'agreement', 'issuer_under_indenture': 'instrument_terms',
    'series_established_under_indenture': 'instrument_terms',
}
ROLE_PATTERN = re.compile(r',\s+as\s+(issuer|guarantor|trustee(?:\s+and\s+notes\s+collateral\s+agent)?|administrative\s+agent|collateral\s+agent|lender|arranger)\b', re.I)
LEGAL_NAME = re.compile(r'(?:[A-Z][A-Za-z0-9&.\'’()\-]*\s+){0,18}[A-Z][A-Za-z0-9&.\'’()\-]*(?:,\s*(?:Inc\.|L\.P\.|N\.A\.|National Association))?(?:,\s*National Association)?$')


def _entity(subject, document, quote, source_texts=(), *, allow_issuer_identifier=False):
    name = str(subject.get('legal_name') or '').strip()
    identifier = subject.get('identifier')
    issues, resolved = [], None
    if identifier:
        # Only a standalone typed CIK is usable. A CIK in a descriptive OP or
        # filing reference does not identify that legal party.
        match = re.fullmatch(r'CIK\s+(\d{1,10})', str(identifier).strip(), re.I)
        if match:
            cik = _cik(match.group(1))
            literal_identifier = re.search(re.escape(name) + r'\s*[(,]?\s*CIK\s+' + re.escape(match.group(1)) + r'\b', quote, re.I) if name else None
            issuer_named = name and any(' '.join(name.casefold().split()) in ' '.join(text.casefold().split()) for text in (quote, *source_texts))
            expected_name = (document.get('company_name') or document.get('issuer_name')) if document else None
            matches_metadata_name = expected_name is None or ' '.join(str(expected_name).casefold().split()) == ' '.join(name.casefold().split())
            partnership_without_named_metadata = not expected_name and bool(re.search(r'\bL\.P\.(?:\s|$)|\bOperating Partnership\b', name, re.I))
            if literal_identifier or (allow_issuer_identifier and document and cik == _cik(document.get('cik')) and issuer_named and matches_metadata_name and not partnership_without_named_metadata):
                resolved = 'cik:' + cik
            else:
                issues.append('identifier_not_supported_by_source_identity')
        else:
            issues.append('ambiguous_identifier')
    return {'entity_id': resolved or 'name:' + _stable_id(name), 'legal_name': name,
            'identity_status': 'supported_identifier' if resolved else 'unresolved_name',
            'identifiers': [identifier] if resolved else [], 'asserted_identifiers': [identifier] if identifier else [],
            'issues': issues}


def _named_roles(quote):
    """Extract only literal named role clauses, for human review."""
    results = []
    for match in ROLE_PATTERN.finditer(quote):
        preceding = quote[:match.start()]
        # Role clauses and agreement introduction delimit the preceding party.
        previous_roles = list(ROLE_PATTERN.finditer(preceding))
        if previous_roles:
            preceding = preceding[previous_roles[-1].end():].lstrip(' ,')
        preceding = re.split(r'\b(?:by and among|among|between|and)\s+', preceding)[-1]
        if ', as successor in interest to ' in preceding:
            preceding = preceding.split(', as successor in interest to ', 1)[0]
        preceding = re.sub(r'\s*\(CIK\s+\d+\)\s*$', '', preceding)
        name_match = re.fullmatch(r"[A-Z][A-Za-z0-9&.'’(), \-]{1,180}", preceding.strip())
        if not name_match:
            continue
        name = name_match.group().strip()
        # Exclude unnamed collective parties even when they appear capitalized.
        if re.search(r'\b(?:Guarantors|Company|Operating Partnership|Subsidiaries|Agents)\b', name) and name in {'Guarantors', 'Company', 'Operating Partnership', 'Subsidiaries', 'Agents'}:
            continue
        label = match.group(1).lower()
        roles = ['trustee', 'collateral_agent'] if 'trustee' in label and 'collateral' in label else [label.replace(' ', '_')]
        for role in roles:
            results.append((name, role))
    # ATM list language establishes potential agents, not completed allocations.
    agents = re.search(r'with each of (.+?)\s*\(each,? an [“\"�]Agent[”\"�]', quote, re.S)
    if agents:
        names = agents.group(1).strip().rstrip('.')
        # Corporate suffixes terminate list entries. Internal commas in a firm
        # name (Keefe, Bruyette & Woods, Inc.) remain inside the literal name.
        parts = re.findall(r'(?:^|(?<=LLC),\s*|(?<=Inc\.),\s*)(?:and\s+)?(.+?(?:LLC|Inc\.))(?=,\s*|$)', names)
        for name in parts:
            if name and name in quote:
                results.append((name, 'sales_agent'))
    return list(dict.fromkeys(results))


def _history(assertion, edge):
    relation = assertion.get('relation_type')
    kind = HISTORY_TYPES.get(relation)
    if kind is None:
        return None
    quote = edge['evidence'].get('quote', '')
    # Preserve nominal amount expressions rather than equating debt principal,
    # offering authorization, or borrowing capacity with realized cash.
    amounts = [{'literal': m.group(), 'char_start_in_quote': m.start(),
                'char_end_in_quote': m.end(), 'interpretation': 'unallocated_reported_expression'}
               for m in re.finditer(r'\$\s*\d[\d,.]*(?:[ \u00a0]*(?:million|billion))?', quote, re.I)]
    return {'assertion_id': assertion.get('assertion_id'), 'company_id': edge['company_id'],
            'subject_id': edge['subject_id'], 'instrument_id': edge['instrument_id'],
            'history_type': kind, 'relation_type': relation,
            'effective_at': assertion.get('effective_at'), 'available_at': edge['available_at'],
            'reported_amounts': amounts, 'is_cash_movement': False, 'additive': False,
            'evidence': edge['evidence'], 'eligibility': edge['eligibility'],
            'unknowns': assertion.get('unknowns', [])}


def _subject_role_supported(assertion, entity, document, quote):
    """Require an explicit named role or a narrow subject/action clause.

    Filing narrator aliases apply only to the evidenced issuer. Merely naming
    a trustee in the same passage cannot assign it an issuer/borrower action.
    This is a conservative gate, not general narrative relation extraction.
    """
    relation = assertion.get('relation_type')
    role = RELATION_ROLES.get(relation)
    name = r'\s+'.join(re.escape(part) for part in entity['legal_name'].split())
    if not name:
        return False
    text = ' '.join(quote.split())
    direct = re.search(name + r'\s*,?\s+as\s+' + str(role) + r'\b', text, re.I)
    if direct or any(n.casefold() == entity['legal_name'].casefold() and r == role
                     for n, r in _named_roles(text)):
        return True
    if relation in {'issuer_under_indenture', 'series_established_under_indenture'}:
        return False
    expected_name = (document.get('company_name') or document.get('issuer_name')) if document else None
    named_issuer = expected_name is not None and ' '.join(str(expected_name).casefold().split()) == ' '.join(entity['legal_name'].casefold().split())
    identified_issuer = bool(document and entity['entity_id'] == 'cik:' + str(_cik(document.get('cik'))))
    issuer = named_issuer or identified_issuer
    actor = '(?:' + name + (r'|\b(?:we|our|the company|the trust)\b' if issuer else '') + ')'
    # Only an optional definition may intervene between the actor and verb;
    # an intervening "as trustee" clause cannot silently become borrower.
    actor += r'\s*(?:\([^)]{0,100}\)\s*)?'
    if relation == 'facility_terms_and_balance_snapshot':
        finance = r'\b(?:borrowings?|credit\s+facilit(?:y|ies)|revolver|loan)\b'
        possession = re.search(name + r"(?:'s|’s)\s+[^;]{0,80}" + finance, text, re.I)
        narrator = issuer and re.search(r'\bour\s+[^;]{0,80}' + finance, text, re.I)
        borrowing = re.search(actor + r'(?:has|have|had|owes?|borrowed)\s+[^;]{0,100}' + finance, text, re.I)
        return bool(possession or narrator or borrowing)
    patterns = {
        'borrower_under': r'(?:entered(?:\s+into)?|borrowed\s+under)\b[^;]{0,180}\b(?:credit\s+(?:facility|agreement)|loan|revolver)\b',
        'entered_revolving_credit_facilities': r'entered(?:\s+into)?\b[^;]{0,180}\b(?:credit\s+facilit(?:y|ies)|revolver)\b',
        'planned_use_of_proceeds': r'(?:intends?|plans?)\s+to\s+use\b[^;]{0,100}\bproceeds\b',
        'completed_debt_issuance': r'(?:completed\b[^;]{0,120}\b(?:offering|issuance)|issued\b[^;]{0,120}\bnotes)\b',
        'completed_secured_note_issuance': r'(?:completed\b[^;]{0,120}\b(?:offering|issuance)|issued\b[^;]{0,120}\bnotes)\b',
        'entered_sales_agreements_authorizing_equity_offering': r'(?:entered\b[^;]{0,100}\bsales agreements?|implemented\b[^;]{0,160}\bissuance program)\b',
        'aggregate_completed_equity_sale_reported': r'issued\b[^;]{0,120}\b(?:shares|equity)\b',
    }
    action = patterns.get(relation)
    if action and re.search(actor + action, text, re.I):
        return True
    # Reported issuance bullets can omit "we" when issuer identity is explicit.
    return bool(issuer and relation == 'aggregate_completed_equity_sale_reported'
                and re.match(r'Issued\b[^;]{0,120}\b(?:shares|equity)\b', text, re.I))


def build_relationships(assertions: list[dict], documents: list[dict], as_of: str | None = None) -> dict:
    """Build verified role facts, local instruments, and reviewable intersections.

    An inclusive ``as_of`` cutoff applies to available_at only. The output never
    treats a trustee, arranger, or agent as a lender. Exact names can generate
    intersections for review; only supported party identifiers can qualify an
    intersection as a resolved entity intersection.
    """
    cutoff = _timestamp(as_of, required=True) if as_of is not None else None
    index = _EvidenceIndex(documents)
    entities, instruments, edges, history, review, links = {}, {}, [], [], [], []
    assertion_instruments, instrument_names = {}, {}
    rejected, pit_excluded = 0, 0
    identities = defaultdict(set)
    for assertion in assertions:
        identities[assertion.get('assertion_id')].add(_stable_id(assertion))
    seen_assertions = set()
    for assertion in assertions:
        reference = assertion.get('evidence') or {}
        issues, document = index.verify(assertion, [reference])
        assertion_key = assertion.get('assertion_id')
        if not assertion_key:
            issues.append('assertion_id_missing')
        elif len(identities[assertion_key]) > 1:
            issues.append('assertion_id_conflict')
        elif assertion_key in seen_assertions:
            continue
        seen_assertions.add(assertion_key)
        relation = assertion.get('relation_type')
        role = RELATION_ROLES.get(relation)
        if not role:
            issues.append('relation_type_unrecognized')
        subject = assertion.get('subject') or {}
        quote = reference.get('quote') or ''
        expected_issuer_name = (document.get('company_name') or document.get('issuer_name')) if document else None
        matches_named_issuer = expected_issuer_name is not None and ' '.join(str(expected_issuer_name).casefold().split()) == ' '.join(str(subject.get('legal_name') or '').casefold().split())
        entity = _entity(subject, document, quote, index.content(document)[1] if document else (), allow_issuer_identifier=role not in COUNTERPARTY_ROLES or matches_named_issuer)
        if not entity['legal_name']:
            issues.append('subject_name_missing')
        if entity['legal_name'] and ' '.join(entity['legal_name'].casefold().split()) not in ' '.join(quote.casefold().split()) and entity['identity_status'] != 'supported_identifier':
            issues.append('subject_name_not_in_quote')
        if role in COUNTERPARTY_ROLES:
            name_pattern = r'\s+'.join(re.escape(part) for part in entity['legal_name'].split())
            role_pattern = {'collateral_agent': r'(?:notes\s+)?collateral\s+agent', 'sales_agent': r'(?:sales\s+)?agent'}.get(role, role.replace('_', r'\s+'))
            direct = re.search(name_pattern + r'\s*,?\s+as\s+' + role_pattern + r'\b', quote, re.I)
            compound = any(n.casefold() == entity['legal_name'].casefold() and r == role for n, r in _named_roles(quote))
            if not (direct or compound):
                issues.append('asserted_role_not_in_quote')
        elif role and not _subject_role_supported(assertion, entity, document, quote):
            issues.append('asserted_role_not_in_quote')
        if HISTORY_TYPES.get(relation) == 'completed_event' and not re.search(r'\bcompleted\b.{0,120}\b(?:offering|issuance)\b|\bissued\b.{0,160}\bnet\s+proceeds\b', quote, re.I | re.S):
            issues.append('completed_event_not_in_quote')
        available = _available_record(assertion, document)
        eligibility = _eligibility(issues, available, cutoff)
        company_cik = _cik(document.get('cik')) if document else None
        company_id = 'cik:' + company_cik if company_cik else None
        pit_excluded += not eligibility['pit_eligible']
        if not eligibility['eligible']:
            rejected += bool(issues)
            review.append({'assertion_id': assertion.get('assertion_id'), 'assertion': assertion,
                           'issues': sorted(set(issues)), 'eligibility': eligibility,
                           'identity_issues': entity['issues']})
            continue
        entities.setdefault(entity['entity_id'], entity)
        stored = entities[entity['entity_id']]
        stored['asserted_identifiers'] = sorted(set(stored['asserted_identifiers'] + entity['asserted_identifiers']))
        stored['issues'] = sorted(set(stored['issues'] + entity['issues']))
        target = assertion.get('object') or {}
        # Default identity is local to the sourced assertion. Amounts, rates,
        # and dates alone do not establish instrument identity.
        instrument_id = 'instrument:' + _stable_id([_document_id(document), assertion.get('assertion_id'), target.get('legal_name')])
        same = re.fullmatch(r'same facility as assertion ([\w-]+)', str(target.get('identifier') or ''), re.I)
        if same:
            prior = assertion_instruments.get(same.group(1))
            if prior and instrument_names.get(prior) == target.get('legal_name') and target.get('legal_name', '') in quote:
                prior_instrument = instruments[prior]
                if prior_instrument['company_id'] == company_id and prior_instrument['document_id'] == _document_id(document):
                    instrument_id = prior
                    links.append({'from_assertion_id': assertion.get('assertion_id'), 'to_assertion_id': same.group(1),
                                  'relation': 'same_explicitly_named_facility', 'evidence': reference,
                                  'eligibility': eligibility})
        instrument = instruments.setdefault(instrument_id, {'instrument_id': instrument_id,
            'legal_name': target.get('legal_name'), 'asserted_identifier': assertion.get('instrument_identifier'),
            'identity_status': 'source_local_named_instrument', 'company_id': company_id,
            'document_id': _document_id(document), 'assertion_ids': [], 'evidence': []})
        instrument['assertion_ids'].append(assertion.get('assertion_id'))
        instrument['evidence'].append(reference)
        assertion_instruments[assertion.get('assertion_id')] = instrument_id
        instrument_names[instrument_id] = target.get('legal_name')
        edge = {'edge_id': 'edge:' + _stable_id([assertion.get('assertion_id'), role]),
                'assertion_id': assertion.get('assertion_id'), 'subject_id': entity['entity_id'],
                'subject_name': entity['legal_name'], 'instrument_id': instrument_id, 'company_id': company_id,
                'relation_type': relation, 'role': role, 'is_lender': role == 'lender',
                'effective_at': assertion.get('effective_at'), 'available_at': available,
                'evidence': reference, 'eligibility': eligibility, 'identity_issues': entity['issues'],
                'unknowns': assertion.get('unknowns', []), 'candidate_expansion': False}
        edges.append(edge)
        if entity['issues']:
            review.append({'assertion_id': assertion.get('assertion_id'), 'item_type': 'entity_identity',
                           'entity_id': entity['entity_id'], 'issues': entity['issues'], 'evidence': reference})
        financial = _history(assertion, edge)
        if financial:
            history.append(financial)
        for name, named_role in _named_roles(quote):
            if name.casefold() == entity['legal_name'].casefold() and named_role == role:
                continue
            named = _entity({'legal_name': name}, document, quote)
            entities.setdefault(named['entity_id'], named)
            candidate = {**edge, 'edge_id': 'edge:' + _stable_id([assertion.get('assertion_id'), name, named_role]),
                         'subject_id': named['entity_id'], 'subject_name': name, 'role': named_role,
                         'is_lender': named_role == 'lender', 'candidate_expansion': True,
                         'identity_issues': [], 'eligibility': _eligibility([], available, cutoff, candidate=True)}
            edges.append(candidate)
            review.append({'assertion_id': assertion.get('assertion_id'), 'item_type': 'named_role_expansion',
                           'edge_id': candidate['edge_id'], 'issues': ['human_review_required'],
                           'evidence': reference, 'eligibility': candidate['eligibility']})
    counterparties = defaultdict(list)
    for edge in edges:
        if edge['role'] in COUNTERPARTY_ROLES and edge['company_id'] and edge['eligibility']['source_eligible']:
            counterparties[edge['subject_id']].append(edge)
    intersections = []
    for counterparty_id, related in counterparties.items():
        company_ids = sorted({r['company_id'] for r in related})
        if len(company_ids) < 2:
            continue
        identified = entities[counterparty_id]['identity_status'] == 'supported_identifier'
        candidate = not identified or any(r['candidate_expansion'] for r in related)
        intersections.append({'intersection_id': 'intersection:' + _stable_id([counterparty_id, company_ids]),
                              'counterparty_id': counterparty_id,
                              'counterparty_name': entities[counterparty_id]['legal_name'],
                              'company_ids': company_ids,
                              'basis': 'shared_verified_counterparty' if identified else 'shared_exact_name_counterparty',
                              'identity_status': entities[counterparty_id]['identity_status'],
                              'roles': sorted({r['role'] for r in related}),
                              'edge_ids': [r['edge_id'] for r in related],
                              'evidence': [r['evidence'] for r in related],
                              'eligibility': _eligibility([], max((_timestamp(r['available_at']) for r in related)).isoformat() if all(_timestamp(r['available_at']) is not None for r in related) else None, cutoff, candidate=candidate)})
    return {'schema_version': 1, 'as_of': as_of,
            'company_entities': _company_entities(documents, index, cutoff, entities),
            'entities': list(entities.values()), 'instruments': list(instruments.values()),
            'instrument_links': links, 'role_edges': edges, 'financial_history': history,
            'intersections': intersections, 'review': review,
            'coverage': {'input_assertions': len(assertions), 'documents': len(documents),
                         'source_rejected': rejected, 'pit_excluded': pit_excluded,
                         'verified_role_edges': sum(e['eligibility']['eligible'] for e in edges),
                         'candidate_role_edges': sum(e['candidate_expansion'] for e in edges),
                         'resolved_intersections': sum(i['eligibility']['eligible'] for i in intersections),
                         'candidate_intersections': sum(not i['eligibility']['eligible'] for i in intersections),
                         'complete': False, 'scope': 'retained_source_assertions_only'}}


def _company_entities(documents, index, cutoff, entities):
    """Keep issuer metadata nodes separate from named instrument parties."""
    companies = {}
    for document in documents:
        cik = _cik(document.get('cik'))
        if not cik:
            continue
        failures, _, _, digest = index.content(document)
        available = _available_record({}, document)
        eligibility = _eligibility(failures, available, cutoff)
        if not eligibility['eligible']:
            continue
        identifier = 'cik:' + cik
        name = document.get('company_name') or document.get('issuer_name') or entities.get(identifier, {}).get('legal_name')
        node = companies.setdefault(identifier, {'entity_id': identifier, 'cik': cik,
            'legal_name': name, 'identity_status': 'explicit_manifest_issuer_identifier',
            'identity_scope': 'filing_issuer_metadata_no_operating_partnership_alias',
            'source_documents': []})
        if node['legal_name'] is None and name:
            node['legal_name'] = name
        node['source_documents'].append({'document_id': _document_id(document),
            'source_sha256': digest, 'available_at': available})
    for node in companies.values():
        times = [_timestamp(d['available_at']) for d in node['source_documents']]
        aware = [t for t in times if t is not None]
        available = min(aware).isoformat() if aware else None
        node['available_at'] = available
        node['eligibility'] = _eligibility([], available, cutoff)
    return list(companies.values())


def discover_relationship_candidates(documents: list[dict], as_of: str | None = None) -> dict:
    """Read cached native prose agreement passages into exact review candidates.

    No OCR, files, requests, model calls, party allocations, or adjudicated edges
    are produced. Native extraction/source integrity is required even for a
    discovery candidate. Missing timestamps prevent PIT discovery eligibility.
    """
    cutoff = _timestamp(as_of, required=True) if as_of is not None else None
    index = _EvidenceIndex(documents)
    candidates, issues, skipped = [], [], 0
    for document in documents:
        failures, _, pages, digest = index.content(document)
        if failures:
            issues.append({'document_id': _document_id(document), 'issues': failures})
            skipped += 1
            continue
        if 'ocr' in str(document.get('source_method') or '').lower():
            issues.append({'document_id': _document_id(document), 'issues': ['native_text_required']})
            skipped += 1
            continue
        available = _available_record({}, document)
        if cutoff is not None and not _eligibility([], available, cutoff)['pit_eligible']:
            skipped += 1
            continue
        for page in pages:
            text = page.get('text', '')
            if 'ocr' in str(page.get('method') or page.get('extraction_method') or '').lower():
                continue
            for match in re.finditer(r'[^\r\n]+', text):
                quote = match.group()
                if len(quote) > 4000 or not re.search(r'\b(?:agreement|indenture|facility|sales agreements?)\b', quote, re.I):
                    continue
                if not re.search(r'\b(?:trustee|lender|agent|arranger|borrower|guarantor|issuer)\b', quote, re.I):
                    continue
                reference = {'document_id': _document_id(document), 'source_sha256': digest,
                             'quote': quote, 'locator': 'native_page_character_span',
                             'page_number': page.get('number'), 'char_start': match.start(), 'char_end': match.end()}
                candidates.append({'candidate_id': 'candidate:' + _stable_id(reference),
                                   'candidate_type': 'native_prose_agreement', 'available_at': available,
                                   'evidence': reference, 'eligibility': _eligibility([], available, cutoff, candidate=True),
                                   'issues': ['native_text_decode_loss'] if '\ufffd' in quote else [],
                                   'named_role_candidates': [{'legal_name': n, 'role': r} for n, r in _named_roles(quote)]})
    return {'schema_version': 1, 'as_of': as_of, 'candidates': candidates,
            'coverage': {'documents': len(documents), 'skipped_documents': skipped,
                         'candidate_count': len(candidates), 'issues': issues, 'complete': False}}

def _normalized_text_map(text):
    parts, starts, ends = [], [], []
    for token in re.finditer(r'\s+|\S+', text):
        value = token.group()
        if value[0].isspace():
            parts.append(' ')
            starts.append(token.start())
            ends.append(token.end())
        else:
            parts.append(value)
            starts.extend(range(token.start(), token.end()))
            ends.extend(range(token.start() + 1, token.end() + 1))
    return ''.join(parts), starts, ends


def normalize_assertions(assertions: list[dict], documents: list[dict]) -> dict:
    """Recover exact native quote spans using whitespace equivalence only.

    The supplied assertions and retained files are never changed. Substantive
    wording, punctuation, capitalization, and party identity remain untouched.
    Ambiguous matches and integrity failures remain review items. Changes retain
    both original and corrected evidence for a reproducible audit.
    """
    from copy import deepcopy
    index = _EvidenceIndex(documents)
    normalized, changes, review, page_cache = [], [], [], {}
    for original in assertions:
        reference = original.get('evidence') or {}
        document = index.find(original, reference)
        if document is None:
            review.append({'assertion_id': original.get('assertion_id'), 'assertion': original,
                           'issues': ['document_missing_or_ambiguous']})
            continue
        failures, texts, pages, expected = index.content(document)
        failures = list(failures)
        if reference.get('source_sha256') != expected:
            failures.append('evidence_source_hash_mismatch')
        if failures:
            review.append({'assertion_id': original.get('assertion_id'), 'assertion': original,
                           'issues': sorted(set(failures))})
            continue
        quote = reference.get('quote')
        if not isinstance(quote, str) or not quote.strip():
            review.append({'assertion_id': original.get('assertion_id'), 'assertion': original,
                           'issues': ['quote_missing']})
            continue
        query = ' '.join(quote.split())
        locations = []
        search_pages = pages or ([{'number': None, 'text': document['raw_text']}] if isinstance(document.get('raw_text'), str) else [])
        for page in search_pages:
            text = page.get('text', '')
            cache_key = (id(document), page.get('number'), _stable_id(text))
            if cache_key not in page_cache:
                page_cache[cache_key] = _normalized_text_map(text)
            plain, starts, ends = page_cache[cache_key]
            cursor = 0
            while (position := plain.find(query, cursor)) >= 0:
                start, end = starts[position], ends[position + len(query) - 1]
                locations.append((page.get('number'), start, end, text[start:end]))
                cursor = position + len(query)
        if len(locations) != 1:
            review.append({'assertion_id': original.get('assertion_id'), 'assertion': original,
                           'issues': ['quote_not_found' if not locations else 'quote_location_ambiguous']})
            continue
        number, start, end, exact = locations[0]
        assertion = deepcopy(original)
        corrected = {**reference, 'quote': exact, 'page_number': number,
                     'char_start': start, 'char_end': end,
                     'locator_type': 'cached_page_character_span',
                     'locator': f'native extracted page {number}, character span {start}:{end}'}
        assertion['evidence'] = corrected
        normalized.append(assertion)
        if corrected != reference:
            changes.append({'assertion_id': original.get('assertion_id'),
                            'method': 'exact_native_span' if exact == quote else 'whitespace_equivalent_native_span',
                            'original_evidence': deepcopy(reference), 'normalized_evidence': deepcopy(corrected)})
    return {'assertions': normalized, 'changes': changes, 'review': review,
            'coverage': {'input_assertions': len(assertions), 'normalized_assertions': len(normalized),
                         'changes': len(changes), 'review_assertions': len(review)}}
