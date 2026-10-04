"""Hand-derived checks for the private, period-unit HAC diagnostic."""

import math
import unittest

from hac_diagnostics import diagnose_sharpe_hac


class HacDiagnosticTests(unittest.TestCase):
    def test_sample_ddof_one_point_and_private_scope(self):
        report = diagnose_sharpe_hac((0.01, 0.02, -0.01, 0.0), hac_lags=0)
        self.assertEqual(report.status, "diagnostic_only")
        self.assertEqual(report.n_periods, 4)
        self.assertAlmostEqual(report.period_sharpe, 0.005 / math.sqrt(1 / 6000))
        self.assertAlmostEqual(sum(report.influence), 0)
        self.assertFalse(report.user_reportable)
        self.assertIsNone(report.ci95)

    def test_zero_mean_influence_and_hac_se_use_divisor_n(self):
        report = diagnose_sharpe_hac((-1, 0, 1), hac_lags=0)
        self.assertEqual(report.period_sharpe, 0)
        for actual, expected in zip(report.influence, (-1, 0, 1)):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(report.autocovariances[0], 2 / 3)
        self.assertAlmostEqual(report.hac_variance, 2 / 3)
        self.assertAlmostEqual(report.standard_error, math.sqrt(2) / 3)

    def test_asymmetry_includes_squared_return_influence(self):
        report = diagnose_sharpe_hac((0, 1, 3), hac_lags=1)
        self.assertAlmostEqual(report.period_sharpe, 4 * math.sqrt(2 / 3) / math.sqrt(14))
        for actual, numerator in zip(report.influence, (-30, 6, 24)):
            self.assertAlmostEqual(actual, numerator / (7 * math.sqrt(21)))
        self.assertAlmostEqual(report.autocovariances[0], 24 / 49)
        self.assertAlmostEqual(report.autocovariances[1], -4 / 343)
        self.assertAlmostEqual(report.hac_variance, 164 / 343)
        self.assertAlmostEqual(report.standard_error, math.sqrt(164 / 1029))
        self.assertNotAlmostEqual(report.hac_variance, 41 / 63)

    def test_constant_and_near_constant_have_no_point_or_se(self):
        for values in ((1, 1, 1), (1 - 1e-8, 1, 1 + 1e-8)):
            with self.subTest(values=values):
                report = diagnose_sharpe_hac(values, hac_lags=0)
                self.assertEqual(report.status, "unavailable")
                self.assertIn("normalized_variance_at_or_below_floor", report.reasons)
                self.assertIsNone(report.period_sharpe)
                self.assertIsNone(report.standard_error)
                self.assertIsNone(report.ci95)

    def test_invalid_sequences_and_lags_are_explicit(self):
        for values in (None, 2, True, "123", (), (1,), (1, False), (1, float("nan")),
                       (1, float("inf"))):
            with self.subTest(values=values):
                report = diagnose_sharpe_hac(values, hac_lags=0)
                self.assertEqual(report.status, "unavailable")
                self.assertTrue(report.reasons)
                self.assertIsNone(report.period_sharpe)
                self.assertIsNone(report.standard_error)
        for lags in (True, 1.0, -1, 3, None):
            with self.subTest(lags=lags):
                report = diagnose_sharpe_hac((0, 1, 3), hac_lags=lags)
                self.assertIn("invalid_hac_lags", report.reasons)
                self.assertIsNone(report.period_sharpe)

    def test_large_finite_positive_scaling_is_invariant(self):
        base = diagnose_sharpe_hac((0.7, 0.9, 0.7, 0.9), hac_lags=1)
        large = diagnose_sharpe_hac((7e307, 9e307, 7e307, 9e307), hac_lags=1)
        self.assertEqual(base.status, "diagnostic_only")
        self.assertEqual(large.status, "diagnostic_only")
        self.assertAlmostEqual(large.period_sharpe, base.period_sharpe)
        self.assertAlmostEqual(large.standard_error, base.standard_error)

    def test_result_and_diagnostics_are_immutable(self):
        report = diagnose_sharpe_hac((0, 1, 3), hac_lags=1)
        with self.assertRaises((AttributeError, TypeError)):
            report.period_sharpe = 10
        with self.assertRaises(TypeError):
            report.influence[0] = 10


if __name__ == "__main__":
    unittest.main()
