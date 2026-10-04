import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_offline_complete_submission_exhibit_evidence_and_no_forecast(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            submission = root / 'submission.txt'
            submission.write_text('<DOCUMENT>\n<TYPE>8-K\n<FILENAME>main.htm\n<TEXT><p>Item 2.02 Results of Operations.</p><p>See Exhibit 99.1.</p></TEXT>\n</DOCUMENT>\n<DOCUMENT>\n<TYPE>EX-99.1\n<FILENAME>release.htm\n<TEXT><p>Quarterly earnings results</p><p>Revenue fell. Net loss was $2.3 million.</p></TEXT>\n</DOCUMENT>', encoding='utf-8')
            with submission.open('a', encoding='utf-8') as handle:
                handle.write('\n<DOCUMENT>\n<TYPE>JS\n<FILENAME>Show.js\n<TEXT>bad terrible loss fake viewer content</TEXT>\n</DOCUMENT>')
            command = [sys.executable, str(ROOT / 'scripts/analyze_8k_documents.py'), '--cik', '1234',
                       '--accession', '0000001234-24-000001', '--submission', str(submission),
                       '--output-dir', str(root / 'out'), '--raw-dir', str(root / 'raw')]
            result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(Path(result.stdout.strip()).read_text())
            self.assertEqual(report['family_status'], 'in_first_family')
            self.assertEqual(len(report['inventory']), 3)
            self.assertEqual(len(report['transcripts']), 2)
            self.assertFalse(any('fake viewer' in e['quoted_text'] for e in report['evidence']))
            self.assertTrue(any('Net loss was $2.3 million.' == e['quoted_text'] for e in report['evidence']))
            self.assertIsNone(report['options']['forecast'])
            self.assertIn('option_quotes_missing', report['options']['reason_codes'])
            self.assertEqual(report['wording']['status'], 'providers_unavailable')
            for ev in report['evidence']:
                t = next(t for t in report['transcripts'] if t['document_id'] == ev['document_id'])
                self.assertEqual(t['normalized_text'][ev['char_start']:ev['char_end']], ev['quoted_text'])
            result = subprocess.run(command + ['--mode', 'anticipation', '--target-accession',
                                               '0000001234-24-000001', '--decision', '2024-02-01T12:00:00Z'],
                                    cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            anticipation = json.loads(Path(result.stdout.strip()).read_text())
            self.assertEqual(anticipation['wording']['evidence_assessments'], [])
            self.assertIn('target_filing_leakage', anticipation['options']['reason_codes'])
            self.assertFalse(anticipation['feature_export_eligible'])


if __name__ == '__main__':
    unittest.main()
