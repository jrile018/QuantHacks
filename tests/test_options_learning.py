"""Hand-computed fixtures test software contracts, not financial performance."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src import options_learning as learning
from scripts import train_options_model as cli


def fixture():
    config = json.loads((Path(__file__).parents[1] / 'configs/options_learning.json').read_text())
    config.update(max_quote_age_seconds=60, max_spread_fraction=.5,
                  execution_costs=dict(entry_fees=1, exit_fees=1,
                                       entry_slippage_cost=2, exit_slippage_cost=2),
                  train_end_utc='2024-01-10T00:00:00Z',
                  validation_end_utc='2024-01-20T00:00:00Z',
                  test_end_utc='2024-01-30T00:00:00Z',
                  min_train_events=2, min_validation_events=2, min_test_events=2)
    provenance = dict(quote_data_kind='synthetic', quote_provider='fixture',
                      quote_provenance_reference='fixture only', feature_provenance_reference='fixture only',
                      calendar_provenance_reference='fixture only', experiment_id='unit-test',
                      experiment_frozen_at_utc='2023-12-01T00:00:00Z')
    event = dict(event_id='e1', event_group_id='g1', cik='1234', security_id='SEC1',
                 decision_at_utc='2024-01-02T15:00:00Z', mode='post_release',
                 currency='USD', deliverable='100 SEC1 common shares', mapping_evidence='fixture mapping')
    for field in ['mapping_public_at_utc', 'mapping_receipt_at_utc', 'mapping_processing_at_utc',
                  'mapping_valid_from_utc']:
        event[field] = '2023-12-01T00:00:00Z'
    event['mapping_valid_to_utc'] = '2025-01-01T00:00:00Z'
    features = [dict(event_id='e1', feature_name='tone', value=.2, source_id='doc',
                     source_record_id='rec1', source_url='https://example.invalid/fixture',
                     definition_version='v1', public_at_utc='2024-01-02T14:00:00Z',
                     receipt_at_utc='2024-01-02T14:01:00Z', processing_at_utc='2024-01-02T14:02:00Z',
                     valid_from_utc='2024-01-02T14:00:00Z', accession='old')]
    registry = dict(features=[dict(feature_name='tone', source_id='doc', definition_version='v1',
                                  role='predictor', independence_evidence='fixture rubric frozen without outcomes')])
    sessions = [dict(session_id=d, open_at_utc=f'{d}T14:30:00Z', close_at_utc=f'{d}T21:00:00Z',
                     calendar_source='fixture', calendar_version='v1') for d in ['2024-01-02', '2024-01-03']]
    quotes = []
    for snapshot, timestamp, call, put in [
        ('decision', '2024-01-02T14:59:30Z', (9, 11), (9, 11)),
        ('atdecision', '2024-01-02T15:00:00Z', (9, 11), (9, 11)),
        ('entry', '2024-01-02T15:00:01Z', (9, 11), (9, 11)),
        ('lateentry', '2024-01-02T15:01:00Z', (19, 21), (19, 21)),
        ('exit', '2024-01-03T21:00:00Z', (14, 16), (4, 6))]:
        for kind, prices, strike in [('call', call, 105), ('put', put, 95)]:
            quotes.append(dict(quote_id=f'{snapshot}-{kind}', snapshot_id=snapshot,
                               security_id='SEC1', contract_id=kind, option_type=kind, strike=strike,
                               expiry='2024-05-01', timestamp_utc=timestamp, receipt_at_utc=timestamp,
                               bid=prices[0], ask=prices[1], bid_size=10, ask_size=10, multiplier=100,
                               currency='USD', deliverable='100 SEC1 common shares', underlying_price=100,
                               underlying_timestamp_utc=timestamp, underlying_receipt_at_utc=timestamp))
    return [[event], features, quotes, sessions, registry, provenance, config]


class DatasetTests(unittest.TestCase):
    def test_first_entry_and_next_session_cost_targets(self):
        result = learning.build_dataset(*fixture())
        self.assertEqual(result['excluded'], [])
        row = result['rows'][0]
        self.assertEqual(row['entry_at_utc'], '2024-01-02T15:00:01+00:00')
        self.assertEqual(row['exit_at_utc'], '2024-01-03T21:00:00+00:00')
        self.assertEqual(row['targets']['call_premium_change'], .5)
        self.assertEqual(row['targets']['put_premium_change'], -.5)
        self.assertAlmostEqual(row['targets']['call_net_return'], 294 / 1103)
        self.assertAlmostEqual(row['targets']['put_net_return'], -706 / 1103)

    def test_tie_break_smaller_strike(self):
        args = fixture()
        for quote in args[2][:2]:
            twin = dict(quote, contract_id=quote['contract_id']+'-smaller', quote_id=quote['quote_id']+'-smaller',
                        strike=104 if quote['option_type']=='call' else 94)
            quote['strike'] = 106 if quote['option_type']=='call' else 96
            args[2].append(twin)
        # Duplicate the smaller candidates in all executable snapshots.
        for quote in list(args[2][2:10]):
            args[2].append(dict(quote, contract_id=quote['contract_id']+'-smaller',
                               quote_id=quote['quote_id']+'-smaller',
                               strike=104 if quote['option_type']=='call' else 94))
            quote['strike'] = 106 if quote['option_type']=='call' else 96
        result = learning.build_dataset(*args)
        self.assertEqual(result['rows'][0]['contracts']['call']['strike'], 104)

    def test_future_feature_rejected_not_silently_imputed(self):
        args = fixture()
        args[1][0]['processing_at_utc'] = '2024-01-03T00:00:00Z'
        result = learning.build_dataset(*args)
        self.assertFalse(result['rows'])
        self.assertIn('feature_after_decision', result['excluded'][0]['reason'])

    def test_anticipation_target_accession_forbidden(self):
        args = fixture()
        args[0][0].update(mode='anticipation', target_accession='old')
        self.assertIn('target_filing_leakage', learning.build_dataset(*args)['excluded'][0]['reason'])

    def test_missing_exit_does_not_use_same_session_close(self):
        args = fixture()
        args[2] = [q for q in args[2] if q['snapshot_id']!='exit']
        self.assertIn('next_session_exit_missing', learning.build_dataset(*args)['excluded'][0]['reason'])

    def test_boolean_market_numbers_and_evidence_rejected(self):
        args = fixture()
        args[2][0]['multiplier'] = True
        self.assertIn('invalid_quote', learning.build_dataset(*args)['excluded'][0]['reason'])
        args = fixture()
        args[0][0]['mapping_evidence'] = True
        self.assertIn('mapping_evidence', learning.build_dataset(*args)['excluded'][0]['reason'])

    def test_quote_receipt_late_excludes_decision_snapshot(self):
        args = fixture()
        for q in args[2]:
            if q['snapshot_id'] in ('decision', 'atdecision'):
                q['receipt_at_utc'] = '2024-01-02T15:02:00Z'
        self.assertIn('decision_pair_missing', learning.build_dataset(*args)['excluded'][0]['reason'])

    def test_industry_revision_and_missingness_are_point_in_time(self):
        args=fixture()
        args[1][0].update(value=None,missing_reason='not_applicable')
        self.assertIsNone(learning.build_dataset(*args)['rows'][0]['features']['tone'])
        args[1][0]['valid_from_utc']='2024-01-04T00:00:00Z'
        self.assertIn('feature_after_decision',learning.build_dataset(*args)['excluded'][0]['reason'])

    def test_no_quotes_and_absent_independence_evidence_rejected(self):
        args=fixture()
        args[2]=[]
        self.assertIn('decision_pair_missing',learning.build_dataset(*args)['excluded'][0]['reason'])
        args=fixture()
        args[4]['features'][0]['independence_evidence']=True
        with self.assertRaisesRegex(ValueError,'independence_evidence'):
            learning.build_dataset(*args)

    def test_zero_liquidity_quote_does_not_poison_other_eligible_quotes(self):
        args=fixture()
        twin=dict(args[2][0],quote_id='zero-size',contract_id='illiquid',strike=104,bid_size=0)
        args[2].append(twin)
        result=learning.build_dataset(*args)
        self.assertEqual(result['rows'][0]['contracts']['call']['contract_id'],'call')

    def test_mapping_expiry_before_exit_blocks_label(self):
        args=fixture()
        args[0][0]['mapping_valid_to_utc']='2024-01-03T00:00:00Z'
        self.assertIn('mapping_expired_before_exit',learning.build_dataset(*args)['excluded'][0]['reason'])

    def test_cost_currency_must_match_instrument(self):
        args=fixture()
        args[-1]['execution_cost_currency']='EUR'
        self.assertIn('cost_currency_mismatch',learning.build_dataset(*args)['excluded'][0]['reason'])

    def test_target_receipt_retained_and_cutoff_enforced(self):
        args=fixture()
        args[0][0]['label_available_at_utc']='2024-01-03T21:00:30Z'
        built=learning.build_dataset(*args)['rows']
        self.assertEqual(built[0]['label_available_at_utc'],'2024-01-03T21:00:30+00:00')
        cfg=copy.deepcopy(args[-1])
        cfg['train_end_utc']='2024-01-03T21:00:00Z'
        self.assertFalse(learning.split_dataset(built,cfg)['train'])

    def test_late_outcome_receipt_is_availability_not_quote_staleness(self):
        args=fixture()
        args[0][0]['label_available_at_utc']='2024-01-04T12:00:00Z'
        built=learning.build_dataset(*args)
        self.assertEqual(built['rows'][0]['label_available_at_utc'],'2024-01-04T12:00:00+00:00')

    def test_exit_quote_received_after_close_is_not_executable(self):
        args=fixture()
        for q in args[2]:
            if q['snapshot_id']=='exit':
                q['receipt_at_utc']='2024-01-03T21:00:01Z'
        self.assertIn('next_session_exit_missing',learning.build_dataset(*args)['excluded'][0]['reason'])

    def test_asynchronous_ticks_use_preserved_asof_snapshot_anchor(self):
        args=fixture()
        for q in args[2]:
            q['snapshot_at_utc']=q['timestamp_utc']
            if q['snapshot_id']=='entry':
                q['timestamp_utc']='2024-01-02T15:00:00Z'
                q['underlying_timestamp_utc']='2024-01-02T14:59:59Z'
        result=learning.build_dataset(*args)
        self.assertEqual(result['rows'][0]['entry_at_utc'],'2024-01-02T15:00:01+00:00')
        self.assertEqual(result['rows'][0]['contracts']['call']['entry_quote_at_utc'],
                         '2024-01-02T15:00:00+00:00')

    def test_stale_underlying_or_future_tick_blocks_snapshot(self):
        args=fixture()
        for q in args[2]:
            q['underlying_timestamp_utc']='2024-01-01T00:00:00Z'
        self.assertIn('decision_pair_missing',learning.build_dataset(*args)['excluded'][0]['reason'])
        args=fixture()
        args[2][0]['snapshot_at_utc']='2024-01-02T14:59:29Z'
        self.assertIn('invalid_quote',learning.build_dataset(*args)['excluded'][0]['reason'])


def row(event, decision, end, group=None, value=1, call=.2, put=-.1):
    return dict(event_id=event, event_group_id=group or event, decision_at_utc=decision,
                entry_at_utc=decision, exit_at_utc=end, label_available_at_utc=end,
                features={'tone': value}, quote_data_kind='historical_bid_ask',
                targets=dict(call_premium_change=call, put_premium_change=put,
                             call_net_return=call, put_net_return=put))


class SplitTests(unittest.TestCase):
    def test_overlap_and_label_receipt_purged(self):
        cfg=fixture()[-1]
        rows=[row('overlap','2024-01-09T00:00:00Z','2024-01-11T00:00:00Z'),
              row('clean','2024-01-05T00:00:00Z','2024-01-06T00:00:00Z'),
              row('val','2024-01-10T01:00:00Z','2024-01-12T00:00:00Z')]
        result=learning.split_dataset(rows,cfg)
        self.assertEqual([r['event_id'] for r in result['train']], ['clean'])
        self.assertEqual([r['event_id'] for r in result['validation']], ['val'])

    def test_economic_event_group_never_crosses_folds(self):
        cfg=fixture()[-1]
        rows=[row('original','2024-01-05T00:00:00Z','2024-01-06T00:00:00Z',group='same'),
              row('amendment','2024-01-15T00:00:00Z','2024-01-16T00:00:00Z',group='same')]
        result=learning.split_dataset(rows,cfg)
        self.assertFalse(result['train'])
        self.assertEqual([r['event_id'] for r in result['validation']], ['amendment'])

    def test_late_label_receipt_excluded(self):
        cfg=fixture()[-1]
        candidate=row('late','2024-01-05T00:00:00Z','2024-01-06T00:00:00Z')
        candidate['label_available_at_utc']='2024-01-11T00:00:00Z'
        self.assertFalse(learning.split_dataset([candidate],cfg)['train'])

    def test_embargo_purges_near_boundary(self):
        cfg=fixture()[-1]
        cfg['embargo_seconds']=86400
        rows=[row('near','2024-01-08T00:00:00Z','2024-01-09T12:00:00Z'),
              row('val','2024-01-10T01:00:00Z','2024-01-11T00:00:00Z')]
        result=learning.split_dataset(rows,cfg)
        self.assertFalse(result['train'])
        self.assertEqual(result['purged'][0]['reason'],'overlapping_label_interval_or_embargo')


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'optional NumPy training dependency absent')
class ModelTests(unittest.TestCase):
    def samples(self):
        return [row(str(d),f'2024-01-{d:02d}T00:00:00Z',f'2024-01-{d+1:02d}T00:00:00Z',
                    value=v,call=c,put=p) for d,v,c,p in
                [(2,1,.2,-.1),(4,3,-.2,.3),(12,100,.2,-.1),(14,200,-.1,-.2),
                 (22,300,.1,.2),(24,400,-.2,-.1)]]

    def test_train_only_scaling_and_json_predict(self):
        cfg=fixture()[-1]
        result=learning.train_model(self.samples(),cfg)
        model=json.loads(json.dumps(result['model'],allow_nan=False))
        self.assertEqual(model['preprocessing']['medians'], [2])
        self.assertEqual(model['preprocessing']['means'][0],2)
        predictions=learning.predict(model, {'tone': None})
        self.assertEqual(set(predictions),set(learning.TARGET_NAMES))
        self.assertIn('no_trade', result['metrics']['test']['choice_confusion'])

    def test_synthetic_or_one_class_training_refused(self):
        rows=self.samples()
        rows[0]['quote_data_kind']='synthetic'
        with self.assertRaisesRegex(ValueError,'historical_bid_ask'):
            learning.train_model(rows,fixture()[-1])

    def test_insufficient_distinct_economic_events_refused(self):
        rows=self.samples()
        rows[1]['event_group_id']=rows[0]['event_group_id']
        with self.assertRaisesRegex(ValueError,'insufficient_train_events'):
            learning.train_model(rows,fixture()[-1])

    def test_selection_can_finish_without_opening_final_test_metrics(self):
        result=learning.train_model(self.samples(),fixture()[-1],evaluate_test=False)
        self.assertNotIn('test',result['metrics'])
        self.assertEqual(result['final_test_evaluations'],0)
        scored=learning.evaluate_final_test(result,self.samples(),fixture()[-1])
        self.assertEqual(scored['final_test_evaluations'],1)
        with self.assertRaisesRegex(ValueError,'already_evaluated'):
            learning.evaluate_final_test(scored,self.samples(),fixture()[-1])
        rows=self.samples()
        rows[1]['targets']=copy.deepcopy(rows[0]['targets'])
        with self.assertRaisesRegex(ValueError,'class_diversity'):
            learning.train_model(rows,fixture()[-1])


class CLITests(unittest.TestCase):
    def test_holdout_ledger_refuses_reuse_across_experiment_names(self):
        with tempfile.TemporaryDirectory() as temp:
            rows=[row('test','2024-01-22T00:00:00Z','2024-01-23T00:00:00Z')]
            provenance=fixture()[-2]
            path=cli.reserve_holdout(Path(temp),rows,fixture()[-1],provenance)
            self.assertTrue(path.exists())
            provenance['experiment_id']='new-name-same-heldout'
            with self.assertRaisesRegex(ValueError,'heldout_already_reserved'):
                cli.reserve_holdout(Path(temp),rows,fixture()[-1],provenance)

    def test_holdout_ledger_refuses_partial_cohort_overlap_and_provider_change(self):
        with tempfile.TemporaryDirectory() as temp:
            rows=[row('a','2024-01-22T00:00:00Z','2024-01-23T00:00:00Z'),
                  row('b','2024-01-24T00:00:00Z','2024-01-25T00:00:00Z')]
            provenance=fixture()[-2]
            cli.reserve_holdout(Path(temp),rows,fixture()[-1],provenance)
            provenance['quote_provider']='renamed-provider'
            with self.assertRaisesRegex(ValueError,'heldout_overlap'):
                cli.reserve_holdout(Path(temp),rows[:1],fixture()[-1],provenance)

    def test_cli_audits_fixture_and_refuses_synthetic_fit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            names=['events','features','quotes','sessions','registry','provenance','config']
            args=fixture()
            command=[sys.executable,str(Path(__file__).parents[1]/'scripts/train_options_model.py')]
            for name,value in zip(names,args):
                path=root/(name+('.jsonl' if name in names[:4] else '.json'))
                path.write_text('\n'.join(json.dumps(r) for r in value) if name in names[:4] else json.dumps(value))
                command += ['--'+name,str(path)]
            first=subprocess.run(command+['--output',str(root/'audit')],capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertEqual(json.loads((root/'audit/audit.json').read_text())['eligible_rows'],1)
            second=subprocess.run(command+['--fit','--output',str(root/'fit')],capture_output=True,text=True)
            self.assertNotEqual(second.returncode,0)
            self.assertFalse((root/'fit/model.json').exists())


if __name__=='__main__':
    unittest.main()
