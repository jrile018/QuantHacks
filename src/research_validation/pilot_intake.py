"""Evidence intake for the frozen wording pilot; no performance calculation.

The caller supplies a separately pinned root review receipt and a transport-aware
artifact reader.  A producer's quality/status booleans cannot authorize replay.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from math import isfinite
import re

from .wording_equity_pilot import validate_pilot_calendar, validate_pilot_protocol


REQUIRED_ROLES = (
    'source_exact_version_public_bound', 'model_historical_availability',
    'dated_security_identity', 'corporate_action_coverage',
    'executable_quote_update_coverage', 'costs', 'borrow_collateral',
)
WEIGHTS_SHA256 = 'e5897858ff819aad7629b96ce521ae5477952d03634ef5dd30ed2d76357a9f00'
TOKEN_SAFE_PREFLIGHT_SHA256 = 'e0c9e8980f084a27b77e426cea83a38174a1aea65be727da27125436fa706c38'
TOKEN_SAFE_CORE_SHA256 = 'e787b65388897d25739f537202256a59375ea028b771d592b9c82b3678de1f21'
TOKEN_SAFE_RUNNER_SHA256 = '9a3bdd71f18fe3620f21a16ef73d69b94f4b841f3386a8c2b116c35cc215437a'
TOKEN_SAFE_CONFIG_SHA256 = '23d17ce64d4881c58fd4a971781c1a0606f391da7c8332ea20eeccefa4e12a40'
TOKEN_SAFE_SPLITTER_ID = 'finbert_token_safe_word_boundary_v1'
TOKEN_SAFE_CHILD_ID_TAG = 'token_safe_word_boundary_v1'
_SHA = re.compile(r'[0-9a-f]{64}\Z')
_COSTS = ('entry_fee', 'exit_fee', 'entry_slippage', 'exit_slippage')


def canonical_sha256(value):
    """Canonical digest for independent receipt and packet pins."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _time(value):
    if not isinstance(value, str):
        raise ValueError('timestamp_required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('utc_timestamp_required')
    return parsed.astimezone(timezone.utc)


def _number(value, *, positive=False):
    try:
        finite = isfinite(value)
    except (TypeError, ValueError, OverflowError):
        finite = False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not finite:
        raise ValueError('finite_number_required')
    if value < 0 or (positive and value == 0):
        raise ValueError('nonnegative_number_required')
    return value


def _descriptor(value):
    if (not isinstance(value, dict) or not isinstance(value.get('path'), str) or
            not value['path'] or not isinstance(value.get('sha256'), str) or
            not _SHA.fullmatch(value['sha256'])):
        raise ValueError('artifact_descriptor_required')
    return value


def _read(value, reader):
    descriptor = _descriptor(value)
    try:
        data = reader(descriptor)
    except Exception as exc:
        raise ValueError('artifact_unreadable') from exc
    if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != descriptor['sha256']:
        raise ValueError('artifact_hash_mismatch')
    if 'bytes' in descriptor and descriptor['bytes'] != len(data):
        raise ValueError('artifact_size_mismatch')
    return data


def _json_artifact(value, reader):
    try:
        return json.loads(_read(value, reader).decode('utf-8'),
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('artifact_json_invalid') from exc


def _anchors(packet):
    keys = ('canonical_execution_protocol', 'full_span_provenance',
            'model_provenance_summary', 'producer_artifact_manifest', 'input_manifest',
            'preprocessing', 'splitter_configuration', 'producer_code',
            'shared_artifact_lineage')
    result = {key: packet[key] for key in keys if key in packet}
    result['candidate_lineage'] = {row['candidate_id']: row.get('artifact_lineage', {})
                                   for row in packet.get('candidate_rows', [])
                                   if isinstance(row, dict) and isinstance(row.get('candidate_id'), str)}
    return result


def _allowed_flags(value):
    return isinstance(value, list) and set(value).issubset({'unresolved_table_structure'})


def _token_safe_shared(packet, body, reader):
    """Bind the prospective Feb AMT preflight and exact producer bytes.

    This preflight is limited to its listed documents; it is not a model or
    historical availability approval and never replaces the root review.
    """
    if (body.get('schema_version') != 'token-safe-wording-handoff-v1' or
            'candidates' in body or not isinstance(body.get('candidate_rows'), list) or
            len(body['candidate_rows']) != len(packet['candidate_rows'])):
        raise ValueError('unsupported_full_span_body_schema')
    if (body.get('splitter_id') != TOKEN_SAFE_SPLITTER_ID or
            body.get('classifier_context_equivalent') is not False or
            packet.get('splitter_id') != TOKEN_SAFE_SPLITTER_ID or
            packet.get('classifier_context_equivalent') is not False):
        raise ValueError('token_safe_context_or_splitter_mismatch')
    for key in ('preprocessing', 'splitter_configuration', 'producer_code',
                'shared_artifact_lineage', 'recipe_id', 'splitter_id',
                'classifier_context_equivalent', 'canonical_execution_protocol',
                'model_provenance_summary', 'source_provenance_summary',
                'input_manifest', 'input_sha256', 'code_sha256',
                'candidate_count', 'diagnostic_event_count', 'counts'):
        if packet.get(key) != body.get(key):
            raise ValueError('token_safe_body_packet_mismatch')
    if (packet.get('source_scoring_artifact_manifest') is not None and
            packet['source_scoring_artifact_manifest'] != body.get('producer_artifact_manifest')):
        raise ValueError('token_safe_body_packet_mismatch')
    lineage = packet.get('shared_artifact_lineage')
    code = packet.get('producer_code')
    if not isinstance(lineage, dict) or not isinstance(code, dict):
        raise ValueError('token_safe_shared_lineage_missing')
    pins = {'preprocessing': TOKEN_SAFE_PREFLIGHT_SHA256,
            'splitter_configuration': TOKEN_SAFE_CONFIG_SHA256}
    for name, pin in pins.items():
        if _descriptor(packet.get(name))['sha256'] != pin:
            raise ValueError('token_safe_' + name + '_pin_mismatch')
    if (lineage.get('preflight') != packet['preprocessing'] or
            lineage.get('splitter_config') != packet['splitter_configuration']):
        raise ValueError('token_safe_shared_lineage_mismatch')
    for name, shared_name, pin in (
            ('src/token_safe_wording.py', 'token_safe_core', TOKEN_SAFE_CORE_SHA256),
            ('scripts/score_token_safe_wording.py', 'token_safe_runner', TOKEN_SAFE_RUNNER_SHA256)):
        desc = _descriptor(code.get(name))
        if desc['sha256'] != pin or lineage.get(shared_name) != desc:
            raise ValueError('token_safe_code_pin_mismatch')
    for desc in code.values():
        _read(desc, reader)
    for name in ('token_safe_core', 'token_safe_runner'):
        _read(lineage[name], reader)
    preflight = _json_artifact(packet['preprocessing'], reader)
    config = _json_artifact(packet['splitter_configuration'], reader)
    if (not isinstance(preflight, dict) or
            preflight.get('schema_version') != 'token-safe-wording-preflight-v1' or
            preflight.get('scoring_performed') is not False or
            preflight.get('weights_loaded') is not False or
            preflight.get('effective_model_tokens') != 512 or
            preflight.get('splitter_sha256') != TOKEN_SAFE_CORE_SHA256 or
            preflight.get('runner_sha256') != TOKEN_SAFE_RUNNER_SHA256 or
            preflight.get('splitter_config_sha256') != TOKEN_SAFE_CONFIG_SHA256 or
            not isinstance(preflight.get('documents'), list)):
        raise ValueError('token_safe_preflight_invalid')
    if (not isinstance(config, dict) or
            config.get('schema_version') != 'wording-token-safe-preprocessing-v1' or
            config.get('splitter_id') != TOKEN_SAFE_SPLITTER_ID or
            type(config.get('max_model_tokens')) is not int or
            config['max_model_tokens'] != 512 or
            config.get('add_special_tokens') is not True or
            config.get('truncation') is not False or
            config.get('text_mask') != 'unchanged_normalized_transcript'):
        raise ValueError('token_safe_config_invalid')
    return preflight


def _token_safe_base_spans(transcript):
    """Reconstruct the pinned base splitter geometry, without model inference."""
    text, doc = transcript['normalized_text'], transcript['document_id']
    text_sha = hashlib.sha256(text.encode()).hexdigest()
    boundaries = re.compile(r'\n|\f|(?<!\d)[.!?](?=\s|$)|(?<=\d)[.!?](?=\s|$)')
    spans, beginning = [], 0
    for match in boundaries.finditer(text):
        spans.append((beginning, match.start() if match.group() in ('\n', '\f') else match.end()))
        beginning = match.end()
    spans.append((beginning, len(text)))
    result, item, section = [], None, f'{doc}:document'
    for start, end in spans:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end-1].isspace():
            end -= 1
        if end <= start:
            continue
        quote = text[start:end]
        heading = re.search(r'\bItem\s+(\d{1,2}\.\d{2})\b', quote, re.IGNORECASE)
        if heading:
            item = heading.group(1)
            section = f'{doc}:item_{item}_{start}'
        page = next((p.get('page_number') for p in transcript['page_records']
                     if p['char_start'] <= start and end <= p['char_end']), None)
        result.append({'evidence_id': hashlib.sha256(f'{doc}:{text_sha}:{start}:{end}'.encode()).hexdigest(),
            'document_id': doc, 'text_sha256': text_sha, 'section_id': section,
            'sec_item': item, 'page_number': page, 'char_start': start,
            'char_end': end, 'quoted_text': quote, 'bounding_box': None,
            'record_type': 'item_heading' if heading else 'statement'})
    return result


def _token_safe_candidate(body, row, transcript, wording, preflight, reader):
    """Prove every base parent and saved child before signal arithmetic."""
    matches = [item for item in body.get('candidate_rows', []) if isinstance(item, dict)
               and item.get('cik') == row.get('cik') and item.get('accession') == row.get('accession')]
    if len(matches) != 1:
        raise ValueError('token_safe_candidate_identity')
    item = matches[0]
    if {k: v for k, v in item.items() if k not in ('fragment_lineage', 'parent_partition_lineage')} != {
            k: v for k, v in row.items() if not k.startswith('_') and k != 'security_id'}:
        raise ValueError('token_safe_thin_full_row_mismatch')
    lineage = row['artifact_lineage']
    receipt = _json_artifact(lineage.get('span_receipt'), reader)
    if (not isinstance(receipt, dict) or receipt.get('schema_version') != 'token-safe-wording-spans-v1' or
            receipt.get('splitter_id') != TOKEN_SAFE_SPLITTER_ID or
            type(receipt.get('max_model_tokens')) is not int or receipt['max_model_tokens'] != 512 or
            receipt.get('document_id') != transcript.get('document_id') or
            receipt.get('source_sha256') != lineage['source']['sha256'] or
            receipt.get('transcript_sha256') != lineage['transcript']['sha256'] or
            receipt.get('text_sha256') != transcript.get('text_sha256') or
            wording.get('span_receipt_sha256') != lineage['span_receipt']['sha256'] or
            wording.get('splitter_id') != TOKEN_SAFE_SPLITTER_ID or
            wording.get('preflight_sha256') != TOKEN_SAFE_PREFLIGHT_SHA256 or
            item.get('classifier_context_equivalent') is not False):
        raise ValueError('token_safe_span_binding_mismatch')
    docs = [d for d in preflight['documents'] if isinstance(d, dict) and
            isinstance(d.get('entry'), dict) and d['entry'].get('cik') == row.get('cik') and
            d['entry'].get('accession') == row.get('accession') and
            d['entry'].get('document_role') == row.get('document_role') and
            d.get('source_sha256') == lineage['source']['sha256']]
    if len(docs) != 1:
        raise ValueError('token_safe_preflight_scope_mismatch')
    pre = docs[0]
    if (pre.get('document_id') != transcript.get('document_id') or
            pre.get('transcript_sha256') != lineage['transcript']['sha256'] or
            pre.get('text_sha256') != transcript.get('text_sha256') or
            pre.get('span_receipt_sha256') != lineage['span_receipt']['sha256'] or
            any(pre['entry'].get(k) != v for k, v in (
                ('source_sha256', lineage['source']['sha256']),
                ('transcript_sha256', lineage['transcript']['sha256']),
                ('text_sha256', transcript.get('text_sha256'))))):
        raise ValueError('token_safe_preflight_document_mismatch')
    text = transcript['normalized_text']
    base = _token_safe_base_spans(transcript)
    parents, saved, fragments = receipt.get('parents'), wording.get('evidence_assessments'), item.get('fragment_lineage')
    if (not isinstance(parents, list) or not isinstance(saved, list) or
            not isinstance(fragments, list) or len(base) != len(parents) or
            not base or len(saved) > 20000 or len(saved) != len(fragments) or
            item.get('parent_partition_lineage') != parents or
            item.get('base_fragment_count') != len(base) or
            pre.get('base_evidence_count') != len(base)):
        raise ValueError('token_safe_parent_or_child_count')
    expected, gaps, cursor, subdivided = [], [], 0, 0
    for original, parent in zip(base, parents):
        if not isinstance(parent, dict):
            raise ValueError('token_safe_parent_invalid')
        if original['char_start'] > cursor:
            gap = text[cursor:original['char_start']]
            if not gap.isspace():
                raise ValueError('token_safe_base_gap')
            gaps.append({'char_start': cursor, 'char_end': original['char_start'],
                         'text_sha256': hashlib.sha256(gap.encode()).hexdigest()})
        cursor = original['char_end']
        if (any(parent.get(k) != original[k] for k in ('evidence_id', 'char_start', 'char_end')) or
                parent.get('quoted_text_sha256') != hashlib.sha256(original['quoted_text'].encode()).hexdigest() or
                type(parent.get('original_token_count')) is not int or
                not 1 <= parent['original_token_count'] <= 2000000):
            raise ValueError('token_safe_base_parent_changed')
        children = parent.get('children')
        unchanged = parent['original_token_count'] <= 512
        if (not isinstance(children, list) or not children or len(children) > 20000 or
                (unchanged and len(children) != 1) or (not unchanged and len(children) <= 1)):
            raise ValueError('token_safe_parent_partition_invalid')
        subdivided += not unchanged
        child_cursor = original['char_start']
        for child in children:
            if not isinstance(child, dict):
                raise ValueError('token_safe_child_invalid')
            start, end = child.get('char_start'), child.get('char_end')
            if (type(start) is not int or type(end) is not int or
                    start != child_cursor or not start < end <= original['char_end']):
                raise ValueError('token_safe_child_partition')
            child_cursor = end
            child_id = (original['evidence_id'] if unchanged else hashlib.sha256(
                f"{original['evidence_id']}|{TOKEN_SAFE_CHILD_ID_TAG}|{start}|{end}".encode()).hexdigest())
            tokens = child.get('token_count')
            if (child.get('evidence_id') != child_id or child.get('unchanged') is not unchanged or
                    child.get('quoted_text_sha256') != hashlib.sha256(text[start:end].encode()).hexdigest() or
                    type(tokens) is not int or not 1 <= tokens <= 512 or
                    type(child.get('token_count_with_specials')) is not int or
                    child['token_count_with_specials'] != tokens or
                    child.get('includes_special_tokens') is not True or
                    (unchanged and tokens != parent['original_token_count'])):
                raise ValueError('token_safe_child_identity_or_tokens')
            expected.append((original, child, start, end))
        if child_cursor != original['char_end']:
            raise ValueError('token_safe_child_partition')
    if cursor < len(text):
        gap = text[cursor:]
        if not gap.isspace():
            raise ValueError('token_safe_base_gap')
        gaps.append({'char_start': cursor, 'char_end': len(text),
                     'text_sha256': hashlib.sha256(gap.encode()).hexdigest()})
    if receipt.get('structural_whitespace_gaps') != gaps or len(expected) != len(saved) or len(expected) != pre.get('evidence_count') or item.get('subdivided_parent_count') != subdivided:
        raise ValueError('token_safe_partition_incomplete')
    identities = set()
    for (original, child, start, end), saved_row, fragment in zip(expected, saved, fragments):
        if not isinstance(saved_row, dict) or not isinstance(fragment, dict):
            raise ValueError('token_safe_saved_child_missing')
        identity = child['evidence_id']
        if identity in identities or saved_row.get('evidence_id') != identity:
            raise ValueError('token_safe_saved_child_reordered_or_duplicate')
        identities.add(identity)
        if (saved_row.get('parent_evidence_id') != original['evidence_id'] or
                saved_row.get('token_safe_unchanged') is not child['unchanged'] or
                saved_row.get('char_start') != start or saved_row.get('char_end') != end or
                saved_row.get('quoted_text') != text[start:end] or
                any(saved_row.get(k) != original[k] for k in ('document_id', 'text_sha256',
                    'section_id', 'sec_item', 'page_number', 'bounding_box', 'record_type')) or
                type(saved_row.get('token_count_with_specials')) is not int or
                saved_row['token_count_with_specials'] != child['token_count'] or
                not isinstance(saved_row.get('financial_sentiment'), dict) or
                saved_row['financial_sentiment'].get('token_count') != child['token_count'] or
                saved_row['financial_sentiment'].get('truncated') is not False or
                fragment != dict(saved_row, character_weight=end-start)):
            raise ValueError('token_safe_saved_child_mismatch')
    return item


def _candidate_full_span(body, row, protocol, transcript, wording):
    if not isinstance(body, dict) or body.get('recipe_id') != protocol['signal_recipe_id']:
        raise ValueError('full_span_recipe')
    schema = body.get('schema_version')
    if schema is None:
        items = body.get('candidates')
    elif schema == 'token-safe-wording-handoff-v1':
        items = body.get('candidate_rows')
    else:
        raise ValueError('unsupported_full_span_body_schema')
    if not isinstance(items, list):
        raise ValueError('full_span_candidate_rows')
    matches = [item for item in items if
               isinstance(item, dict) and item.get('cik') == row.get('cik') and
               item.get('accession') == row.get('accession')]
    if len(matches) != 1:
        raise ValueError('full_span_identity')
    item = matches[0]
    if (not _allowed_flags(item.get('source_quality_flags')) or
            not _allowed_flags(item.get('transcript_quality_flags')) or
            item.get('exclusions', []) != [] or item.get('status') == 'excluded'):
        raise ValueError('full_span_quality_flags')
    source = row['artifact_lineage']['source']
    transcript_descriptor = row['artifact_lineage']['transcript']
    if (not isinstance(transcript, dict) or not isinstance(wording, dict) or
            transcript.get('source_sha256') != source['sha256'] or
            not isinstance(transcript.get('normalized_text'), str) or
            not _allowed_flags(transcript.get('quality_flags')) or
            transcript.get('text_sha256') != hashlib.sha256(transcript['normalized_text'].encode('utf-8')).hexdigest() or
            wording.get('source_sha256') != source['sha256'] or
            wording.get('transcript_sha256') != transcript_descriptor['sha256'] or
            wording.get('text_sha256') != transcript['text_sha256'] or
            wording.get('model_revision') != protocol['signal_model_revision'] or
            wording.get('failures') != [] or wording.get('truncated_fragments') != 0 or
            not _allowed_flags(wording.get('source_quality_flags'))):
        raise ValueError('transcript_or_saved_wording_binding')
    normalized_text = transcript['normalized_text']
    fragments = item.get('fragment_lineage')
    saved_fragments = wording.get('evidence_assessments')
    if (not isinstance(fragments, list) or not fragments or item.get('fragment_count') != len(fragments) or
            not isinstance(saved_fragments, list) or len(saved_fragments) != len(fragments)):
        raise ValueError('full_span_fragment_count')
    spans, weighted, total, hashes = [], 0.0, 0, set()
    comparable = ('char_start', 'char_end', 'quoted_text', 'text_sha256',
                  'financial_sentiment', 'evidence_id', 'document_id')
    for fragment, saved in zip(fragments, saved_fragments):
        if not isinstance(fragment, dict):
            raise ValueError('full_span_fragment')
        if not isinstance(saved, dict) or any(fragment.get(key) != saved.get(key) for key in comparable):
            raise ValueError('saved_wording_fragment_mismatch')
        if fragment.get('status') not in (None, 'complete', 'ok'):
            raise ValueError('full_span_fragment_failed')
        start, end = fragment.get('char_start'), fragment.get('char_end')
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            raise ValueError('full_span_fragment_bounds')
        if fragment.get('character_weight') != end-start:
            raise ValueError('full_span_fragment_weight')
        if fragment.get('quoted_text') != normalized_text[start:end]:
            raise ValueError('full_span_quote_mismatch')
        sentiment = fragment.get('financial_sentiment')
        if not isinstance(sentiment, dict) or sentiment.get('truncated') is not False:
            raise ValueError('full_span_fragment_truncated')
        probabilities = sentiment.get('probabilities')
        if not isinstance(probabilities, dict):
            raise ValueError('full_span_fragment_probability')
        try:
            neg, neu, pos = (_number(probabilities[k]) for k in ('negative', 'neutral', 'positive'))
        except (KeyError, ValueError) as exc:
            raise ValueError('full_span_fragment_probability') from exc
        if abs(neg+neu+pos-1) > 1e-5:
            raise ValueError('full_span_fragment_probability')
        spans.append((start, end))
        total += end-start
        weighted += (end-start)*(pos-neg)
        hashes.add(fragment.get('text_sha256'))
    spans.sort()
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError('full_span_overlap')
    cursor = 0
    for start, end in spans:
        if normalized_text[cursor:start].strip():
            raise ValueError('full_span_nonwhitespace_gap')
        cursor = end
    if normalized_text[cursor:].strip():
        raise ValueError('full_span_nonwhitespace_gap')
    if (total != item.get('covered_characters') or
            item.get('normalized_text_characters') != len(normalized_text) or
            spans[-1][1] > len(normalized_text) or
            len(hashes) != 1 or not _SHA.fullmatch(next(iter(hashes), ''))):
        raise ValueError('full_span_incomplete')
    if next(iter(hashes)) != transcript['text_sha256']:
        raise ValueError('full_span_text_hash_mismatch')
    value = item.get('diagnostic_value')
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value) or abs(value-weighted/total) > 1e-8:
        raise ValueError('full_span_diagnostic_mismatch')
    if not -1 <= value <= 1:
        raise ValueError('signal_out_of_range')
    flags = sorted(set(item['source_quality_flags'] + item['transcript_quality_flags'] +
                       transcript['quality_flags'] + wording['source_quality_flags']))
    return value, next(iter(hashes)), flags


def _session(calendar, protocol, public):
    ready = public + timedelta(seconds=protocol['processing_latency_seconds'])
    for row in calendar['rows']:
        opening, close = _time(row['open_at_utc']), _time(row['close_at_utc'])
        if opening > ready:
            entry = opening + timedelta(seconds=protocol['entry_delay_seconds'])
            exit_at = close - timedelta(seconds=protocol['exit_before_close_seconds'])
            if entry >= exit_at:
                raise ValueError('session_too_short')
            return entry, exit_at
    raise ValueError('next_session_missing')


def _covers(data, entry, exit_at, *, start='start_at_utc', end='end_at_utc'):
    if _time(data[start]) > entry or _time(data[end]) < exit_at:
        raise ValueError('evidence_interval_incomplete')


def _available(data, entry):
    if _time(data['available_at_utc']) > entry:
        raise ValueError('evidence_arrives_after_decision')


def _quotes(rows, instrument, entry, protocol):
    if not isinstance(rows, list):
        raise ValueError('quote_rows_required')
    matching = []
    for row in rows:
        if not isinstance(row, dict) or row.get('instrument_id') != instrument:
            continue
        try:
            at = _time(row['at_utc'])
            if at > entry or (entry-at).total_seconds() > protocol['max_quote_age_seconds']:
                continue
            available = _time(row['available_at_utc'])
            if available > entry or row.get('currency') != 'USD' or row.get('raw_price') is not True or row.get('evidence_kind') != 'update':
                continue
            bid, ask = _number(row['bid'], positive=True), _number(row['ask'], positive=True)
            _number(row['bid_size'], positive=True)
            _number(row['ask_size'], positive=True)
            if bid <= ask:
                matching.append(row)
        except (KeyError, TypeError, ValueError):
            continue
    if not matching:
        raise ValueError('entry_quote_missing')
    return rows


def _role(roles, name, row, protocol, reader):
    proof = roles.get(name)
    if not isinstance(proof, dict) or proof.get('status') != 'qualified':
        raise ValueError(name + ':not_qualified')
    evidence = proof.get('evidence')
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(name + ':evidence_missing')
    for descriptor in evidence:
        _read(descriptor, reader)
    data = proof.get('data')
    lineage = row.get('artifact_lineage', {})
    source = lineage.get('source', {})
    if (not isinstance(data, dict) or data.get('source_sha256') != source.get('sha256') or
            data.get('horizon_id') != protocol['horizon_id'] or
            data.get('model_revision') != protocol['signal_model_revision'] or
            data.get('security_id') != row.get('security_id') or
            data.get('transcript_sha256') != lineage.get('transcript', {}).get('sha256') or
            data.get('wording_sha256') != lineage.get('wording', {}).get('sha256') or
            data.get('full_span_sha256') != row.get('_approved_full_span_sha256')):
        raise ValueError(name + ':binding_mismatch')
    if row.get('_token_safe_pins') is not None and any(
            data.get(key + '_sha256') != pin for key, pin in row['_token_safe_pins'].items()):
        raise ValueError(name + ':token_safe_binding_mismatch')
    return data


def _normalize(row, full_span, roles, market, quote_rows, protocol, calendar, reader,
               token_safe_preflight=None):
    source = row.get('artifact_lineage', {}).get('source')
    if not isinstance(source, dict) or row.get('form') != protocol['event_form'] or row.get('item') != protocol['event_item'] or row.get('document_role') != protocol['signal_document_role'] or row.get('recipe_id') != protocol['signal_recipe_id']:
        raise ValueError('producer_identity_or_recipe')
    if row.get('cik') not in protocol['cik_universe']:
        raise ValueError('cik_universe')
    if row.get('source_sha256') not in (None, source['sha256']):
        raise ValueError('producer_source_hash_conflict')
    transcript = _json_artifact(row['artifact_lineage']['transcript'], reader)
    wording = _json_artifact(row['artifact_lineage']['wording'], reader)
    if token_safe_preflight is not None:
        _token_safe_candidate(full_span, row, transcript, wording, token_safe_preflight, reader)
    signal, body_hash, text_flags = _candidate_full_span(full_span, row, protocol, transcript, wording)
    if row.get('diagnostic_value') != signal:
        raise ValueError('producer_full_span_conflict')
    source_proof = _role(roles, 'source_exact_version_public_bound', row, protocol, reader)
    if source_proof.get('proof_class') != 'independent_historical_exact_version' or source_proof.get('full_body_sha256') != body_hash:
        raise ValueError('historical_exact_version_proof_missing')
    if source_proof.get('accepted_signal') != {
            'value': signal, 'recipe_id': protocol['signal_recipe_id'],
            'source_sha256': source['sha256'], 'full_body_sha256': body_hash,
            'model_revision': protocol['signal_model_revision'],
            'weights_sha256': WEIGHTS_SHA256}:
        raise ValueError('reviewed_signal_binding_mismatch')
    public = _time(source_proof.get('public_by_utc'))
    if not datetime.fromisoformat(protocol['date_from']).date() <= public.date() < datetime.fromisoformat(protocol['protected_from']).date():
        raise ValueError('public_bound_outside_2024')
    entry, exit_at = _session(calendar, protocol, public)
    model = _role(roles, 'model_historical_availability', row, protocol, reader)
    if model.get('weights_sha256') != WEIGHTS_SHA256:
        raise ValueError('model_weights_mismatch')
    _available(model, entry)
    identity = _role(roles, 'dated_security_identity', row, protocol, reader)
    _covers(identity, entry, exit_at, start='valid_from_utc', end='valid_through_utc')
    _available(identity, entry)
    actions = _role(roles, 'corporate_action_coverage', row, protocol, reader)
    if actions.get('action_status') != 'verified_none':
        raise ValueError('unsupported_corporate_action')
    _available(actions, entry)
    _covers(actions, entry, exit_at)
    quote_proof = _role(roles, 'executable_quote_update_coverage', row, protocol, reader)
    if quote_proof.get('quote_kind') != 'raw_update' or quote_proof.get('quote_artifact') != market['artifacts']['quote_updates']:
        raise ValueError('quote_proof_mismatch')
    if (not isinstance(market.get('candidate_market'), list) or
            {'cik': row['cik'], 'accession': row['accession'], 'security_id': row['security_id']} not in market['candidate_market']):
        raise ValueError('market_identity_missing')
    _quotes(quote_rows, row['security_id'], entry, protocol)
    costs = _role(roles, 'costs', row, protocol, reader)
    if costs.get('currency') != 'USD':
        raise ValueError('cost_currency')
    for key in _COSTS:
        _number(costs[key])
    _available(costs, entry)
    if _time(costs['valid_from_utc']) > entry:
        raise ValueError('cost_interval_incomplete')
    if _time(costs['valid_through_utc']) < exit_at:
        raise ValueError('cost_interval_incomplete')
    borrow = _role(roles, 'borrow_collateral', row, protocol, reader)
    _number(borrow['quantity'], positive=True)
    _number(borrow['total_fee'])
    _number(borrow['margin'], positive=True)
    if borrow.get('recall_status') != 'verified_none':
        raise ValueError('short_recall_unqualified')
    # The current cash ledger has no separate dividend/finance debit.  Positive
    # obligations require an engine extension; explicit verified zero is allowed.
    if _number(borrow['dividend_obligation']) != 0 or _number(borrow['financing_cost']) != 0:
        raise ValueError('unsupported_short_obligation')
    _available(borrow, entry)
    if _time(borrow['valid_from_utc']) > entry:
        raise ValueError('borrow_interval_incomplete')
    if _time(borrow['valid_through_utc']) < exit_at:
        raise ValueError('borrow_interval_incomplete')
    return {'candidate_id': row['candidate_id'], 'cik': row['cik'],
            'accession': row['accession'], 'security_id': row['security_id'],
            'source_sha256': source['sha256'], 'form': row['form'], 'items': [row['item']],
            'signal_document_role': row['document_role'],
            'signal_recipe_id': row['recipe_id'], 'signal': signal,
            'normalized_text_quality_flags': text_flags,
            'financial_table_semantics_qualified': False,
            'source_quality': 'qualified', 'public_clock_quality': 'qualified',
            'model_vintage_quality': 'qualified', 'identity_quality': 'qualified',
            'public_by_utc': source_proof['public_by_utc'],
            'corporate_actions': {'qualified': True, 'status': 'verified_none',
                                  'horizon_id': protocol['horizon_id'], 'security_id': row['security_id'],
                                  'available_at_utc': actions['available_at_utc'],
                                  'start_at_utc': actions['start_at_utc'], 'end_at_utc': actions['end_at_utc']},
            'costs': {'qualified': True, 'currency': 'USD',
                      **{key: costs[key] for key in _COSTS},
                      'available_at_utc': costs['available_at_utc'],
                      'valid_through_utc': costs['valid_through_utc']},
            'borrow': {'qualified': True, 'quantity': borrow['quantity'],
                       'total_fee': borrow['total_fee'], 'available_at_utc': borrow['available_at_utc'],
                       'valid_through_utc': borrow['valid_through_utc']},
            'margin': borrow['margin'], 'margin_available_at_utc': borrow['available_at_utc']}


def _market_security(row, market):
    candidates = market.get('candidate_market')
    if not isinstance(candidates, list):
        raise ValueError('market_identity_missing')
    matches = [item for item in candidates if isinstance(item, dict) and
               item.get('cik') == row.get('cik') and item.get('accession') == row.get('accession')]
    if len(matches) != 1:
        raise ValueError('ambiguous_market_identity' if matches else 'market_identity_missing')
    security = matches[0].get('security_id')
    if not isinstance(security, str) or not security:
        raise ValueError('market_security_id_missing')
    if row.get('security_id') not in (None, security):
        raise ValueError('producer_market_security_conflict')
    return security


def inspect_pilot_intake(packet, market_packet, approval_receipt, *, expected_approval_sha256,
                         protocol, calendar, read_artifact):
    """Inspect source, market, and separate review evidence without replaying P&L.

    Synthetic reviews expose normalized candidates only as a report preview.
    Returned replay candidates and quotes require a distinct real historical
    root-approved receipt whose canonical digest was supplied independently.
    """
    validate_pilot_protocol(protocol)
    validate_pilot_calendar(calendar, protocol)
    if not isinstance(packet, dict) or packet.get('schema_version') != 'wording-equity-pilot-producer-packet-v1' or not isinstance(packet.get('candidate_rows'), list):
        raise ValueError('producer_packet_schema')
    rows = packet['candidate_rows']
    reasons = []
    producer_anchors = _anchors(packet)
    protocol_descriptor = packet.get('canonical_execution_protocol')
    if not isinstance(protocol_descriptor, dict) or protocol_descriptor.get('sha256') != 'e7197cea447fe9e413fe659b4ab2bdd41468e6cdb4933d7f82fb4560bab78acb':
        reasons.append('protocol_byte_pin_mismatch')
    full_span = None
    token_safe_preflight = None
    model_summary = None
    for name in ('canonical_execution_protocol', 'full_span_provenance',
                 'model_provenance_summary', 'producer_artifact_manifest', 'input_manifest'):
        try:
            body = _read(packet[name], read_artifact)
            if name == 'full_span_provenance':
                full_span = json.loads(body.decode('utf-8'))
            if name == 'model_provenance_summary':
                model_summary = json.loads(body.decode('utf-8'))
        except (KeyError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            reasons.append(str(exc) if isinstance(exc, ValueError) else name + ':artifact_unreadable')
    if isinstance(full_span, dict):
        if full_span.get('schema_version') == 'token-safe-wording-handoff-v1':
            try:
                token_safe_preflight = _token_safe_shared(packet, full_span, read_artifact)
            except (KeyError, TypeError, ValueError) as exc:
                reasons.append(str(exc) if isinstance(exc, ValueError) else 'token_safe_shared_invalid')
        elif (full_span.get('schema_version') is not None or
              not isinstance(full_span.get('candidates'), list) or
              'candidate_rows' in full_span):
            reasons.append('unsupported_full_span_body_schema')
    elif full_span is not None:
        reasons.append('unsupported_full_span_body_schema')
    for row in rows:
        if not isinstance(row, dict):
            reasons.append('candidate_mapping_required')
            continue
        for desc in row.get('artifact_lineage', {}).values():
            try:
                _read(desc, read_artifact)
            except ValueError as exc:
                reasons.append(str(exc))
    if isinstance(model_summary, dict):
        model_weights = model_summary.get('weights_sha256')
        if model_weights is None:
            model_weights = model_summary.get('model_files_from_retained_run_receipt', {}).get('model.safetensors')
        if model_summary.get('revision') != protocol['signal_model_revision'] or model_weights != WEIGHTS_SHA256:
            reasons.append('model_artifact_binding_mismatch')
    else:
        reasons.append('model_artifact_binding_mismatch')
    market = market_packet if isinstance(market_packet, dict) else {}
    quote_rows = None
    if market.get('schema_version') != 'pilot-market-packet-v1':
        reasons.append('market_packet_missing')
    else:
        try:
            quote_rows = _json_artifact(market['artifacts']['quote_updates'], read_artifact)
        except (KeyError, TypeError, ValueError) as exc:
            reasons.append(str(exc) if isinstance(exc, ValueError) else 'quote_artifact_missing')
    protected_quote_payload = False
    if isinstance(quote_rows, list):
        for quote in quote_rows:
            if isinstance(quote, dict):
                for field in ('at_utc', 'available_at_utc'):
                    try:
                        if _time(quote.get(field)).year >= 2025:
                            protected_quote_payload = True
                    except ValueError:
                        pass
    if protected_quote_payload:
        reasons.append('protected_quote_payload_refused')
    approved = False
    if expected_approval_sha256 is None:
        reasons.append('root_approval_missing')
    elif not isinstance(expected_approval_sha256, str) or not _SHA.fullmatch(expected_approval_sha256) or not isinstance(approval_receipt, dict) or canonical_sha256(approval_receipt) != expected_approval_sha256:
        reasons.append('approval_digest_mismatch')
    else:
        receipt = approval_receipt
        if (receipt.get('schema_version') != 'pilot-reviewed-evidence-receipt-v1' or
                receipt.get('scope') != 'research_only' or receipt.get('source_mode') != 'qualified_only' or
                receipt.get('proof_scope') not in ('real_historical', 'synthetic_engineering') or
                not isinstance(receipt.get('reviewer'), str) or not receipt['reviewer'] or
                not isinstance(receipt.get('review_version'), str) or not receipt['review_version'] or
                receipt.get('protocol_sha256') != canonical_sha256(protocol) or
                receipt.get('recipe_id') != protocol['signal_recipe_id'] or
                receipt.get('producer_packet_sha256') != canonical_sha256(packet) or
                receipt.get('market_packet_sha256') != canonical_sha256(market) or
                receipt.get('artifact_anchors') != {'producer': producer_anchors,
                                                    'market': market.get('artifacts')}):
            reasons.append('approval_binding_mismatch')
        else:
            approved = True
    reviews = {}
    if approved:
        items = approval_receipt.get('candidate_reviews')
        if not isinstance(items, list):
            reasons.append('candidate_reviews_missing')
        else:
            for item in items:
                if not isinstance(item, dict):
                    reasons.append('candidate_review_mapping_required')
                    continue
                key = (item.get('cik'), item.get('accession'))
                if key in reviews:
                    reasons.append('duplicate_candidate_review')
                reviews[key] = item.get('roles')
    exclusions, accepted = [], []
    for index, row in enumerate(rows):
        row_reasons = list(dict.fromkeys(reasons))
        identity = row.get('candidate_id') if isinstance(row, dict) else None
        if approved and not row_reasons:
            roles = reviews.get((row.get('cik'), row.get('accession'))) if isinstance(row, dict) else None
            if not isinstance(roles, dict):
                row_reasons.append('candidate_review_missing')
            else:
                for role in REQUIRED_ROLES:
                    if role not in roles:
                        row_reasons.append(role + ':missing')
                if not row_reasons:
                    try:
                        candidate_row = dict(row,
                            security_id=_market_security(row, market),
                            _approved_full_span_sha256=packet['full_span_provenance']['sha256'])
                        if token_safe_preflight is not None:
                            candidate_row['_token_safe_pins'] = {
                                'span_receipt': row['artifact_lineage']['span_receipt']['sha256'],
                                'preprocessing': packet['preprocessing']['sha256'],
                                'splitter_configuration': packet['splitter_configuration']['sha256']}
                        accepted.append(_normalize(candidate_row, full_span, roles, market, quote_rows,
                                                   protocol, calendar, read_artifact,
                                                   token_safe_preflight))
                    except (KeyError, TypeError, ValueError) as exc:
                        row_reasons.append(str(exc) if isinstance(exc, ValueError) else 'required_evidence_missing')
        if row_reasons:
            exclusions.append({'index': index, 'candidate_id': identity,
                               'reasons': sorted(set(row_reasons)),
                               'producer_reported_status': row.get('status') if isinstance(row, dict) else None,
                               'producer_reported_exclusions': row.get('exclusions') if isinstance(row, dict) else None})
    status = ('insufficient' if exclusions or not accepted else
              'synthetic_contract_only' if approval_receipt['proof_scope'] == 'synthetic_engineering'
              else 'qualified_for_replay')
    is_real = status == 'qualified_for_replay'
    report = {'schema_version': 'pilot-intake-report-v1', 'status': status,
              'proof_scope': approval_receipt.get('proof_scope') if approved else None,
              'synthetic_test_scope': status == 'synthetic_contract_only',
              'headline_proof_status': 'unresolved_whole_run_intraday_gross',
              'canonical_economic_qualified': False, 'headline_economic_qualified': False,
              'protected_quote_payload_refused': protected_quote_payload,
              'denominators': {'producer_candidates': len(rows), 'normalized_candidates': len(accepted),
                               'excluded_candidates': len(exclusions),
                               'producer_reported_counts': packet.get('counts')},
              'exclusions': exclusions, 'required_proof_roles': list(REQUIRED_ROLES),
              'economic_result': None, 'training_performed': False, 'heldout_accessed': False,
              'synthetic_candidate_preview': accepted if status == 'synthetic_contract_only' else [],
              'synthetic_quote_count': len(quote_rows) if status == 'synthetic_contract_only' else 0}
    return {'report': report, 'candidates': accepted if is_real else [],
            'quote_rows': quote_rows if is_real else []}
