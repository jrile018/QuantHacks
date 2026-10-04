"""Bounded continuation of published instrument assertions, not a canonical ledger.

This module does not acquire sources or re-adjudicate the upstream evidence.
It keeps canonical IDs/eligibility and adds literal, source-local component
scopes. An agreement reference is a relation, never an identity merge.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from decimal import Decimal
import re

from src.reit_histories import _stable_id, _timestamp
from src.reit_relationships import _named_roles


_AMOUNT = r'(?P<symbol>\$|USD\s+|EUR\s+|GBP\s+)(?P<number>\d[\d,.]*)(?:[\s\u00a0]*(?P<scale>million|billion))?'
_NOTE = re.compile(r'(?:' + _AMOUNT + r'\s+aggregate principal amount of (?:its\s+)?)?(?P<rate>\d+\.\d+)%\s+(?P<label>senior\s+(?:unsecured\s+|secured\s+)?notes\s+due\s+(?P<year>\d{4}))', re.I)
_FACILITY = re.compile(_AMOUNT + r'\s+(?:unsecured\s+)?(?:multicurrency\s+)?revolving credit facility,?\s+consisting of (?P<tranches>two|\d+) tranches,?\s+that will mature in\s+(?P<month>[A-Za-z]+)\s+(?P<year>\d{4})', re.I)
_PRIOR = re.compile(r'previous\s+' + _AMOUNT + r'\s+(?:unsecured\s+)?(?:multicurrency\s+)?revolving credit facility', re.I)
_CAPACITY = re.compile(_AMOUNT + r'\s+(?:senior\s+)?(?:unsecured\s+)?(?:multicurrency\s+)?revolving credit facilit(?:y|ies)', re.I)
_PROCEEDS = re.compile(r'(?:net proceeds of\s+' + _AMOUNT + r'|' + _AMOUNT.replace('(?P<', '(?P<p_') + r'\s+net proceeds)', re.I)
_BASE = re.compile(r'\bIndenture,?\s+dated\s+(?:as of\s+)?(?P<date>[A-Za-z]+\s+\d{1,2},\s+\d{4})', re.I)


def _eligible(row, cutoff):
    result = deepcopy(row.get('eligibility', {}))
    result.setdefault('source_eligible', False)
    result.setdefault('eligible', False)
    result.setdefault('reasons', [])
    available = _timestamp(row.get('available_at'))
    result['pit_eligible'] = available is not None and (cutoff is None or available <= cutoff)
    if cutoff is not None and not result['pit_eligible']:
        result['eligible'] = False
        result['reasons'] = sorted(set(result['reasons'] + ['not_yet_available' if available else 'availability_unknown_or_not_timezone_aware']))
    return result


def _provenance(row):
    evidence = row.get('evidence') or {}
    return bool(evidence.get('source_sha256') and evidence.get('document_id')
                and evidence.get('locator') and isinstance(evidence.get('quote'), str)
                and evidence['quote'])


def _amount(match, prefix=''):
    number = match.group(prefix + 'number')
    value = Decimal(number.replace(',', ''))
    scale = match.group(prefix + 'scale')
    value *= {'million': Decimal(1000000), 'billion': Decimal(1000000000)}.get((scale or '').lower(), Decimal(1))
    symbol = match.group(prefix + 'symbol').strip()
    return str(value), symbol if symbol in {'USD', 'EUR', 'GBP'} else None, symbol


def _component(event, kind, label, span, *, tranche_count=None):
    identifier = 'component:' + _stable_id([event['instrument_id'], event['subject_id'],
        event['event_id'], event['evidence']['document_id'], event['evidence']['source_sha256'],
        event['evidence']['locator'], event['evidence'].get('page_number'), kind, label, list(span)])
    result = {'component_id': identifier, 'parent_instrument_id': event['instrument_id'],
              'subject_id': event['subject_id'], 'company_id': event.get('company_id'),
              'component_kind': kind, 'literal_name': label, 'event_id': event['event_id'],
              'identity_status': 'source_local_scope_not_cross_document_identity',
              'evidence': deepcopy(event['evidence']), 'eligibility': deepcopy(event['eligibility']),
              'quote_span': list(span)}
    if tranche_count is not None:
        result['tranche_count'] = tranche_count
        result['tranche_identities'] = None
    return result


def _term(event, component, metric, value, match, **extra):
    return {'instrument_id': event['instrument_id'], 'component_id': component['component_id'],
            'subject_id': event['subject_id'], 'event_id': event['event_id'],
            'metric': metric, 'value': value, 'currency': None, 'amount_kind': None,
            'effective_at': event.get('effective_at'), 'available_at': event.get('available_at'),
            'period_start': event.get('period_start'), 'period_end': event.get('period_end'),
            'eligibility': deepcopy(event['eligibility']), 'evidence': deepcopy(event['evidence']),
            'quote_span': [match.start(), match.end()], 'literal_scope': match.group(),
            'additive': False, **extra}


def _derive(event):
    quote = event['evidence']['quote']
    relation = event.get('relation_type')
    components, terms = [], []
    for match in _NOTE.finditer(quote):
        label = match.group('rate') + '% ' + match.group('label')
        c = _component(event, 'note_series', label, match.span())
        components.append(c)
        terms.extend([_term(event, c, 'stated_interest_rate_percent', match.group('rate'), match),
                      _term(event, c, 'maturity', match.group('year'), match, precision='year')])
        if match.group('number'):
            value, currency, symbol = _amount(match)
            kind = 'planned_repayment_principal' if relation == 'planned_use_of_proceeds' else 'issued_principal' if relation in {'completed_debt_issuance', 'completed_secured_note_issuance'} else 'stated_principal'
            terms.append(_term(event, c, 'amount', value, match, currency=currency,
                               currency_symbol=symbol, amount_kind=kind))
    for match in _FACILITY.finditer(quote):
        count = 2 if match.group('tranches').lower() == 'two' else int(match.group('tranches'))
        label = 'facility maturing ' + match.group('month') + ' ' + match.group('year')
        c = _component(event, 'facility', label, match.span(), tranche_count=count)
        components.append(c)
        value, currency, symbol = _amount(match)
        terms.extend([_term(event, c, 'amount', value, match, currency=currency, currency_symbol=symbol, amount_kind='capacity'),
                      _term(event, c, 'maturity', match.group('month') + ' ' + match.group('year'), match, precision='month')])
    prior = _PRIOR.search(quote)
    if prior and re.search(r'amend and\s+restate', quote, re.I):
        c = _component(event, 'prior_facility_reference', prior.group(), prior.span())
        components.append(c)
        value, currency, symbol = _amount(prior)
        terms.append(_term(event, c, 'amount', value, prior, currency=currency, currency_symbol=symbol, amount_kind='prior_capacity'))
    if relation == 'planned_use_of_proceeds':
        for match in _CAPACITY.finditer(quote):
            c = _component(event, 'facility_reference', match.group(), match.span())
            components.append(c)
            value, currency, symbol = _amount(match)
            terms.append(_term(event, c, 'amount', value, match, currency=currency, currency_symbol=symbol, amount_kind='capacity'))
    for match in _PROCEEDS.finditer(quote):
        prefix = '' if match.group('number') is not None else 'p_'
        c = _component(event, 'proceeds_report', 'reported net proceeds', match.span())
        components.append(c)
        value, currency, symbol = _amount(match, prefix)
        terms.append(_term(event, c, 'amount', value, match, currency=currency, currency_symbol=symbol, amount_kind='net_proceeds_reported'))
    return components, terms


def _queue(event, status, request, **extra):
    return {'queue_id': 'history-review:' + _stable_id([event.get('event_id'), status, request, extra]),
            'status': status, 'instrument_id': event.get('instrument_id'),
            'assertion_id': event.get('assertion_id'), 'evidence': deepcopy(event.get('evidence')),
            'request': request, **extra}


def _link(left, right_id, relation, evidence, *, target_kind='instrument'):
    return {'link_id': 'instrument-link:' + _stable_id([left['instrument_id'], right_id, relation, evidence]),
            'from_instrument_id': left['instrument_id'], 'target_kind': target_kind,
            ('to_component_id' if target_kind == 'component' else 'to_instrument_id'): right_id,
            'relation_type': relation, 'identity_merge': False,
            'effective_at': left.get('effective_at'), 'available_at': left.get('available_at'),
            'eligibility': deepcopy(left['eligibility']), 'evidence': deepcopy(evidence)}


def _calendar_period(start, end):
    try:
        return bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(start))
                    and re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(end))
                    and date.fromisoformat(start) < date.fromisoformat(end))
    except (ValueError, TypeError):
        return False


def _same_base_anchor(base, series):
    # The bounded packet can prove a same-document reference with full named
    # parties. Repeated dates or shared names across filings remain unresolved.
    if (base['evidence']['document_id'], base['evidence']['source_sha256']) != (series['evidence']['document_id'], series['evidence']['source_sha256']):
        return False
    named_parties = _named_roles(base['evidence']['quote'])
    quote = ' '.join(series['evidence']['quote'].casefold().split())
    return bool(named_parties and all(' '.join(name.casefold().split()) in quote
                                     for name, _ in named_parties))


def _correspondence_scopes(components, reviews, cutoff, queue):
    """Reviewed correspondence affects ordering only; components never merge."""
    index = {c['component_id']: c for c in components}
    candidates = []
    def reject(review, issues):
        queue.append(_queue({'event_id': review.get('correspondence_id'), 'evidence': review.get('component_anchors')},
                            'correspondence_review_unresolved',
                            'Provide approved same-scope review with exact source/version/clause anchors and a known review time.',
                            correspondence_id=review.get('correspondence_id'), issues=issues))
    for supplied in reviews:
        review = deepcopy(supplied)
        anchors = review.get('component_anchors') or []
        ids = [a.get('component_id') for a in anchors]
        reviewed = _timestamp(review.get('reviewed_at'))
        issues = []
        if not review.get('correspondence_id') or review.get('review_status') != 'approved' or not review.get('identity_basis'):
            issues.append('explicit_approved_review_missing')
        if reviewed is None or (cutoff is not None and reviewed > cutoff):
            issues.append('review_information_time_unavailable')
        if len(set(ids)) < 2 or len(set(ids)) != len(ids) or any(i not in index for i in ids):
            issues.append('component_anchors_missing_or_ambiguous')
        else:
            scope = {(index[i]['parent_instrument_id'], index[i]['subject_id'], index[i]['component_kind']) for i in ids}
            if len(scope) != 1:
                issues.append('different_instrument_entity_or_component_kind')
            for anchor in anchors:
                c = index[anchor['component_id']]
                evidence = c['evidence']
                if any(anchor.get(k) != evidence.get(k) for k in ('document_id', 'source_sha256', 'locator')) or anchor.get('quote_span') != c['quote_span']:
                    issues.append('source_version_or_clause_anchor_mismatch')
        if issues:
            reject(review, sorted(set(issues)))
        else:
            candidates.append((review, ids))
    references = defaultdict(int)
    for _, ids in candidates:
        for i in ids:
            references[i] += 1
    mapping, accepted = {}, []
    for review, ids in candidates:
        if any(references[i] != 1 for i in ids):
            reject(review, ['overlapping_correspondence_reviews'])
            continue
        ordering_id = 'reviewed-history-scope:' + _stable_id([review['correspondence_id'], sorted(ids)])
        for i in ids:
            mapping[i] = ordering_id
        accepted.append({**review, 'ordering_scope_id': ordering_id, 'canonical_identity_merge': False})
    return mapping, accepted


def _views(events, queue, correspondence_scopes):
    groups = defaultdict(list)
    unordered = []
    for event in events:
        if not event['eligibility'].get('eligible'):
            continue
        for term in event['terms']:
            if _timestamp(term.get('available_at')) is None:
                unordered.append({**deepcopy(term), 'ordering_status': 'information_time_unknown'})
                continue
            ordering_scope = correspondence_scopes.get(term['component_id'], term['component_id'])
            key = (term['instrument_id'], ordering_scope, term['subject_id'], term['metric'], term['currency'], term['amount_kind'])
            groups[key].append(term)
    original, latest, flows = [], [], []
    for key in sorted(groups, key=str):
        rows = sorted(groups[key], key=lambda r: (_timestamp(r['available_at']) is None,
                                                 _timestamp(r['available_at']).isoformat() if _timestamp(r['available_at']) else '', r['event_id']))
        original.append(deepcopy(rows[0]))
        latest.append(deepcopy(rows[-1]))
        occupied = []
        for term in rows:
            event = next(e for e in events if e['event_id'] == term['event_id'])
            if term['metric'] != 'amount' or term['amount_kind'] != 'net_proceeds_reported' or not event['is_cash_movement']:
                continue
            start, end = term.get('period_start'), term.get('period_end')
            if not term['currency'] or not _calendar_period(start, end):
                queue.append(_queue(event, 'cash_flow_scope_incomplete', 'Provide explicit currency and exact nonempty reporting period; no flow is inferred.'))
                continue
            # Periods use [start,end); overlapping observations are alternatives.
            if any(start < old_end and old_start < end for old_start, old_end in occupied):
                queue.append(_queue(event, 'overlapping_flow_period', 'Resolve overlapping reports before any aggregation.'))
                continue
            occupied.append((start, end))
            flows.append(deepcopy(term))
    return {'original': original, 'latest': latest, 'nonoverlapping_flow': flows,
            'information_time_unordered': unordered,
            'ordering_scope': 'source_version_clause_or_explicit_reviewed_correspondence',
            'period_convention': '[period_start,period_end)', 'aggregation_performed': False}


def build_instrument_history_packet(histories, instruments=(), role_edges=(), entities=(), *, as_of=None, reviewed_correspondences=()):
    """Extend only retained source-supported assertions; never join by name/amount.

    `eligible` is inherited, with an optional stricter information cutoff.
    Upstream candidate roles cannot become eligible in this extension.
    Raw-source hashes/quote locators are inherited, not independently verified.
    """
    cutoff = _timestamp(as_of, required=True) if as_of is not None else None
    instrument_index = {i['instrument_id']: i for i in instruments}
    events, components, links, queue = [], [], [], []
    roles = deepcopy(list(role_edges))
    inputs = deepcopy(list(histories))
    existing = {(r['instrument_id'], r.get('assertion_id')) for r in inputs}
    for role in roles:
        role['eligibility'] = _eligible(role, cutoff)
        role['syndicate_share'] = None
        role['exposure_amount'] = None
        role['connection_interpretation'] = 'instrument_role_only_no_causal_exposure'
        if (role['instrument_id'], role.get('assertion_id')) not in existing and not role.get('candidate_expansion'):
            inputs.append({**deepcopy(role), 'subject_id': role['subject_id'], 'history_type': 'role_assertion',
                           'is_cash_movement': False, 'additive': False})
            existing.add((role['instrument_id'], role.get('assertion_id')))
    for source in inputs:
        event = deepcopy(source)
        event['event_id'] = 'instrument-event:' + _stable_id([source.get('assertion_id'), source['instrument_id'], source.get('subject_id'), source.get('evidence')])
        event['eligibility'] = _eligible(event, cutoff)
        if not event['eligibility'].get('source_eligible') or not _provenance(event):
            queue.append(_queue(event, 'source_quarantined', 'Resolve source eligibility and hash-bound quote locator before using this assertion.'))
            continue
        event['lifecycle_status'] = 'planned_only' if event.get('relation_type') == 'planned_use_of_proceeds' else 'agreement_reported' if event.get('relation_type') in {'borrower_under', 'entered_revolving_credit_facilities'} else 'assertion_only'
        if event.get('relation_type') == 'instrument_terminated':
            name = instrument_index.get(event['instrument_id'], {}).get('legal_name')
            quote = ' '.join(event['evidence']['quote'].split())
            if name and re.search(re.escape(name) + r'\s+(?:was|is|has been)\s+terminated\b', quote, re.I):
                event['lifecycle_status'] = 'terminated_reported'
            else:
                queue.append(_queue(event, 'lifecycle_scope_unresolved', 'Provide a termination clause explicitly naming this instrument.'))
        # A completed offering's principal is not a cash receipt measurement.
        event['is_cash_movement'] = bool(event.get('is_cash_movement') and event.get('relation_type') == 'cash_flow_reported')
        event['additive'] = False
        event['first_public_at'] = None
        event['date_interpretation'] = 'effective_date_distinct_from_information_date'
        event['evidence_verification'] = 'inherited_published_source_eligibility_not_revalidated_raw_bytes'
        derived_components, event['terms'] = _derive(event)
        components.extend(derived_components)
        events.append(event)
        operative = {
            'issuer_under_indenture': ('Executed base indenture referenced by the full named-party/date clause; original principal and any amendments.', ['issuer', 'guarantor', 'trustee']),
            'series_established_under_indenture': ("Officers' certificate for the quoted series under the dated base indenture; exact maturity, principal and settlement clauses.", ['issuer', 'guarantor', 'trustee']),
            'completed_debt_issuance': ('Operative note-series and supplemental-indenture clauses for each stated rate/maturity series; exact settlement, proceeds and maturity dates.', ['issuer', 'trustee']),
            'completed_secured_note_issuance': ('Operative indenture and guarantor schedules for the dated secured-note issuance; keep all declared source conflicts excluded.', ['issuer', 'guarantor', 'trustee', 'collateral_agent']),
            'entered_revolving_credit_facilities': ('Executed new facilities, prior agreement reference, and tranche/currency schedules; named lender/agent roles, commitments and subsequent outstanding balance disclosures.', ['borrower', 'lender', 'administrative_agent', 'guarantor']),
            'planned_use_of_proceeds': ('Executed multicurrency revolver agreement amended/restated in December 2021 and subsequent amendments explicitly referenced in the quote; actual repayment confirmation for the old note series.', ['borrower', 'lender', 'administrative_agent']),
        }.get(event.get('relation_type'))
        if operative:
            queue.append(_queue(event, 'operative_agreement_missing', operative[0],
                                effective_at=event.get('effective_at'),
                                requested_evidence_roles=operative[1],
                                availability_in_retained_corpus='not_checked_outside_bounded_packet',
                                requested_instrument_scopes=[c['literal_name'] for c in derived_components]))
        if source.get('unknowns'):
            queue.append(_queue(event, 'missing_evidence', 'Retrieve operative source clauses resolving: ' + '; '.join(source['unknowns'])))
        if not _timestamp(event.get('available_at')):
            queue.append(_queue(event, 'information_date_unknown', 'Provide observed source availability evidence; original first-public date remains unknown.'))
        if event.get('relation_type') == 'planned_use_of_proceeds':
            queue.append(_queue(event, 'repayment_unconfirmed', 'Provide completed repayment notice or subsequent balance evidence tied to the exact old notes/facility; intention is insufficient.'))
        if 'SUPPLEMENTAL INDENTURE' in event['evidence']['quote'].upper():
            queue.append(_queue(event, 'agreement_series_link_unresolved', 'Provide operative supplemental-indenture clauses naming each note series and linking it to the completed offering; cover-page dates/aggregate amounts do not prove identity.'))
        for c in derived_components:
            if c['component_kind'] == 'prior_facility_reference':
                links.append(_link(event, c['component_id'], 'amends_and_restates_reference', [event['evidence']], target_kind='component'))
            if c.get('tranche_count'):
                queue.append(_queue(event, 'tranche_identity_unknown', 'Provide named tranche schedules, currency/commitment terms, lender and agent roles, and syndicate shares for ' + c['literal_name'], component_id=c['component_id']))
    bases = [e for e in events if e.get('relation_type') == 'issuer_under_indenture']
    for series in [e for e in events if e.get('relation_type') == 'series_established_under_indenture']:
        reference = _BASE.search(series['evidence']['quote'])
        matches = [b for b in bases if b['company_id'] == series['company_id'] and b['subject_id'] == series['subject_id']
                   and reference and _BASE.search(b['evidence']['quote'])
                   and _same_base_anchor(b, series)
                   and _BASE.search(b['evidence']['quote']).group('date').casefold() == reference.group('date').casefold()]
        if len(matches) == 1:
            link = _link(series, matches[0]['instrument_id'], 'series_under_agreement', [matches[0]['evidence'], series['evidence']])
            if not matches[0]['eligibility'].get('eligible'):
                link['eligibility']['eligible'] = False
                link['eligibility']['reasons'] = sorted(set(link['eligibility']['reasons'] + ['referenced_agreement_ineligible']))
            links.append(link)
        else:
            queue.append(_queue(series, 'agreement_series_link_unresolved', 'Provide uniquely identified same-issuer base agreement referenced by this series.'))
    events.sort(key=lambda e: (e.get('effective_at') is None, e.get('effective_at') or '', e.get('available_at') or '', e['event_id']))
    component_map = {}
    for c in components:
        if c['component_id'] in component_map and c != component_map[c['component_id']]:
            raise ValueError('component identity collision with inconsistent provenance')
        component_map.setdefault(c['component_id'], c)
    ordering_scopes, accepted_reviews = _correspondence_scopes(list(component_map.values()), reviewed_correspondences, cutoff, queue)
    views = _views(events, queue, ordering_scopes)
    return {'schema_version': 'reit-instrument-history-extension-2', 'as_of': as_of,
            'events': events, 'components': list(component_map.values()), 'instrument_links': links,
            'role_assertions': roles, 'entities': deepcopy(list(entities)),
            'canonical_instruments': deepcopy(list(instruments)), 'views': views,
            'reviewed_correspondences': accepted_reviews, 'missing_evidence_queue': queue, 'limits': {'canonical_identity_merges': 0,
                'raw_sources_revalidated': False, 'cash_movements_inferred': 0,
                'first_public_dates_inferred': 0, 'causal_exposures_inferred': 0,
                'coverage': 'bounded_retained_assertions_only', 'cross_source_ordering': 'explicit_reviewed_correspondence_required', 'missing_mentions_imply_termination': False}}

