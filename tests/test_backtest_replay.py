"""Offline replay contract against a pinned, synthetic selected-leg snapshot."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.backtest_replay import compare_replays, reproduce


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "backtest_replay"


class BacktestReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.snapshot = self.root / "snapshot"
        shutil.copytree(FIXTURE, self.snapshot)

    def test_two_fresh_runs_have_identical_scientific_tables_and_analytic_stock_return(self):
        first = reproduce(self.snapshot, self.root / "first")
        second = reproduce(self.snapshot, self.root / "second")
        self.assertEqual(first["status"], "synthetic_engineering_replay")
        self.assertEqual(first["economic_qualification"], "not_established")
        self.assertEqual(first["counts"]["events"], 1)
        self.assertEqual(first["counts"]["selected_legs"], 4)
        self.assertEqual(first["exported_tables"], second["exported_tables"])
        compare_replays(self.root / "first", self.root / "second")
        rows = pd.read_csv(self.root / "first" / "results.csv")
        row = rows[(rows.entry == "pre") & (rows.horizon.astype(str) == "exp")].iloc[0]
        self.assertAlmostEqual(row.stock, 0.1, places=5)
        self.assertAlmostEqual(row.long_call, 0.04, places=5)

    def test_tampered_input_fails_before_creating_output(self):
        path = self.snapshot / "option_bars.csv"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            reproduce(self.snapshot, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_missing_input_fails_closed(self):
        (self.snapshot / "option_legs.csv").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            reproduce(self.snapshot, self.root / "out")

    def test_existing_output_is_never_overwritten(self):
        output = self.root / "out"
        output.mkdir()
        marker = output / "marker"
        marker.write_text("leave me", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            reproduce(self.snapshot, output)
        self.assertEqual(marker.read_text(encoding="utf-8"), "leave me")

    def test_frozen_settings_mismatch_fails(self):
        settings = self.snapshot / "replay.json"
        data = json.loads(settings.read_text(encoding="utf-8"))
        data["settings"]["risk_free"] = 0.1
        settings.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "settings mismatch"):
            reproduce(self.snapshot, self.root / "out")

    def test_missing_selected_leg_is_rejected_even_with_updated_hash(self):
        path = self.snapshot / "option_legs.csv"
        legs = pd.read_csv(path)
        legs = legs[legs.leg_code != "P_L0.05"]
        legs.to_csv(path, index=False)
        data = json.loads((self.snapshot / "replay.json").read_text(encoding="utf-8"))
        import hashlib
        data["inputs"]["option_legs.csv"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (self.snapshot / "replay.json").write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "selected legs"):
            reproduce(self.snapshot, self.root / "out")

    def test_rehashed_event_with_delayed_post_session_is_rejected(self):
        import hashlib
        path = self.snapshot / "events.csv"
        events = pd.read_csv(path, dtype={"cik": str, "accession_number": str})
        events.loc[0, "t_0"] = "2024-01-10"
        events.to_csv(path, index=False)
        receipt_path = self.snapshot / "replay.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["inputs"]["events.csv"] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "pre/post session rule"):
            reproduce(self.snapshot, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_compare_rejects_corrupted_prior_table(self):
        reproduce(self.snapshot, self.root / "first")
        reproduce(self.snapshot, self.root / "second")
        with (self.root / "first" / "results.csv").open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            compare_replays(self.root / "first", self.root / "second")


if __name__ == "__main__":
    unittest.main()
