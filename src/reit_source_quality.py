"""Offline evidence audit. Eligibility is scoped to retained source use, not accuracy.

No network requests, OCR, inferred timestamps, numeric quality scores or universe
claims. Callers retain responsibility for establishing trusted expected identity.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import json
import re
from urllib.parse import unquote, urlsplit


SEC_HOSTS = frozenset({'www.sec.gov', 'data.sec.gov', 'sec.gov'})
# Exact issuer hosts reviewed in the retained catalog and integrity evidence.
# Neither caller-provided official_domains nor an arbitrary URL grants authority.
ISSUER_HOSTS = {
    'ir.agnc.com': ('AGNC Investment Corp.', 'docs/reit_document_url_explanations.txt:15; docs/reit-source-validation-2026-10-03.md'),
    'investor.digitalrealty.com': ('Digital Realty', 'docs/reit_document_url_explanations.txt:14'),
    'investors.equityapartments.com': ('Equity Residential', 'docs/reit_document_url_explanations.txt:13'),
    'americantower.gcs-web.com': ('American Tower Corporation', 'docs/reit-source-validation-2026-10-03.md; live_urls.json'),
    'www.realtyincome.com': ('Realty Income Corporation', 'docs/reit-collection-integrity-2026-10-03.md; retained Realty Income manifest URL'),
}
FACT_FIELDS = ('issuer', 'period', 'metric', 'value', 'unit', 'scale', 'basis', 'quote', 'locator')
ACCESS_NOTICE = re.compile(r'(<title[^>]*>\s*(?:access denied|forbidden)|request rate threshold exceeded|your request originates from an undeclared automated tool|<h1[^>]*>\s*access denied)', re.I)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {'script', 'style'} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _known(value):
    return value is not None and str(value).strip().lower() not in {'', 'unknown', 'null', 'none'}


def _cik(value):
    return str(int(str(value))) if _known(value) and str(value).isdigit() else None


def _axis(state, **evidence):
    return dict(state=state, **evidence)


def _status(row):
    """Read both legacy receipt fields and the acquisition broker's status."""
    return next((row[key] for key in ('http_status', 'transport_status', 'status')
                 if row.get(key) is not None), None)


def _sniff(raw):
    body = raw.lstrip()
    if body.startswith(b'%PDF-'):
        return 'application/pdf', None
    try:
        decoded = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return 'unknown', None
    try:
        obj = json.loads(decoded)
        return 'application/json', obj
    except (ValueError, TypeError):
        pass
    if re.search(r'<(?:html|!doctype\s+html|head|body|ix:header|div|table)\b', decoded, re.I):
        return 'text/html', decoded
    return 'unknown', decoded


def audit_source(source: dict, raw_bytes: bytes | None = None, expected: dict | None = None) -> dict:
    """Audit one source; expected is independent issuer/filing identity evidence.

    Source financial_evidence is observation-grade input, checked against linked
    content. Source-grade eligibility does not imply all observations are complete.
    PDF content_text is usable only with extracted_raw_sha256 binding to bytes.
    """
    expected = expected or {}
    url = source.get('url') or source.get('source_url') or ''
    reasons, failures = [], []
    axes = {}
    try:
        parts = urlsplit(url)
        safe = (parts.scheme == 'https' and bool(parts.hostname) and parts.username is None
                and parts.password is None and parts.port in {None, 443}
                and not any(ord(c) < 33 or ord(c) == 127 for c in url))
        host = (parts.hostname or '').lower()
    except (ValueError, TypeError):
        parts = urlsplit(''); host = ''; safe = False
    if not safe:
        failures.append('unsafe_url')
    official = 'sec' if host in SEC_HOSTS else 'issuer' if host in ISSUER_HOSTS else 'unverified'
    authority_ref = ('SEC exact host allowlist; docs/reit-source-validation-2026-10-03.md'
                     if official == 'sec' else ISSUER_HOSTS[host][1] if official == 'issuer' else None)
    axes['authority'] = _axis(official, host=host, evidence_reference=authority_ref)
    if official == 'unverified':
        reasons.append('authority_not_established')
    raw_hash = hashlib.sha256(raw_bytes).hexdigest() if raw_bytes is not None else None
    declared_hash = source.get('sha256') or source.get('raw_sha256')
    integrity = 'verified' if raw_hash and declared_hash == raw_hash else 'computed_unanchored' if raw_hash else 'unknown'
    if raw_hash and _known(declared_hash) and declared_hash != raw_hash:
        integrity = 'mismatch'; failures.append('raw_hash_mismatch')
    axes['integrity'] = _axis(integrity, actual_sha256=raw_hash, declared_sha256=declared_hash)
    actual_mime, decoded = _sniff(raw_bytes) if raw_bytes is not None else ('unknown', None)
    declared_mime = (source.get('content_type') or source.get('mime_type') or '').split(';')[0].strip().lower()
    if actual_mime != 'unknown' and declared_mime in {'application/pdf', 'text/html', 'application/json'} and actual_mime != declared_mime:
        failures.append('mime_mismatch')
    content = None
    if actual_mime == 'text/html':
        parser = _Text(); parser.feed(decoded); content = ' '.join(parser.parts)
        if ACCESS_NOTICE.search(decoded):
            failures.append('access_notice_not_financial_document')
    elif actual_mime == 'application/json':
        content = json.dumps(decoded, ensure_ascii=False)
    elif actual_mime == 'application/pdf' and source.get('extracted_raw_sha256') == raw_hash:
        content = source.get('content_text')
    axes['representation'] = _axis('verified' if actual_mime != 'unknown' else 'unknown',
                                  declared_mime=declared_mime or None, actual_mime=actual_mime,
                                  content_text_linked=content is not None)
    identity = {key: source.get(key) for key in ('issuer', 'cik', 'accession', 'document', 'period', 'form')}
    identity['document'] = identity['document'] or source.get('document_name') or source.get('filename')
    identity['period'] = identity['period'] or source.get('report_date') or source.get('reportDate') or source.get('period_end')
    checks = {}
    for key, wanted in expected.items():
        if key in identity and _known(wanted) and _known(identity[key]):
            observed = identity[key]
            ok = _cik(observed) == _cik(wanted) if key == 'cik' else str(observed) == str(wanted)
            checks['expected_' + key] = ok
            if not ok:
                failures.append('expected_' + key + '_mismatch')
    archive = re.fullmatch(r'/Archives/edgar/data/(\d+)/(\d{18})/([^/]+)', unquote(parts.path)) if official == 'sec' else None
    axes['authority']['document_authority'] = ('primary_filed_source' if archive else
                                             'official_issuer_source' if official == 'issuer' else
                                             'official_endpoint' if official == 'sec' else 'unknown')
    if archive:
        for key, actual in zip(('cik', 'accession', 'document'), archive.groups()):
            supplied = identity[key]
            ok = None if not _known(supplied) else (_cik(supplied) == _cik(actual) if key == 'cik' else str(supplied).replace('-', '') == actual if key == 'accession' else supplied == actual)
            checks['url_' + key] = ok
            if ok is False:
                failures.append('url_' + key + '_mismatch')
    for key in ('issuer', 'period'):
        checks['content_' + key] = bool(str(identity[key]) in content) if content is not None and _known(identity[key]) else None
        if checks['content_' + key] is False:
            reasons.append('content_' + key + '_cue_missing')
    if actual_mime == 'application/json' and isinstance(decoded, dict) and _known(identity['cik']) and 'cik' in decoded:
        checks['json_cik'] = _cik(decoded['cik']) == _cik(identity['cik'])
        if not checks['json_cik']:
            failures.append('json_cik_mismatch')
    if official == 'issuer' and _known(identity['issuer']):
        # Exact curated issuer binding, never substring matching another issuer.
        checks['host_issuer'] = identity['issuer'] == ISSUER_HOSTS[host][0]
        if not checks['host_issuer']:
            failures.append('host_issuer_mismatch')
    required = ['content_issuer', 'content_period'] + (['url_cik', 'url_accession', 'url_document'] if archive else [])
    identity_verified = bool(required) and all(checks.get(key) is True for key in required)
    axes['content_identity'] = _axis('verified' if identity_verified else 'unknown', identity=identity, checks=checks)
    timestamps = {key: source.get(key) if _known(source.get(key)) else None
                  for key in ('reported_at', 'accepted_at', 'retrieved_at', 'first_public_at')}
    # Timestamp precision, timezone and origin must be explicit for historical use.
    publication = source.get('first_public_evidence')
    timestamp_valid = False
    if timestamps['first_public_at']:
        try:
            stamp = datetime.fromisoformat(str(timestamps['first_public_at']).replace('Z', '+00:00'))
            timestamp_valid = stamp.tzinfo is not None
        except ValueError:
            pass
    anchored_publication = (isinstance(publication, dict) and publication.get('url') == url
                            and publication.get('raw_sha256') == raw_hash and raw_hash is not None
                            and publication.get('timestamp') == timestamps['first_public_at']
                            and publication.get('kind') == 'public_availability_observation'
                            and publication.get('publicly_available') is True)
    pit = 'supported_observation' if timestamp_valid and anchored_publication else 'needs_review'
    axes['point_in_time'] = _axis(pit, timestamps=timestamps,
                                 first_public_evidence=publication,
                                 exact_first_public_time='unknown',
                                 note='A bound public observation establishes availability by that time, not exact first availability or executable trading time.')
    live = source.get('live_validation') or {}
    status = _status(source)
    if status is None:
        status = _status(live)
    availability = ('access_restricted' if status in {403, 429} else 'observed_available' if status == 200 or live.get('state') == 'rendered_page'
                    else 'tool_limit' if live.get('state') == 'tool_limit' else 'unknown')
    history = source.get('availability_history') or []
    historical_counts = dict(Counter(str(_status(r)) if _status(r) is not None else 'unknown' for r in history))
    axes['availability'] = _axis(availability, transport_status=status, historical_reliability='limited_observations' if len(history) > 1 else 'unknown',
                                 historical_status_counts=historical_counts,
                                 observations=history, live_validation=live,
                                 note='Single receipts and global access restrictions do not establish historical reliability or dead links.')
    facts = source.get('financial_evidence') or []
    observations = []
    for fact in facts:
        missing = [key for key in FACT_FIELDS if not _known(fact.get(key))]
        quote_match = fact.get('quote') in content if content is not None and _known(fact.get('quote')) else None
        context_match = all(fact.get(key) == identity[key] and _known(identity[key]) for key in ('issuer', 'period'))
        value_match = None
        if quote_match is True and _known(fact.get('value')):
            try:
                quoted = [Decimal(n.replace(',', '')) for n in re.findall(r'(?<![\w.])-?\d[\d,]*(?:\.\d+)?(?![\w.])', fact['quote'])]
                value_match = Decimal(str(fact['value'])) in quoted
            except (InvalidOperation, TypeError):
                value_match = False
            if not value_match:
                failures.append('financial_value_not_in_quote')
        if quote_match is False or not context_match:
            failures.append('financial_quote_or_context_mismatch')
        observations.append(dict(state='complete' if not missing and quote_match is True and context_match and value_match is True else 'needs_review',
                                 missing=missing, quote_match=quote_match, value_match=value_match, context_match=context_match, observation=fact))
    axes['financial_evidence'] = _axis('complete' if observations and all(o['state'] == 'complete' for o in observations) else 'needs_review', observations=observations,
                                     financial_accuracy='not_assessed')
    role = (source.get('role') or source.get('source_role') or '').lower()
    discovery = ((any(word in role for word in ('discovery', 'landing', 'directory', 'aggregator')) and not identity_verified)
                 or 'reit-directory' in parts.path or (official == 'sec' and not archive))
    financial_form = identity['form'] in {'10-K', '10-Q', '8-K', '10-K/A', '10-Q/A', '8-K/A'}
    if failures:
        eligibility = 'quarantine'
    elif discovery:
        eligibility = 'discovery_only'
    elif official == 'issuer' and content is not None and identity_verified:
        eligibility = 'supporting_only'
    elif official == 'sec' and archive and identity_verified and integrity == 'verified' and financial_form:
        eligibility = 'eligible_as_primary'
    else:
        eligibility = 'needs_review'
    if not identity_verified:
        reasons.append('content_identity_incomplete')
    if integrity != 'verified':
        reasons.append('retained_integrity_not_anchored')
    if pit == 'needs_review':
        reasons.append('first_public_availability_unknown')
    if axes['financial_evidence']['state'] != 'complete':
        reasons.append('observation_evidence_incomplete')
    return dict(schema_version='1.0', url=url, quality_axes=axes, eligibility=eligibility,
                reasons=sorted(set(failures + reasons)), evidence=dict(authority_reference=authority_ref,
                raw_sha256=raw_hash, identity=identity, timestamps=timestamps),
                coverage=dict(source_grade=eligibility, observation_grade=axes['financial_evidence']['state'],
                point_in_time=pit, universe_completeness='unknown', financial_accuracy='not_assessed',
                extraction_fidelity='not_assessed', ocr='not_audited'))


def audit_registry(sources: list[dict], receipts: list[dict] | None = None) -> dict:
    """Audit caller supplied metadata/bytes and flag equal-context conflicts.

    receipts join only on exact URL; preserve all observations. No file IO here.
    Same amount alone is never duplicate proof; SHA256 represents byte lineage.
    """
    by_url = defaultdict(list)
    for receipt in receipts or []:
        by_url[receipt.get('url')].append(receipt)
    results, groups, comparable = [], defaultdict(list), defaultdict(list)
    for index, original in enumerate(sources):
        source = dict(original)
        receipt_rows = by_url.get(source.get('url'), [])
        if receipt_rows:
            source['availability_history'] = receipt_rows
            statuses = [_status(r) for r in receipt_rows]
            if 'http_status' not in source and statuses[-1] is not None:
                source['http_status'] = statuses[-1]
            # Do not silently copy a live receipt timestamp onto retained bytes.
        result = audit_source(source, source.get('raw_bytes'), source.get('expected'))
        result['source_id'] = source.get('source_id', str(index))
        results.append(result)
        digest = result['evidence']['raw_sha256']
        if digest:
            groups[digest].append(index)
        for fact in source.get('financial_evidence') or []:
            keys = ('issuer', 'period', 'metric', 'unit', 'scale', 'basis')
            if not all(_known(fact.get(k)) for k in keys + ('value',)):
                continue
            key = tuple(str(fact[k]) for k in keys) + (json.dumps(fact.get('dimensions', {}), sort_keys=True),)
            try:
                value = Decimal(str(fact['value']))
            except InvalidOperation:
                continue
            if value.is_finite():
                comparable[key].append((index, str(value)))
    duplicates = [dict(raw_sha256=digest, source_indices=indices, lineage='same_retained_bytes')
                  for digest, indices in groups.items() if len(indices) > 1]
    conflicts = []
    for key, rows in comparable.items():
        if len({Decimal(value) for _, value in rows}) > 1:
            conflicts.append(dict(context=dict(zip(('issuer', 'period', 'metric', 'unit', 'scale', 'basis', 'dimensions'), key)),
                                  observations=[dict(source_index=i, value=v) for i, v in rows], resolution='needs_review'))
            for index, _ in rows:
                results[index]['reasons'].append('cross_source_financial_conflict')
                results[index]['coverage']['observation_grade'] = 'needs_review'
                if results[index]['eligibility'] != 'quarantine':
                    results[index]['eligibility'] = 'needs_review'
                results[index]['coverage']['source_grade'] = results[index]['eligibility']
    return dict(schema_version='1.0', sources=results, duplicate_groups=duplicates, conflicts=conflicts,
                eligibility_counts=dict(Counter(r['eligibility'] for r in results)),
                coverage=dict(source_count=len(results), receipt_count=len(receipts or []),
                              universe_completeness='unknown', financial_accuracy='not_assessed',
                              limitation='Conflict detection covers only explicitly supplied comparable observations; absence of conflicts is not agreement.'))
