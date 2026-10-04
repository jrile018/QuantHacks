"""Small synthetic safety fixtures; never evidence of market performance."""
import importlib
import unittest

import numpy as np
import pandas as pd


def panel(n=140):
    rng = np.random.default_rng(17)
    dates = pd.bdate_range('2020-01-01', periods=n)
    common = rng.normal(0, .01, n)
    return pd.concat([
        pd.DataFrame({'date': dates, 'ticker': name,
                      'adjclose': 100 * np.exp(np.cumsum(common + rng.normal(0, .005, n)))})
        for name in ['SPY', 'AAA', 'BBB', 'CCC']], ignore_index=True)


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('src.multi_market.features'),
                             'causal feature module must exist')
        self.features = importlib.import_module('src.multi_market.features')

    def test_appending_future_prices_preserves_every_earlier_feature(self):
        data = panel()
        cutoff = data.date.sort_values().unique()[100]
        before = self.features.build_features(data[data.date <= cutoff], window=20)
        after = self.features.build_features(data, window=20)
        labels = ['target', 'label_available_at']
        pd.testing.assert_frame_equal(before.drop(columns=labels),
            after[after.date <= cutoff].reset_index(drop=True).drop(columns=labels))

    def test_future_unavailable_price_cannot_change_features(self):
        data = panel()
        data['decision_at'] = data.date + pd.Timedelta(hours=23)
        data['available_at'] = data.decision_at
        row = (data.ticker == 'AAA') & (data.date == data.date.max())
        data.loc[row, 'available_at'] += pd.Timedelta(days=1)
        changed = data.copy()
        changed.loc[row, 'adjclose'] *= 100
        pd.testing.assert_frame_equal(self.features.build_features(data, window=20),
                                      self.features.build_features(changed, window=20))

    def test_futures_negative_prices_and_rolls_are_point_changes(self):
        data = pd.DataFrame({'date': pd.bdate_range('2020-01-01', periods=5),
                             'ticker': ['CL'] * 5, 'asset_class': ['future'] * 5,
                             'close': [5., -35., -20., 100., 101.],
                             'contract_id': ['A', 'A', 'A', 'B', 'B']})
        got = self.features.price_changes(data).price_change.to_numpy()
        np.testing.assert_allclose(got, [np.nan, -40, 15, np.nan, 1], equal_nan=True)

    def test_futures_without_contract_identity_are_rejected(self):
        data = panel(10).rename(columns={'adjclose': 'close'})
        data['asset_class'] = 'future'
        with self.assertRaisesRegex(ValueError, 'contract_id'):
            self.features.price_changes(data)

    def test_explicit_internal_factor_works_without_a_benchmark_symbol(self):
        data = panel().query("ticker != 'SPY'")
        got = self.features.build_features(data, benchmark='__equal_weight_panel__', window=20)
        self.assertGreater(got.residual_concentration.notna().sum(), 0)
        self.assertEqual(set(got.ticker), {'AAA', 'BBB', 'CCC'})

    def test_future_new_instrument_cannot_change_earlier_state(self):
        data = panel()
        cutoff = data.date.sort_values().unique()[100]
        first = self.features.build_features(data[data.date <= cutoff], window=20)
        addition = data[(data.ticker == 'AAA') & (data.date > cutoff)].copy()
        addition['ticker'] = 'NEW'
        second = self.features.build_features(pd.concat([data, addition]), window=20)
        columns = self.features.BASELINE_FEATURES + ['residual_peer_shock', 'residual_concentration', 'edge_turnover']
        actual = second[(second.date <= cutoff) & (second.ticker != 'NEW')].reset_index(drop=True)
        pd.testing.assert_frame_equal(first[columns], actual[columns])

    def test_missing_date_never_creates_a_next_session_target(self):
        data = panel(10)
        missing = data.date.unique()[5]
        data = data[~((data.ticker == 'AAA') & (data.date == missing))]
        got = self.features.build_features(data, window=3)
        prior = got[(got.ticker == 'AAA') & (got.date == data.date.unique()[4])]
        self.assertTrue(prior.target.isna().all())


if __name__ == '__main__':
    unittest.main()
