from datetime import datetime, timedelta, timezone
import importlib
import unittest


class CashLabelTests(unittest.TestCase):
    def setUp(self):
        self.labels = importlib.import_module('src.multi_market.labels')

    def test_long_option_uses_ask_then_bid_and_multiplier(self):
        result = self.labels.round_trip_cash(2.1, 2.7, 3, 100, 'long', 4.5)
        self.assertAlmostEqual(result, 175.5)

    def test_short_cash_reverses_sides(self):
        self.assertAlmostEqual(self.labels.round_trip_cash(4.0, 3.0, 2, 50, 'short', 2), 98)

    def test_negative_futures_prices_use_cash_differences(self):
        self.assertAlmostEqual(self.labels.round_trip_cash(-35, -20, 1, 1000, 'long', 5), 14995)

    def test_cash_inputs_reject_nonfinite_or_invalid_exposure(self):
        for quantity, multiplier, cost in [(0, 100, 0), (1, -1, 0), (1, 100, -1), (float('nan'), 100, 0)]:
            with self.subTest(quantity=quantity, multiplier=multiplier, cost=cost):
                with self.assertRaises(ValueError):
                    self.labels.round_trip_cash(1, 2, quantity, multiplier, 'long', cost)

    def test_settlement_cash_equals_lifecycle_profit(self):
        flows = self.labels.futures_cash_flows(103, 101, [104, 102], 2, 50, 'long', 3)
        self.assertAlmostEqual(sum(flows), -203)
        self.assertAlmostEqual(sum(flows), self.labels.round_trip_cash(103, 101, 2, 50, 'long', 3))

    def test_actual_roll_legs_do_not_include_the_contract_price_gap(self):
        old = self.labels.futures_cash_flows(100, 102, [101], 1, 50, 'long', 2)
        new = self.labels.futures_cash_flows(120, 119, [121], 1, 50, 'long', 2)
        self.assertAlmostEqual(sum(old) + sum(new), 46)

    def test_short_settlement_cash_reconciles(self):
        flows = self.labels.futures_cash_flows(103, 101, [104, 102], 2, 50, 'short', 3)
        self.assertAlmostEqual(sum(flows), 197)


class ExecutableQuoteTests(unittest.TestCase):
    def setUp(self):
        self.labels = importlib.import_module('src.multi_market.labels')
        self.clock = datetime(2025, 1, 6, 14, 35, tzinfo=timezone.utc)

    def quote(self, **overrides):
        fields = dict(instrument_key='ESM5', event_time=self.clock - timedelta(seconds=1),
                      available_time=self.clock, bid=100., ask=101., bid_size=3., ask_size=2.)
        fields.update(overrides)
        return self.labels.Quote(**fields)

    def test_entry_price_is_side_specific(self):
        quote = self.quote()
        self.assertEqual(self.labels.executable_price(quote, 'buy', 2, self.clock, 10), 101)
        self.assertEqual(self.labels.executable_price(quote, 'sell', 3, self.clock, 10), 100)

    def test_zero_or_insufficient_size_is_a_nonfill(self):
        for size in [0, 1, float('nan')]:
            with self.subTest(size=size):
                self.assertIsNone(self.labels.executable_price(self.quote(ask_size=size), 'buy', 2, self.clock, 10))

    def test_crossed_quote_is_not_executable(self):
        self.assertIsNone(self.labels.executable_price(self.quote(bid=102, ask=101), 'buy', 1, self.clock, 10))

    def test_quote_arriving_after_cutoff_cannot_fill(self):
        quote = self.quote(available_time=self.clock + timedelta(seconds=1))
        self.assertIsNone(self.labels.executable_price(quote, 'buy', 1, self.clock, 10))

    def test_stale_or_future_event_is_not_repaired(self):
        for event in [self.clock - timedelta(seconds=11), self.clock + timedelta(seconds=1)]:
            self.assertIsNone(self.labels.executable_price(self.quote(event_time=event), 'buy', 1, self.clock, 10))

    def test_naive_timestamp_cannot_pass_clock_audit(self):
        with self.assertRaises(ValueError):
            self.labels.executable_price(self.quote(), 'buy', 1, self.clock.replace(tzinfo=None), 10)

    def test_sampled_quote_cannot_claim_update_execution(self):
        quote = self.quote(evidence_kind='interval_sample')
        self.assertIsNone(self.labels.executable_price(quote, 'buy', 1, self.clock, 10))
        self.assertEqual(self.labels.executable_price(quote, 'buy', 1, self.clock, 10, allow_sampled_proxy=True), 101)

    def test_negative_futures_quote_can_be_valid(self):
        quote = self.quote(bid=-36, ask=-35)
        self.assertEqual(self.labels.executable_price(quote, 'buy', 1, self.clock, 10), -35)


if __name__ == '__main__':
    unittest.main()
