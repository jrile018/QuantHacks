from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_reit_filing_pilot as pilot


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.gold = {
            'id': 'revolver_capacity', 'page': 85, 'label': 'credit facilities',
            'amount_text': '$4.0 billion', 'value_usd': '4000000000',
            'amount_kind': 'capacity', 'amount_basis': 'facility_commitment',
            'relationship': 'borrower', 'period': '2025-12-31',
            'source_url': 'https://example.test/report.pdf',
        }

    def test_review_candidate_requires_correct_page_label_and_amount(self):
        good = {'source_url': self.gold['source_url'], 'evidence': [{
            'page_number': 85, 'quoted_text': 'New $4.0 billion unsecured credit facilities'}]}
        wrong_page = {'source_url': self.gold['source_url'], 'evidence': [{
            'page_number': 84, 'quoted_text': 'New $4.0 billion unsecured credit facilities'}]}
        wrong_label = {'source_url': self.gold['source_url'], 'evidence': [{
            'page_number': 85, 'quoted_text': '$4.0 billion in property acquisitions'}]}
        scored = pilot.score_assertions([self.gold], [], [wrong_page, wrong_label, good])
        self.assertEqual(scored['results'][0]['outcome'], 'review_candidate')
        self.assertEqual(scored['summary']['review_candidate'], 1)

    def test_capacity_called_cash_flow_is_misclassified(self):
        evidence = [{'page_number': 85, 'quoted_text': 'New $4.0 billion credit facilities'}]
        wrong = {'source_url': self.gold['source_url'], 'value': '4000000000',
                 'amount_kind': 'flow', 'amount_basis': 'reported_cash_movement',
                 'relationship': 'borrower', 'status': 'parsed', 'evidence': evidence,
                 'currency': 'USD', 'as_of_date': '2025-12-31'}
        scored = pilot.score_assertions([self.gold], [wrong], [])
        self.assertEqual(scored['results'][0]['outcome'], 'misclassified')
        right = {**wrong, 'amount_kind': 'capacity', 'amount_basis': 'facility_commitment'}
        scored = pilot.score_assertions([self.gold], [right], [])
        self.assertEqual(scored['results'][0]['outcome'], 'classified_correctly')

    def test_wrong_value_currency_or_period_is_not_correct(self):
        evidence = [{'page_number': 85, 'quoted_text': 'New $4.0 billion credit facilities'}]
        right = {'source_url': self.gold['source_url'], 'value': '4000000000',
                 'amount_kind': 'capacity', 'amount_basis': 'facility_commitment',
                 'relationship': 'borrower', 'status': 'parsed', 'evidence': evidence,
                 'currency': 'USD', 'as_of_date': '2025-12-31'}
        for change in ({'value': '4000000'}, {'currency': 'EUR'}, {'as_of_date': '2024-12-31'}):
            with self.subTest(change=change):
                row = {**right, **change}
                scored = pilot.score_assertions([self.gold], [row], [])
                self.assertEqual(scored['results'][0]['outcome'], 'misclassified')

    def test_conflicting_parsed_records_cannot_hide_behind_correct_record(self):
        evidence = [{'page_number': 85, 'quoted_text': 'New $4.0 billion credit facilities'}]
        right = {'source_url': self.gold['source_url'], 'value': '4000000000',
                 'amount_kind': 'capacity', 'amount_basis': 'facility_commitment',
                 'relationship': 'borrower', 'status': 'parsed', 'evidence': evidence,
                 'currency': 'USD', 'as_of_date': '2025-12-31'}
        wrong = {**right, 'amount_kind': 'flow', 'amount_basis': 'reported_cash_movement'}
        scored = pilot.score_assertions([self.gold], [right, wrong], [])
        self.assertEqual(scored['results'][0]['outcome'], 'misclassified')

    def test_selected_amount_and_year_prevent_other_row_columns_from_matching(self):
        gold = {**self.gold, 'page': 69, 'label': 'Proceeds from term loan', 'amount_text': '100',
                'value_usd': '100000', 'period': '2025', 'amount_kind': 'flow',
                'amount_basis': 'reported_cash_movement'}
        quote = 'Proceeds from term loan 100 200 300'
        def record(year, raw_value):
            return {'source_url': gold['source_url'], 'value': str(raw_value * 1000),
                    'currency': 'USD', 'period_start': year + '-01-01', 'period_end': year + '-12-31',
                    'amount_kind': 'flow', 'amount_basis': 'reported_cash_movement',
                    'relationship': 'borrower', 'status': 'parsed', 'evidence': [{
                    'page_number': 69, 'quoted_text': quote, 'evidence_role': 'amount',
                    'column_year': year, 'selected_amount_text': str(raw_value)}]}
        scored = pilot.score_assertions([gold], [record('2025', 100), record('2024', 200), record('2023', 300)], [])
        self.assertEqual(scored['results'][0]['outcome'], 'classified_correctly')
        self.assertEqual(scored['results'][0]['matched_record_count'], 1)

    def test_selected_amount_requires_whole_value_not_numeric_substring(self):
        gold = {**self.gold, 'amount_text': '100', 'label': 'credit facilities'}
        row = {'source_url': gold['source_url'], 'evidence': [{'page_number': 85,
               'quoted_text': 'The credit facilities had 1000 available', 'selected_amount_text': '1000'}]}
        self.assertEqual(pilot.score_assertions([gold], [], [row])['results'][0]['outcome'], 'missed')

    def test_amount_in_different_context_is_not_credit(self):
        unrelated = {'source_url': self.gold['source_url'], 'evidence': [{
            'page_number': 85, 'quoted_text': '$4.0 billion in property acquisitions'}]}
        scored = pilot.score_assertions([self.gold], [], [unrelated])
        self.assertEqual(scored['results'][0]['outcome'], 'missed')

    def test_local_pdf_hash_is_checked_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'report.pdf'
            source.write_bytes(b'%PDF-1.4\nfake')
            with patch.object(pilot, 'selected_native_pdf_pages', side_effect=AssertionError('must not extract')):
                with self.assertRaisesRegex(ValueError, 'hash'):
                    pilot.prepare_local_pdf(source, Path(tmp) / 'run', expected_sha256='0' * 64)

    def test_prepared_manifest_and_text_have_same_source_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'report.pdf'
            source.write_bytes(b'%PDF-1.4\nfake')
            digest = sha256(source.read_bytes()).hexdigest()
            pages = [{'number': 69, 'text': 'cash flows'}, {'number': 70, 'text': 'currency'}, {'number': 85, 'text': 'credit facilities'}]
            with patch.object(pilot, 'selected_native_pdf_pages', return_value=pages) as extract:
                manifest = pilot.prepare_local_pdf(source, Path(tmp) / 'run', expected_sha256=digest)
            document = manifest['documents'][0]
            self.assertEqual(document['sha256'], digest)
            self.assertEqual(document['url'], pilot.REALTY_REPORT_URL)
            self.assertTrue(Path(document['source_path']).is_file())
            self.assertTrue(Path(document['text_path']).is_file())
            self.assertEqual(extract.call_args.args[1:], ((69, 70, 85),))
            self.assertEqual(manifest['sampled_pdf_pages'], [69, 70, 85])

    def test_answer_key_rejects_wrong_source_hash_or_unsampled_page(self):
        key = {'source_url': pilot.REALTY_REPORT_URL, 'source_sha256': pilot.REALTY_SHA256,
               'assertions': [{**self.gold, 'source_url': pilot.REALTY_REPORT_URL}]}
        pilot.validate_answer_key(key)
        with self.assertRaisesRegex(ValueError, 'hash'):
            pilot.validate_answer_key({**key, 'source_sha256': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'page'):
            pilot.validate_answer_key({**key, 'assertions': [{**key['assertions'][0], 'page': 99}]})


if __name__ == '__main__':
    unittest.main()
