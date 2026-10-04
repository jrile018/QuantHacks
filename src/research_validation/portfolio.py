"""Small chronological cash ledger for qualified raw quote research legs.

This is not a broker simulator. Unprovided lifecycle, borrow, corporate actions,
roll fills and protection exposures cannot be inferred from prices.
"""
from __future__ import annotations
from src.multi_market.labels import Quote, executable_price
from .evaluate import _time, _number, _rows


def replay_portfolio(forecasts, quotes, sessions, experiment):
    """Replay fixed actual-instrument legs, costs and explicit futures settlements.

    Forecast rows are already frozen orders: entry/exit clocks, side, quantity,
    multiplier and futures collateral. There is no inferred trading policy.
    Returns use initial account wealth, never premium or posted margin alone.
    """
    result = {'schema_version': '1.0', 'mode': 'research_only', 'status': 'insufficient', 'ledger': [], 'trades': [], 'no_trade_decisions': [], 'rejected': [], 'diagnostics': [], 'protection_claim': False, 'arbitrage_claim': False, 'limitations': ['Quotes supply hypothetical all-or-none fills, not proof of execution.', 'Intermediate equity uses last fills/settlements rather than full synchronized liquidation marks.', 'No inferred assignments, corporate actions, financing, maintenance-margin liquidation or roll trades.']}
    try:
        if experiment.get('mode') != 'research_only':
            raise ValueError('research_only_required')
        objective = experiment.get('objective')
        if objective not in {'standalone', 'protection'}:
            raise ValueError('registered_objective_required')
        if objective == 'protection':
            exposure = experiment.get('dated_exposure')
            if not exposure or not exposure.get('holdings') or not exposure.get('as_of_utc'):
                raise ValueError('dated_exposure_required')
            _time(exposure['as_of_utc'])
            raise ValueError('protection_comparator_not_implemented')
        initial = _number(experiment['initial_cash'])
        if initial <= 0 or not experiment.get('currency'):
            raise ValueError('positive_account_cash_and_currency_required')
        costs = {k: _number(experiment[k]) for k in ('entry_fee', 'exit_fee', 'entry_slippage', 'exit_slippage')}
        if any(v < 0 for v in costs.values()):
            raise ValueError('negative_execution_cost')
        max_age = _number(experiment['max_quote_age_seconds'])
        calendar = [(_time(s['open_at_utc']), _time(s['close_at_utc'])) for s in _rows(sessions)]
        calendar.sort()
        if any(a >= b for a,b in calendar) or any(calendar[i][1] >= calendar[i+1][0] for i in range(len(calendar)-1)):
            raise ValueError('invalid_session_calendar')
        quote_map, quote_ids = {}, set()
        for row in _rows(quotes):
            try:
                if row['quote_id'] in quote_ids:
                    raise ValueError('duplicate_quote_id')
                quote_ids.add(row['quote_id'])
                if row.get('raw_price') is not True or row.get('currency') != experiment['currency']:
                    raise ValueError('raw_currency_quote_required')
                q = Quote(row['instrument_id'], _time(row['at_utc']), _time(row['available_at_utc']), _number(row['bid']), _number(row['ask']), _number(row['bid_size']), _number(row['ask_size']), row['evidence_kind'])
                quote_map.setdefault(row['instrument_id'], []).append((row, q))
            except (KeyError, ValueError, TypeError) as exc:
                result['rejected'].append({'quote_id': row.get('quote_id'), 'reason': str(exc)})
        def price(instrument, side, quantity, clock, multiplier=None):
            for row, q in sorted(quote_map.get(instrument, []), key=lambda pair: pair[1].event_time, reverse=True):
                value = executable_price(q, side, quantity, clock, max_age)
                if value is not None:
                    if multiplier is not None and _number(row.get('multiplier', 1)) != multiplier:
                        raise ValueError('instrument_multiplier_mismatch')
                    return value, row['quote_id']
            raise ValueError('qualified_execution_quote_missing')
        events, identities = [], set()
        for forecast in _rows(forecasts):
            try:
                trade = dict(forecast)
                if trade.get('side') == 'no_trade':
                    decision = _time(trade['decision_at_utc'])
                    identity = (trade['instrument_id'], decision)
                    if identity in identities:
                        raise ValueError('duplicate_instrument_decision')
                    identities.add(identity)
                    result['no_trade_decisions'].append(trade['decision_id'])
                    continue
                decision, entry, exit = [_time(trade[k]) for k in ('decision_at_utc', 'entry_at_utc', 'exit_at_utc')]
                if not decision <= entry < exit:
                    raise ValueError('invalid_trade_interval')
                if any(not any(a <= at <= b for a,b in calendar) for at in (entry, exit)):
                    raise ValueError('execution_outside_supplied_session')
                identity = (trade['instrument_id'], decision)
                if identity in identities:
                    raise ValueError('duplicate_instrument_decision')
                identities.add(identity)
                asset = trade['asset_class']
                if asset not in {'equity', 'option', 'futures'} or trade['side'] not in {'long', 'short'}:
                    raise ValueError('unsupported_asset_or_side')
                if trade.get('exit_instrument_id', trade['instrument_id']) != trade['instrument_id']:
                    raise ValueError('explicit_roll_legs_required')
                if any(trade.get(k) for k in ('corporate_actions', 'assignment', 'delivery', 'expiry_cashflow', 'cashflows')):
                    raise ValueError('unsupported_lifecycle_requires_explicit_adapter')
                quantity, multiplier = _number(trade['quantity']), _number(trade['multiplier'])
                if quantity <= 0 or multiplier <= 0 or (asset == 'equity' and multiplier != 1):
                    raise ValueError('invalid_exposure_units')
                if asset in {'futures','option'} and not quantity.is_integer():
                    raise ValueError('whole_contract_quantity_required')
                if asset == 'equity' and not quantity.is_integer() and experiment.get('allow_fractional_equity') is not True:
                    raise ValueError('unregistered_fractional_equity_policy')
                borrow_fee = 0.0
                if trade['side'] == 'short' and asset != 'futures':
                    borrow = trade.get('borrow')
                    if asset != 'equity' or not borrow or borrow.get('qualified') is not True or _time(borrow['available_at_utc']) > decision or _time(borrow['valid_through_utc']) < exit or _number(borrow['quantity']) < quantity:
                        raise ValueError('unknown_borrow')
                    borrow_fee = _number(borrow['total_fee'])
                    if borrow_fee < 0:
                        raise ValueError('invalid_borrow_fee')
                opening, entry_qid = price(trade['instrument_id'], 'buy' if trade['side'] == 'long' else 'sell', quantity, entry, multiplier)
                closing, exit_qid = None, None
                if asset != 'futures' and opening <= 0:
                    raise ValueError('positive_security_prices_required')
                margin = _number(trade.get('margin', 0))
                needs_margin = asset == 'futures' or (asset == 'equity' and trade['side']=='short')
                if margin < 0 or (needs_margin and margin <= 0):
                    raise ValueError('dated_margin_collateral_required')
                if needs_margin and (not trade.get('margin_available_at_utc') or _time(trade['margin_available_at_utc']) > decision):
                    raise ValueError('future_or_unknown_margin_terms')
                trade.update(_entry=opening, _exit=closing, _quantity=quantity, _multiplier=multiplier, _margin=margin, _mark=opening, _borrow_fee=borrow_fee, _entry_at=entry, _exit_at=exit, _entry_quote_id=entry_qid, _exit_quote_id=exit_qid, _key=str(len(events))+':'+trade['decision_id'])
                settlement_events = []
                previous = previous_available = entry
                for settlement in trade.get('settlements', []):
                    at, available = _time(settlement['at_utc']), _time(settlement['available_at_utc'])
                    if asset != 'futures' or not previous < at < exit or not at <= available < exit or available <= previous_available:
                        raise ValueError('invalid_settlement_chronology')
                    settlement_events.append((available, 1, trade['_key'], 'settlement', trade, _number(settlement['price'])))
                    previous, previous_available = at, available
                events.extend([(entry, 2, trade['_key'], 'entry', trade, opening), *settlement_events, (exit, 0, trade['_key'], 'exit', trade, closing)])
            except (KeyError, ValueError, TypeError) as exc:
                result['rejected'].append({'decision_id': forecast.get('decision_id'), 'instrument_id': forecast.get('instrument_id'), 'reason': str(exc)})
        cash, collateral, restricted_short_proceeds, positions, consumed = initial, 0.0, 0.0, {}, {}
        for at, _, key, action, trade, mark in sorted(events, key=lambda event: event[:3]):
            sign = 1 if trade['side'] == 'long' else -1
            units = trade['_quantity']*trade['_multiplier']
            asset = trade['asset_class']
            if action == 'entry':
                qid = trade['_entry_quote_id']
                quote = next(q for row,q in quote_map[trade['instrument_id']] if row['quote_id'] == qid)
                side = 'buy' if sign == 1 else 'sell'
                available_size = quote.ask_size if side == 'buy' else quote.bid_size
                if consumed.get((qid, side), 0) + trade['_quantity'] > available_size:
                    result['rejected'].append({'decision_id': trade['decision_id'], 'reason': 'quote_size_exhausted'})
                    continue
                if asset == 'futures' and any(p['asset_class'] == 'futures' and p['instrument_id'] == trade['instrument_id'] for p in positions.values()):
                    result['rejected'].append({'decision_id': trade['decision_id'], 'reason': 'duplicate_futures_position_requires_aggregation'})
                    continue
                security_collateral = trade['_margin'] if asset == 'futures' or sign == -1 else 0.0
                required = security_collateral + costs['entry_fee'] + costs['entry_slippage'] + (mark*units if asset != 'futures' and sign == 1 else 0.0)
                if required > cash:
                    result['rejected'].append({'decision_id': trade['decision_id'], 'reason': 'insufficient_cash'})
                    continue
                cash -= costs['entry_fee'] + costs['entry_slippage'] + security_collateral
                trade['_restricted_short_proceeds'] = mark*units if asset=='equity' and sign==-1 else 0.0
                restricted_short_proceeds += trade['_restricted_short_proceeds']
                if asset != 'futures' and sign == 1:
                    cash -= mark*units
                collateral += security_collateral
                trade['_collateral'] = security_collateral
                positions[key] = trade
                consumed[(qid, side)] = consumed.get((qid, side), 0)+trade['_quantity']
            elif key not in positions:
                continue
            elif action == 'settlement':
                cash += sign*(mark-trade['_mark'])*units
                trade['_mark'] = mark
            else:
                try:
                    mark, qid = price(trade['instrument_id'], 'sell' if sign == 1 else 'buy', trade['_quantity'], at, trade['_multiplier'])
                    if asset != 'futures' and mark <= 0:
                        raise ValueError('invalid_exit_security_price')
                except ValueError:
                    result['rejected'].append({'decision_id':trade['decision_id'],'reason':'qualified_exit_quote_missing_open_position'})
                    continue
                trade['_exit'], trade['_exit_quote_id'] = mark, qid
                side = 'sell' if sign == 1 else 'buy'
                quote = next(q for row,q in quote_map[trade['instrument_id']] if row['quote_id'] == qid)
                available_size = quote.bid_size if side == 'sell' else quote.ask_size
                if consumed.get((qid, side), 0)+trade['_quantity'] > available_size:
                    result['rejected'].append({'decision_id': trade['decision_id'], 'reason': 'exit_quote_size_exhausted_open_position'})
                    continue
                cash += trade['_restricted_short_proceeds']
                restricted_short_proceeds -= trade['_restricted_short_proceeds']
                cash += (sign*(mark-trade['_mark'])*units if asset == 'futures' else sign*mark*units)
                cash += trade['_collateral']
                collateral -= trade['_collateral']
                cash -= costs['exit_fee']+costs['exit_slippage']+trade['_borrow_fee']
                consumed[(qid, side)] = consumed.get((qid, side), 0)+trade['_quantity']
                positions.pop(key)
                gain = sign*(trade['_exit']-trade['_entry'])*units-sum(costs.values())-trade['_borrow_fee']
                result['trades'].append({'decision_id': trade['decision_id'], 'instrument_id': trade['instrument_id'], 'cash_gain': gain, 'entry_quote_id': trade['_entry_quote_id'], 'exit_quote_id': trade['_exit_quote_id'], 'margin_is_collateral': asset == 'futures'})
            if cash < 0:
                result['diagnostics'].append('cash_buffer_breached_no_liquidation_model')
            equity = cash+collateral+restricted_short_proceeds+sum((1 if p['side'] == 'long' else -1)*p['_mark']*p['_quantity']*p['_multiplier'] for p in positions.values() if p['asset_class'] != 'futures')
            result['ledger'].append({'at_utc': at.isoformat(), 'action': action, 'decision_id': trade['decision_id'], 'cash': cash, 'collateral': collateral, 'restricted_short_proceeds':restricted_short_proceeds, 'equity': equity, 'positions': {k: {'instrument_id': p['instrument_id'], 'quantity': p['_quantity'], 'side': p['side'], 'asset_class': p['asset_class']} for k,p in positions.items()}})
        final_equity = result['ledger'][-1]['equity'] if result['ledger'] else initial
        result.update(initial_equity=initial, final_equity=final_equity, account_return=(final_equity-initial)/initial, return_denominator='initial_account_equity', open_positions=len(positions), status='replayed' if result['trades'] or result['no_trade_decisions'] else 'insufficient')
        if positions or result['diagnostics']:
            result['status'] = 'ineligible'
        return result
    except (KeyError, ValueError, TypeError) as exc:
        return dict(result, status='ineligible', diagnostics=[str(exc)])
