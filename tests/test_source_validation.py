"""Source intake gate tests with only synthetic, local inputs."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.source_validation import validate_sources
from scripts.run_document_batch import run_batch
from src.document_evidence import build_evidence


ROOT = Path(__file__).resolve().parents[1]


class SourceValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def source(self, source_id='alpha-source', *, stage='discovery', engine='native',
               records=None, metadata=None):
        folder = self.root / 'configs' / 'sources' / source_id
        folder.mkdir(parents=True)
        settings = dict(schema_version='1.0', source_id=source_id, owner='alice',
                        stage=stage, engine=engine)
        settings.update(metadata or {})
        (folder / 'source.json').write_text(json.dumps(settings), encoding='utf-8')
        (folder / 'README.md').write_text('# Source\nCanonical publisher and acquisition procedure.\n', encoding='utf-8')
        if records is None:
            records = [dict(document_id=f'{source_id}:record-1',
                            source_path=f'../../../data/raw/team_sources/{source_id}/record-1.txt',
                            source_url='https://example.org/record-1.txt')]
        self.write_manifest(folder / 'manifest.jsonl', records)
        return folder

    @staticmethod
    def write_manifest(path, records):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(json.dumps(record) + '\n' for record in records), encoding='utf-8')

    def test_empty_repository_is_valid(self):
        self.assertEqual(validate_sources(self.root),
                         {'ok': True, 'sources': 0, 'documents': 0, 'errors': []})

    def test_discovery_validates_without_downloaded_original(self):
        self.source()
        result = validate_sources(self.root)
        self.assertEqual(result, {'ok': True, 'sources': 1, 'documents': 1, 'errors': []})
        self.assertFalse((self.root / 'data' / 'raw').exists())

    def test_selected_source_still_checks_global_document_uniqueness(self):
        selected = self.source('alpha-source')
        self.source('beta-source', records=[dict(document_id='alpha-source:record-1',
                    source_path='../../../data/raw/team_sources/beta-source/other.txt',
                    source_url='https://example.org/other.txt')])
        result = validate_sources(self.root, selected)
        self.assertFalse(result['ok'])
        self.assertTrue(any('duplicate document_id' in error for error in result['errors']))

    def test_source_metadata_required_and_glm_pinned_to_ignored_cache(self):
        source = self.source(metadata={'owner': '  ', 'schema_version': '2.0',
                                       'source_id': 'Beta_Source'}, engine='glm')
        result = validate_sources(self.root)
        self.assertFalse(result['ok'])
        for part in ('schema_version', 'source_id', 'owner', 'model_revision', 'model_cache'):
            self.assertTrue(any(part in error for error in result['errors']), part)
        (source / 'source.json').write_text(json.dumps(dict(schema_version='1.0',
            source_id='alpha-source', owner='alice', stage='discovery', engine='glm',
            model_revision='pinned-revision', model_cache='data/raw/team_sources/alpha-source/model-cache')),
            encoding='utf-8')
        self.assertTrue(validate_sources(self.root)['ok'])

    def test_manifest_rejects_url_as_path_escape_placeholders_bad_url_and_bad_hash(self):
        cases = [
            ('URL input', 'source_path', 'https://example.org/file.txt', 'source_path'),
            ('raw escape', 'source_path', '../../../data/raw/team_sources/alpha-source/../beta.txt', 'source_path'),
            ('placeholder', 'document_id', 'alpha-source:REPLACE_ID', 'REPLACE_'),
            ('bad URL', 'source_url', 'file:///tmp/file.txt', 'source_url'),
            ('bad hash', 'source_sha256', 'unverified', 'source_sha256'),
            ('naive UTC', 'public_at_utc', '2020-01-01T12:00:00', 'public_at_utc'),
            ('offset clock', 'public_at_utc', '2020-01-01T12:00:00-05:00', 'public_at_utc'),
        ]
        source = self.source()
        original = json.loads((source / 'manifest.jsonl').read_text())
        for name, field, value, expected in cases:
            with self.subTest(name=name):
                self.write_manifest(source / 'manifest.jsonl', [{**original, field: value}])
                errors = validate_sources(self.root)['errors']
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_missing_companion_files_and_malformed_jsonl_fail(self):
        source = self.source()
        (source / 'README.md').unlink()
        (source / 'manifest.jsonl').write_text('{bad json}\n', encoding='utf-8')
        errors = validate_sources(self.root)['errors']
        self.assertTrue(any('README.md' in error for error in errors))
        self.assertTrue(any('manifest.jsonl' in error for error in errors))

    def test_source_metadata_utc_and_readme_placeholder_are_checked(self):
        source = self.source(metadata={'published_at_utc': '2020-01-01T12:00:00'})
        (source / 'README.md').write_text('Get data from REPLACE_URL.', encoding='utf-8')
        errors = validate_sources(self.root)['errors']
        self.assertTrue(any('published_at_utc' in error for error in errors))
        self.assertTrue(any('REPLACE_' in error and 'README.md' in error for error in errors))

    def test_malformed_json_field_types_return_errors_instead_of_crashing(self):
        source = self.source(metadata={'stage': [], 'engine': {}})
        result = validate_sources(self.root)
        self.assertFalse(result['ok'])
        self.assertTrue(any('stage' in error for error in result['errors']))
        self.assertTrue(any('engine' in error for error in result['errors']))

    def test_registry_wrong_type_is_not_treated_as_empty(self):
        registry = self.root / 'configs' / 'sources'
        registry.parent.mkdir()
        registry.write_text('not a directory', encoding='utf-8')
        result = validate_sources(self.root)
        self.assertFalse(result['ok'])
        self.assertTrue(any('configs/sources' in error.replace('\\', '/') for error in result['errors']))

    def test_oversize_metadata_manifest_and_readme_are_rejected(self):
        source = self.source()
        for name in ('source.json', 'manifest.jsonl', 'README.md'):
            with self.subTest(name=name):
                path = source / name
                original = path.read_bytes()
                path.write_bytes(b'x' * 1_100_000)
                try:
                    self.assertTrue(any('size' in error and name in error
                                        for error in validate_sources(self.root)['errors']))
                finally:
                    path.write_bytes(original)

    def test_registry_and_source_folder_symlinks_are_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        registry = self.root / 'configs' / 'sources'
        registry.parent.mkdir()
        try:
            registry.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f'symlinks unavailable: {exc}')
        self.assertTrue(any('symlink' in error for error in validate_sources(self.root)['errors']))
        registry.unlink()
        registry.mkdir()
        self.source('real-source')
        (registry / 'real-source').rename(outside / 'real-source')
        (registry / 'real-source').symlink_to(outside / 'real-source', target_is_directory=True)
        self.assertTrue(any('symlink' in error for error in validate_sources(self.root)['errors']))

    def test_companion_symlink_and_fixture_ancestor_symlink_are_rejected(self):
        source = self.source(stage='extracted')
        fixture = self.root / 'examples' / 'team_sources' / 'alpha-source'
        fixture.mkdir(parents=True)
        sample = fixture / 'sample.txt'
        sample.write_bytes(b'Synthetic result.\n')
        self.write_manifest(fixture / 'manifest.jsonl', [dict(document_id='alpha-source:synthetic-v1',
            source_path='sample.txt', source_sha256=hashlib.sha256(sample.read_bytes()).hexdigest())])
        external = self.root / 'external.txt'
        external.write_text('safe content', encoding='utf-8')
        try:
            (fixture / 'probe').symlink_to(external)
        except OSError as exc:
            self.skipTest(f'symlinks unavailable: {exc}')
        (fixture / 'probe').unlink()
        for companion in ('source.json', 'README.md', 'manifest.jsonl'):
            with self.subTest(companion=companion):
                path = source / companion
                original = path.read_bytes()
                path.unlink()
                external.write_bytes(original)
                path.symlink_to(external)
                try:
                    self.assertTrue(any('symlink' in error and companion in error
                                        for error in validate_sources(self.root)['errors']))
                finally:
                    path.unlink()
                    path.write_bytes(original)
        sample.unlink()
        sample.symlink_to(external)
        self.assertTrue(any('symlink' in error for error in validate_sources(self.root)['errors']))

    def test_extracted_requires_runnable_hashed_utf8_fixture(self):
        self.source(stage='extracted')
        errors = validate_sources(self.root)['errors']
        self.assertTrue(any('team_sources' in error and 'manifest.jsonl' in error for error in errors))
        sample = self.root / 'examples' / 'team_sources' / 'alpha-source' / 'sample.txt'
        sample.parent.mkdir(parents=True)
        sample.write_bytes(b'Revenue did not rise.\n')
        fixture = sample.parent / 'manifest.jsonl'
        self.write_manifest(fixture, [dict(document_id='alpha-source:synthetic-v1',
            source_path='sample.txt', source_sha256=hashlib.sha256(sample.read_bytes()).hexdigest())])
        self.assertTrue(validate_sources(self.root)['ok'])
        sample.write_bytes(b'Changed bytes.\n')
        self.assertTrue(any('source_sha256' in error for error in validate_sources(self.root)['errors']))

    def test_fixture_rejects_missing_hash_and_path_outside_fixture(self):
        self.source(stage='extracted')
        fixture = self.root / 'examples' / 'team_sources' / 'alpha-source' / 'manifest.jsonl'
        self.write_manifest(fixture, [dict(document_id='alpha-source:synthetic-v1',
            source_path='../../../data/raw/team_sources/alpha-source/real.txt')])
        errors = validate_sources(self.root)['errors']
        self.assertTrue(any('source_path' in error for error in errors))
        self.assertTrue(any('source_sha256' in error for error in errors))

    def test_extracted_fixture_must_produce_meaningful_transcript(self):
        self.source(stage='extracted')
        fixture = self.root / 'examples' / 'team_sources' / 'alpha-source' / 'manifest.jsonl'
        sample = fixture.parent / 'empty.html'
        sample.parent.mkdir(parents=True)
        sample.write_bytes(b'<script>only hidden content</script>')
        self.write_manifest(fixture, [dict(document_id='alpha-source:synthetic-v1',
            source_path='empty.html', source_sha256=hashlib.sha256(sample.read_bytes()).hexdigest())])
        self.assertTrue(any('transcript' in error for error in validate_sources(self.root)['errors']))

    def test_cli_prints_machine_json_and_nonzero_on_violation(self):
        command = [sys.executable, str(ROOT / 'scripts' / 'validate_team_sources.py'),
                   '--repo-root', str(self.root)]
        valid = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertEqual(json.loads(valid.stdout)['sources'], 0)
        self.source(metadata={'stage': 'REPLACE_STAGE'})
        invalid = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(invalid.returncode, 1, invalid.stderr)
        self.assertFalse(json.loads(invalid.stdout)['ok'])

    def test_extracted_fixture_runs_batch_and_exact_evidence_resume(self):
        self.source(stage='extracted')
        fixture_dir = self.root / 'examples' / 'team_sources' / 'alpha-source'
        fixture_dir.mkdir(parents=True)
        content = b'Item 2.02 Results\nRevenue did not rise.\n'
        sample = fixture_dir / 'sample.txt'
        sample.write_bytes(content)
        source_hash = hashlib.sha256(content).hexdigest()
        manifest = fixture_dir / 'manifest.jsonl'
        self.write_manifest(manifest, [dict(document_id='alpha-source:synthetic-v1',
            source_path='sample.txt', source_sha256=source_hash)])
        self.assertTrue(validate_sources(self.root)['ok'])
        output = self.root / 'data' / 'processed' / 'team_sources' / 'alpha-source' / 'smoke'
        self.assertEqual(run_batch(manifest, output, {'engine': 'native'})['completed'], 1)
        journal = json.loads((output / 'manifest.jsonl').read_text(encoding='utf-8').splitlines()[0])
        transcript = json.loads(Path(journal['output_path']).read_text(encoding='utf-8'))
        self.assertEqual(journal['source_sha256'], source_hash)
        self.assertEqual(transcript['source_sha256'], source_hash)
        self.assertEqual(transcript['text_sha256'], hashlib.sha256(transcript['normalized_text'].encode()).hexdigest())
        evidence = build_evidence(transcript)
        self.assertIn('Revenue did not rise.', [row['quoted_text'] for row in evidence])
        for row in evidence:
            self.assertEqual(transcript['normalized_text'][row['char_start']:row['char_end']], row['quoted_text'])
            self.assertEqual(row['text_sha256'], transcript['text_sha256'])
        self.assertEqual(run_batch(manifest, output, {'engine': 'native'})['skipped'], 1)


if __name__ == '__main__':
    unittest.main()
