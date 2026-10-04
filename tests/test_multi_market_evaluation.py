import importlib
import unittest

import numpy as np
import pandas as pd


def fixture():
    rng = np.random.default_rng(4)
    dates = pd.bdate_range('2020-01-01', periods=90)
    rows = pd.DataFrame({'date': np.repeat(dates, 3), 'ticker': ['A', 'B', 'C'] * 90})
    rows['x'] = rng.normal(size=len(rows))
    rows['candidate'] = rng.normal(size=len(rows))
    rows['target'] = .01 * rows.x + rng.normal(0, .01, len(rows))
    rows['label_available_at'] = rows.date + pd.Timedelta(days=1, hours=23)
    rows['volatility'] = .02
    return rows, dates


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('src.multi_market.evaluation'),
                             'paired evaluation module must exist')
        self.evaluation = importlib.import_module('src.multi_market.evaluation')

    def run_study(self, rows, dates):
        return self.evaluation.evaluate_forecasts(rows, baseline=['x'],
            candidates={'candidate': ['candidate']}, holdout_start=dates[60],
            holdout_end=dates[79], bootstrap_repetitions=50, block_sessions=5)

    def test_appending_future_rows_preserves_holdout_predictions(self):
        rows, dates = fixture()
        first = self.run_study(rows[rows.date <= dates[79]], dates)
        second = self.run_study(rows, dates)
        pd.testing.assert_frame_equal(first.predictions, second.predictions)

    def test_holdout_and_unavailable_training_labels_do_not_change_predictions(self):
        rows, dates = fixture()
        rows.loc[rows.date == dates[58], 'label_available_at'] = dates[62]
        original = self.run_study(rows, dates)
        changed = rows.copy()
        changed.loc[(changed.date >= dates[60]) | (changed.date == dates[58]), 'target'] += 1000
        again = self.run_study(changed, dates)
        np.testing.assert_array_equal(original.predictions.baseline, again.predictions.baseline)
        np.testing.assert_array_equal(original.predictions.candidate, again.predictions.candidate)

    def test_missing_candidate_excludes_same_rows_for_every_model_and_reports_it(self):
        rows, dates = fixture()
        row = (rows.date == dates[65]) & (rows.ticker == 'B')
        rows.loc[row, 'candidate'] = np.nan
        result = self.run_study(rows, dates)
        self.assertEqual(len(result.predictions), 59)
        self.assertEqual(result.report['cohort']['excluded_holdout_rows'], 1)
        self.assertEqual(result.report['metrics']['baseline']['rows'], 59)
        self.assertEqual(result.report['metrics']['candidate']['rows'], 59)

    def test_bootstrap_is_deterministic_and_bundles_cross_section(self):
        rows, _ = fixture()
        rows['gain'] = np.repeat(np.arange(90, dtype=float), 3)
        a = self.evaluation.calendar_block_interval(rows, 'gain', repetitions=100, block_sessions=5, seed=9)
        b = self.evaluation.calendar_block_interval(rows.iloc[::-1], 'gain', repetitions=100, block_sessions=5, seed=9)
        self.assertEqual(a, b)
        self.assertEqual(a['calendar_sessions'], 90)
        self.assertEqual(a['mean'], 44.5)

    def test_failed_candidate_is_archived_and_no_economic_profit_is_claimed(self):
        rows, dates = fixture()
        rows['candidate'] = np.nan
        result = self.run_study(rows, dates)
        self.assertEqual(result.report['status'], 'blocked')
        self.assertTrue(result.report['failures'])
        self.assertEqual(result.report['roles']['direct_signal']['economic_status'], 'blocked')
        self.assertNotIn('net_profit', result.report)


if __name__ == '__main__':
    unittest.main()
