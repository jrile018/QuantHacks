from hashlib import sha256
from contextlib import redirect_stdout
import io
import json
import os
import shutil
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from src import reit_dataset as dataset


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        raw = self.root / 'source.html'
        raw.write_text('retained financial evidence', encoding='utf-8')
        digest = sha256(raw.read_bytes()).hexdigest()
        text = self.root / 'text.json'
        self.url = 'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/report.htm'
        text.write_text(json.dumps({'sha256': digest, 'source_url': self.url,
                                   'accession': '0000000001-26-000001', 'pages': [{'number': 1, 'text': 'retained'}]}))
        self.doc = {'document_id': 'doc1', 'source_path': str(raw), 'sha256': digest,
                    'text_path': str(text), 'url': self.url, 'accession': '0000000001-26-000001'}
        self.inputs = {'universe': {'issuers': [{'issuer_id': 'cik:0000000001', 'cik': '0000000001'}], 'securities': []},
                       'inventory': {'selected': [], 'documents': []},
                       'quality': {'sources': [{'eligibility': 'needs_review', 'quality_axes': {'point_in_time': {'state': 'needs_review'}}}]},
                       'histories': {'financial_history': [{'record_id': 'f1', 'issuer_cik': '0000000001', 'effective_at': '2024-01-01', 'value': '42', 'unit': 'USD', 'evidence': [{'document_id': 'doc1'}]}], 'review': []},
                       'network': {'entities': [], 'instruments': [], 'role_edges': [], 'intersections': [], 'review': []},
                       'documents': [self.doc], 'provenance': {'scope': 'fixture'}}

    def publish(self):
        return dataset.publish_snapshot(self.root / 'snapshots', **self.inputs)

    def test_publication_and_verified_idempotent_reuse_preserve_rows(self):
        result = self.publish()
        directory = Path(result['snapshot_dir'])
        manifest_bytes = (directory / 'manifest.json').read_bytes()
        again = self.publish()
        self.assertEqual(again['fingerprint'], result['fingerprint'])
        self.assertEqual(manifest_bytes, (directory / 'manifest.json').read_bytes())
        self.assertTrue(dataset.verify_snapshot(directory)['valid'])
        connection = sqlite3.connect(directory / 'dataset.sqlite')
        self.addCleanup(connection.close)
        row = json.loads(connection.execute('SELECT row_json FROM financial_histories').fetchone()[0])
        self.assertEqual(row, self.inputs['histories']['financial_history'][0])
        self.assertFalse(result['historical_ready'])
        self.assertFalse(result['trading_ready'])

    def test_original_source_mutation_invalidates_reopen_and_reuse(self):
        result = self.publish()
        Path(self.doc['source_path']).write_text('changed')
        self.assertFalse(dataset.verify_snapshot(result['snapshot_dir'])['valid'])
        with self.assertRaises(ValueError):
            self.publish()

    def test_extracted_text_identity_mismatch_rejects_publication(self):
        path = Path(self.doc['text_path'])
        value = json.loads(path.read_text())
        value['source_url'] = self.url + '.wrong'
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.publish()

    def test_export_mutation_invalidates_snapshot(self):
        result = self.publish()
        (Path(result['snapshot_dir']) / 'financial_histories.jsonl').write_text('{}\n')
        self.assertFalse(dataset.verify_snapshot(result['snapshot_dir'])['valid'])

    def test_publication_crash_never_exposes_committed_snapshot(self):
        with patch.object(dataset, '_write_manifest', side_effect=OSError('crash')):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(list((self.root / 'snapshots').glob('snapshot-*')), [])

    def test_query_filters_are_parameterized_and_read_only(self):
        from scripts.query_reit_dataset import query_snapshot
        result = self.publish()
        self.assertEqual(len(query_snapshot(result['snapshot_dir'], issuer_cik='1')), 1)
        self.assertEqual(query_snapshot(result['snapshot_dir'], evidence='doc1', date='2024-01-01')[0]['value'], '42')
        with self.assertRaises(ValueError):
            query_snapshot(result['snapshot_dir'], issuer_cik="1' OR 1=1 --")
        with self.assertRaises(ValueError):
            query_snapshot(result['snapshot_dir'], table='financial_histories; DROP TABLE entities')

    def test_malformed_input_is_explicit_error(self):
        self.inputs['network']['role_edges'] = 'bad'
        with self.assertRaises(ValueError):
            self.publish()

    def test_relative_source_references_reopen_from_another_directory(self):
        original = Path.cwd()
        try:
            os.chdir(self.root)
            self.doc['source_path'] = 'source.html'
            self.doc['text_path'] = 'text.json'
            result = self.publish()
            os.chdir(original)
            self.assertTrue(dataset.verify_snapshot(result['snapshot_dir'])['valid'])
        finally:
            os.chdir(original)

    def test_network_financial_history_is_preserved_without_summing(self):
        self.inputs['network']['financial_history'] = [{'record_id': 'capacity1', 'value': '42', 'aggregate_granularity': 'facility'}]
        result = self.publish()
        path = Path(result['snapshot_dir']) / 'instrument_financial_histories.jsonl'
        self.assertTrue(path.exists())
        self.assertEqual(json.loads(path.read_text()), self.inputs['network']['financial_history'][0])

    def test_collector_text_digest_rejects_changed_content_before_publication(self):
        text=Path(self.doc['text_path'])
        self.doc['text_sha256']=sha256(text.read_bytes()).hexdigest()
        value=json.loads(text.read_text())
        value['pages'][0]['text']='changed financial meaning'
        text.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            self.publish()

    def test_company_entities_are_independently_queryable(self):
        self.inputs['network']['company_entities']=[{'entity_id':'cik:0000000001','cik':'0000000001','name':'Example'}]
        result=self.publish()
        path=Path(result['snapshot_dir'])/'company_entities.jsonl'
        self.assertTrue(path.exists())
        self.assertEqual(json.loads(path.read_text()),self.inputs['network']['company_entities'][0])

    def test_missing_original_extraction_digest_is_an_explicit_gap(self):
        result=self.publish()
        text_lineage=[row for row in result['lineage'] if row['text_path']]
        self.assertTrue(text_lineage)
        self.assertFalse(text_lineage[0]['text_verified'])
        self.assertTrue(any(gap['kind']=='extracted_digest_unanchored' for gap in result['gaps']))

    def test_contradictory_extraction_hash_alias_is_rejected(self):
        self.doc['extracted_text_sha256']=sha256(Path(self.doc['text_path']).read_bytes()).hexdigest()
        self.doc['text_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            self.publish()

    def test_extracted_source_path_mismatch_is_rejected(self):
        path = Path(self.doc['text_path'])
        value = json.loads(path.read_text())
        value['source_path'] = str(self.root / 'another.html')
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'path identity'):
            self.publish()

    def test_quality_review_and_pit_are_not_promoted(self):
        result = self.publish()
        rows = (Path(result['snapshot_dir']) / 'sources.jsonl').read_text()
        self.assertEqual(json.loads(rows), self.inputs['quality']['sources'][0])
        self.assertFalse(result['pipeline_complete'])

    def test_original_extracted_json_mutation_invalidates_reopen(self):
        result = self.publish()
        path = Path(self.doc['text_path'])
        value = json.loads(path.read_text())
        value['pages'][0]['text'] = 'different extraction'
        path.write_text(json.dumps(value))
        self.assertFalse(dataset.verify_snapshot(result['snapshot_dir'])['valid'])

    def test_project_relative_snapshot_is_identical_after_relocation(self):
        from scripts.query_reit_dataset import query_snapshot
        relocation = tempfile.TemporaryDirectory()
        self.addCleanup(relocation.cleanup)
        relocated = Path(relocation.name)
        for field in ('source_path', 'text_path'):
            shutil.copyfile(self.doc[field], relocated / Path(self.doc[field]).name)
        self.doc['text_sha256'] = sha256(Path(self.doc['text_path']).read_bytes()).hexdigest()
        self.inputs['quality']['sources'][0]['evidence'] = [dict(self.doc)]
        self.inputs['network']['company_entities'] = [{'entity_id': 'cik:0000000001'}]
        first = dataset.publish_snapshot(self.root / 'snapshots', source_root=self.root, **self.inputs)
        local_inputs = json.loads(json.dumps(self.inputs))
        for doc in (local_inputs['documents'][0], local_inputs['quality']['sources'][0]['evidence'][0]):
            doc['source_path'] = str(relocated / 'source.html')
            doc['text_path'] = str(relocated / 'text.json')
        second = dataset.publish_snapshot(relocated / 'snapshots', source_root=relocated, **local_inputs)
        self.assertEqual(first['fingerprint'], second['fingerprint'])
        self.assertEqual(first['reference_mode'], 'project_relative')
        first_dir, second_dir = Path(first['snapshot_dir']), Path(second['snapshot_dir'])
        self.assertEqual({p.name: p.read_bytes() for p in first_dir.iterdir()},
                         {p.name: p.read_bytes() for p in second_dir.iterdir()})
        self.assertNotIn(str(self.root), (first_dir / 'manifest.json').read_text())
        for directory, source_root in ((first_dir, self.root), (second_dir, relocated), (first_dir, relocated)):
            self.assertTrue(dataset.verify_snapshot(directory, source_root=source_root)['valid'])
            self.assertEqual(len(query_snapshot(directory, source_root=source_root)), 1)
        self.assertEqual(json.loads((first_dir / 'documents.jsonl').read_text())['source_path'], 'source.html')
        self.assertEqual(json.loads((first_dir / 'sources.jsonl').read_text())['evidence'][0]['text_path'], 'text.json')
        (relocated / 'source.html').write_text('changed')
        self.assertFalse(dataset.verify_snapshot(first_dir, source_root=relocated)['valid'])

    def test_portable_query_cli_and_default_verifier_root(self):
        from scripts.query_reit_dataset import main
        result = dataset.publish_snapshot(self.root / 'snapshots', source_root=self.root, **self.inputs)
        with patch.object(dataset, 'PROJECT_ROOT', self.root):
            self.assertTrue(dataset.verify_snapshot(result['snapshot_dir'])['valid'])
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([result['snapshot_dir'], '--source-root', str(self.root), '--issuer-cik', '1']), 0)
        self.assertEqual(json.loads(output.getvalue())['record_id'], 'f1')

    def test_portable_inputs_use_platform_independent_newlines(self):
        result = dataset.publish_snapshot(self.root / 'snapshots', source_root=self.root, **self.inputs)
        self.assertNotIn(b'\r\n', (Path(result['snapshot_dir']) / 'inputs.json').read_bytes())

    def test_each_extraction_hash_alias_is_checked(self):
        fields = ('extracted_text_sha256', 'text_artifact_sha256', 'text_sha256')
        digest = sha256(Path(self.doc['text_path']).read_bytes()).hexdigest()
        for contradictory in fields:
            with self.subTest(contradictory=contradictory):
                for field in fields:
                    self.doc[field] = 'f' * 64 if field == contradictory else digest
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    self.publish()

    def test_duplicate_source_reference_cannot_hide_extraction_digest_conflict(self):
        self.doc['text_sha256'] = sha256(Path(self.doc['text_path']).read_bytes()).hexdigest()
        conflicting = dict(self.doc, extracted_text_sha256='f' * 64)
        self.inputs['quality']['sources'][0]['evidence'] = [conflicting]
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.publish()

    def test_duplicate_source_reference_preserves_originally_unanchored_gap(self):
        self.doc['text_sha256'] = sha256(Path(self.doc['text_path']).read_bytes()).hexdigest()
        self.inputs['quality']['sources'][0]['evidence'] = [dict(self.doc, original_extraction_digest_unanchored=True)]
        result = self.publish()
        self.assertTrue(any(gap['kind'] == 'extracted_digest_unanchored' for gap in result['gaps']))
        self.assertTrue(any(row['text_path'] and not row['text_verified'] for row in result['lineage']))

    def test_project_relative_extraction_path_identity_resolves_against_source_root(self):
        text = Path(self.doc['text_path'])
        value = json.loads(text.read_text())
        value['source_path'] = 'source.html'
        text.write_text(json.dumps(value))
        self.doc['source_path'] = 'source.html'
        self.doc['text_path'] = 'text.json'
        result = dataset.publish_snapshot(self.root / 'snapshots', source_root=self.root, **self.inputs)
        self.assertTrue(dataset.verify_snapshot(result['snapshot_dir'], source_root=self.root)['valid'])

    def test_portable_publication_rejects_embedded_absolute_extraction_path(self):
        text = Path(self.doc['text_path'])
        value = json.loads(text.read_text())
        value['source_path'] = self.doc['source_path']
        text.write_text(json.dumps(value))
        original_bytes = text.read_bytes()
        self.doc['text_sha256'] = sha256(original_bytes).hexdigest()
        with self.assertRaisesRegex(ValueError, 'project-relative source_path'):
            dataset.publish_snapshot(self.root / 'snapshots', source_root=self.root, **self.inputs)
        self.assertEqual(text.read_bytes(), original_bytes)
        absolute_snapshot = self.publish()
        self.assertTrue(dataset.verify_snapshot(absolute_snapshot['snapshot_dir'])['valid'])

    def test_project_relative_paths_reject_escape_and_external_paths(self):
        for field in ('source_path', 'text_path', 'text_artifact_path'):
            for value in ('../outside.html', str(self.root.parent / 'outside.html'), 'C:\\outside\\source.html'):
                with self.subTest(field=field, value=value):
                    inputs = json.loads(json.dumps(self.inputs))
                    inputs['documents'][0][field] = value
                    with self.assertRaisesRegex(ValueError, 'outside source root|unsafe source reference'):
                        dataset.publish_snapshot(self.root / 'snapshots', source_root=self.root, **inputs)

    def test_project_relative_symlink_escape_invalidates_reopen(self):
        result = dataset.publish_snapshot(self.root / 'snapshots', source_root=self.root, **self.inputs)
        outside = self.root.parent / (self.root.name + '-outside.html')
        outside.write_bytes(Path(self.doc['source_path']).read_bytes())
        self.addCleanup(outside.unlink)
        raw = Path(self.doc['source_path'])
        raw.unlink()
        try:
            raw.symlink_to(outside)
        except OSError as exc:
            self.skipTest('symlinks unavailable: ' + str(exc))
        checked = dataset.verify_snapshot(result['snapshot_dir'], source_root=self.root)
        self.assertFalse(checked['valid'])
        self.assertTrue(any('outside source root' in error for error in checked['errors']))

    def test_declared_but_originally_unanchored_extraction_remains_gap(self):
        self.doc['text_sha256'] = sha256(Path(self.doc['text_path']).read_bytes()).hexdigest()
        self.doc['original_extraction_digest_unanchored'] = True
        result = self.publish()
        self.assertFalse(next(row for row in result['lineage'] if row['text_path'])['text_verified'])
        self.assertTrue(any(gap['kind'] == 'extracted_digest_unanchored' for gap in result['gaps']))


if __name__ == '__main__':
    unittest.main()
