"""Tiny, offline fixtures for portable history preparation and resume."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src import reit_history_remote as remote
from src.reit_acquisition import FetchBroker


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PortableResumeTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)

    def broker_fixture(self):
        root = self.root/'data/raw/reit_broker'
        broker = FetchBroker(root, contact_email='test@example.com', transport=lambda url, headers: {
            'status': 200, 'body': b'official bytes', 'content_type': 'application/json'})
        result = broker.fetch('https://data.sec.gov/submissions/CIK0000000001.json')
        return root, result

    def test_mapping_accepts_windows_project_paths_and_rejects_escapes(self):
        old = r'C:\research\QuantHaxs'
        self.assertEqual(remote.map_project_path(old+r'\data\raw\reit_broker\objects\abc', old, self.root), self.root/'data/raw/reit_broker/objects/abc')
        for path in [r'C:\other\data\raw\x', 'data/raw/../../outside', 'private/secrets', 'https://example.com/x']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                remote.map_project_path(path, old, self.root)

    def test_migration_preserves_receipt_database_and_reuses_bytes(self):
        root, result = self.broker_fixture()
        before = (root/'broker.sqlite').read_bytes()
        manifest = remote.migrate_broker(root, self.root/'run/broker', contact='test@example.com', rate=2)
        reused = FetchBroker(self.root/'run/broker', contact_email='test@example.com', transport=lambda *a: self.fail('redownload')).fetch(result['url'])
        self.assertTrue(reused['cached'])
        self.assertEqual(reused['receipt'], result['receipt'])
        self.assertEqual(manifest['verified_count'], 1)
        self.assertEqual((root/'broker.sqlite').read_bytes(), before)

    def test_missing_objects_unavailable_and_changed_bytes_rejected(self):
        root, result = self.broker_fixture()
        Path(result['path']).unlink()
        manifest = remote.migrate_broker(root, self.root/'run/broker', contact='test@example.com', rate=2)
        self.assertEqual(manifest['unavailable'][0]['sha256'], result['sha256'])
        with closing(sqlite3.connect(self.root/'run/broker/broker.sqlite')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM cache').fetchone()[0], 0)
        Path(result['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash'):
            remote.migrate_broker(root, self.root/'another/broker', contact='test@example.com', rate=2)

    def test_source_database_requires_a_checkpointed_backup(self):
        root, _ = self.broker_fixture()
        wal = root/'broker.sqlite-wal'
        wal.write_bytes(b'pending source changes')
        with self.assertRaisesRegex(ValueError, 'backup'):
            remote.migrate_broker(root, self.root/'run/broker', contact='test@example.com', rate=2)

    def test_separate_backup_database_and_source_block_preserved(self):
        root, result = self.broker_fixture()
        with closing(sqlite3.connect(root/'broker.sqlite')) as db:
            db.execute("UPDATE groups SET blocked='HTTP 429 stop'")
            db.commit()
        snapshot = self.root/'snapshot.sqlite'
        (root/'broker.sqlite').rename(snapshot)
        original = snapshot.read_bytes()
        remote.migrate_broker(root, self.root/'run/broker', contact='test@example.com', rate=2, source_database=snapshot)
        derived = FetchBroker(self.root/'run/broker', contact_email='test@example.com', transport=lambda *a: self.fail('blocked network'))
        self.assertEqual(derived.fetch(result['url'])['receipt'], result['receipt'])
        from src.reit_acquisition import AcquisitionBlocked
        with self.assertRaises(AcquisitionBlocked):
            derived.fetch('https://data.sec.gov/submissions/CIK0000000002.json')
        self.assertEqual(snapshot.read_bytes(), original)

    def test_repeat_migration_preserves_new_cache_receipts_and_http_block(self):
        root, result = self.broker_fixture()
        destination = self.root/'run/broker'
        remote.migrate_broker(root, destination, contact='test@example.com', rate=2)
        from src.reit_acquisition import AcquisitionBlocked
        requests = []
        def transport(url, headers):
            requests.append(url)
            return {'status': 200 if len(requests) == 1 else 403, 'body': b'new official bytes'}
        broker = FetchBroker(destination, contact_email='test@example.com', transport=transport,
                             clock=lambda: 2000000000, sleep=lambda _: None)
        newer = broker.fetch('https://data.sec.gov/submissions/CIK0000000002.json')
        with self.assertRaises(AcquisitionBlocked):
            broker.fetch('https://data.sec.gov/submissions/CIK0000000003.json')
        with closing(sqlite3.connect(destination/'broker.sqlite')) as db:
            before = db.execute('SELECT name,last_start,blocked FROM groups').fetchall()
        receipts = broker.receipts()
        remote.migrate_broker(root, destination, contact='test@example.com', rate=2)
        with closing(sqlite3.connect(destination/'broker.sqlite')) as db:
            self.assertEqual(db.execute('SELECT name,last_start,blocked FROM groups').fetchall(), before)
        self.assertEqual(broker.fetch(newer['url'])['receipt'], newer['receipt'])
        self.assertEqual(broker.receipts(), receipts)
        with self.assertRaises(AcquisitionBlocked):
            broker.fetch('https://data.sec.gov/submissions/CIK0000000004.json')
        self.assertEqual(len(requests), 2)

    def test_metadata_permits_only_explicit_cik_scalar_normalization(self):
        cik = '0000000001'
        raw_data = {'cik': 1, 'filings': {'recent': {}, 'files': []}}
        raw = self.root/'data/raw/reit_broker/objects/official'
        digest = write_json(raw, raw_data)
        retained = dict(raw_data, cik=cik)
        row = {'cik': cik, 'submissions': retained, 'source_url': 'https://data.sec.gov/submissions/CIK'+cik+'.json',
               'source_path': r'C:\old\data\raw\reit_broker\objects\official', 'source_sha256': digest, 'historical_pages': []}
        metadata, _ = remote.prepare_metadata({'metadata': [row]}, [cik], old_root=r'C:\old', new_root=self.root)
        self.assertEqual(metadata[0]['submissions']['cik'], cik)
        retained['unknown_field'] = 'not present in official bytes'
        with self.assertRaisesRegex(ValueError, 'payload'):
            remote.prepare_metadata({'metadata': [row]}, [cik], old_root=r'C:\old', new_root=self.root)

    def frozen_fixture(self):
        ciks = [str(i).zfill(10) for i in range(1, 82)]
        universe, plan = self.root/'universe.json', self.root/'plan.json'
        hashes = {'universe': write_json(universe, {'validated': [{'cik': cik} for cik in ciks]})}
        hashes['plan'] = write_json(plan, {'batches': [{'batch_index': n+1, 'ciks': ciks[n*10:(n+1)*10]} for n in range(9)]})
        return universe, plan, hashes, ciks

    def test_frozen_selection_explicit_81_and_hash_bound(self):
        universe, plan, hashes, ciks = self.frozen_fixture()
        value = remote.frozen_inputs(universe, plan, expected_hashes=hashes)
        self.assertEqual(value['ciks'], ciks)
        self.assertEqual(len(value['batches']), 9)
        self.assertEqual(value['batches'][-1]['ciks'], [ciks[-1]])
        write_json(universe, {'validated': [{'cik': '0000000001'}]})
        with self.assertRaisesRegex(ValueError, 'hash'):
            remote.frozen_inputs(universe, plan, expected_hashes=hashes)

    def test_plan_rejects_overlapping_or_changed_groups(self):
        universe, plan, hashes, _ = self.frozen_fixture()
        value = remote.load_json(plan)
        value['batches'][1]['ciks'][0] = value['batches'][0]['ciks'][0]
        hashes['plan'] = write_json(plan, value)
        with self.assertRaisesRegex(ValueError, 'batch'):
            remote.frozen_inputs(universe, plan, expected_hashes=hashes)

    def test_resume_rejects_configuration_change_and_leaves_old_queues(self):
        old_queue = self.root/'old/document_tasks.sqlite'
        old_queue.parent.mkdir()
        old_queue.write_bytes(b'original queue facts')
        config = {'end_date': '2026-10-03', 'contact': 'test@example.com', 'rate': 2, 'input_hashes': {'universe': 'a'}}
        checkpoint = remote.checkpoint(self.root/'fresh', config)
        self.assertEqual(checkpoint['completed_batches'], [])
        checkpoint['completed_batches'] = [1]
        remote.save_json(self.root/'fresh/checkpoint.json', checkpoint)
        self.assertEqual(remote.checkpoint(self.root/'fresh', config)['completed_batches'], [1])
        with self.assertRaisesRegex(ValueError, 'configuration'):
            remote.checkpoint(self.root/'fresh', dict(config, rate=1))
        self.assertEqual(old_queue.read_bytes(), b'original queue facts')

    def test_metadata_paths_hash_verified_and_missing_pages_pending(self):
        cik = '0000000001'
        data = {'cik': 1, 'filings': {'recent': {'accessionNumber': [], 'filingDate': [], 'form': [], 'primaryDocument': []}, 'files': [{'name': 'CIK'+cik+'-submissions-001.json', 'filingFrom': '2022-01-01', 'filingTo': '2024-01-01'}]}}
        raw = self.root/'data/raw/reit_broker/objects/source'
        digest = write_json(raw, data)
        original = {'metadata': [{'cik': cik, 'submissions': data, 'source_url': 'https://data.sec.gov/submissions/CIK'+cik+'.json', 'source_path': r'C:\old\data\raw\reit_broker\objects\source', 'source_sha256': digest, 'retrieved_at': '2026-10-03T00:00:00Z', 'historical_pages': []}]}
        metadata, status = remote.prepare_metadata(original, [cik], old_root=r'C:\old', new_root=self.root)
        self.assertEqual(metadata[0]['source_path'], str(raw))
        self.assertEqual(status['pending'][0]['name'], 'CIK'+cik+'-submissions-001.json')
        raw.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash'):
            remote.prepare_metadata(original, [cik], old_root=r'C:\old', new_root=self.root)

    def test_missing_pages_fetched_before_history_and_resume_skips_complete(self):
        cik = '0000000001'
        page_name = 'CIK'+cik+'-submissions-001.json'
        arrays = {'accessionNumber': [], 'filingDate': [], 'form': [], 'primaryDocument': []}
        main = {'cik': 1, 'filings': {'recent': arrays, 'files': [{'name': page_name}]}}
        requests = []
        def transport(url, headers):
            requests.append(url)
            return {'status': 200, 'body': json.dumps(main if url.endswith('CIK'+cik+'.json') else arrays).encode()}
        broker = FetchBroker(self.root/'broker', contact_email='test@example.com', transport=transport, sleep=lambda _: None)
        metadata = remote.complete_metadata([], [cik], broker, self.root/'metadata_status.json')
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(metadata[0]['historical_pages']), 1)
        self.assertTrue(remote.load_json(self.root/'metadata_status.json')['metadata_complete'])
        remote.complete_metadata(metadata, [cik], broker, self.root/'metadata_status.json')
        self.assertEqual(len(requests), 2)
        state = remote.checkpoint(self.root/'run', {'max_exhibits': 10000})
        frozen = {'batches': [{'batch_index': 1, 'ciks': [cik]}], 'universe': {'validated': [{'cik': cik}]}}
        calls = []
        def history(rows, universe, output, same_broker, limit, **kwargs):
            self.assertTrue(rows[0]['historical_pages'])
            self.assertIs(same_broker, broker)
            calls.append(kwargs['requested'])
            remote.save_json(output/'collection/manifest.json', {'documents': []})
            manifest = {'selected_collection_complete': True, 'history_complete': False, 'omitted_exhibits': []}
            remote.save_json(output/'batches/synthetic/batch_manifest.json', manifest)
            return manifest
        remote.run_batches(metadata, frozen, self.root/'run', broker, state, history_stage=history, max_exhibits=10000)
        state = remote.checkpoint(self.root/'run', {'max_exhibits': 10000})
        remote.run_batches(metadata, frozen, self.root/'run', broker, state, history_stage=history, max_exhibits=10000)
        self.assertEqual(calls, [[cik]])
        self.assertEqual(state['completed_batches'], [1])

    def test_resume_rejects_vanished_collection_records(self):
        cik = '0000000001'
        arrays = {'accessionNumber': [], 'filingDate': [], 'form': [], 'primaryDocument': []}
        metadata = [{'cik': cik, 'submissions': {'cik': 1, 'filings': {'recent': arrays, 'files': []}}, 'historical_pages': []}]
        state = remote.checkpoint(self.root/'run', {})
        frozen = {'batches': [{'batch_index': 1, 'ciks': [cik]}], 'universe': {'validated': [{'cik': cik}]}}
        def history(rows, universe, output, broker, limit, **kwargs):
            source, text = output/'collection/raw.htm', output/'collection/text.json'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'official tiny filing')
            text.write_bytes(b'{"text":"official tiny filing"}')
            url = 'https://www.sec.gov/Archives/edgar/data/1/000000000124000001/test.htm'
            document = {'url': url, 'cik': cik, 'source_path': str(source), 'text_path': str(text),
                        'sha256': remote.file_hash(source), 'text_sha256': remote.file_hash(text)}
            remote.save_json(output/'collection/manifest.json', {'documents': [document]})
            value = {'selected_collection_complete': True, 'history_complete': False, 'omitted_exhibits': [],
                     'completed_document_urls': [url], 'completed_exhibit_urls': []}
            remote.save_json(output/'batches/synthetic/batch_manifest.json', value)
            return value
        remote.run_batches(metadata, frozen, self.root/'run', None, state, history_stage=history)
        collection = self.root/'run/history/batch-01/collection/manifest.json'
        remote.save_json(collection, {'documents': []})
        with self.assertRaisesRegex(ValueError, 'collection'):
            remote.run_batches(metadata, frozen, self.root/'run', None, state, history_stage=history)
        # Even replacing just the stored file digest cannot erase the pinned identities.
        state['batch_results']['1']['collection_manifest_sha256'] = remote.file_hash(collection)
        with self.assertRaisesRegex(ValueError, 'identity'):
            remote.run_batches(metadata, frozen, self.root/'run', None, state, history_stage=history)

    def test_prepared_resume_rejects_missing_broker_or_migration(self):
        source, _ = self.broker_fixture()
        output = self.root/'run'
        state = remote.checkpoint(output, {})
        migration = remote.migrate_broker(source, output/'broker', contact='test@example.com', rate=2)
        remote.save_json(output/'cache_migration.json', migration)
        state['preparation_status'] = 'prepared'
        state['migration_sha256'] = remote.file_hash(output/'cache_migration.json')
        remote.save_json(output/'checkpoint.json', state)
        (output/'broker/broker.sqlite').unlink()
        with self.assertRaisesRegex(ValueError, 'broker'):
            remote.validate_prepared_resume(output, state)
        (output/'cache_migration.json').unlink()
        with self.assertRaisesRegex(ValueError, 'migration'):
            remote.validate_prepared_resume(output, state)
