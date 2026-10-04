"""Registered role diagnostics on frozen predictions; synthetic safety tests."""
import importlib
import unittest

import numpy as np
import pandas as pd


def rows():
    dates = pd.bdate_range('2025-01-01', periods=20)
    frame = pd.DataFrame({'date': np.repeat(dates, 2), 'ticker': ['A', 'B'] * 20})
    frame['target'] = np.linspace(-1, 1, 40)
    frame['baseline'] = .2
    frame['simple_substitute'] = -.1
    frame['zero'] = 0.
    frame['candidate'] = frame.simple_substitute
    return frame


class RoleComparisonTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('scripts.multi_market.complete_role_comparisons'),
                             'frozen role comparison module must exist')
        self.module = importlib.import_module('scripts.multi_market.complete_role_comparisons')

    def test_identical_mean_predictions_have_exactly_zero_forecast_and_sign_increment(self):
        report = self.module.compare_frozen(rows(), candidates=['candidate'])
        for role in ['forecast', 'direct_signal']:
            pair = report[role]['candidate']['simple_substitute']['paired_increment']
            self.assertEqual((pair['mean'], pair['lower'], pair['upper']), (0., 0., 0.))

    def test_calendar_cluster_counts_include_every_same_day_instrument(self):
        report = self.module.compare_frozen(rows(), candidates=['candidate'])
        self.assertEqual(report['cohort']['paired_rows'], 40)
        self.assertEqual(report['cohort']['calendar_sessions'], 20)
        self.assertEqual(report['cohort']['instruments_per_session_min'], 2)
        self.assertEqual(report['cohort']['instruments_per_session_max'], 2)
        for role in ['forecast', 'direct_signal']:
            pair = report[role]['candidate']['zero']['paired_increment']
            self.assertEqual(pair['calendar_sessions'], 20)

    def test_nonfinite_candidate_excludes_same_row_for_all_comparisons(self):
        data = rows()
        data.loc[0, 'candidate'] = np.inf
        report = self.module.compare_frozen(data, candidates=['candidate'])
        self.assertEqual(report['cohort']['excluded_rows'], 1)
        self.assertEqual(report['cohort']['paired_rows'], 39)
        for role in ['forecast', 'direct_signal']:
            for pair in report[role]['candidate'].values():
                self.assertEqual(pair['rows'], 39)
                self.assertEqual(pair['cohort_sha256'], report['cohort']['keys_sha256'])

    def test_duplicate_decisions_are_rejected(self):
        data = rows()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.module.compare_frozen(pd.concat([data, data.iloc[:1]]), candidates=['candidate'])

    def test_risk_aggregate_matching_is_descriptive_and_policy_gate_inconclusive(self):
        source = {'cohort': {'paired_holdout_rows': 40}, 'roles': {'risk_filter': {'proxy_metrics': {
            'baseline': {'average_gross_exposure': .8, 'downside_second_moment': .16,
                         'mean_uncosted_long_mark_change': .04},
            'candidate': {'average_gross_exposure': .4, 'downside_second_moment': .02,
                          'mean_uncosted_long_mark_change': .03},
            'uniform_half_cash': {'average_gross_exposure': .5, 'downside_second_moment': .09,
                                 'mean_uncosted_long_mark_change': .02}}}}}
        report = self.module.compare_frozen(rows(), candidates=['candidate'], original_report=source)
        risk = report['risk_filter']
        self.assertEqual(risk['policy_comparison_status'], 'inconclusive_stateless')
        match = risk['descriptive_average_exposure_match']['candidate']
        self.assertAlmostEqual(match['uniformly_scaled_baseline']['downside_second_moment'], .04)
        self.assertAlmostEqual(match['candidate_minus_scaled_baseline_downside'], -.02)
        self.assertFalse(risk['prospectively_causal'])


if __name__ == '__main__':
    unittest.main()
