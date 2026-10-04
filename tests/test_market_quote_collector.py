import json
import tempfile
import unittest
from unittest.mock import Mock
from src.market_quote_collector import collect_request, sip_iso, validate_page_url


class QuoteCollectorTests(unittest.TestCase):
    def test_complete_pagination_is_not_reported_truncated(self):
        item = {'sip_timestamp': 1723555800000000123, 'bid_price': 2, 'ask_price': 2.1, 'bid_size': 1, 'ask_size': 1}
        payloads = [{'results': [item], 'next_url': 'https://api.massive.com/v3/quotes/AAPL?cursor=2'},
                    {'results': [dict(item, sip_timestamp=1723555800000000223)]}]
        responses = []
        for payload in payloads:
            response = Mock(status_code=200, content=json.dumps(payload).encode())
            response.json.return_value = payload
            responses.append(response)
        session = Mock()
        session.get.side_effect = responses
        with tempfile.TemporaryDirectory() as temp:
            result = collect_request({'ticker': 'AAPL', 'start_utc': '2024-08-13T13:30:00Z', 'end_utc': '2024-08-13T13:31:00Z'}, session, temp)
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['quotes']), 2)

    def test_preserves_sip_and_does_not_invent_historical_receipt(self):
        request = {'ticker': 'O:AAPL240920C00250000', 'start_utc': '2024-08-13T13:30:00Z', 'end_utc': '2024-08-13T13:31:00Z'}
        payload = {'results': [{'sip_timestamp': 1723555800000000123, 'bid_price': 2, 'ask_price': 2.1, 'bid_size': 1, 'ask_size': 1}]}
        response = Mock(status_code=200, content=json.dumps(payload).encode())
        response.json.return_value = payload
        session = Mock()
        session.get.return_value = response
        with tempfile.TemporaryDirectory() as temp:
            result = collect_request(request, session, temp)
            second = collect_request(request, session, temp)
        self.assertTrue(result['complete'])
        self.assertEqual(result, second)
        self.assertEqual(session.get.call_count, 1)
        self.assertIsNone(result['quotes'][0]['receipt_at_utc'])
        self.assertTrue(result['quotes'][0]['timestamp_utc'].endswith('.000000123Z'))

    def test_pagination_must_remain_at_provider(self):
        with self.assertRaises(ValueError):
            validate_page_url('https://attacker.example/v3/quotes/AAPL')

    def test_blocks_do_not_become_empty_success(self):
        session = Mock()
        session.get.return_value.status_code = 403
        with tempfile.TemporaryDirectory() as temp:
            result = collect_request({'ticker': 'AAPL', 'start_utc': '2024-08-13T13:30:00Z', 'end_utc': '2024-08-13T13:31:00Z'}, session, temp)
        self.assertEqual(result['status'], 'access_blocked')
        self.assertFalse(result['complete'])


if __name__ == '__main__':
    unittest.main()
