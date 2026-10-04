import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.document_transcript import extract_path, normalize_ocr


class TranscriptTests(unittest.TestCase):
    def test_backend_truncation_flags_survive_normalization(self):
        record = normalize_ocr({'engine': 'glm_ocr', 'pages': [{'number': 1, 'text': 'Partial statement',
                                  'quality_flags': ['generation_token_limit_reached', 'machine_unreviewed']}]}, 'doc')
        self.assertIn('generation_token_limit_reached', record['page_records'][0]['quality_flags'])
        self.assertIn('generation_token_limit_reached', record['quality_flags'])
        self.assertIn('incomplete_text', record['quality_flags'])

    def test_html_preserves_financial_text_and_table_spans(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.html'
            path.write_text('<script>bad</script><style>bad</style><p>Item 2.02 Results</p><p>We did not lose &minus;3.25 million.</p><table><tr><th>USD millions</th><th>2026</th></tr><tr><td>Net income</td><td>-3.25</td></tr></table>', encoding='utf-8')
            record = extract_path(path, 'doc')
        text = record['normalized_text']
        self.assertNotIn('bad', text)
        self.assertIn('not lose −3.25', text)
        self.assertIn('Net income\t-3.25', text)
        self.assertIn('unresolved_table_structure', record['quality_flags'])
        for row in record['table_records']:
            self.assertEqual(text[row['char_start']:row['char_end']], row['quoted_text'])
        self.assertEqual(record['text_sha256'], hashlib.sha256(text.encode()).hexdigest())
        self.assertIsNone(record['page_records'][0]['page_number'])

    def test_ocr_keeps_page_order_and_confidence(self):
        payload = {'sha256': 'a' * 64, 'engine': 'glm-ocr', 'engine_version': 'pinned', 'text': 'A\n\f\nB', 'pages': [{'number': 1, 'text': 'A', 'confidence': None}, {'number': 2, 'text': 'B', 'confidence': .8}]}
        record = normalize_ocr(payload, 'doc')
        self.assertEqual(record['source_sha256'], 'a' * 64)
        self.assertEqual(record['normalized_text'], payload['text'])
        for page in record['page_records']:
            self.assertEqual(record['normalized_text'][page['char_start']:page['char_end']], page['text'])
        self.assertIsNone(record['page_records'][0]['confidence'])
        self.assertIn('unverified_reading_order', record['quality_flags'])

    def test_mismatched_source_hash_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.txt'
            path.write_text('Results')
            with self.assertRaises(ValueError):
                extract_path(path, 'doc', 'a' * 64)

    def test_empty_and_malformed_ocr_are_flagged(self):
        self.assertIn('incomplete_text', normalize_ocr({'pages': []}, 'doc')['quality_flags'])
        self.assertIn('malformed_text', normalize_ocr({'pages': [{'number': 1, 'text': None}]}, 'doc')['quality_flags'])

    def test_json_preserves_original_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ocr.json'
            path.write_text(json.dumps({'sha256': 'b' * 64, 'pages': [{'number': 1, 'text': 'Results'}]}))
            self.assertEqual(extract_path(path, 'doc')['source_sha256'], 'b' * 64)

    def test_plain_table_keeps_row_context_without_inferred_concepts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.txt'
            path.write_text('USD millions\t2026\t2025\nNet income\t-2.50\t3.25\n')
            record = extract_path(path, 'doc')
        self.assertEqual(len(record['table_records']), 2)
        self.assertIn('unresolved_table_structure', record['quality_flags'])
        for row in record['table_records']:
            self.assertEqual(record['normalized_text'][row['char_start']:row['char_end']], row['quoted_text'])
            self.assertEqual(row['structure_status'], 'unresolved')

    def test_normalizer_verifies_actual_declared_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scan.png'
            path.write_bytes(b'original scan bytes')
            with self.assertRaises(ValueError):
                normalize_ocr({'source_path': str(path), 'sha256': 'a' * 64, 'text': 'Results'}, 'doc')

    def test_native_pdf_page_provenance_is_preserved(self):
        record = normalize_ocr({'engine': 'pdfium', 'pages': [{'number': 1, 'text': 'Results', 'method': 'pdf_native', 'confidence': None}]}, 'doc')
        self.assertEqual(record['extraction_method'], 'native_pdf')
        self.assertEqual(record['page_records'][0]['method'], 'pdf_native')

    def test_html_inline_tag_spacing_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.html'
            path.write_text('<p><b>Revenue</b> <i>rose</i>.</p>')
            self.assertIn('Revenue rose.', extract_path(path, 'doc')['normalized_text'])
