"""Acquisition safety boundaries use the real durable ledger and a fake wire."""
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import requests

from src.reit_budget import BudgetLedger, BudgetExceeded

HAS_MODULE = importlib.util.find_spec('src.reit_market_data') is not None
if HAS_MODULE:
    from src.reit_market_data import (DatabentoClient, AmbiguousSubmission,
                                      market_readiness, validate_file, fingerprint)


class Response:
    def __init__(self, value, content=b'', status=200):
        self.value, self.content, self.status_code = value, content, status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError('wire failure with credentials must not escape')
    def json(self):
        return self.value
    def iter_content(self, chunk_size):
        yield self.content
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class Wire:
    def __init__(self, *, timeout=False, cost=10, content=b'market'):
        self.timeout, self.cost, self.content = timeout, cost, content
        self.calls = []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        endpoint = url.rsplit('/', 1)[-1]
        values = {'metadata.list_datasets': ['TEST'],
                  'metadata.list_schemas': ['mbp-1'],
                  'metadata.get_dataset_range': {'start': '2024-01-01T00:00:00Z', 'end': '2027-01-01T00:00:00Z'},
                  'metadata.get_dataset_condition': [{'date': '2024-01-02', 'condition': 'available'}],
                  'metadata.get_cost': self.cost,
                  'batch.submit_job': {'id': 'job1', 'state': 'queued', 'api_key': 'never-save-me'},
                  'batch.get_job_details': {'id': 'job1', 'state': 'done', 'cost_usd': 10},
                  'batch.list_files': [{'filename': 'market.csv', 'size': len(self.content),
                      'hash': 'sha256:' + hashlib.sha256(self.content).hexdigest(),
                      'urls': {'https': 'https://api.databento.com/market.csv'}}]}
        if endpoint == 'batch.submit_job' and self.timeout:
            raise requests.Timeout('contains api key secret')
        return Response(values.get(endpoint), self.content)


class InstallationTest(unittest.TestCase):
    def test_market_acquisition_contract_exists(self):
        self.assertTrue(HAS_MODULE, 'Durable market acquisition client is missing')


@unittest.skipUnless(HAS_MODULE, 'Client not implemented yet')
class AcquisitionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = BudgetLedger(self.root / 'budget.sqlite', external_spend='23.14')
        self.wire = Wire()
        self.client = DatabentoClient('secret', self.root / 'receipts', session=self.wire)
        self.payload = {'dataset': 'TEST', 'symbols': ['O', 'PLD'], 'schema': 'mbp-1',
                        'start': '2024-01-02', 'end': '2024-01-03'}
    def tearDown(self):
        self.tmp.cleanup()
    def test_quote_is_bound_to_exact_submit_filters_and_sanitized(self):
        quote = self.client.quote(self.payload)
        self.assertEqual(quote['payload']['symbols'], 'O,PLD')
        self.assertEqual(quote['fingerprint'], fingerprint(quote['payload']))
        cost_call = next(c for c in self.wire.calls if c[1].endswith('metadata.get_cost'))
        self.assertEqual(cost_call[0], 'POST')
        self.assertEqual(cost_call[2]['data']['symbols'], 'O,PLD')
        altered = dict(self.payload, symbols=['O'])
        with self.assertRaises(ValueError):
            self.client.submit('request1', altered, quote, self.ledger)
        self.assertFalse(any(c[1].endswith('batch.submit_job') for c in self.wire.calls))
        job = self.client.submit('request1', self.payload, quote, self.ledger)
        self.assertEqual(job['id'], 'job1')
        self.assertNotIn('api_key', job)
        receipts = ''.join(p.read_text() for p in (self.root / 'receipts').glob('*.json'))
        self.assertNotIn('never-save-me', receipts)
        self.assertNotIn('secret', receipts)
        self.assertEqual(self.ledger.summary()['orders'][0]['status'], 'submitted')
    def test_budget_conflict_prevents_paid_post(self):
        self.ledger.reserve('other', {'dataset': 'OTHER'}, '210')
        quote = self.client.quote(self.payload)
        with self.assertRaises(BudgetExceeded):
            self.client.submit('request1', self.payload, quote, self.ledger)
        self.assertFalse(any(c[1].endswith('batch.submit_job') for c in self.wire.calls))
    def test_ambiguous_post_holds_funds_and_replay_cannot_buy_twice(self):
        self.wire.timeout = True
        quote = self.client.quote(self.payload)
        with self.assertRaises(AmbiguousSubmission):
            self.client.submit('request1', self.payload, quote, self.ledger)
        order = self.ledger.summary()['orders'][0]
        self.assertEqual(order['status'], 'unknown_held')
        self.assertGreater(float(order['reserved_usd']), 10)
        self.wire.timeout = False
        with self.assertRaises(ValueError):
            self.client.submit('request1', self.payload, quote, self.ledger)
        self.assertEqual(len([c for c in self.wire.calls if c[1].endswith('batch.submit_job')]), 1)
    def test_unknown_submission_recovers_only_from_exact_provider_job(self):
        self.wire.timeout = True
        quote = self.client.quote(self.payload)
        with self.assertRaises(AmbiguousSubmission):
            self.client.submit('request1', self.payload, quote, self.ledger)
        original = self.wire.request
        provider_job = {'id': 'job1', 'state': 'done', 'cost_usd': 9,
            'dataset': 'TEST', 'symbols': ['O', 'PLD'], 'schema': 'mbp-1',
            'start': '2024-01-02T00:00:00Z', 'end': '2024-01-03T00:00:00Z',
            'stype_in': 'raw_symbol', 'stype_out': 'instrument_id',
            'encoding': 'csv', 'compression': 'zstd', 'pretty_px': True, 'pretty_ts': True,
            'map_symbols': True, 'split_symbols': False, 'split_duration': 'month', 'delivery': 'download',
            'ts_received': datetime.now(timezone.utc).isoformat()}
        def details(method, url, **kwargs):
            if url.endswith('batch.get_job_details'):
                return Response(provider_job)
            return original(method, url, **kwargs)
        self.wire.request = details
        provider_job['schema'] = 'trades'
        with self.assertRaises(ValueError):
            self.client.reconcile('request1', 'job1', self.ledger)
        self.assertEqual(self.ledger.summary()['orders'][0]['status'], 'unknown_held')
        provider_job['schema'] = 'mbp-1'
        self.client.reconcile('request1', 'job1', self.ledger)
        order = self.ledger.summary()['orders'][0]
        self.assertEqual(order['status'], 'settled')
        self.assertEqual(order['actual_usd'], '9.00')
    def test_reconciliation_requires_exact_exposed_representation(self):
        self.wire.timeout = True
        quote = self.client.quote(self.payload)
        with self.assertRaises(AmbiguousSubmission):
            self.client.submit('request1', self.payload, quote, self.ledger)
        original = self.wire.request
        provider_job = {'id': 'job1', 'state': 'done', 'cost_usd': 9,
            'dataset': 'TEST', 'symbols': ['O', 'PLD'], 'schema': 'mbp-1',
            'start': '2024-01-02T00:00:00Z', 'end': '2024-01-03T00:00:00Z',
            'stype_in': 'raw_symbol', 'stype_out': 'instrument_id',
            'encoding': 'dbn', 'compression': 'zstd', 'pretty_px': True, 'pretty_ts': True,
            'map_symbols': True, 'split_symbols': False, 'split_duration': 'month', 'delivery': 'download',
            'ts_received': datetime.now(timezone.utc).isoformat()}
        def details(method, url, **kwargs):
            if url.endswith('batch.get_job_details'):
                return Response(provider_job)
            return original(method, url, **kwargs)
        self.wire.request = details
        with self.assertRaises(ValueError):
            self.client.reconcile('request1', 'job1', self.ledger)
        self.assertEqual(self.ledger.summary()['orders'][0]['status'], 'unknown_held')
        provider_job['encoding'] = 'csv'
        del provider_job['compression']
        with self.assertRaises(ValueError):
            self.client.reconcile('request1', 'job1', self.ledger)
    def test_new_request_id_cannot_retry_unknown_identical_purchase(self):
        self.wire.timeout = True
        quote = self.client.quote(self.payload)
        with self.assertRaises(AmbiguousSubmission):
            self.client.submit('request1', self.payload, quote, self.ledger)
        self.wire.timeout = False
        with self.assertRaises(ValueError):
            self.client.submit('request2', self.payload, quote, self.ledger)
        self.assertEqual(len([c for c in self.wire.calls if c[1].endswith('batch.submit_job')]), 1)
    def test_bound_job_cannot_be_settled_using_a_different_cheaper_job(self):
        quote = self.client.quote(self.payload)
        self.client.submit('request1', self.payload, quote, self.ledger)
        original = self.wire.request
        wrong_job = {'id': 'job2', 'state': 'done', 'cost_usd': 1,
            'dataset': 'TEST', 'symbols': ['O', 'PLD'], 'schema': 'mbp-1',
            'start': '2024-01-02T00:00:00Z', 'end': '2024-01-03T00:00:00Z',
            'stype_in': 'raw_symbol', 'stype_out': 'instrument_id',
            'ts_received': datetime.now(timezone.utc).isoformat()}
        def details(method, url, **kwargs):
            if url.endswith('batch.get_job_details'):
                return Response(wrong_job)
            return original(method, url, **kwargs)
        self.wire.request = details
        with self.assertRaises(ValueError):
            self.client.reconcile('request1', 'job2', self.ledger)
        order = self.ledger.summary()['orders'][0]
        self.assertEqual(order['job_id'], 'job1')
        self.assertEqual(order['status'], 'submitted')
        self.assertIsNone(order['actual_usd'])
    def test_stale_price_stops_before_reservation(self):
        quote = self.client.quote(self.payload)
        self.wire.cost = 11
        with self.assertRaises(ValueError):
            self.client.submit('request1', self.payload, quote, self.ledger)
        self.assertEqual(self.ledger.summary()['orders'], [])
    def test_external_spend_is_refreshed_after_reserve_before_submission(self):
        legacy = self.root / 'legacy.json'
        legacy.write_text(json.dumps({'purchases': [], 'actual_plus_quoted_usd': '23.14'}))
        client = DatabentoClient('secret', self.root / 'receipts', session=self.wire,
                                 legacy_ledger=legacy)
        quote = client.quote(self.payload)
        reserve = self.ledger.reserve
        def competing_spend(*args, **kwargs):
            result = reserve(*args, **kwargs)
            legacy.write_text(json.dumps({'purchases': [], 'actual_plus_quoted_usd': '246'}))
            return result
        self.ledger.reserve = competing_spend
        with self.assertRaises(BudgetExceeded):
            client.submit('request1', self.payload, quote, self.ledger)
        self.assertFalse(any(c[1].endswith('batch.submit_job') for c in self.wire.calls))
        self.assertEqual(self.ledger.summary()['orders'][0]['status'], 'reserved')
    def test_missing_schema_prevents_quote_and_purchase(self):
        with self.assertRaises(ValueError):
            self.client.quote(dict(self.payload, schema='cbbo-1s'))
        self.assertFalse(any(c[1].endswith('metadata.get_cost') for c in self.wire.calls))
    def test_empty_date_filtered_catalog_does_not_override_explicit_range(self):
        original = self.wire.request
        def catalog(method, url, **kwargs):
            if url.endswith('metadata.list_datasets') and kwargs.get('params', {}).get('start_date'):
                return Response([])
            return original(method, url, **kwargs)
        self.wire.request = catalog
        result = self.client.quote(self.payload)
        self.assertEqual(result['cost_usd'], '10')
    def test_dataset_wide_history_does_not_override_schema_start(self):
        original = self.wire.request
        def schema_range(method, url, **kwargs):
            if url.endswith('metadata.list_schemas'):
                return Response(['cbbo-1s'])
            if url.endswith('metadata.get_dataset_range'):
                return Response({'start': '2013-04-01', 'end': '2026-10-03',
                    'schema': {'cbbo-1s': {'start': '2025-02-20', 'end': '2026-10-03'}}})
            return original(method, url, **kwargs)
        self.wire.request = schema_range
        with self.assertRaises(ValueError):
            self.client.quote(dict(self.payload, schema='cbbo-1s'))
        self.assertFalse(any(c[1].endswith('metadata.get_cost') for c in self.wire.calls))
    def test_missing_schema_bounds_cannot_fall_back_to_dataset_history(self):
        original = self.wire.request
        def schema_range(method, url, **kwargs):
            if url.endswith('metadata.get_dataset_range'):
                return Response({'start': '2013-04-01', 'end': '2026-10-03', 'schema': {}})
            return original(method, url, **kwargs)
        self.wire.request = schema_range
        with self.assertRaises(ValueError):
            self.client.quote(self.payload)
    def test_download_verifies_files_and_writes_manifest(self):
        manifest = self.client.download('job1', self.root / 'raw')
        self.assertTrue(manifest['files'][0]['verified'])
        self.assertEqual((self.root / 'raw' / 'job1' / 'market.csv').read_bytes(), b'market')
        self.assertTrue((self.root / 'raw' / 'job1' / 'download_manifest.json').exists())
        download = next(c for c in self.wire.calls if c[1].startswith('https://api.'))
        self.assertFalse(download[2]['allow_redirects'])
    def test_truncated_or_overlong_download_never_becomes_verified(self):
        original = self.wire.request
        def truncated(method, url, **kwargs):
            result = original(method, url, **kwargs)
            if url.startswith('https://api.'):
                result.content = b'x'
            return result
        self.wire.request = truncated
        with self.assertRaises(ValueError):
            self.client.download('job1', self.root / 'raw')
        self.assertFalse((self.root / 'raw' / 'job1' / 'market.csv').exists())
    def test_malicious_filename_host_hash_and_size_are_rejected(self):
        safe = self.wire.request('GET', 'batch.list_files').json()[0]
        for name in ('../escape', '..\\escape', 'C:escape', 'CON', 'CON .csv', 'COM¹.txt',
                     'market.csv:stream', 'market.csv.', 'download_manifest.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_file(dict(safe, filename=name))
        for item in (dict(safe, urls={'https': 'https://evil.test/data'}),
                     dict(safe, urls={'https': 'https://api.databento.com@evil.test/data'}),
                     dict(safe, hash='sha256:no'), dict(safe, size=-1)):
            with self.assertRaises(ValueError):
                validate_file(item)
    def test_sparse_manifests_cannot_claim_market_readiness(self):
        status = market_readiness({'inputs': {'options': {'record_count': 100, 'files': []}}})
        self.assertFalse(status['strict_arbitrage_ready'])
        self.assertFalse(status['repricing_ready'])
        self.assertTrue(any('equity' in item for item in status['blockers']))
    def test_exchange_only_equity_cannot_be_upgraded_to_consolidated(self):
        inputs = {}
        for role in ('equity', 'options', 'futures'):
            inputs[role] = {'record_count': 10, 'files': [{'verified': True}],
                'coverage': {'start': '2024-01-01', 'end': '2026-01-01'},
                'independent': True, 'quality_audited': True,
                'quote_scope': 'exchange_only', 'bid_ask_size': True,
                'timestamps': True, 'contract_definitions': True}
        status = market_readiness({'inputs': inputs, 'evidence_gates': {}})
        self.assertFalse(status['strict_arbitrage_ready'])
        self.assertIn('equity: consolidated executable quote scope required', status['blockers'])
    def test_strict_proof_does_not_depend_on_predictive_label_readiness(self):
        inputs = {role: {'record_count': 1, 'files': [{'verified': True}],
                  'coverage': {'start': '2024-01-01', 'end': '2026-01-01'},
                  'independent': True, 'quality_audited': True,
                  'quote_scope': 'consolidated_executable', 'bid_ask_size': True,
                  'timestamps': True, 'contract_definitions': True}
                  for role in ('equity', 'options')}
        gates = {name: True for name in ('synchronized_quotes', 'dividends', 'american_exercise',
            'borrow', 'financing', 'margin', 'assignment', 'leg_risk', 'contract_identity',
            'trial_register', 'cost_capital_stress', 'holdout_audit')}
        status = market_readiness({'inputs': inputs, 'evidence_gates': gates})
        self.assertTrue(status['strict_arbitrage_ready'])
        self.assertFalse(status['repricing_ready'])
    def test_known_mini_feed_cannot_be_relabelled_full_consolidated(self):
        inputs = {role: {'dataset': 'EQUS.MINI' if role == 'equity' else 'OPRA.PILLAR',
                  'record_count': 1, 'files': [{'verified': True}],
                  'coverage': {'start': '2024-01-01', 'end': '2026-01-01'},
                  'independent': True, 'quality_audited': True,
                  'quote_scope': 'consolidated_executable', 'bid_ask_size': True,
                  'timestamps': True, 'contract_definitions': True}
                  for role in ('equity', 'options')}
        gates = {name: True for name in ('synchronized_quotes', 'dividends', 'american_exercise',
            'borrow', 'financing', 'margin', 'assignment', 'leg_risk', 'contract_identity',
            'trial_register', 'cost_capital_stress', 'holdout_audit')}
        status = market_readiness({'inputs': inputs, 'evidence_gates': gates})
        self.assertFalse(status['strict_arbitrage_ready'])
        self.assertTrue(any('EQUS.MINI' in blocker for blocker in status['blockers']))


if __name__ == '__main__':
    unittest.main()
