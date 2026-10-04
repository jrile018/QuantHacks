"""Frozen wording-first equity pilot over the existing cash-ledger engine.

Quality labels and evidence objects are supplied by a verified upstream adapter.
This module checks them but does not establish their provenance.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from math import floor, isfinite, sqrt
from statistics import mean, stdev

from .portfolio import replay_portfolio
from .records import utc

RETURN_SCHEMA_VERSION = 'wording-equity-pilot-result-v2'
PROTOCOL_SHA256 = 'd2fb6f16cb4dae7d3c675aad0bd6c7986a202021962e4ba8cf9ff2859b02a057'
CALENDAR_SHA256 = 'd5b2099c9d04c52439f04e10b61ec73cbf1df3edd5e6c2fdea1cf0bbf3cfc0e1'
CALENDAR_ROWS_SHA256 = 'dab36daed9c3ce207b1189c2f3b45d7d4a46d8ed031f486adbc12a4ef2f97d9e'
CALENDAR_SESSION_COUNT = 252
_COST_KEYS = ('entry_fee', 'exit_fee', 'entry_slippage', 'exit_slippage')
def _finite(value, minimum=None):
    if isinstance(value, bool):
        raise ValueError('finite_number_required')
    x = float(value)
    if not isfinite(x) or (minimum is not None and x < minimum):
        raise ValueError('finite_number_required')
    return x


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_pilot_protocol(protocol):
    """Require the exact frozen v2 protocol, including descriptive policy fields."""
    try:
        if not isinstance(protocol, dict) or _digest(protocol) != PROTOCOL_SHA256:
            raise ValueError('protocol_digest_mismatch')
    except (TypeError, ValueError) as exc:
        raise ValueError('protocol_digest_mismatch') from exc
    return True


def validate_pilot_calendar(calendar, protocol):
    """Require all 252 frozen 2024 sessions and calendar metadata."""
    validate_pilot_protocol(protocol)
    try:
        if not isinstance(calendar, dict):
            raise ValueError('calendar_digest_mismatch')
        rows = calendar['rows']
        if (not isinstance(rows, list) or len(rows) != CALENDAR_SESSION_COUNT or
            _digest(rows) != CALENDAR_ROWS_SHA256 or
            _digest(calendar) != CALENDAR_SHA256):
            raise ValueError('calendar_digest_mismatch')
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('calendar_digest_mismatch') from exc
    return True


def _clock(value):
    return utc(value)


def _costs(row, decision=None, exit_at=None):
    if not isinstance(row, dict) or row.get('qualified') is not True or row.get('currency') != 'USD':
        raise ValueError('cost_evidence')
    values = tuple(_finite(row[k], 0) for k in _COST_KEYS)
    available = _clock(row['available_at_utc'])
    valid = _clock(row['valid_through_utc'])
    if decision is not None and (available > decision or valid < exit_at):
        raise ValueError('cost_evidence')
    return values


def _action(row, protocol, decision=None, entry=None, exit_at=None, security=None):
    if not isinstance(row, dict) or row.get('qualified') is not True or row.get('status') != 'verified_none' or row.get('horizon_id') != protocol['horizon_id']:
        raise ValueError('corporate_actions')
    if row.get('security_id') is not None and row['security_id'] != security:
        raise ValueError('corporate_actions')
    available = _clock(row['available_at_utc'])
    if decision is not None and available > decision:
        raise ValueError('corporate_actions')
    start, end = _clock(row['start_at_utc']), _clock(row['end_at_utc'])
    if start > end or (entry is not None and (start > entry or end < exit_at)):
            raise ValueError('corporate_actions')


def _borrow(row, decision=None, exit_at=None):
    if not isinstance(row, dict) or row.get('qualified') is not True:
        raise ValueError('borrow_evidence')
    quantity = _finite(row['quantity'], 0)
    if quantity <= 0 or _finite(row['total_fee'], 0) < 0:
        raise ValueError('borrow_evidence')
    if decision is not None and (_clock(row['available_at_utc']) > decision or
                                 _clock(row['valid_through_utc']) < exit_at):
        raise ValueError('borrow_evidence')
    return quantity


def _candidate_reasons(candidate, protocol, seen):
    reasons = []
    if not isinstance(candidate, dict):
        return ['candidate_mapping_required']
    identity = candidate.get('candidate_id')
    if not isinstance(identity, str) or not identity:
        reasons.append('candidate_id')
    elif identity in seen:
        reasons.append('duplicate_candidate_id')
    else:
        seen.add(identity)
    for key in ('cik', 'accession', 'security_id'):
        if not isinstance(candidate.get(key), str) or not candidate[key]:
            reasons.append(key)
    if protocol.get('cik_universe') and candidate.get('cik') not in protocol['cik_universe']:
        reasons.append('cik_universe')
    source_hash = candidate.get('source_sha256')
    if not isinstance(source_hash, str) or len(source_hash) != 64 or any(x not in '0123456789abcdef' for x in source_hash.lower()):
        reasons.append('source_sha256')
    if candidate.get('form') != protocol['event_form']:
        reasons.append('event_form')
    if not isinstance(candidate.get('items'), list) or protocol['event_item'] not in candidate['items']:
        reasons.append('event_item')
    if candidate.get('signal_document_role') != protocol['signal_document_role']:
        reasons.append('signal_document_role')
    if candidate.get('signal_recipe_id') != protocol['signal_recipe_id']:
        reasons.append('signal_recipe_id')
    try:
        if not -1 <= _finite(candidate['signal']) <= 1:
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        reasons.append('signal')
    for key in ('source_quality', 'public_clock_quality', 'model_vintage_quality', 'identity_quality'):
        if candidate.get(key) != 'qualified':
            reasons.append(key)
    try:
        public = _clock(candidate['public_by_utc'])
        if public.date() < datetime.fromisoformat(protocol['date_from']).date():
            reasons.append('before_study')
        if public.date() >= datetime.fromisoformat(protocol['protected_from']).date():
            reasons.append('protected_period')
    except (KeyError, TypeError, ValueError):
        reasons.append('public_clock')
    try:
        _action(candidate.get('corporate_actions'), protocol, security=candidate.get('security_id'))
    except (KeyError, TypeError, ValueError):
        reasons.append('corporate_actions')
    try:
        _costs(candidate.get('costs'))
    except (KeyError, TypeError, ValueError):
        reasons.append('cost_evidence')
    try:
        _borrow(candidate.get('borrow'))
        if _finite(candidate['margin'], 0) <= 0:
            raise ValueError()
        _clock(candidate['margin_available_at_utc'])
    except (KeyError, TypeError, ValueError):
        reasons.append('borrow_or_collateral')
    return reasons


def assess_pilot_candidates(candidates, protocol):
    """Retain one record and every exclusion reason for each candidate."""
    validate_pilot_protocol(protocol)
    candidates = list(candidates)
    ids = [x.get('candidate_id') for x in candidates if isinstance(x, dict)]
    keys = [(x.get('cik'), x.get('accession')) for x in candidates if isinstance(x, dict)]
    seen, eligible, excluded = set(), [], []
    for index, candidate in enumerate(candidates):
        reasons = _candidate_reasons(candidate, protocol, seen)
        if isinstance(candidate, dict):
            if ids.count(candidate.get('candidate_id')) > 1 and 'duplicate_candidate_id' not in reasons:
                reasons.append('duplicate_candidate_id')
            key = (candidate.get('cik'), candidate.get('accession'))
            if keys.count(key) > 1:
                reasons.append('duplicate_event_security')
        if reasons:
            excluded.append(dict(index=index, candidate_id=candidate.get('candidate_id') if isinstance(candidate, dict) else None, reasons=reasons))
        else:
            eligible.append(candidate)
    return dict(eligible=eligible, excluded=excluded, received=len(eligible)+len(excluded))


def _sessions(sessions, protocol):
    rows = list(sessions.get('rows', []) if isinstance(sessions, dict) else sessions)
    parsed = []
    for row in rows:
        opening, close = _clock(row['open_at_utc']), _clock(row['close_at_utc'])
        if opening >= close or opening.date() < datetime.fromisoformat(protocol['date_from']).date() or opening.date() >= datetime.fromisoformat(protocol['protected_from']).date():
            raise ValueError('invalid_or_protected_session')
        parsed.append((opening, close, row))
    parsed.sort()
    if any(parsed[i][1] >= parsed[i+1][0] for i in range(len(parsed)-1)):
        raise ValueError('overlapping_sessions')
    return parsed


def _entry_quote(quotes, instrument, at, max_age):
    choices = []
    for q in quotes:
        try:
            event, available = _clock(q['at_utc']), _clock(q['available_at_utc'])
            if (q.get('instrument_id') == instrument and q.get('raw_price') is True and
                q.get('currency') == 'USD' and q.get('evidence_kind') == 'update' and
                event <= at and available <= at and (at-event).total_seconds() <= max_age and
                _finite(q['bid'], 0) > 0 and _finite(q['ask'], 0) > 0 and
                _finite(q['bid'], 0) <= _finite(q['ask'], 0) and
                _finite(q['bid_size'], 0) > 0 and _finite(q['ask_size'], 0) > 0):
                choices.append((event, available, q))
        except (KeyError, TypeError, ValueError):
            continue
    return max(choices, key=lambda item: (item[0], item[1]))[2] if choices else None


def _forecast(candidate, side, qty, decision, entry, exit_at):
    f = dict(decision_id=candidate['candidate_id'], instrument_id=candidate['security_id'],
             asset_class='equity', side=side, quantity=qty, multiplier=1,
             decision_at_utc=decision.isoformat(), entry_at_utc=entry.isoformat(),
             exit_at_utc=exit_at.isoformat(), margin=0)
    if side == 'short':
        f.update(margin=_finite(candidate['margin'], 0),
                 margin_available_at_utc=candidate['margin_available_at_utc'],
                 borrow=candidate['borrow'])
    return f


def _run_session(forecasts, quotes, session, cash, costs, max_age):
    experiment = dict(mode='research_only', objective='standalone', initial_cash=cash,
                      currency='USD', max_quote_age_seconds=max_age,
                      **dict(zip(_COST_KEYS, costs)))
    return replay_portfolio(forecasts, quotes, [session], experiment)


def _sharpe(marks, minimum):
    if len(marks) < minimum + 1:
        return None
    returns = [(b/a)-1 for a,b in zip(marks, marks[1:]) if a > 0]
    if len(returns) < minimum or not any(x != 0 for x in returns):
        return None
    spread = stdev(returns)
    return mean(returns)*sqrt(252)/spread if spread > 0 else None


def replay_wording_pilot(candidates, quotes, sessions, protocol):
    """Replay fixed intraday orders; never use exit evidence for selection or size."""
    validate_pilot_protocol(protocol)
    assessment = assess_pilot_candidates(candidates, protocol)
    validate_pilot_calendar(sessions, protocol)
    calendar = _sessions(sessions, protocol)
    quotes = list(quotes.get('rows', []) if isinstance(quotes, dict) else quotes)
    assigned = {i: [] for i in range(len(calendar))}
    for c in assessment['eligible']:
        public_ready = _clock(c['public_by_utc']) + timedelta(seconds=protocol['processing_latency_seconds'])
        matching = [(i,opening,close) for i,(opening,close,_) in enumerate(calendar) if opening > public_ready]
        if not matching:
            assessment['excluded'].append(dict(candidate_id=c['candidate_id'], reasons=['next_session_missing']))
            continue
        i, opening, close = matching[0]
        entry = opening + timedelta(seconds=protocol['entry_delay_seconds'])
        exit_at = close - timedelta(seconds=protocol['exit_before_close_seconds'])
        if entry >= exit_at:
            assessment['excluded'].append(dict(candidate_id=c['candidate_id'], reasons=['session_too_short']))
            continue
        try:
            _action(c['corporate_actions'],protocol,entry,entry,exit_at,c['security_id'])
            costs = _costs(c['costs'],entry,exit_at)
            capacity = _borrow(c['borrow'],entry,exit_at)
            if _clock(c['margin_available_at_utc']) > entry:
                raise ValueError('borrow_or_collateral')
        except (KeyError, TypeError, ValueError) as exc:
            assessment['excluded'].append(dict(candidate_id=c['candidate_id'], reasons=[str(exc)]))
            continue
        quote = _entry_quote(quotes,c['security_id'],entry,protocol['max_quote_age_seconds'])
        if quote is None:
            assessment['excluded'].append(dict(candidate_id=c['candidate_id'], reasons=['entry_quote_missing']))
            continue
        assigned[i].append((c,entry,entry,exit_at,costs,capacity,quote))
    schedules = {x[4] for group in assigned.values() for x in group}
    if len(schedules) > 1:
        for group in assigned.values():
            for c,*_ in group:
                assessment['excluded'].append(dict(candidate_id=c['candidate_id'], reasons=['incompatible_flat_cost_schedule']))
            group.clear()
    excluded_ids = {x['candidate_id'] for x in assessment['excluded']}
    assessment['eligible'] = [x for x in assessment['eligible'] if x['candidate_id'] not in excluded_ids]
    cash = {'wording':protocol['initial_cash'], 'baseline':protocol['initial_cash']}
    arm_reports = {'wording':[], 'baseline':[]}
    arm_orders = {'wording':[], 'baseline':[]}
    marks = []
    invalid = len(schedules) > 1
    unresolved = set()
    for i,(opening,close,session) in enumerate(calendar):
        group = assigned[i]
        cost_sets = {x[4] for x in group}
        if len(cost_sets)>1:
            invalid = True
            for c,*_ in group:
                assessment['excluded'].append(dict(candidate_id=c['candidate_id'], reasons=['incompatible_flat_cost_schedule']))
            group=[]
        costs = next(iter(cost_sets), (0,0,0,0))
        n=len(group)
        orders = {'wording':[], 'baseline':[]}
        if n:
            fees=n*sum(costs)+sum(_finite(x[0]['borrow']['total_fee'],0) for x in group)
            margins=sum(_finite(x[0]['margin'],0) for x in group if _finite(x[0]['signal'])<0)
            common=min(cash.values())-fees-margins
            budget=max(0,min(min(cash.values())/n,common/n))
            for c,decision,entry,exit_at,_,capacity,q in group:
                long_price=_finite(q['ask'],0)
                short_price=_finite(q['bid'],0)
                cap=min(_finite(q['ask_size'],0),_finite(q['bid_size'],0),capacity)
                qty=min(floor(budget/max(long_price,short_price)),floor(cap))
                if qty<=0:
                    invalid=True
                    assessment['excluded'].append(dict(candidate_id=c['candidate_id'],reasons=['entry_capacity_or_cash']))
                    continue
                side='long' if c['signal']>0 else 'short' if c['signal']<0 else 'no_trade'
                if side!='no_trade':
                    orders['wording'].append(_forecast(c,side,qty,decision,entry,exit_at))
                orders['baseline'].append(_forecast(c,'long',qty,decision,entry,exit_at))
        for arm in ('wording','baseline'):
            arm_orders[arm].extend(orders[arm])
            report=_run_session(orders[arm],quotes,session,cash[arm],costs,protocol['max_quote_age_seconds'])
            arm_reports[arm].append(report)
            if report['status']=='ineligible' or report['rejected'] or report['open_positions'] or report['diagnostics']:
                invalid=True
            if report.get('open_positions',0)==0 and report.get('ledger'):
                final=report['ledger'][-1]
                if final['positions'] or final['collateral']!=0 or final['restricted_short_proceeds']!=0:
                    invalid=True
            if report.get('open_positions',0) or (report.get('ledger') and (report['ledger'][-1]['positions'] or report['ledger'][-1]['collateral'] or report['ledger'][-1]['restricted_short_proceeds'])):
                unresolved.add(arm)
            if arm not in unresolved:
                cash[arm]=report.get('final_equity',cash[arm])
        marks.append(dict(session_id=session.get('session_id'),at_utc=close.isoformat(),
                          wording_equity=None if 'wording' in unresolved else cash['wording'],
                          baseline_equity=None if 'baseline' in unresolved else cash['baseline'],
                          cash_reference=protocol['initial_cash']))
    def joined(arm):
        reports=arm_reports[arm]
        return dict(status='ineligible' if any(x['status']=='ineligible' for x in reports) else 'contract_replayed',
                    initial_equity=protocol['initial_cash'],final_equity=cash[arm],
                    reserved_orders=arm_orders[arm],
                    trades=[t for r in reports for t in r['trades']],
                    rejected=[t for r in reports for t in r['rejected']],
                    ledger=[t for r in reports for t in r['ledger']],
                    open_positions=sum(r.get('open_positions',0) for r in reports),
                    diagnostics=[t for r in reports for t in r['diagnostics']])
    measured=bool(assessment['eligible']) and not invalid
    result=dict(schema_version=RETURN_SCHEMA_VERSION,mode='research_only',
                status='contract_replayed' if measured else 'insufficient',assessment=assessment,
                wording=joined('wording'),baseline=joined('baseline'),marks=marks,
                cash_reference=dict(initial_equity=protocol['initial_cash'],
                                    final_equity=protocol['initial_cash'],rate=0),
                wording_pnl=cash['wording']-protocol['initial_cash'] if measured else None,
                baseline_pnl=cash['baseline']-protocol['initial_cash'] if measured else None,
                wording_sharpe=_sharpe([protocol['initial_cash']]+[m['wording_equity'] for m in marks],
                                       protocol['minimum_sharpe_periods']) if measured else None,
                baseline_sharpe=_sharpe([protocol['initial_cash']]+[m['baseline_equity'] for m in marks],
                                       protocol['minimum_sharpe_periods']) if measured else None,
                wording_win_rate=(sum(t['cash_gain']>0 for t in joined('wording')['trades'])/len(joined('wording')['trades']) if measured and joined('wording')['trades'] else None),
                baseline_win_rate=(sum(t['cash_gain']>0 for t in joined('baseline')['trades'])/len(joined('baseline')['trades']) if measured and joined('baseline')['trades'] else None),
                confidence_interval=None,
                evidence_acceptance='external_receipt_required',
                economic_qualification='contract_only',
                canonical_economic_qualified=False,
                headline_eligible=False,
                pnl_scope='contract_replay_only',
                continuous_intraday_gross_qualification='external_receipt_required',
                short_lifecycle_qualification='external_receipt_required',
                assumptions=['Candidate evidence labels are supplied but not accepted here; an external receipt is required.',
                             'Quotes represent hypothetical all-or-none fills.',
                             'Cash has no outside yield; short proceeds are restricted.',
                             'Gross cap applies to reserved entry orders and flat daily closes; unobserved intraday exposure is not certified.',
                             'Input attests no corporate actions over each holding horizon; external acceptance is required.',
                             'Inference and protected final test remain separate.'])
    return result