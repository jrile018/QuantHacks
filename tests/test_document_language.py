import csv
import tempfile
import unittest
from pathlib import Path

from src.document_language import DictionaryProvider, analyze_wording, compare_prior


def evidence(text, id='e1'):
    return {'evidence_id': id, 'document_id': 'd', 'text_sha256': 'hash',
            'quoted_text': text, 'section_id': 's', 'sec_item': '2.02'}


class LanguageTests(unittest.TestCase):
    def test_missing_providers_do_not_make_up_labels(self):
        result = analyze_wording([evidence('Income declined.')])
        self.assertEqual(result['status'], 'providers_unavailable')
        self.assertIsNone(result['evidence_assessments'][0]['financial_sentiment'])
        self.assertEqual(result['annotation_status'], 'machine_unreviewed')

    def test_dictionary_counts_are_not_contextual_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'dictionary.csv'
            path.write_text('Word,Negative,Positive,Uncertainty\nLOSS,2009,0,0\nGAIN,0,2009,0\nMAY,0,0,2009\n', encoding='utf-8')
            provider = DictionaryProvider(path, 'fixture-v1')
            result = analyze_wording([evidence('There was no loss; income may gain.')], dictionary=provider)
        item = result['evidence_assessments'][0]
        self.assertEqual(item['dictionary']['counts']['negative'], 1)
        self.assertEqual(item['dictionary']['counts']['uncertainty'], 1)
        self.assertIsNone(item['financial_sentiment'])
        self.assertEqual(len(result['provider_revisions']['dictionary']['sha256']), 64)

    def test_comparison_requires_prior_public_timing(self):
        now = {'cik': '1', 'public_at_utc': '2024-02-01T12:00:00Z', 'public_at_evidence': 'release archive'}
        prior = {'cik': '1', 'public_at_utc': '2024-03-01T12:00:00Z', 'public_at_evidence': 'release archive'}
        rows = compare_prior([evidence('Income rose.')], [evidence('Income rose.', 'prior')], now, prior)
        self.assertEqual(rows['status'], 'comparison_unavailable')
        prior['public_at_utc'] = '2023-11-01T12:00:00Z'
        rows = compare_prior([evidence('Income rose.')], [evidence('Income rose.', 'prior')], now, prior)
        self.assertEqual(rows['statements'][0]['novelty'], 'unchanged')
        self.assertEqual(rows['statements'][0]['prior_evidence_id'], 'prior')
        prior['public_at_evidence'] = None
        self.assertEqual(compare_prior([], [], now, prior)['status'], 'comparison_unavailable')

    def test_unverified_marker_cannot_support_comparison(self):
        now = {'cik': '1', 'public_at_utc': '2024-02-01T12:00:00Z', 'public_at_evidence': 'unverified'}
        prior = dict(now, public_at_utc='2023-11-01T12:00:00Z')
        self.assertEqual(compare_prior([evidence('Income rose.')], [evidence('Income rose.')], now, prior)['status'], 'comparison_unavailable')


if __name__ == '__main__':
    unittest.main()
