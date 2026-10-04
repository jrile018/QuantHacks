from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import analyze_reit_money as analyzer
from tests.test_reit_inline_facts import filing, fact
from tests.test_reit_money_records import document


def fixture(root):
    original = root / 'cache' / 'report.htm'
    original.parent.mkdir()
    raw = filing(fact())
    original.write_bytes(raw)
    metadata = document(raw)
    metadata['source_path'] = str(original)
    text = root / 'text' / 'report.json'
    text.parent.mkdir()
    text.write_text(json.dumps({'sha256': metadata['sha256'], 'source_path': str(original),
                                'source_url': metadata['url'], 'accession': metadata['accession'],
                                'pages': [], 'source_method': 'html_native_text'}))
    metadata['text_path'] = str(text)
    manifest = {'run_status': 'complete', 'companies': [], 'documents': [metadata]}
    (root / 'manifest.json').write_text(json.dumps(manifest))
    return original, text, manifest


class AnalyzerTests(unittest.TestCase):
    def test_offline_analysis_has_exact_outputs_and_reuses_unchanged_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            first = analyzer.analyze_collection(root)
            self.assertEqual(first['run_status'], 'complete')
            self.assertEqual(first['parsed_record_count'], 1)
            out = root / 'money_analysis'
            rows = [json.loads(line) for line in (out / 'money_records.jsonl').read_text().splitlines()]
            self.assertEqual(rows[0]['value'], '1234')
            for filename, digest in first['output_sha256'].items():
                self.assertEqual(sha256((out / filename).read_bytes()).hexdigest(), digest)
            with patch.object(analyzer, 'build_document_records', side_effect=AssertionError('must reuse')):
                second = analyzer.analyze_collection(root)
            self.assertEqual(second['reused_document_count'], 1)

    def test_source_change_and_missing_text_are_partial_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, text, _ = fixture(root)
            analyzer.analyze_collection(root)
            original.write_bytes(b'changed')
            result = analyzer.analyze_collection(root)
            self.assertEqual(result['run_status'], 'partial')
            self.assertEqual(result['parsed_record_count'], 0)
            self.assertIn('hash', result['errors'][0]['message'].lower())
            original.write_bytes(filing(fact()))
            text.unlink()
            result = analyzer.analyze_collection(root)
            self.assertEqual(result['run_status'], 'partial')

    def test_outside_collection_sources_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / 'collection'
            root.mkdir()
            _, _, manifest = fixture(root)
            outside = base / 'external.htm'
            outside.write_bytes(filing(fact()))
            manifest['documents'][0]['source_path'] = str(outside)
            (root / 'manifest.json').write_text(json.dumps(manifest))
            result = analyzer.analyze_collection(root)
            self.assertEqual(result['run_status'], 'partial')
            self.assertIn('outside', result['errors'][0]['message'].lower())

    def test_text_provenance_mismatch_cannot_reuse_cached_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, text, _ = fixture(root)
            analyzer.analyze_collection(root)
            payload = json.loads(text.read_text())
            payload['source_url'] = 'https://example.test/wrong'
            text.write_text(json.dumps(payload))
            result = analyzer.analyze_collection(root)
            self.assertEqual(result['run_status'], 'partial')
            self.assertEqual(result['reused_document_count'], 0)

    def test_changed_settings_and_corrupt_cache_force_reanalysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            analyzer.analyze_collection(root)
            changed = analyzer.analyze_collection(root, max_candidates_per_document=2)
            self.assertEqual(changed['reused_document_count'], 0)
            cache = next((root / 'money_analysis' / 'cache').glob('*.json'))
            payload = json.loads(cache.read_text())
            payload['result']['records'][0]['value'] = '999'
            cache.write_text(json.dumps(payload))
            repeated = analyzer.analyze_collection(root, max_candidates_per_document=2)
            self.assertEqual(repeated['reused_document_count'], 0)

    def test_pdf_rule_source_change_invalidates_analysis_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            rule_source = root / 'pdf_rule.py'
            rule_source.write_text('revision = 1\n')
            with patch.object(analyzer.reit_pdf_money, '__file__', str(rule_source)):
                analyzer.analyze_collection(root)
                unchanged = analyzer.analyze_collection(root)
                self.assertEqual(unchanged['reused_document_count'], 1)
                rule_source.write_text('revision = 2\n')
                changed = analyzer.analyze_collection(root)
                self.assertEqual(changed['reused_document_count'], 0)
                self.assertEqual(changed['parsed_record_count'], 1)

    def test_companyfacts_are_verified_and_exported_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, manifest = fixture(root)
            cik, accn = manifest['documents'][0]['cik'], manifest['documents'][0]['accession']
            data = {'cik': int(cik), 'facts': {'us-gaap': {'ProceedsFromBorrowings': {'units': {'USD': [
                {'val': 1234, 'accn': accn, 'start': '2026-01-01', 'end': '2026-06-30', 'form': '10-Q'}
            ]}}}}}
            path = root / 'cache' / cik / 'companyfacts.json'
            path.parent.mkdir()
            path.write_text(json.dumps(data))
            manifest['companies'] = [{'cik': cik, 'coverage': {'companyfacts': 'available', 'companyfacts_sha256': sha256(path.read_bytes()).hexdigest()}}]
            (root / 'manifest.json').write_text(json.dumps(manifest))
            result = analyzer.analyze_collection(root)
            self.assertEqual(result['comparison_fact_count'], 1)
            self.assertEqual(result['parsed_record_count'], 1)
            rows = [json.loads(line) for line in (root / 'money_analysis' / 'comparison_facts.jsonl').read_text().splitlines()]
            self.assertEqual(rows[0]['source_kind'], 'companyfacts_comparison')
            path.write_text('{}')
            repeated = analyzer.analyze_collection(root)
            self.assertEqual(repeated['comparison_fact_count'], 0)
            self.assertEqual(repeated['run_status'], 'partial')

    def test_no_documents_and_incomplete_collection_do_not_claim_full_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'manifest.json').write_text(json.dumps({'run_status': 'blocked', 'documents': [], 'companies': []}))
            result = analyzer.analyze_collection(root)
            self.assertEqual(result['run_status'], 'partial')
            self.assertTrue(result['coverage_warnings'])

    def test_manifest_hash_identifies_the_snapshot_actually_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            original_manifest = (root / 'manifest.json').read_bytes()
            real_build = analyzer.build_document_records
            def replace_manifest(*args, **kwargs):
                (root / 'manifest.json').write_text('{"documents": [], "run_status": "blocked"}')
                return real_build(*args, **kwargs)
            with patch.object(analyzer, 'build_document_records', side_effect=replace_manifest):
                result = analyzer.analyze_collection(root)
            self.assertEqual(result['collection_manifest_sha256'], sha256(original_manifest).hexdigest())

    def test_deep_xml_produces_partial_outputs_instead_of_aborting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, text, manifest = fixture(root)
            raw = filing(fact('<b>' * 1100 + '1' + '</b>' * 1100))
            original.write_bytes(raw)
            manifest['documents'][0]['sha256'] = sha256(raw).hexdigest()
            payload = json.loads(text.read_text())
            payload['sha256'] = manifest['documents'][0]['sha256']
            text.write_text(json.dumps(payload))
            (root / 'manifest.json').write_text(json.dumps(manifest))
            result = analyzer.analyze_collection(root)
            self.assertEqual(result['run_status'], 'partial')
            self.assertIn('xml_depth_limit', result['documents'][0]['coverage']['issues'])
            self.assertTrue((root / 'money_analysis' / 'analysis_manifest.json').is_file())

    def test_cached_text_quote_identifies_its_own_artifact_hash_and_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, text, _ = fixture(root)
            payload = json.loads(text.read_text())
            payload['pages'] = [{'number': 1, 'text': 'Loan capacity is $100 million; this does not establish a draw.'}]
            text.write_text(json.dumps(payload))
            analyzer.analyze_collection(root)
            candidate = json.loads((root / 'money_analysis' / 'review_candidates.jsonl').read_text().splitlines()[0])
            evidence = candidate['evidence'][0]
            self.assertEqual(Path(evidence['text_artifact_path']), text)
            self.assertEqual(evidence['text_artifact_sha256'], sha256(text.read_bytes()).hexdigest())

    def test_relocated_text_artifact_invalidates_cached_evidence_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, text, manifest = fixture(root)
            payload = json.loads(text.read_text())
            payload['pages'] = [{'number': 1, 'text': 'Loan capacity is $100 million.'}]
            text.write_text(json.dumps(payload))
            analyzer.analyze_collection(root)
            moved = text.with_name('moved.json')
            text.rename(moved)
            manifest['documents'][0]['text_path'] = str(moved)
            (root / 'manifest.json').write_text(json.dumps(manifest))
            result = analyzer.analyze_collection(root)
            self.assertEqual(result['reused_document_count'], 0)
            candidate = json.loads((root / 'money_analysis' / 'review_candidates.jsonl').read_text().splitlines()[0])
            self.assertEqual(Path(candidate['evidence'][0]['text_artifact_path']), moved)


if __name__ == '__main__':
    unittest.main()
