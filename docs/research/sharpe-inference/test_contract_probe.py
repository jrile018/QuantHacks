"""Observable checks for the offline, synthetic return-contract probe."""

import math
import unittest

from contract_probe import assess_panel


DATES = (
    "2024-01-01T00:00:00Z",
    "2024-01-02T00:00:00Z",
    "2024-01-03T00:00:00Z",
    "2024-01-04T00:00:00Z",
)


def panel(**changes):
    args = dict(
        timestamps=DATES,
        expected_calendar=DATES,
        net_returns=(0.01, -0.01, 0.02, 0.0),
        reference_returns=(0.0,) * 4,
        reference_kind="declared_zero",
        periods_per_year=252,
        provenance={"recipe": "synthetic", "caller_eligible": True},
        marks_complete=True,
        costs_complete=True,
        flows_reconciled=True,
        timing_verified=True,
    )
    args.update(changes)
    return assess_panel(**args)


class ContractProbeTests(unittest.TestCase):
    def test_hand_derived_sample_sharpe_is_private_diagnostic(self):
        result = panel()
        self.assertEqual(result.n_periods, 4)
        self.assertEqual(result.status, "diagnostic_only")
        self.assertAlmostEqual(result.diagnostics["mean_excess_return"], 0.005)
        self.assertAlmostEqual(result.diagnostics["sample_variance"], 1 / 6000)
        self.assertAlmostEqual(result.diagnostics["period_sharpe"], math.sqrt(0.15))
        self.assertAlmostEqual(result.diagnostics["annualized_conventional_sharpe"], math.sqrt(0.15 * 252))
        self.assertFalse(result.user_reportable)
        self.assertIsNone(result.ci95)
        self.assertIn("inference_method_not_implemented", result.reasons)
        self.assertIn("calibration_pending", result.reasons)

    def test_invalid_inputs_retain_original_period_count_and_reasons(self):
        cases = (
            ({"timestamps": DATES[:-1]}, "length_mismatch"),
            ({"reference_returns": (0.0,) * 3}, "length_mismatch"),
            ({"timestamps": (DATES[0], DATES[1], DATES[3])}, "calendar_mismatch"),
            ({"timestamps": (DATES[0], DATES[1], DATES[1], DATES[3])}, "duplicate_timestamp"),
            ({"timestamps": (DATES[1], DATES[0], DATES[2], DATES[3])}, "nonmonotone_timestamp"),
            ({"timestamps": ("2024-01-01T00:00:00",) + DATES[1:]}, "invalid_timestamp"),
            ({"net_returns": (0.01, float("nan"), 0.02, 0.0)}, "invalid_net_return"),
            ({"net_returns": (0.01, None, 0.02, 0.0)}, "invalid_net_return"),
            ({"net_returns": (0.01, True, 0.02, 0.0)}, "invalid_net_return"),
            ({"reference_returns": (0.0, None, 0.0, 0.0)}, "invalid_reference_return"),
            ({"reference_returns": (0.0, False, 0.0, 0.0)}, "invalid_reference_return"),
            ({"reference_returns": (0.0, float("inf"), 0.0, 0.0)}, "invalid_reference_return"),
            ({"reference_returns": (0.0, 0.01, 0.0, 0.0)}, "declared_zero_mismatch"),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason, changes=changes):
                result = panel(**changes)
                self.assertIn(reason, result.reasons)
                self.assertEqual(result.n_periods, len(changes.get("net_returns", (0.01, -0.01, 0.02, 0.0))))
                self.assertEqual(result.status, "unavailable")
                self.assertFalse(result.user_reportable)
                self.assertIsNone(result.ci95)

    def test_empty_sparse_constant_and_bankruptcy_are_explicit(self):
        for returns, reason in (((), "insufficient_periods"), ((0.0,), "insufficient_periods"), ((0.0,) * 4, "undefined_variance")):
            result = panel(timestamps=DATES[:len(returns)], expected_calendar=DATES[:len(returns)],
                           net_returns=returns, reference_returns=(0.0,) * len(returns))
            self.assertIn(reason, result.reasons)
            self.assertIsNone(result.diagnostics["period_sharpe"])
        result = panel(net_returns=(0.01, -1.0, 0.02, 0.0))
        self.assertIn("bankruptcy_or_ruin", result.reasons)
        self.assertEqual(result.n_periods, 4)
        self.assertIsNone(result.diagnostics["period_sharpe"])

    def test_unresolved_evidence_never_promotes_caller_claim(self):
        for flag in ("marks_complete", "costs_complete", "flows_reconciled", "timing_verified"):
            result = panel(**{flag: False})
            self.assertIn(flag + "_unresolved", result.reasons)
            self.assertEqual(result.status, "unavailable")
            self.assertFalse(result.user_reportable)
            self.assertIsNone(result.ci95)

    def test_provenance_is_copied_and_claims_cannot_promote(self):
        source = {"recipe": "synthetic", "nested": {"claim": "eligible"}}
        result = panel(provenance=source)
        source["nested"]["claim"] = "changed"
        self.assertEqual(result.provenance["nested"]["claim"], "eligible")
        self.assertFalse(result.user_reportable)

    def test_provenance_rejects_mutable_unknown_and_ambiguous_keys(self):
        for provenance in (
            {"nested": {"mutable": bytearray(b"old")}},
            {"nested": {"mutable": {1, 2}}},
            {1: "first", "1": "second"},
            {"value": float("nan")},
        ):
            with self.subTest(provenance=provenance):
                result = panel(provenance=provenance)
                self.assertIn("invalid_provenance", result.reasons)
                self.assertEqual(result.n_periods, 4)
                self.assertEqual(result.status, "unavailable")
                self.assertFalse(result.user_reportable)
                self.assertIsNone(result.ci95)

    def test_finite_operands_that_overflow_formula_withhold_point(self):
        for changes in (
            {"net_returns": (1e308, 9e307, 1e308, 9e307)},
            {"net_returns": (1e308,) * 4, "reference_returns": (-1e308,) * 4,
             "reference_kind": "observed_series"},
        ):
            with self.subTest(changes=changes):
                result = panel(**changes)
                self.assertIn("numerical_diagnostic_unavailable", result.reasons)
                self.assertIsNone(result.diagnostics["period_sharpe"])
                self.assertEqual(result.status, "unavailable")
                self.assertFalse(result.user_reportable)
                self.assertIsNone(result.ci95)

    def test_absent_or_scalar_series_is_explicitly_unavailable(self):
        for field in ("timestamps", "expected_calendar", "net_returns", "reference_returns"):
            for value in (None, 1):
                with self.subTest(field=field, value=value):
                    result = panel(**{field: value})
                    self.assertIn("invalid_" + field, result.reasons)
                    self.assertEqual(result.status, "unavailable")
                    self.assertFalse(result.user_reportable)
                    self.assertIsNone(result.ci95)


if __name__ == "__main__":
    unittest.main()
