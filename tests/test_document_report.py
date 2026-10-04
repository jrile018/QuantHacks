import unittest
from src.document_report import options_readiness, render_markdown, select_contracts


class ReadinessTests(unittest.TestCase):
    def test_daily_bars_cannot_become_executable_quotes(self):
        result = options_readiness([], [], market={'daily_bars': [{'close': 2}]})
        self.assertIn('option_quotes_missing', result['reason_codes'])
        self.assertIsNone(result['forecast'])
        self.assertEqual(result['status'], 'not_ready')

    def test_read_after_cutoff_and_unknown_publication_block(self):
        record = {'document_id': 'd', 'public_at_utc': '2024-01-01T12:00:00Z',
                  'public_at_evidence': 'archive', 'receipt_at_utc': '2024-01-01T12:01:00Z'}
        transcript = {'document_id': 'd', 'processing_completed_at_utc': '2024-01-01T12:02:00Z'}
        result = options_readiness([record], [transcript], decision='2024-01-01T12:01:30Z')
        self.assertIn('processing_after_decision', result['reason_codes'])
        record['public_at_evidence'] = None
        result = options_readiness([record], [transcript], mode='anticipation', decision='2024-01-02T12:00:00Z')
        self.assertIn('public_timestamp_unverified', result['reason_codes'])

    def test_future_accession_never_predictor(self):
        row = {'document_id': 'd', 'accession': 'target'}
        result = options_readiness([row], [], mode='anticipation', target_accession='target')
        self.assertIn('target_filing_leakage', result['reason_codes'])

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            options_readiness([], [], decision='2024-01-01T12:00:00')

    def test_unverified_marker_cannot_support_readiness(self):
        record = {'document_id': 'd', 'public_at_utc': '2024-01-01T12:00:00Z', 'public_at_evidence': 'unverified'}
        result = options_readiness([record], [], decision='2024-01-02T12:00:00Z')
        self.assertIn('public_timestamp_unverified', result['reason_codes'])

    def test_contract_rule_uses_shared_expiry_and_strike_ties(self):
        quotes = []
        for kind, strikes in [('call', [104, 106]), ('put', [94, 96])]:
            for strike in strikes:
                quotes.append({'contract_id': f'{kind}{strike}', 'option_type': kind, 'strike': strike,
                               'expiry': '2024-05-01', 'timestamp': '2024-01-02T12:00:00Z',
                               'bid': 2, 'ask': 2.1, 'bid_size': 1, 'ask_size': 1, 'multiplier': 100})
        pair = select_contracts(quotes, 100, '2024-01-02T12:00:01Z', {'max_quote_age_seconds': 5, 'max_spread_fraction': .1})
        self.assertEqual(pair['call']['strike'], 104)
        self.assertEqual(pair['put']['strike'], 94)
        self.assertIsNone(select_contracts(quotes, 100, '2024-01-02T12:00:01Z', {}))


if __name__ == '__main__':
    unittest.main()
