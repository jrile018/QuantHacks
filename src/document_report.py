"""Traceable two-answer reports; no trained market predictor in this stage."""
from __future__ import annotations

import math
from datetime import date
from .document_language import utc_timestamp, has_public_evidence

TARGET = 'call_put_3to6m_5pct_next_session_v1'


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def select_contracts(quotes, spot, decision, settings):
    cutoff = utc_timestamp(decision)
    age = settings.get('max_quote_age_seconds')
    spread = settings.get('max_spread_fraction')
    if not (cutoff and positive(spot) and positive(age) and positive(spread)):
        return None
    eligible = []
    for q in quotes:
        try:
            timestamp = utc_timestamp(q.get('timestamp'))
            expiry = date.fromisoformat(q['expiry'])
            dte = (expiry - cutoff.date()).days
            if not timestamp or not 0 <= (cutoff - timestamp).total_seconds() <= age or not 90 <= dte <= 180:
                continue
            if not all(positive(q.get(k)) for k in ('strike', 'bid', 'ask', 'bid_size', 'ask_size', 'multiplier')):
                continue
            if q['bid'] > q['ask'] or (q['ask'] - q['bid']) / ((q['ask'] + q['bid']) / 2) > spread:
                continue
            if q.get('option_type') not in ('call', 'put') or not q.get('contract_id'):
                continue
            eligible.append(q)
        except (ValueError, TypeError, KeyError):
            continue
    shared = {q['expiry'] for q in eligible if q['option_type'] == 'call'} & {q['expiry'] for q in eligible if q['option_type'] == 'put'}
    if not shared:
        return None
    expiry = min(shared, key=lambda v: (abs((date.fromisoformat(v) - cutoff.date()).days - 120), v))
    return {kind: min((q for q in eligible if q['expiry'] == expiry and q['option_type'] == kind),
                      key=lambda q: (abs(q['strike'] - spot * ratio), q['strike'], q['contract_id']))
            for kind, ratio in [('call', 1.05), ('put', .95)]}


def options_readiness(inventory, transcripts, *, mode='post_release', decision=None,
                      target_accession=None, market=None, settings=None):
    if mode not in ('post_release', 'anticipation'):
        raise ValueError('Unknown analysis mode')
    cutoff = utc_timestamp(decision)
    market, settings = market or {}, settings or {}
    reasons, available = [], []
    if cutoff is None:
        reasons.append('decision_timestamp_missing')
    if not inventory:
        reasons.append('document_inventory_missing')
    if mode == 'anticipation' and not target_accession:
        reasons.append('target_accession_missing')
    by_id = {t['document_id']: t for t in transcripts}
    for record in inventory:
        if record.get('identity_status') != 'verified':
            reasons.append('submission_identity_unverified')
        if mode == 'anticipation' and target_accession and record.get('accession') == target_accession:
            reasons.append('target_filing_leakage')
        for field, missing, late in [('public_at_utc', 'public_timestamp_unverified', 'public_after_decision'),
                                     ('receipt_at_utc', 'receipt_timestamp_unavailable', 'receipt_after_decision'),
                                     ('processing_completed_at_utc', 'processing_timestamp_unavailable', 'processing_after_decision')]:
            source = by_id.get(record['document_id'], {}) if field.startswith('processing') else record
            try:
                timestamp = utc_timestamp(source.get(field))
            except (ValueError, TypeError):
                timestamp = None
            if timestamp is None or (field == 'public_at_utc' and not has_public_evidence(record)):
                reasons.append(missing)
            elif cutoff and (timestamp > cutoff or (mode == 'anticipation' and field == 'public_at_utc' and timestamp == cutoff)):
                reasons.append(late)
        if record.get('inventory_status') not in ('complete', 'available', 'retrieved', 'ok'):
            reasons.append('document_coverage_incomplete')
        if not by_id.get(record['document_id'], {}).get('normalized_text', '').strip():
            reasons.append('document_text_missing')
    # Coverage declarations alone cannot establish point-in-time issuer mappings,
    # synchronized quotes, calendars, or a validated model. Preserve them for audit.
    required = ['point_in_time_issuer_mapping', 'synchronized_option_quotes', 'underlying_price',
                'contract_selection', 'execution_costs', 'options_session_calendar', 'validated_prediction_model']
    mapping = market.get('issuer_mapping') or {}
    if not mapping.get('evidence') or not mapping.get('security_id'):
        reasons.append('issuer_mapping_missing')
    else:
        available.append('issuer_mapping_metadata')
        reasons.append('issuer_mapping_unvalidated')
    quotes = market.get('quotes') or []
    if not quotes:
        reasons.append('option_quotes_missing')
    else:
        available.append('option_quote_records')
        reasons.append('quote_coverage_unvalidated')
    underlying = market.get('underlying') or {}
    if not positive(underlying.get('price')) or not underlying.get('timestamp'):
        reasons.append('underlying_price_missing')
    else:
        available.append('underlying_price_record')
        reasons.append('underlying_price_unvalidated')
    pair = select_contracts(quotes, underlying.get('price'), decision, settings) if cutoff else None
    if pair is None:
        reasons.append('contract_selection_unavailable')
    else:
        available.append('candidate_contract_pair')
    costs = settings.get('execution_costs')
    if not isinstance(costs, dict) or not all(isinstance(costs.get(k), (float, int)) and not isinstance(costs.get(k), bool)
                                             and math.isfinite(costs[k]) and costs[k] >= 0
                                             for k in ('entry_fees', 'exit_fees', 'entry_slippage_cost', 'exit_slippage_cost')):
        reasons.append('execution_costs_unconfigured')
    else:
        available.append('execution_cost_assumptions')
    reasons.extend(['options_session_calendar_unvalidated', 'prediction_model_untrained', 'prediction_model_unvalidated'])
    return {'status': 'not_ready', 'mode': mode, 'decision_timestamp_utc': cutoff.isoformat() if cutoff else None,
            'target_rule_id': TARGET, 'required_inputs': required, 'available_inputs': available,
            'reason_codes': sorted(set(reasons)), 'candidate_contracts': pair, 'forecast': None,
            'limitation': 'Candidate selection is diagnostic only. Issuer, quote and session coverage validation and market learning are later stages.'}


def render_markdown(report):
    def literal(value):
        return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('`', '&#96;')
    wording, options = report['wording'], report['options']
    lines = ['# 8-K document analysis', '', f"Run: {report['run_id']}", '',
             '## 1. How is this document worded?', '', f"Provider status: **{wording['status']}**. Labels: **{wording['annotation_status']}**.", '',
             f"Comparison: {wording['novelty_comparison']['status']}.", '']
    for item in wording['evidence_assessments']:
        lines += [f"### Evidence {item['evidence_id']}", '', literal(item['quoted_text']), '']
        if item['dictionary']:
            lines += [f"Dictionary counts: {item['dictionary']['counts']}", '']
        if item['financial_sentiment']:
            lines += [f"FinBERT: {item['financial_sentiment']}", '']
    lines += ['## 2. How might option prices be affected?', '',
              '**No option-price forecast is available.** Wording alone does not establish call or put repricing.', '',
              f"Readiness: **{options['status']}**. Mode: {options['mode']}.", '', 'Missing or unvalidated prerequisites:', '']
    lines += [f'- {reason}' for reason in options['reason_codes']]
    lines += ['', '## Coverage and limitations', '']
    lines += [f'- {literal(flag)}' for flag in report.get('quality_flags', [])]
    lines += [f'- {message}' for message in wording['limitations']]
    lines += ['', 'Exact document hashes, evidence offsets and source inventory are in report.json.', '']
    return '\n'.join(lines)
