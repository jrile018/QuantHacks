"""Fail-closed dated market qualification against tiny original CSV fixtures."""
import csv
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest


def module():
    try:
        return importlib.import_module('src.reit_market_qualification')
    except ModuleNotFoundError:
        return None


def quote(**changes):
    return dict(ts_recv='2024-01-02T15:00:00.000000000Z',
                ts_event='2024-01-02T14:59:59.000000000Z', publisher_id='2',
                instrument_id='10', symbol='AMT', bid_px_00='100', ask_px_00='101',
                bid_sz_00='20', ask_sz_00='10', **changes)


def definition(**changes):
    row = dict(ts_recv='2024-01-02T11:00:00Z', ts_event='2024-01-02T11:00:00Z',
               publisher_id='2', instrument_id='10', raw_symbol='AMT', symbol='AMT',
               instrument_class='K', security_update_action='A', contract_multiplier='2147483647',
               expiration='', activation='', underlying='', currency='USD', strike_price='')
    row.update(changes)
    return row


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.q = module()
        self.assertIsNotNone(self.q, 'Streaming qualification module must exist')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def index(self, rows=None, dataset='EQUS.MINI'):
        index = self.q.DefinitionIndex(self.root / ('defs-' + str(len(list(self.root.glob('defs-*.sqlite')))) + '.sqlite'))
        self.addCleanup(index.close)
        for n, row in enumerate(rows or [definition()], 2):
            index.add(dataset, row, {'raw_sha256': 'a'*64, 'raw_file': 'def.csv', 'row_number': n})
        index.finish()
        return index

    def normalize(self, row=None, rows=None, dataset='EQUS.MINI',
                  interval_replay_assumption='historical_interval_endpoint_replay'):
        return self.q.normalize_quote(row or quote(), dataset=dataset, schema='bbo-1m',
            index=self.index(rows, dataset), degraded_dates={'2024-06-03'},
            provenance={'raw_sha256': 'b'*64, 'raw_file': 'quote.csv', 'row_number': 2},
            interval_replay_assumption=interval_replay_assumption)

    def test_valid_quote_keeps_lineage_without_assuming_multiplier_or_nbbo(self):
        result = self.normalize()
        self.assertEqual(result['reasons'], [])
        self.assertEqual(result['mark']['mid'], 100.5)
        self.assertIsNone(result['mark']['contract_multiplier'])
        self.assertFalse(result['mark']['national_nbbo'])
        self.assertEqual(result['mark']['definition_provenance']['row_number'], 2)

    def test_future_last_trade_even_one_nanosecond_is_rejected(self):
        row = quote()
        row['ts_event'] = '2024-01-02T15:00:00.000000001Z'
        self.assertIn('future_last_trade', self.normalize(row)['reasons'])

    def test_quote_missing_crossed_locked_and_sentinel_are_excluded(self):
        cases = [('bid_px_00', '', 'missing_or_invalid_price'),
                 ('bid_px_00', '102', 'crossed_or_locked_quote'),
                 ('ask_px_00', '100', 'crossed_or_locked_quote'),
                 ('ask_px_00', '9223372036.854775807', 'missing_or_invalid_price'),
                 ('ask_sz_00', '0', 'missing_or_invalid_size')]
        for field, value, reason in cases:
            with self.subTest(field=field, value=value):
                row = quote()
                row[field] = value
                # Each index lives in its own file, so duplicate snapshots cannot affect the test.
                result = self.normalize(row)
                self.assertIn(reason, result['reasons'])

    def test_null_undefined_and_old_last_trade_do_not_assert_quote_staleness(self):
        for trade in ('', '18446744073709551615', '2023-01-01T00:00:00Z'):
            with self.subTest(trade=trade):
                row = quote()
                row['ts_event'] = trade
                result = self.normalize(row)
                self.assertEqual(result['reasons'], [])
                mark = result['mark']
                self.assertEqual(mark['last_trade_at_utc'], trade if trade.startswith('2023') else None)
                self.assertIsNone(mark['quote_updated_at_utc'])
                self.assertIsNone(mark['quote_age_seconds'])
                self.assertFalse(mark['quote_freshness_verified'])

    def test_blank_last_trade_is_a_valid_interval_diagnostic(self):
        row = quote()
        row['ts_event'] = ''
        result = self.q.normalize_quote(row, dataset='EQUS.MINI', schema='bbo-1m',
            index=self.index(), degraded_dates=set(),
            provenance={'raw_sha256': 'b'*64, 'raw_file': 'quote.csv', 'row_number': 2})
        self.assertEqual(result['reasons'], [])

    def test_forward_filled_trade_does_not_mark_quote_stale(self):
        row = quote()
        row['ts_event'] = '2023-01-01T00:00:00Z'
        result = self.q.normalize_quote(row, dataset='EQUS.MINI', schema='bbo-1m',
            index=self.index(), degraded_dates=set(),
            provenance={'raw_sha256': 'b'*64, 'raw_file': 'quote.csv', 'row_number': 2})
        self.assertEqual(result['reasons'], [])

    def test_optional_last_trade_does_not_permit_malformed_clock(self):
        row = quote()
        row['ts_event'] = 'not-a-timestamp'
        self.assertIn('invalid_last_trade_timestamp', self.normalize(row)['reasons'])

    def test_quality_window_uses_minute_interval_instead_of_forward_filled_trade(self):
        row = quote()
        row.update(ts_recv='2024-06-04T15:00:00Z', ts_event='2024-06-03T15:00:00Z')
        defined = definition(ts_recv='2024-06-04T11:00:00Z', ts_event='2024-06-04T11:00:00Z')
        self.assertEqual(self.normalize(row, [defined])['reasons'], [])
        row['ts_recv'] = '2024-06-04T00:00:30Z'
        defined.update(ts_recv='2024-06-04T00:00:00Z', ts_event='2024-06-04T00:00:00Z')
        self.assertIn('degraded_quote_interval', self.normalize(row, [defined])['reasons'])

    def test_observed_availability_remains_unknown_and_replay_requires_opt_in(self):
        mark = self.normalize(interval_replay_assumption=None)['mark']
        for field in ('public_at_utc', 'available_at_utc', 'received_at_utc', 'processed_at_utc',
                      'quote_updated_at_utc', 'assumed_available_at_utc'):
            self.assertIsNone(mark[field])
        self.assertFalse(mark['canonical_consumer_ready'])
        self.assertIn('interval_replay_assumption_required', self.q.equity_candidate(mark, set())['reasons'])

    def test_candidate_uses_explicit_replay_clock_without_promoting_observed_availability(self):
        mark = self.normalize()['mark']
        candidate = self.q.equity_candidate(mark, set())['candidate']
        self.assertIsNone(candidate['feature_available_at_utc'])
        self.assertEqual(candidate['feature_assumed_available_at_utc'], '2024-01-02T15:00:00.000000000Z')
        self.assertEqual(candidate['feature_availability_assumption'], 'historical_interval_endpoint_replay')
        self.assertFalse(candidate['canonical_consumer_ready'])
        self.assertIn('feature_interval_outside_lookback',
                      self.q.equity_candidate(mark, set(), lookback_seconds=30)['reasons'])

    def test_mapping_must_match_dataset_publisher_symbol_and_observed_date(self):
        cases = [definition(symbol='O', raw_symbol='O'), definition(publisher_id='3'),
                 definition(ts_recv='2024-01-01T11:00:00Z', ts_event='2024-01-01T11:00:00Z'),
                 definition(ts_recv='2024-01-02T16:00:00Z')]
        for row in cases:
            with self.subTest(row=row):
                self.assertIn('dated_definition_missing_or_identity_mismatch', self.normalize(rows=[row])['reasons'])

    def test_cancelled_and_ambiguous_same_timestamp_definition_cannot_qualify(self):
        self.assertIn('definition_deleted', self.normalize(rows=[definition(security_update_action='D')])['reasons'])
        other = definition(raw_symbol='O', symbol='O')
        self.assertIn('ambiguous_dated_definition', self.normalize(rows=[definition(), other])['reasons'])

    def test_futures_spread_cannot_be_promoted_to_outright(self):
        result = self.normalize(rows=[definition(instrument_class='S')], dataset='GLBX.MDP3')
        self.assertIn('unsupported_instrument_class', result['reasons'])

    def test_option_expiration_sentinel_is_not_a_valid_lifecycle(self):
        row = definition(instrument_class='C', underlying='AMT', strike_price='100',
                         expiration='18446744073709551615')
        result = self.normalize(rows=[row], dataset='OPRA.PILLAR')
        self.assertIn('option_terms_missing', result['reasons'])

    def test_product_schema_pair_cannot_be_relabelled(self):
        row = definition(instrument_class='C', underlying='AMT', strike_price='100',
                         expiration='2024-02-01T21:00:00Z')
        result = self.normalize(rows=[row], dataset='OPRA.PILLAR')  # helper supplies bbo, not cbbo
        self.assertIn('unsupported_dataset_or_schema', result['reasons'])

    def test_cost_hash_binding_requires_the_actual_retained_source(self):
        mark = self.normalize()['mark']
        evidence = {'value': 0, 'verified': True, 'source': str(self.root/'missing-cost.csv'),
                    'source_sha256': 'c'*64, 'reviewer': 'source-review',
                    'retrieved_at_utc': '2026-01-01T00:00:00Z',
                    'reviewed_at_utc': '2026-01-02T00:00:00Z',
                    'public_at_utc': '2023-01-01T00:00:00Z',
                    'valid_from': '2024-01-01T00:00:00Z', 'valid_to': '2025-01-01T00:00:00Z'}
        self.assertIn('fees_unknown', self.q.qualify_tracks([mark], costs={'fees': evidence})['repricing']['reasons'])

    def test_dated_costs_must_cover_the_mark_and_be_available_then(self):
        mark = self.normalize()['mark']
        evidence = {'value': 0, 'verified': True, 'source': 'retained-cost.csv',
                    'source_sha256': 'c'*64, 'reviewer': 'source-review',
                    'retrieved_at_utc': '2026-01-01T00:00:00Z',
                    'reviewed_at_utc': '2026-01-02T00:00:00Z',
                    'public_at_utc': '2023-01-01T00:00:00Z',
                    'valid_from': '2023-01-01T00:00:00Z', 'valid_to': '2023-12-01T00:00:00Z'}
        source = self.root/'retained-cost.csv'
        source.write_text('fees,0\n')
        evidence.update(source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertIn('fees_unknown', self.q.qualify_tracks([mark], costs={'fees': evidence})['repricing']['reasons'])
        evidence.update(valid_from='2024-01-01T00:00:00Z', valid_to='2025-01-01T00:00:00Z',
                        public_at_utc='2024-01-03T00:00:00Z')
        self.assertIn('fees_unknown', self.q.qualify_tracks([mark], costs={'fees': evidence})['repricing']['reasons'])
        evidence['public_at_utc'] = '2023-01-01T00:00:00Z'
        self.assertNotIn('fees_unknown', self.q.qualify_tracks([mark], costs={'fees': evidence})['repricing']['reasons'])

    def test_future_feature_availability_cannot_be_used_by_candidate(self):
        mark = self.normalize()['mark']
        mark['assumed_available_at_utc'] = '2024-01-02T15:00:00.000000001Z'
        result = self.q.equity_candidate(mark, set())
        self.assertIsNone(result['candidate'])
        self.assertIn('feature_not_available_at_decision', result['reasons'])

    def test_sentinel_multiplier_and_unknown_costs_block_economic_tracks(self):
        mark = self.normalize()['mark']
        packet = self.q.qualify_tracks([mark], costs={})
        self.assertEqual(packet['diagnostic']['status'], 'candidate_only')
        self.assertEqual(packet['repricing']['status'], 'insufficient')
        self.assertIn('fees_unknown', packet['repricing']['reasons'])
        self.assertIn('contract_multiplier_unknown', packet['strict_arbitrage']['reasons'])
        self.assertIn('interval_quotes_not_simultaneous_execution', packet['strict_arbitrage']['reasons'])
        self.assertFalse(packet['arbitrage_claim'])

    def test_false_zero_negative_or_unreviewed_cost_evidence_does_not_qualify(self):
        mark = self.normalize()['mark']
        for value in (None, False, -1, float('nan'), {'value': 0, 'verified': False}):
            with self.subTest(value=value):
                packet = self.q.qualify_tracks([mark], costs={'fees': value})
                self.assertIn('fees_unknown', packet['repricing']['reasons'])

    def test_complete_window_rejected_before_forecast_outcome_access(self):
        mark = self.normalize()['mark']
        mark['mark_at_utc'] = '2024-06-02T23:30:00Z'
        result = self.q.equity_candidate(mark, {'2024-06-03'}, holding_seconds=3600)
        self.assertIsNone(result['candidate'])
        self.assertIn('degraded_full_window', result['reasons'])
        mark['mark_at_utc'] = '2024-06-04T00:00:30Z'
        result = self.q.equity_candidate(mark, {'2024-06-03'}, lookback_seconds=60)
        self.assertIsNone(result['candidate'])

    def test_equity_forecast_is_bounded_development_only_and_unscored(self):
        result = self.q.equity_candidate(self.normalize()['mark'], {'2024-06-03'})
        row = result['candidate']
        self.assertEqual(row['prediction_mid'], 100.5)
        self.assertFalse(row['outcomes_read'])
        self.assertEqual(row['model'], 'frozen_persistence_baseline')
        mark = self.normalize()['mark']
        mark['mark_at_utc'] = '2025-12-31T23:30:00Z'
        self.assertIn('holding_window_outside_development', self.q.equity_candidate(mark, set())['reasons'])

    def fixture_file(self, name, rows):
        path = self.root / name
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        raw = path.read_bytes()
        return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}

    def test_corrupt_raw_hash_and_duplicate_csv_headers_fail_closed(self):
        file = self.fixture_file('q.csv', [quote()])
        file['sha256'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'raw_hash_mismatch'):
            list(self.q.verified_csv_rows(file))
        path = self.root / 'duplicate.csv'
        path.write_text('symbol,symbol\nAMT,O\n')
        raw = path.read_bytes()
        file = {'path': str(path), 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        with self.assertRaisesRegex(ValueError, 'duplicate_csv_columns'):
            list(self.q.verified_csv_rows(file))

    def metadata_file(self):
        path = self.root/'condition.json'
        path.write_text('[]\n', encoding='utf-8')
        raw = path.read_bytes()
        return {'path': str(path), 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    def test_json_auxiliary_descriptor_is_rejected_by_csv_reader(self):
        # This JSON can look like an empty CSV to DictReader; type must fail first.
        with self.assertRaisesRegex(ValueError, 'non_csv_source_descriptor:condition.json'):
            list(self.q.verified_csv_rows(self.metadata_file()))

    def test_non_csv_source_descriptor_fails_preflight_without_output_directory(self):
        config = {'jobs': [dict(job_id='definition-job', dataset='EQUS.MINI', schema='definition',
                               files=[self.fixture_file('def.csv', [definition()]), self.metadata_file()])]}
        output = self.root/'output'
        with self.assertRaisesRegex(ValueError, 'non_csv_source_descriptor:condition.json'):
            self.q.run_qualification(config, {'union_dates': []}, output)
        self.assertFalse(output.exists())

    def test_streaming_run_counts_all_rows_preserves_rejection_and_refuses_overwrite(self):
        bad = quote()
        bad['ask_px_00'] = '99'
        config = {'jobs': [dict(job_id='definition-job', dataset='EQUS.MINI', schema='definition',
                              files=[self.fixture_file('def.csv', [definition()])]),
                           dict(job_id='quote-job', dataset='EQUS.MINI', schema='bbo-1m',
                              files=[self.fixture_file('quotes.csv', [quote(), bad])])]}
        rule = {'union_dates': ['2024-06-03']}
        output = self.root / 'output'
        report = self.q.run_qualification(config, rule, output, sample_limit=1,
                     interval_replay_assumption='historical_interval_endpoint_replay')
        self.assertEqual(report['quotes']['EQUS.MINI']['rows'], 2)
        self.assertEqual(report['quotes']['EQUS.MINI']['qualified_diagnostic_rows'], 1)
        self.assertEqual(report['quotes']['EQUS.MINI']['rejection_counts']['crossed_or_locked_quote'], 1)
        self.assertEqual(report['candidate_count'], 1)
        self.assertFalse(report['consumer_accepted'])
        with self.assertRaises(FileExistsError):
            self.q.run_qualification(config, rule, output)

    def test_duplicate_raw_descriptor_cannot_double_count_source_rows(self):
        file = self.fixture_file('q.csv', [quote()])
        config = {'jobs': [dict(job_id='quote-job', dataset='EQUS.MINI', schema='bbo-1m', files=[file, file])]}
        with self.assertRaisesRegex(ValueError, 'duplicate_raw_file'):
            self.q.run_qualification(config, {'union_dates': []}, self.root/'duplicate-output')


if __name__ == '__main__':
    unittest.main()
