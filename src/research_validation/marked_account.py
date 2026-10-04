"""Full-account daily NAV export from the frozen wording bridge.

This detached contract snapshot is not accepted market evidence.
Containers guard ordinary mutation; serialized artifacts require external hashes.
The portfolio engine already includes execution and borrow costs in equity.
"""
from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy

from .records import utc
from .wording_equity_pilot import validate_pilot_calendar

SCHEMA_VERSION = 'wording-marked-account-panel-v1'
ARMS = {'wording': 'wording_equity', 'baseline': 'baseline_equity'}
SCOPES = {'contract_only', 'synthetic_engineering'}


class FrozenDict(dict):
    """Guard ordinary dict writes; base-class calls can bypass this convenience."""

    def _deny(self, *args, **kwargs):
        raise TypeError('immutable_panel')

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _deny


class FrozenList(list):
    """Guard ordinary list writes; base-class calls can bypass this convenience."""

    def _deny(self, *args, **kwargs):
        raise TypeError('immutable_panel')

    __setitem__ = __delitem__ = append = clear = extend = insert = pop = remove = reverse = sort = __iadd__ = __imul__ = _deny


def _freeze(value):
    if isinstance(value, dict):
        return FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return FrozenList(_freeze(item) for item in value)
    return value


def _hash(value):
    """Hash input records, including malformed NaN tokens, without accepting them."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=True).encode()).hexdigest()


def _positive(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and number > 0


def _flat(ledger_row):
    try:
        return (ledger_row['positions'] == {} and
                float(ledger_row['collateral']) == 0.0 and
                float(ledger_row['restricted_short_proceeds']) == 0.0 and
                _positive(ledger_row['equity']))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _daily_ledger(ledger, rows):
    """Assign supplied ledger events to frozen sessions without price inference."""
    buckets = [[] for _ in rows]
    outside = False
    previous = None
    for event in ledger:
        try:
            at = utc(event['at_utc'])
            if previous is not None and at < previous:
                outside = True
            previous = at
            found = False
            for index, session in enumerate(rows):
                if utc(session['open_at_utc']) <= at <= utc(session['close_at_utc']):
                    buckets[index].append(event)
                    found = True
                    break
            if not found:
                outside = True
        except (KeyError, TypeError, ValueError, OverflowError):
            outside = True
    return buckets, outside


def _trade_accounting(source, buckets):
    """Bind every closed gain to one canonical exit; reject outside income."""
    trades = source.get('trades', [])
    orders = source.get('reserved_orders', [])
    if not isinstance(trades, list) or not isinstance(orders, list):
        return None, 'invalid_trade_or_order_evidence'
    if (trades or orders) and not any(buckets):
        return None, 'trade_ledger_missing'
    exits = {}
    for index, daily in enumerate(buckets):
        for event in daily:
            if event.get('action') not in ('entry', 'exit'):
                return None, 'unsupported_ledger_action'
            if event['action'] == 'exit':
                key = event.get('decision_id')
                if not isinstance(key, str) or not key or key in exits:
                    return None, 'invalid_or_duplicate_exit'
                exits[key] = (index, event)
    gains = [[] for _ in buckets]
    seen = set()
    try:
        for trade in trades:
            key = trade['decision_id']
            gain = trade['cash_gain']
            if (key in seen or key not in exits or isinstance(gain, bool) or
                    not isinstance(gain, (int, float)) or not math.isfinite(float(gain))):
                return None, 'invalid_trade_gain_evidence'
            seen.add(key)
            gains[exits[key][0]].append(float(gain))
        if seen != set(exits):
            return None, 'trade_exit_reconciliation'
        if orders:
            order_keys = set()
            for order in orders:
                key = order['decision_id']
                if key in order_keys or key not in exits or utc(order['exit_at_utc']) != utc(exits[key][1]['at_utc']):
                    return None, 'order_exit_reconciliation'
                order_keys.add(key)
            if order_keys != seen:
                return None, 'order_trade_reconciliation'
        sums = [math.fsum(x) for x in gains]
        if not all(math.isfinite(x) for x in sums):
            return None, 'invalid_trade_gain_evidence'
        return sums, None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, 'invalid_trade_gain_evidence'


def export_marked_account_panel(replay_result, calendar, protocol, *,
                                arm='wording', scope='contract_only'):
    """Return a detached JSON-compatible panel and assess_panel keyword arguments.

    Each net return uses consecutive full-account NAV. Period zero is an
    undated initial-funding anchor before the first reference session opens.
    No acceptance of costs, timing, flows or intraday gross exposure occurs.
    """
    validate_pilot_calendar(calendar, protocol)
    if arm not in ARMS or scope not in SCOPES:
        raise ValueError('unsupported_arm_or_scope')
    if not isinstance(replay_result, dict):
        raise ValueError('replay_mapping_required')
    if scope == 'synthetic_engineering' and replay_result.get('synthetic_fixture_id') != 'wording_equity_engineering-v1':
        raise ValueError('explicit_synthetic_fixture_tag_required')

    sessions = calendar['rows']
    initial = float(protocol['initial_cash'])
    field = ARMS[arm]
    source = replay_result.get(arm)
    source = source if isinstance(source, dict) else {}
    marks = replay_result.get('marks')
    marks = marks if isinstance(marks, list) else []
    ledger = source.get('ledger')
    ledger = ledger if isinstance(ledger, list) else []
    buckets, ledger_outside = _daily_ledger(ledger, sessions)
    daily_gains, accounting_reason = _trade_accounting(source, buckets)
    unsupported_flows = any(replay_result.get(k) for k in ('external_flows', 'flows', 'cashflows'))
    contract_replayed = (replay_result.get('schema_version') == 'wording-equity-pilot-result-v2' and
                         replay_result.get('status') == 'contract_replayed' and
                         replay_result.get('economic_qualification') == 'contract_only' and
                         replay_result.get('canonical_economic_qualified') is False and
                         replay_result.get('headline_eligible') is False and
                         source.get('open_positions') == 0 and
                         not source.get('rejected') and not source.get('diagnostics'))
    provenance = dict(replay_sha256=_hash(replay_result), ledger_sha256=_hash(ledger),
                      config_sha256=_hash(protocol), protocol_sha256=_hash(protocol),
                      calendar_sha256=_hash(calendar),
                      calendar_rows_sha256=_hash(sessions),
                      source='existing_wording_bridge_ledger',
                      scope=scope, synthetic_fixture=(scope == 'synthetic_engineering'),
                      economic_qualified=False, evidence_acceptance='external_receipt_required')
    anchor = dict(period_index=0, kind='initial_funding',
                  before_utc=sessions[0]['open_at_utc'],
                  observed_at_utc=None, nav=initial,
                  external_flow=initial)
    rows = []
    previous_nav = initial
    locked_unresolved = False
    for index, session in enumerate(sessions):
        expected_close = session['close_at_utc']
        mark = marks[index] if index < len(marks) and isinstance(marks[index], dict) else None
        nav = None
        reason = None
        if unsupported_flows:
            reason = 'unsupported_external_flow'
        elif not contract_replayed:
            reason = 'replay_not_contract_replayed'
        elif ledger_outside:
            reason = 'ledger_outside_or_unordered'
        elif accounting_reason:
            reason = accounting_reason
        elif locked_unresolved:
            reason = 'prior_unresolved_position'
        elif mark is None:
            reason = 'missing_mark'
        elif mark.get('session_id') != session['session_id']:
            reason = 'mark_session_mismatch'
        else:
            try:
                if utc(mark['at_utc']) != utc(expected_close):
                    reason = 'mark_timestamp_mismatch'
            except (KeyError, TypeError, ValueError, OverflowError):
                reason = 'mark_timestamp_mismatch'
            if reason is None:
                value = mark.get(field)
                if value is None:
                    reason = 'missing_nav'
                elif not _positive(value):
                    reason = 'nonpositive_nav'
                else:
                    nav = float(value)
        daily = buckets[index]
        if daily:
            final = daily[-1]
            if not _flat(final):
                nav, reason = None, 'unresolved_position_or_ledger'
                locked_unresolved = True
            elif nav is not None and not math.isclose(nav, float(final['equity']),
                                                      rel_tol=1e-10, abs_tol=1e-6):
                nav, reason = None, 'mark_ledger_mismatch'
        elif nav is not None and previous_nav is not None and not math.isclose(
                nav, previous_nav, rel_tol=1e-10, abs_tol=1e-6):
            nav, reason = None, 'unreconciled_no_trade_nav'
        net_return = None
        if nav is not None and previous_nav is not None:
            delta = nav - previous_nav
            if not math.isfinite(delta) or not math.isclose(delta, daily_gains[index], rel_tol=1e-10, abs_tol=1e-6):
                nav, reason = None, 'trade_gain_nav_mismatch'
            else:
                value = nav / previous_nav - 1.0
                if math.isfinite(value) and value > -1.0:
                    net_return = value
                else:
                    net_return, reason = None, 'invalid_net_return'
        elif nav is not None and previous_nav is None:
            reason = 'prior_nav_missing'
        rows.append(dict(period_index=index+1, session_id=session['session_id'],
                         at_utc=expected_close, nav=nav, net_return=net_return,
                         reason=reason))
        previous_nav = nav
    count_exact = len(marks) == len(sessions)
    if not count_exact:
        # Preserve the calendar grid but never present a complete probe panel.
        for row in rows:
            if row['reason'] is None:
                row['reason'] = 'mark_count_mismatch'
                row['net_return'] = None
    marks_complete = (count_exact and all(row['nav'] is not None and
                                           row['net_return'] is not None and
                                           row['reason'] is None for row in rows))
    status = 'contract_exported' if marks_complete and contract_replayed else 'insufficient'
    timestamps = [s['close_at_utc'] for s in sessions]
    net_returns = [row['net_return'] for row in rows]
    reference_returns = [0.0 for _ in sessions]
    panel = dict(schema_version=SCHEMA_VERSION, status=status, scope=scope, arm=arm,
                 canonical_economic_qualified=False, headline_eligible=False,
                 evidence_acceptance='external_receipt_required',
                 anchor=anchor, rows=rows, provenance=provenance,
                 accounting='existing_full_account_nav_no_added_costs_or_income')
    probe_args = dict(timestamps=timestamps, expected_calendar=timestamps,
                      net_returns=net_returns, reference_returns=reference_returns,
                      reference_kind='declared_zero', periods_per_year=252,
                      provenance=deepcopy(provenance), marks_complete=marks_complete,
                      costs_complete=False, flows_reconciled=False,
                      timing_verified=False)
    # JSON round-trip detaches all nested containers from the replay input.
    snapshot = json.loads(json.dumps(dict(panel=panel, probe_args=probe_args),
                                     allow_nan=False))
    return _freeze(snapshot)