"""Small, offline checks for the reusable research pipeline."""

import unittest
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src import capital_liquidity, data, implementation, main, risk_management


class DataTests(unittest.TestCase):
    def test_missing_key_fails_cleanly_in_noninteractive_run(self):
        with patch.object(sys.stdin, "isatty", return_value=False):
            with patch.object(data, "getpass", side_effect=AssertionError("prompted")):
                with self.assertRaisesRegex(RuntimeError, "MISSING_TEST_API_KEY"):
                    data.load_api_key("MISSING_TEST_API_KEY")

    def test_normalize_ticker_unifies_share_class_separators(self):
        self.assertEqual(data.normalize_ticker(" brk/b "), "BRK.B")
        self.assertIsNone(data.normalize_ticker(" "))

    def test_build_events_collapses_multiple_disclosures_for_one_filer_and_day(self):
        raw = pd.DataFrame(
            [
                {
                    "cik": "0001",
                    "filing_date": pd.Timestamp("2024-01-08"),
                    "tickers": ["BRK/B"],
                    "accession_number": "a",
                    "filing_url": "https://example.test/a",
                    "supporting_text": "first",
                },
                {
                    "cik": "0001",
                    "filing_date": pd.Timestamp("2024-01-08"),
                    "tickers": ["BRK.B"],
                    "accession_number": "a",
                    "filing_url": "https://example.test/a",
                    "supporting_text": "second",
                },
            ]
        )
        with patch.object(data, "fetch_disclosures", return_value=raw):
            events = data.build_events("tag", "2024-01-01", "2024-01-31", ["BRK.B"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events.iloc[0]["ticker"], "BRK.B")
        self.assertEqual(events.iloc[0]["t_pre"], pd.Timestamp("2024-01-05"))
        self.assertEqual(events.iloc[0]["t_0"], pd.Timestamp("2024-01-09"))

    def test_nontrading_day_filing_enters_on_first_following_session(self):
        self.assertEqual(data.safe_entry_session(pd.Timestamp("2024-01-06")), pd.Timestamp("2024-01-08"))

    def test_build_events_returns_empty_table_when_api_has_no_disclosures(self):
        with patch.object(data, "fetch_disclosures", return_value=pd.DataFrame()):
            events = data.build_events("rare_tag", "2024-01-01", "2024-01-31", ["AAPL"])
        self.assertTrue(events.empty)
        self.assertIn("ticker", events.columns)


class ImplementationTests(unittest.TestCase):
    def test_evaluate_empty_priced_events_returns_typed_empty_table(self):
        result = implementation.evaluate([])
        self.assertTrue(result.empty)
        self.assertIn("ratio", result.columns)

    def test_strategy_pnl_uses_entry_and_exit_marks(self):
        entry = {"C_K": 10.0, "P_K": 8.0, "C_U0.05": 5.0, "P_L0.05": 4.0}
        exit_ = {"C_K": 13.0, "P_K": 6.0, "C_U0.05": 3.0, "P_L0.05": 7.0}
        got = implementation.strategy_pnl(entry, exit_, 100.0, 105.0, 0.05)
        expected = {
            "stock": 0.05,
            "long_call": 0.03,
            "covered_call": 0.07,
            "protective_put": 0.08,
            "collar": 0.10,
            "cash_secured_put": -0.03,
        }
        for strategy, want in expected.items():
            with self.subTest(strategy=strategy):
                self.assertAlmostEqual(got[strategy], want)

    def test_empty_study_window_has_clear_error(self):
        with patch.object(implementation, "build_events", return_value=pd.DataFrame(columns=["filing_date"])):
            with self.assertRaisesRegex(ValueError, "No 8-K events"):
                implementation.run_study("tag", "2024-01-01", "2024-01-31")

    def test_study_with_no_evaluable_horizon_has_clear_error(self):
        events = pd.DataFrame({"filing_date": [pd.Timestamp("2024-01-08")]})
        with patch.object(implementation, "build_events", return_value=events), \
             patch.object(implementation, "price_events", return_value=([object()], pd.DataFrame())), \
             patch.object(implementation, "evaluate", return_value=pd.DataFrame()):
            with self.assertRaisesRegex(ValueError, "No evaluated horizons"):
                implementation.run_study("tag", "2024-01-01", "2024-01-31")


class RiskTests(unittest.TestCase):
    def test_risk_budget_caps_whole_contracts(self):
        self.assertEqual(risk_management.contracts_within_risk_budget(10_000, 0.01, 35), 2)
        self.assertEqual(risk_management.contracts_within_risk_budget(10_000, 0.01, 101), 0)

    def test_risk_budget_rejects_nonpositive_loss(self):
        with self.assertRaises(ValueError):
            risk_management.contracts_within_risk_budget(10_000, 0.01, 0)


class CapitalLiquidityTests(unittest.TestCase):
    def test_long_call_capacity_respects_capital_risk_and_volume(self):
        result = capital_liquidity.plan_trade(
            strategy="long_call",
            spot=100.0,
            strikes={"K": 100.0, "L0.05": 95.0, "U0.05": 105.0},
            marks={"C_K": 5.0, "P_K": 4.0, "C_U0.05": 2.0, "P_L0.05": 2.0},
            volumes={"C_K": 200, "P_K": 200, "C_U0.05": 200, "P_L0.05": 200},
            capital=10_000.0,
            risk_fraction=0.10,
            participation=0.05,
            cost_haircut=0.05,
            otm=0.05,
        )
        self.assertEqual(result["capital_per_contract"], 550.0)
        self.assertEqual(result["max_loss_per_contract"], 550.0)
        self.assertEqual(result["capacity_contracts"], 1)
        self.assertEqual(result["volume_contracts"], 10)
        self.assertEqual(result["round_trip_cost_per_contract"], 50.0)

    def test_cash_secured_put_reserves_full_strike(self):
        result = capital_liquidity.plan_trade(
            strategy="cash_secured_put",
            spot=100.0,
            strikes={"K": 100.0, "L0.05": 95.0, "U0.05": 105.0},
            marks={"P_L0.05": 2.0},
            volumes={"P_L0.05": 100},
            capital=10_000.0,
            risk_fraction=1.0,
            participation=1.0,
            cost_haircut=0.05,
            otm=0.05,
        )
        self.assertEqual(result["capital_per_contract"], 9_520.0)
        self.assertEqual(result["max_loss_per_contract"], 9_320.0)
        self.assertEqual(result["capacity_contracts"], 1)


class RunnerTests(unittest.TestCase):
    def test_source_hash_identifies_exact_code_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "engine.py"
            path.write_bytes(b"value = 1\n")
            first = main.hash_sources([path])
            self.assertEqual(first, main.hash_sources([path]))
            path.write_bytes(b"value = 1\r\n")
            self.assertEqual(first, main.hash_sources([path]))
            path.write_text("value = 2\n", encoding="utf-8")
            self.assertNotEqual(first, main.hash_sources([path]))

    def test_help_needs_no_api_key(self):
        with patch.object(data, "load_api_key", side_effect=AssertionError("key requested")):
            with self.assertRaises(SystemExit) as raised:
                main.main(["--help"])
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
