import importlib
import unittest
import numpy as np
import pandas as pd


def fixture():
    dates = pd.bdate_range('2024-01-01', periods=50)
    data = pd.DataFrame({'date': dates, 'ticker': 'A', 'x': np.linspace(-1, 1, 50),
                         'state': np.linspace(-.5, .5, 50), 'volatility': np.linspace(.01, .03, 50),
                         'target': np.sin(np.arange(50))})
    data['label_available_at'] = data.date.shift(-1) + pd.Timedelta(hours=23)
    data.loc[0, 'x'] = np.nan
    train = data.iloc[1:29]
    holdout = data.iloc[30:].copy()
    report = {'cohort': {'eligible_train_rows_before_feature_exclusions': 29,
                         'excluded_train_rows': 1, 'paired_train_rows': 28,
                         'eligible_holdout_rows_before_feature_exclusions': 20,
                         'excluded_holdout_rows': 0, 'paired_holdout_rows': 20}}
    return data, holdout, report, dates


class RiskComparisonTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('scripts.multi_market.complete_risk_comparisons'),
                             'causal frozen risk comparison module must exist')
        self.module = importlib.import_module('scripts.multi_market.complete_risk_comparisons')

    def run_fixture(self, data, holdout, report, dates):
        return self.module.complete_risk(data, holdout, report, baseline=['x', 'volatility'],
            candidates={'candidate': ['state']}, train_start=dates[0],
            holdout_start=dates[30], holdout_end=dates[-1])

    def test_future_holdout_changes_cannot_change_training_constants(self):
        data, holdout, report, dates = fixture()
        first = self.run_fixture(data, holdout, report, dates)
        changed = data.copy()
        changed.loc[changed.date >= dates[30], ['state', 'volatility', 'target']] *= 10
        second = self.run_fixture(changed, changed.iloc[30:], report, dates)
        self.assertEqual(first['training_constants'], second['training_constants'])

    def test_target_sign_change_does_not_change_risk_exposures(self):
        data, holdout, report, dates = fixture()
        first = self.run_fixture(data, holdout, report, dates)
        data.target *= -1; holdout.target *= -1
        second = self.run_fixture(data, holdout, report, dates)
        for name in first['row_exposures']:
            np.testing.assert_array_equal(first['row_exposures'][name], second['row_exposures'][name])

    def test_reconstructed_counts_and_original_holdout_keys_are_asserted(self):
        data, holdout, report, dates = fixture()
        result = self.run_fixture(data, holdout, report, dates)
        self.assertEqual(result['cohort']['paired_train_rows'], 28)
        self.assertEqual(result['cohort']['excluded_train_rows'], 1)
        self.assertTrue(result['cohort']['original_holdout_keys_match'])
        broken = dict(report, cohort=dict(report['cohort'], paired_train_rows=29))
        with self.assertRaisesRegex(ValueError, 'paired_train_rows'):
            self.run_fixture(data, holdout, broken, dates)

    def test_training_exposure_scale_matches_without_fitting_holdout(self):
        data, holdout, report, dates = fixture()
        result = self.run_fixture(data, holdout, report, dates)
        constant = result['training_constants']['candidates']['candidate']
        self.assertAlmostEqual(constant['candidate_train_average_gross'],
            constant['baseline_train_average_gross'] * constant['baseline_uniform_scale'])
        for pair in result['paired_risk']['candidate'].values():
            self.assertEqual(pair['downside_increment']['calendar_sessions'], 20)
            self.assertEqual(pair['opportunity_increment']['calendar_sessions'], 20)


if __name__ == '__main__':
    unittest.main()
