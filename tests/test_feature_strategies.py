import importlib.util
from pathlib import Path
import unittest
import pandas as pd
import numpy as np

path = Path(__file__).resolve().parents[1] / 'data/packaged_software/backtest_feature_strategies.py'
spec = importlib.util.spec_from_file_location('feature_strategies', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FeatureStrategyTests(unittest.TestCase):
    def test_fixed_shares_and_both_execution_costs(self):
        dates = pd.date_range('2025-01-02', periods=3)
        close = pd.DataFrame({'A':[10,15,20], 'B':[10,10,10]}, index=dates)
        identity = pd.DataFrame('provider_issuer_and_share_identity_match', index=dates, columns=close.columns)
        result, daily = module.replay(close, identity, dates, ['A','B'], 10)
        expected = 1.5 * .999 / 1.001
        self.assertAlmostEqual(result['net_return'], expected-1)
        self.assertAlmostEqual(np.prod(1+daily.net_return), expected)

    def test_missing_future_holding_invalidates_instead_of_dropping(self):
        dates = pd.date_range('2025-01-02', periods=3)
        close = pd.DataFrame({'A':[10,np.nan,20], 'B':[10,10,10]}, index=dates)
        identity = pd.DataFrame('provider_issuer_and_share_identity_match', index=dates, columns=close.columns)
        result, daily = module.replay(close, identity, dates, ['A','B'], 10)
        self.assertEqual(result['status'], 'unresolved_held_price_or_identity')
        self.assertNotIn('net_return', result)
        self.assertTrue(daily.empty)

    def test_composite_requires_all_inputs_and_ignores_outcome(self):
        frame = pd.DataFrame({'profit':range(30), 'cost':range(30), 'label':[100]*30})
        frame.loc[0,'cost'] = np.nan
        first = module.score_rows(frame, [('profit',1), ('cost',-1)])
        frame['label'] = -100
        second = module.score_rows(frame, [('profit',1), ('cost',-1)])
        pd.testing.assert_series_equal(first, second)
        self.assertTrue(pd.isna(first[0]))
        self.assertEqual(first.dropna().nunique(), 1)


if __name__ == '__main__':
    unittest.main()
