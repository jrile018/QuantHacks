"""Auditable supervised options baseline; no network or implicit data acquisition.

Dataset construction uses stdlib. Ridge fitting imports NumPy only when requested.
Vendor provenance is recorded, not independently certified by this importer.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import math
import statistics

TARGET_NAMES = ('call_premium_change', 'put_premium_change', 'call_net_return', 'put_net_return')
RULE = 'call_put_3to6m_5pct_next_session_v1'
KINDS = ('call', 'put')
MISSING_REASONS = {'not_applicable', 'not_published_yet', 'unmatched', 'source_error'}


def timestamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('timezone_timestamp_required')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('invalid_timestamp') from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('timezone_timestamp_required')
    return result.astimezone(timezone.utc)


def number(value, name, *, minimum=None, positive=False):
    if isinstance(value, bool) or value is None or value == '':
        raise ValueError('invalid_numeric_' + name)
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('invalid_numeric_' + name) from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum) or (positive and result <= 0):
        raise ValueError('invalid_numeric_' + name)
    return result


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('invalid_' + name)
    return value.strip()


def validate_config(config, *, fitting=False):
    frozen = {'target_rule_id': RULE, 'expiry_days': {'minimum': 90, 'maximum': 180, 'target': 120},
              'call_spot_ratio': 1.05, 'put_spot_ratio': .95}
    for key, expected in frozen.items():
        if config.get(key) != expected:
            raise ValueError('frozen_target_changed:' + key)
    # Explicit non-bool numerics prevent Python's True == 1 from certifying inputs.
    for key in ('call_spot_ratio', 'put_spot_ratio'):
        number(config[key], key, positive=True)
    for key in ('minimum', 'maximum', 'target'):
        number(config['expiry_days'][key], key, positive=True)
    number(config.get('max_quote_age_seconds'), 'max_quote_age_seconds', positive=True)
    spread = number(config.get('max_spread_fraction'), 'max_spread_fraction', positive=True)
    if spread > 2:
        raise ValueError('invalid_max_spread_fraction')
    costs = config.get('execution_costs')
    if not isinstance(costs, dict):
        raise ValueError('execution_costs_unconfigured')
    for key in ('entry_fees', 'exit_fees', 'entry_slippage_cost', 'exit_slippage_cost'):
        number(costs.get(key), key, minimum=0)
    text(config.get('execution_cost_currency'),'execution_cost_currency')
    text(config.get('cost_assumption_id'),'cost_assumption_id')
    if fitting:
        cutoffs = [timestamp(config.get(k)) for k in ('train_end_utc','validation_end_utc','test_end_utc')]
        if not cutoffs[0] < cutoffs[1] < cutoffs[2]:
            raise ValueError('cutoffs_must_increase')
        number(config.get('embargo_seconds', 0), 'embargo_seconds', minimum=0)
        for key in ('min_train_events','min_validation_events','min_test_events'):
            value = number(config.get(key), key, minimum=2)
            if not value.is_integer():
                raise ValueError('integer_event_minimum_required')
        alphas = config.get('ridge_alphas')
        if not isinstance(alphas, list) or not alphas:
            raise ValueError('ridge_alphas_missing')
        for value in alphas:
            number(value,'ridge_alpha',positive=True)


def _provenance(provenance):
    if provenance.get('quote_data_kind') not in ('historical_bid_ask', 'synthetic'):
        raise ValueError('quote_data_kind_must_be_historical_bid_ask_or_synthetic')
    for key in ('quote_provider','quote_provenance_reference','feature_provenance_reference',
                'calendar_provenance_reference','experiment_id'):
        text(provenance.get(key),key)
    timestamp(provenance.get('experiment_frozen_at_utc'))


def _calendar(sessions):
    result, seen = [], set()
    for record in sessions:
        identifier = text(record.get('session_id'),'session_id')
        if identifier in seen:
            raise ValueError('duplicate_session_id')
        seen.add(identifier)
        text(record.get('calendar_source'),'calendar_source')
        text(record.get('calendar_version'),'calendar_version')
        start, end = timestamp(record.get('open_at_utc')), timestamp(record.get('close_at_utc'))
        if start >= end:
            raise ValueError('invalid_session_interval')
        result.append(dict(record, _open=start, _close=end))
    result.sort(key=lambda s:s['_open'])
    if not result:
        raise ValueError('options_session_calendar_missing')
    if any(a['_close'] >= b['_open'] for a,b in zip(result,result[1:])):
        raise ValueError('overlapping_options_sessions')
    return result


def _registry(registry):
    result = {}
    for r in registry.get('features',[]):
        name = text(r.get('feature_name'),'feature_name')
        if name in result or r.get('role') != 'predictor':
            raise ValueError('duplicate_or_nonpredictor_registry_feature')
        for key in ('source_id','definition_version','independence_evidence'):
            text(r.get(key),key)
        result[name] = r
    if not result:
        raise ValueError('feature_registry_missing')
    return result


def _event_features(event, features, registry):
    decision = timestamp(event.get('decision_at_utc'))
    mode = event.get('mode')
    if mode not in ('post_release','anticipation'):
        raise ValueError('invalid_mode')
    if mode == 'anticipation':
        text(event.get('target_accession'),'target_accession')
    for key in ('event_id','event_group_id','cik','security_id','currency','deliverable','mapping_evidence'):
        text(event.get(key),key)
    source_times = [timestamp(event.get('mapping_' + key)) for key in
                    ('public_at_utc','receipt_at_utc','processing_at_utc','valid_from_utc')]
    if any(t > decision for t in source_times):
        raise ValueError('mapping_after_decision')
    if not source_times[0] <= source_times[1] <= source_times[2]:
        raise ValueError('invalid_mapping_time_order')
    if timestamp(event.get('mapping_valid_to_utc')) <= decision:
        raise ValueError('mapping_expired_at_decision')
    result, lineage = {}, []
    for r in features:
        if r.get('event_id') != event['event_id']:
            continue
        name = text(r.get('feature_name'),'feature_name')
        if name in result:
            raise ValueError('duplicate_feature_observation:' + name)
        if name not in registry:
            raise ValueError('unregistered_feature:' + name)
        definition = registry[name]
        if any(r.get(k) != definition[k] for k in ('source_id','definition_version')):
            raise ValueError('feature_registry_mismatch:' + name)
        for key in ('source_record_id','source_url'):
            text(r.get(key),key)
        if mode == 'anticipation' and r.get('accession') == event['target_accession']:
            raise ValueError('target_filing_leakage')
        times = [timestamp(r.get(k)) for k in ('public_at_utc','receipt_at_utc','processing_at_utc','valid_from_utc')]
        if any(t > decision for t in times) or (mode == 'anticipation' and times[0] == decision):
            raise ValueError('feature_after_decision:' + name)
        if not times[0] <= times[1] <= times[2]:
            raise ValueError('invalid_feature_time_order:' + name)
        if r.get('valid_to_utc') and timestamp(r['valid_to_utc']) <= decision:
            raise ValueError('feature_not_effective:' + name)
        missing = r.get('value') is None or r.get('value') == ''
        if missing and r.get('missing_reason') not in MISSING_REASONS:
            raise ValueError('missing_feature_reason:' + name)
        result[name] = None if missing else number(r['value'],name)
        lineage.append(dict(r))
    if set(result) != set(registry):
        raise ValueError('feature_observation_missing:' + ','.join(sorted(set(registry)-set(result))))
    return result, lineage


def _quotes(quotes, event):
    snapshots, ids, terms = defaultdict(list), set(), {}
    for r in quotes:
        if r.get('security_id') != event['security_id']:
            continue
        try:
            q = dict(r)
            for key in ('quote_id','snapshot_id','contract_id','currency','deliverable'):
                text(q.get(key),key)
            if q['quote_id'] in ids:
                raise ValueError('duplicate_quote_id')
            ids.add(q['quote_id'])
            if q.get('option_type') not in KINDS:
                raise ValueError('option_type')
            for key in ('strike','ask','multiplier','underlying_price'):
                q[key] = number(q.get(key),key,positive=True)
            for key in ('bid_size','ask_size'):
                q[key] = number(q.get(key),key,minimum=0)
            q['bid'] = number(q.get('bid'),'bid',minimum=0)
            if q['bid'] > q['ask']:
                raise ValueError('crossed_quote')
            q['_time'] = timestamp(q.get('timestamp_utc'))
            q['_snapshot'] = timestamp(q.get('snapshot_at_utc') or q.get('timestamp_utc'))
            received = timestamp(q.get('receipt_at_utc'))
            underlying = timestamp(q.get('underlying_timestamp_utc'))
            underlying_received = timestamp(q.get('underlying_receipt_at_utc'))
            if (q['_time'] > q['_snapshot'] or underlying > q['_snapshot'] or received < q['_time']
                    or underlying_received < underlying):
                raise ValueError('future_tick_or_invalid_receipt')
            q['_underlying_time'] = underlying
            q['_available'] = max(received, underlying_received, q['_snapshot'])
            q['_expiry'] = date.fromisoformat(q['expiry'])
            if q['_expiry'] <= q['_time'].date():
                raise ValueError('expired_contract')
            if q['currency'] != event['currency'] or q['deliverable'] != event['deliverable']:
                raise ValueError('instrument_currency_deliverable_mismatch')
            term = tuple(q[k] for k in ('option_type','strike','expiry','multiplier','currency','deliverable'))
            if q['contract_id'] in terms and terms[q['contract_id']] != term:
                raise ValueError('contract_terms_changed')
            terms[q['contract_id']] = term
            snapshots[q['snapshot_id']].append(q)
        except (ValueError,TypeError,KeyError) as exc:
            raise ValueError('invalid_quote:' + str(exc)) from exc
    result = []
    for snapshot, records in snapshots.items():
        if len({q['contract_id'] for q in records}) != len(records):
            raise ValueError('invalid_quote:duplicate_contract_in_snapshot')
        if len({(q['_snapshot'],q['underlying_price'],q['_underlying_time']) for q in records}) != 1:
            raise ValueError('invalid_quote:unsynchronized_snapshot')
        result.append({'snapshot_id':snapshot,'quotes':records,'time':records[0]['_snapshot'],
                       'available':max(q['_available'] for q in records)})
    return sorted(result,key=lambda s:(s['available'],s['time'],s['snapshot_id']))


def _valid(q, at, config, *, require_available=True):
    return (0 <= (at-q['_time']).total_seconds() <= float(config['max_quote_age_seconds'])
            and 0 <= (at-q['_underlying_time']).total_seconds() <= float(config['max_quote_age_seconds'])
            and (not require_available or q['_available'] <= at)
            and q['_expiry'] > at.date()
            and q['bid_size'] > 0 and q['ask_size'] > 0
            and (q['ask']-q['bid']) / ((q['ask']+q['bid'])/2) <= float(config['max_spread_fraction']))


def _decision_pair(snapshots, decision, config):
    for snapshot in reversed(snapshots):
        if snapshot['available'] > decision:
            continue
        candidates = [q for q in snapshot['quotes'] if _valid(q,decision,config)
                      and 90 <= (q['_expiry']-decision.date()).days <= 180]
        shared = {q['expiry'] for q in candidates if q['option_type']=='call'} & {
            q['expiry'] for q in candidates if q['option_type']=='put'}
        if not shared:
            continue
        expiry = min(shared,key=lambda e:(abs((date.fromisoformat(e)-decision.date()).days-120),e))
        spot = snapshot['quotes'][0]['underlying_price']
        return {kind:min((q for q in candidates if q['expiry']==expiry and q['option_type']==kind),
                         key=lambda q:(abs(q['strike']-spot*ratio),q['strike'],q['contract_id']))
                for kind,ratio in [('call',1.05),('put',.95)]}
    raise ValueError('decision_pair_missing')


def _execution_pair(snapshot, selected, at, config, *, require_available=True):
    by_contract = {q['contract_id']:q for q in snapshot['quotes']}
    result = {kind:by_contract.get(selected[kind]['contract_id']) for kind in KINDS}
    return result if all(q and _valid(q,at,config,require_available=require_available)
                         for q in result.values()) else None


def _make_row(event, features, quotes, sessions, registry, provenance, config):
    values,lineage = _event_features(event,features,registry)
    decision = timestamp(event['decision_at_utc'])
    if event['currency'] != config['execution_cost_currency']:
        raise ValueError('cost_currency_mismatch')
    snapshots = _quotes(quotes,event)
    selected = _decision_pair(snapshots,decision,config)
    entry,entry_snapshot,entry_session = None,None,None
    for snapshot in snapshots:
        if snapshot['time'] <= decision:
            continue
        session = next((s for s in sessions if s['_open'] <= snapshot['available'] <= s['_close']),None)
        if session is None:
            continue
        pair = _execution_pair(snapshot,selected,snapshot['available'],config)
        if pair:
            entry,entry_snapshot,entry_session = pair,snapshot,session
            break
    if entry is None:
        raise ValueError('first_synchronized_entry_missing')
    index = sessions.index(entry_session)
    if index+1 == len(sessions):
        raise ValueError('next_options_session_missing')
    exit_session = sessions[index+1]
    exit_at = exit_session['_close']
    if timestamp(event['mapping_valid_to_utc']) <= exit_at:
        raise ValueError('mapping_expired_before_exit')
    exit_pair,exit_snapshot = None,None
    # Executable exit quotes must have been received by the chosen close.
    for snapshot in sorted(snapshots,key=lambda s:(s['time'],s['snapshot_id']),reverse=True):
        if not exit_session['_open'] <= snapshot['time'] <= exit_at:
            continue
        # Validate quote staleness at close separately from receipt availability.
        if (exit_at-snapshot['time']).total_seconds() > float(config['max_quote_age_seconds']):
            continue
        pair = _execution_pair(snapshot,selected,exit_at,config)
        if pair:
            exit_pair,exit_snapshot = pair,snapshot
            break
    if exit_pair is None:
        raise ValueError('next_session_exit_missing')
    costs = {k:float(v) for k,v in config['execution_costs'].items()}
    targets,contracts = {},{}
    for kind in KINDS:
        opening,closing = entry[kind],exit_pair[kind]
        capital = opening['ask']*opening['multiplier']+costs['entry_fees']+costs['entry_slippage_cost']
        proceeds = closing['bid']*closing['multiplier']-costs['exit_fees']-costs['exit_slippage_cost']
        targets[kind+'_premium_change'] = ((closing['bid']+closing['ask'])/(opening['bid']+opening['ask']))-1
        targets[kind+'_net_return'] = (proceeds-capital)/capital
        contracts[kind] = {k:opening[k] for k in ('contract_id','strike','expiry','multiplier','currency','deliverable')}
        contracts[kind].update(selection_quote_id=selected[kind]['quote_id'],entry_quote_id=opening['quote_id'],
                               exit_quote_id=closing['quote_id'],capital=capital,exit_proceeds=proceeds,
                               selection_quote_at_utc=selected[kind]['_time'].isoformat(),
                               entry_quote_at_utc=opening['_time'].isoformat(),
                               exit_quote_at_utc=closing['_time'].isoformat(),
                               entry_underlying_at_utc=opening['_underlying_time'].isoformat(),
                               exit_underlying_at_utc=closing['_underlying_time'].isoformat())
    label_available = max(exit_at,exit_snapshot['available'])
    if event.get('label_available_at_utc'):
        declared = timestamp(event['label_available_at_utc'])
        if declared < label_available:
            raise ValueError('label_availability_before_exit')
        label_available = declared
    return {'event_id':event['event_id'],'event_group_id':event['event_group_id'],'cik':event['cik'],
            'security_id':event['security_id'],'mode':event['mode'],'decision_at_utc':decision.isoformat(),
            'entry_at_utc':entry_snapshot['available'].isoformat(),'exit_at_utc':exit_at.isoformat(),
            'entry_quote_at_utc':entry_snapshot['time'].isoformat(),
            'exit_quote_at_utc':exit_snapshot['time'].isoformat(),
            'label_available_at_utc':label_available.isoformat(),
            'entry_session_id':entry_session['session_id'],'exit_session_id':exit_session['session_id'],
            'features':values,'feature_lineage':lineage,'contracts':contracts,'targets':targets,
            'quote_data_kind':provenance['quote_data_kind'],'target_rule_id':RULE}


def build_dataset(events, features, quotes, sessions, registry, provenance, config):
    """Return eligible paired rows and explicit event exclusions; malformed globals raise."""
    validate_config(config)
    _provenance(provenance)
    calendar,definitions = _calendar(sessions),_registry(registry)
    ids = [text(e.get('event_id'),'event_id') for e in events]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate_event_id')
    if any(f.get('event_id') not in set(ids) for f in features):
        raise ValueError('orphan_feature_event')
    rows,excluded = [],[]
    for event in events:
        try:
            rows.append(_make_row(event,features,quotes,calendar,definitions,provenance,config))
        except (ValueError,TypeError,KeyError) as exc:
            excluded.append({'event_id':event['event_id'],'reason':str(exc)})
    return {'schema_version':'1.0','target_rule_id':RULE,'rows':rows,'excluded':excluded,
            'provenance':dict(provenance),'feature_registry':registry,'config':dict(config),
            'eligible_rows':len(rows),'input_events':len(events),
            'limitations':['Vendor provenance and calendar completeness require independent audit.',
                           'Synthetic fixtures establish software behavior only.']}


def split_dataset(rows, config):
    """Forward temporal split, economic-event grouping, availability and interval purge."""
    validate_config(config,fitting=True)
    names = ('train','validation','test')
    ends = [timestamp(config[k]) for k in ('train_end_utc','validation_end_utc','test_end_utc')]
    parsed,ids,group_latest = [],set(),{}
    for row in rows:
        eid = text(row.get('event_id'),'event_id')
        group = text(row.get('event_group_id'),'event_group_id')
        if eid in ids:
            raise ValueError('duplicate_event_id')
        ids.add(eid)
        decision,start,end,available = [timestamp(row[k]) for k in
                                       ('decision_at_utc','entry_at_utc','exit_at_utc','label_available_at_utc')]
        if not decision <= start < end <= available:
            raise ValueError('invalid_label_interval:' + eid)
        parsed.append((row,decision,start,end,available))
        group_latest[group] = max(group_latest.get(group,decision),decision)
    result = {name:[] for name in names}
    result['purged'] = []
    for row,decision,start,end,available in parsed:
        group_time = group_latest[row['event_group_id']]
        fold = next((i for i,cutoff in enumerate(ends) if group_time <= cutoff),None)
        reason = None
        if fold is None:
            reason = 'outside_final_test_window'
        elif (fold and decision <= ends[fold-1]):
            reason = 'event_group_crosses_boundary'
        elif available > ends[fold]:
            reason = 'label_unavailable_at_fold_cutoff'
        if reason:
            result['purged'].append({'event_id':row['event_id'],'reason':reason})
        else:
            result[names[fold]].append(row)
    embargo = timedelta(seconds=float(config.get('embargo_seconds',0)))
    for fold in (1,0):
        later = [r for n in names[fold+1:] for r in result[n]]
        kept = []
        for row in result[names[fold]]:
            start,end = timestamp(row['entry_at_utc']),timestamp(row['exit_at_utc'])
            if any(start <= timestamp(r['exit_at_utc']) and end >= timestamp(r['entry_at_utc'])-embargo for r in later):
                result['purged'].append({'event_id':row['event_id'],'reason':'overlapping_label_interval_or_embargo'})
            else:
                kept.append(row)
        result[names[fold]] = sorted(kept,key=lambda r:(timestamp(r['decision_at_utc']),r['event_id']))
    result['test'].sort(key=lambda r:(timestamp(r['decision_at_utc']),r['event_id']))
    return result


def _choice(values):
    return max(('no_trade','call','put'),key=lambda k:0 if k=='no_trade' else values[k+'_net_return'])


def _preprocessing(rows):
    names = sorted(rows[0]['features'])
    if not names or any(sorted(r['features']) != names for r in rows):
        raise ValueError('feature_schema_mismatch')
    medians = []
    for name in names:
        observed = [number(r['features'][name],name) for r in rows if r['features'][name] is not None]
        if not observed:
            raise ValueError('all_train_values_missing:' + name)
        medians.append(statistics.median(observed))
    vectors = [[medians[i] if r['features'][n] is None else number(r['features'][n],n) for i,n in enumerate(names)]
               + [float(r['features'][n] is None) for n in names] for r in rows]
    means = [statistics.mean(column) for column in zip(*vectors)]
    scales = [statistics.pstdev(column) or 1.0 for column in zip(*vectors)]
    return {'feature_names':names,'medians':medians,'means':means,'scales':scales,
            'transformed_feature_names':names+[n+'__missing' for n in names]}


def _transform(preprocessing, values):
    names = preprocessing['feature_names']
    if set(values) != set(names):
        raise ValueError('prediction_feature_schema_mismatch')
    vector = [preprocessing['medians'][i] if values[n] is None else number(values[n],n) for i,n in enumerate(names)]
    vector += [float(values[n] is None) for n in names]
    return [(v-m)/s for v,m,s in zip(vector,preprocessing['means'],preprocessing['scales'])]


def predict(model, features):
    """Predict from JSON coefficients and frozen train preprocessing without NumPy."""
    if model.get('schema_version') != '1.0' or model.get('target_names') != list(TARGET_NAMES):
        raise ValueError('invalid_model_schema')
    vector = _transform(model['preprocessing'],features)
    result = {}
    for index,name in enumerate(TARGET_NAMES):
        coefs = model['coefficients'][index]
        if len(coefs) != len(vector):
            raise ValueError('invalid_model_coefficient_shape')
        result[name] = number(model['intercepts'][index],name) + sum(number(c,name)*v for c,v in zip(coefs,vector))
        number(result[name],name)
    return result


def _metrics(rows, predictions):
    confusion = {truth:{pred:0 for pred in ('no_trade','call','put')} for truth in ('no_trade','call','put')}
    returns,correct = [],0
    targets = {}
    for name in TARGET_NAMES:
        errors = [p[name]-r['targets'][name] for r,p in zip(rows,predictions)]
        targets[name] = {'mae':statistics.mean(abs(e) for e in errors),
                         'rmse':math.sqrt(statistics.mean(e*e for e in errors)),
                         'direction_accuracy':statistics.mean((p[name]>0)==(r['targets'][name]>0)
                                                              for r,p in zip(rows,predictions))}
    for row,prediction in zip(rows,predictions):
        truth,selected = _choice(row['targets']),_choice(prediction)
        confusion[truth][selected] += 1
        correct += truth == selected
        returns.append(0 if selected=='no_trade' else row['targets'][selected+'_net_return'])
    return {'events':len(rows),'targets':targets,'choice_accuracy':correct/len(rows),
            'choice_confusion':confusion,'descriptive_mean_selected_net_return':statistics.mean(returns),
            'no_trade_mean_net_return':0.0,
            'limitation':'Single-contract event averages are not portfolio or financial performance evidence.'}


def train_model(rows, config, *, evaluate_test=True):
    """Train-only preprocessing; validation selection; one selected final-test score.

    Call only on dataset-builder output with independently reviewed provenance.
    Statistical sample minima are gates, not guarantees of scientific validity.
    """
    validate_config(config,fitting=True)
    if not rows or any(r.get('quote_data_kind') != 'historical_bid_ask' for r in rows):
        raise ValueError('fit_requires_actual_historical_bid_ask_data')
    splits = split_dataset(rows,config)
    for name,key in [('train','min_train_events'),('validation','min_validation_events'),('test','min_test_events')]:
        groups = {r['event_group_id'] for r in splits[name]}
        if len(groups) < int(config[key]):
            raise ValueError('insufficient_' + name + '_events')
        for r in splits[name]:
            if set(r.get('targets',{})) != set(TARGET_NAMES):
                raise ValueError('target_schema_mismatch')
            for target in TARGET_NAMES:
                number(r['targets'][target],target)
    train = splits['train']
    if len({_choice(r['targets']) for r in train}) < 2:
        raise ValueError('insufficient_train_class_diversity')
    prep = _preprocessing(train)
    try:
        import numpy as np
    except ImportError as exc:
        raise ValueError('optional_numpy_required_for_fit: requirements-training.txt') from exc
    x = np.asarray([_transform(prep,r['features']) for r in train],dtype=float)
    y = np.asarray([[r['targets'][n] for n in TARGET_NAMES] for r in train],dtype=float)
    means = y.mean(axis=0)
    base = {'schema_version':'1.0','target_rule_id':RULE,'target_names':list(TARGET_NAMES),
            'preprocessing':prep,'intercepts':means.tolist(),'coefficients':np.zeros((4,x.shape[1])).tolist(),
            'estimator':'train_mean','alpha':None}
    candidates = [base]
    for alpha in config['ridge_alphas']:
        regularized = x.T@x + float(alpha)*np.eye(x.shape[1])
        # Standardized train columns have mean zero; intercept is unpenalized.
        weights = np.linalg.solve(regularized,x.T@(y-means))
        if not np.isfinite(weights).all():
            raise ValueError('nonfinite_ridge_fit')
        candidates.append(dict(base,coefficients=weights.T.tolist(),estimator='ridge',alpha=float(alpha)))
    def validation_loss(model):
        return statistics.mean((predict(model,r['features'])[n]-r['targets'][n])**2
                               for r in splits['validation'] for n in TARGET_NAMES)
    selected = min(candidates,key=validation_loss)
    result = {'model':selected,'train_mean_baseline_model':base,
            'metrics':{'validation_selection':[{'estimator':m['estimator'],'alpha':m['alpha'],
                                                'mse':validation_loss(m)} for m in candidates]},
            'split_event_ids':{k:[r['event_id'] for r in splits[k]] for k in ('train','validation','test')},
            'split_event_group_ids':{k:sorted({r['event_group_id'] for r in splits[k]})
                                     for k in ('train','validation','test')},
            'purged':splits['purged'],'final_test_evaluations':0,
            'fit_scope':'train_only; validation_selects; final_test_once; no_refit'}
    return evaluate_final_test(result,rows,config) if evaluate_test else result


def evaluate_final_test(fit, rows, config):
    """Evaluate a selected fit once. CLI also reserves the holdout in a persistent ledger."""
    if fit.get('final_test_evaluations') != 0:
        raise ValueError('final_test_already_evaluated')
    splits = split_dataset(rows,config)
    if [r['event_id'] for r in splits['test']] != fit['split_event_ids']['test']:
        raise ValueError('final_test_dataset_changed')
    result = dict(fit,metrics=dict(fit['metrics']),final_test_evaluations=1)
    final_predictions = [predict(fit['model'],r['features']) for r in splits['test']]
    mean_predictions = [predict(fit['train_mean_baseline_model'],r['features']) for r in splits['test']]
    result['metrics']['test'] = _metrics(splits['test'],final_predictions)
    result['metrics']['test_train_mean_baseline'] = _metrics(splits['test'],mean_predictions)
    return result
