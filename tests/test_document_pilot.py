import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hpc import run_document_pilot as pilot
from scripts.build_hipergator_bundle import build
from hpc.submit_document_job import build_command
from src.glm_document_ocr import VERIFIED_MODEL_REVISION


class DocumentPilotTests(unittest.TestCase):
    def ocr_batch(self, root, text='Net loss was (10).'):
        source = root / 'calibration.png'
        source.write_bytes(b'nonblank calibration image fixture')
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        selected = {'document_id': 'calibration', 'source_path': str(source), 'source_sha256': source_hash}
        manifest = root / 'documents.jsonl'
        manifest.write_text(json.dumps(selected) + '\n')
        directory = root / 'transcripts'
        directory.mkdir()
        artifact = directory / 'calibration.ocr.json'
        artifact.write_text(json.dumps({'sha256': source_hash, 'text': text,
                                        'pages': [{'number': 1, 'text': text}]}))
        row = {'document_id': selected['document_id'], 'source_sha256': source_hash,
               'input_record': selected, 'status': 'completed', 'ocr_path': str(artifact),
               'ocr_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}
        journal = directory / 'manifest.jsonl'
        journal.write_text(json.dumps(row) + '\n')
        return manifest, directory, row, artifact

    def test_ocr_gate_accepts_real_content_inside_markdown_fences(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, directory, _, _ = self.ocr_batch(Path(tmp), '```markdown\nNet loss was (10).\n```')
            result = pilot.validate_ocr_batch(manifest, directory)
            self.assertEqual(result, {'status': 'passed', 'checked_documents': 1})

    def test_ocr_gate_rejects_empty_or_formatting_only_content(self):
        for text in ('', '   ', '```markdown\n\n```', '~~~markdown\n~~~', '```markdown```', '**\n| --- | --- |', '<table><tr><td></td></tr></table>'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                manifest, directory, _, _ = self.ocr_batch(Path(tmp), text)
                with self.assertRaisesRegex(RuntimeError, 'empty|formatting'):
                    pilot.validate_ocr_batch(manifest, directory)

    def test_ocr_gate_rejects_missing_or_failed_selected_rows(self):
        for variant in ('missing', 'failed', 'missing_artifact'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as tmp:
                manifest, directory, row, artifact = self.ocr_batch(Path(tmp))
                if variant == 'missing':
                    (directory / 'manifest.jsonl').write_text('')
                elif variant == 'failed':
                    row['status'] = 'failed'
                    (directory / 'manifest.jsonl').write_text(json.dumps(row) + '\n')
                else:
                    artifact.unlink()
                with self.assertRaises((RuntimeError, ValueError, FileNotFoundError)):
                    pilot.validate_ocr_batch(manifest, directory)

    def test_ocr_gate_checks_file_hash_and_original_source_binding(self):
        for variant in ('artifact_hash', 'journal_source', 'payload_source'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as tmp:
                manifest, directory, row, artifact = self.ocr_batch(Path(tmp))
                if variant == 'artifact_hash':
                    artifact.write_text('{}')
                elif variant == 'journal_source':
                    row['source_sha256'] = '0' * 64
                else:
                    payload = json.loads(artifact.read_text())
                    payload['sha256'] = '0' * 64
                    artifact.write_text(json.dumps(payload))
                    row['ocr_sha256'] = hashlib.sha256(artifact.read_bytes()).hexdigest()
                (directory / 'manifest.jsonl').write_text(json.dumps(row) + '\n')
                with self.assertRaisesRegex(ValueError, 'hash|source'):
                    pilot.validate_ocr_batch(manifest, directory)

    def test_empty_calibration_fails_pilot_but_keeps_finbert_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'submission.txt'
            source.write_bytes(b'source')
            filings = root / 'filings.json'
            filings.write_text(json.dumps([{'cik': '1234', 'accession': 'abc', 'submission_path': str(source),
                                           'source_sha256': hashlib.sha256(b'source').hexdigest()}]))
            manifest = root / 'documents.jsonl'
            manifest.write_text(json.dumps({'document_id': 'calibration', 'source_path': 'image.png'}) + '\n')
            report = root / 'report.json'
            report.write_text(json.dumps({'wording': {'provider_revisions': {'finbert': 'pinned'}},
                                          'inventory': [{'wording_selected': True, 'inventory_status': 'complete'}]}))
            torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True,
                is_bf16_supported=lambda: True, get_device_name=lambda _: 'mock GPU'))
            argv = ['pilot', '--model-cache', str(root / 'cache'), '--output-dir', str(root / 'output'),
                    '--filings', str(filings), '--manifest', str(manifest)]
            with patch.dict('sys.modules', {'torch': torch}), patch.dict('os.environ', {'SLURM_JOB_ID': '123'}), \
                 patch('sys.argv', argv), patch.object(pilot, 'resolve_model_snapshot', return_value='local-model'), \
                 patch.object(pilot, 'filing_ocr_map', return_value={}), \
                 patch.object(pilot, 'validate_ocr_batch', side_effect=RuntimeError('empty formatting-only OCR calibration'), create=True), \
                 patch.object(pilot.subprocess, 'run', side_effect=[SimpleNamespace(stdout='', returncode=0), SimpleNamespace(stdout=str(report), returncode=0)]), \
                 patch('builtins.print'):
                with self.assertRaisesRegex(RuntimeError, 'empty'):
                    pilot.main()
            result = json.loads((root / 'output/pilot-run.json').read_text())
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['reports'], [str(report)])
            self.assertEqual(result['ocr_acceptance']['status'], 'failed')

    def test_offline_pilot_accepts_the_inference_only_snapshot_downloaded_by_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'submission.txt').write_bytes(b'source')
            filings = root / 'filings.json'
            filings.write_text(json.dumps([{'cik': '1234', 'accession': 'abc',
                                           'submission_path': 'submission.txt',
                                           'source_sha256': hashlib.sha256(b'source').hexdigest()}]))
            report = root / 'report.json'
            report.write_text(json.dumps({'wording': {'provider_revisions': {'finbert': 'pinned'}},
                                          'inventory': [{'wording_selected': True, 'inventory_status': 'complete'}]}))
            expected_patterns = ['*.json', '*.safetensors', '*.jinja', '*.txt', '*.model']
            def cached_snapshot(*args, **kwargs):
                if kwargs.get('allow_patterns') != expected_patterns:
                    raise RuntimeError('Incomplete snapshot: unrequested README/legacy weights are absent')
                self.assertTrue(kwargs['local_files_only'])
                return str(root / 'cached-model')
            snapshot = Mock(side_effect=cached_snapshot)
            torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True,
                is_bf16_supported=lambda: True, get_device_name=lambda _: 'mock GPU'))
            argv = ['pilot', '--model-cache', str(root / 'cache'), '--output-dir', str(root / 'output'),
                    '--filings', str(filings), '--manifest', str(root / 'documents.jsonl')]
            with patch.dict('sys.modules', {'torch': torch, 'huggingface_hub': SimpleNamespace(snapshot_download=snapshot)}), \
                 patch.dict('os.environ', {'SLURM_JOB_ID': '123'}), patch('sys.argv', argv), \
                 patch.object(pilot, 'validate_ocr_batch', return_value={'status': 'passed', 'checked_documents': 1}, create=True), \
                 patch.object(pilot.subprocess, 'run', side_effect=[SimpleNamespace(stdout='', returncode=0), SimpleNamespace(stdout=str(report), returncode=0)]), \
                 patch('builtins.print'):
                pilot.main()
            self.assertEqual(json.loads((root / 'output/pilot-run.json').read_text())['status'], 'completed')

    def test_pilot_launcher_preserves_manifest_and_fresh_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / 'documents.jsonl'
            manifest.write_text(json.dumps({'document_id': 'one', 'source_path': 'page.png'}) + '\n')
            filings = root / 'filings.json'
            filings.write_text(json.dumps([{'cik': '1234', 'accession': 'abc',
                                           'submission_path': 'filing.txt', 'source_sha256': 'a' * 64}]))
            output = root / 'new-pilot'
            config = dict(account='ai-workshop', qos='ai-workshop', partition='observed-partition',
                          gres='gpu:1', cpus_per_task=2, memory='16G', time='00:30:00',
                          workdir=str(root), python='/actual/env/bin/python',
                          output_dir=str(output), model_cache='/actual/cache',
                          model_revision=VERIFIED_MODEL_REVISION, environment_script='/actual/activate.sh')
            command = build_command(config, manifest, mode='pilot')
            self.assertEqual(command[-6:], [config['environment_script'], config['python'],
                                           config['model_cache'], str(output), str(manifest), str(filings)])
            self.assertTrue(command[-7].endswith('document_pilot.sbatch'))
            self.assertIn('--output=' + str(root / 'new-pilot-slurm-%j.log'), command)
            with self.assertRaisesRegex(ValueError, 'revision'):
                build_command({**config, 'model_revision': 'a' * 40}, manifest, mode='pilot')
            output.mkdir()
            with self.assertRaisesRegex(ValueError, 'fresh'):
                build_command(config, manifest, mode='pilot')

    def test_completed_gpu_artifact_is_mapped_only_to_its_filing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ocr = root / 'page.ocr.json'
            ocr.write_text('{}')
            row = {'status': 'completed', 'input_record': {
                'cik': '0000001234', 'accession': 'abc', 'filename': 'release.pdf'},
                'ocr_path': str(ocr), 'ocr_sha256': hashlib.sha256(b'{}').hexdigest()}
            (root / 'manifest.jsonl').write_text(json.dumps(row) + '\n')
            self.assertEqual(pilot.filing_ocr_map(root, {'cik': '1234', 'accession': 'abc'}),
                             {'release.pdf': str(ocr.resolve())})
            self.assertEqual(pilot.filing_ocr_map(root, {'cik': '1234', 'accession': 'other'}), {})
            ocr.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'hash'):
                pilot.filing_ocr_map(root, {'cik': '1234', 'accession': 'abc'})

    def test_combined_pilot_rejects_empty_filing_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'filings.json'
            source.write_text('[]')
            with self.assertRaisesRegex(ValueError, 'filing'):
                pilot.read_filings(source)

    def test_provider_presence_does_not_hide_failed_extraction(self):
        report = {'wording': {'provider_revisions': {'finbert': 'pinned'}},
                  'inventory': [{'wording_selected': True, 'inventory_status': 'failed_extraction'}]}
        with self.assertRaisesRegex(RuntimeError, 'extraction'):
            pilot.validate_report(report)

    def test_bundle_resolves_document_paths_relative_to_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'local-source.html').write_bytes(b'<p>real input</p>')
            (root / 'documents.jsonl').write_text(json.dumps({
                'document_id': 'one', 'source_path': 'local-source.html',
                'source_sha256': hashlib.sha256(b'<p>real input</p>').hexdigest()}) + '\n')
            result = build(root / 'bundle.tar.gz', root / 'documents.jsonl')
            self.assertEqual(result['documents'], 1)


if __name__ == '__main__':
    unittest.main()
