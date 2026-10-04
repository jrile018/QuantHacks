"""Synthetic, offline checks of Lattice's native option artifacts."""

import csv
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from tools.options_native import _session_age, ingest_options, study_options


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class NativeOptionsTest(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.study = self.root / "source"
        self.study.mkdir()
        self.run = self.root / "run"
        self.run.mkdir()
        event_id = "CIK:0000000123:accession:ABC"
        write_csv(self.study / "events.csv", [{"cik": "0000000123", "accession_number": "accession",
            "ticker": "ABC", "event_date": "2024-01-08", "t_pre": "2024-01-05", "t_0": "2024-01-09"}])
        write_csv(self.study / "results.csv", [{"ticker": "ABC", "event_date": "2024-01-08",
            "t_0": "2024-01-09", "bucket": "front", "entry": "post", "entry_date": "2024-01-09",
            "horizon": "5", "otm": "0.05", "long_call": "0.12", "realized": "0.03"}])
        write_csv(self.study / "capacity.csv", [{"ticker": "ABC", "event_date": "2024-01-08",
            "entry_date": "2024-01-09", "bucket": "front", "strategy": "long_call",
            "capacity_contracts": "2"}])
        write_csv(self.study / "option_legs.csv", [
            {"event_id": event_id, "bucket": "front", "leg_code": code,
             "contract_ticker": f"O:ABC-{code}", "underlying_ticker": "ABC",
             "contract_type": kind, "strike": "100", "expiration_date": "2024-02-16",
             "selection_date": "2024-01-05", "spot_pre": "101", "shares_per_contract": "100"}
            for code, kind in (("C_K", "call"), ("P_K", "put"))])
        write_csv(self.study / "option_bars.csv", [
            {"contract_ticker": f"O:ABC-{code}", "session": session, "close": close, "volume": "10"}
            for code, pre, future in (("C_K", "5", "999"), ("P_K", "4", "999"))
            for session, close in (("2024-01-05", pre), ("2024-01-09", future))])
        exported = {}
        for name in ("events", "results", "capacity", "option_legs", "option_bars"):
            path = self.study / f"{name}.csv"
            with path.open(newline="", encoding="utf-8") as handle:
                count = sum(1 for _ in csv.DictReader(handle))
            exported[name] = {"rows": count, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        (self.study / "manifest.json").write_text(json.dumps({"event_count": 1,
            "entry": "post", "exported_tables": exported}), encoding="utf-8")

    def test_native_parquet_and_causal_features(self) -> None:
        ingest = ingest_options(self.study, self.run / "gm-options-ingest", "fixture")
        self.assertEqual(ingest["contract_rows"], 2)
        self.assertEqual(pq.read_table(self.run / "gm-options-ingest" / "bars.parquet").num_rows, 4)
        score = pa.table({"date": ["2024-01-05", "2024-01-09"], "ticker": ["ABC", "ABC"],
                          "view": ["B", "B"], "estimator": ["mahalanobis", "mahalanobis"],
                          "depth": [1.5, 999.0], "pvalue": [0.2, 0.0], "inside": [True, False]})
        scores_path = self.run / "scores.parquet"
        pq.write_table(score, scores_path)
        summary = study_options(self.run / "gm-options-ingest", self.run / "gm-options-study",
                                "fixture", scores_path)
        features = pq.read_table(self.run / "gm-options-study" / "event_features.parquet").to_pylist()
        self.assertEqual(len(features), 1)
        self.assertAlmostEqual(features[0]["atm_straddle_implied_move"], 9 / 101)
        self.assertEqual(features[0]["score_depth"], 1.5)
        self.assertEqual(features[0]["score_date"], "2024-01-05")
        self.assertEqual(summary["matched_event_buckets"], 1)
        outcomes = pq.read_table(self.run / "gm-options-study" / "event_outcomes.parquet").to_pylist()
        self.assertEqual(outcomes[0]["long_call"], 0.12)
        capacity = pq.read_table(self.run / "gm-options-ingest" / "capacity.parquet").to_pylist()[0]
        self.assertEqual(capacity["capacity_contracts"], 2.0)
        self.assertNotIn("long_call", features[0])

    def test_rejects_changed_source_hash(self) -> None:
        with (self.study / "option_bars.csv").open("a", encoding="utf-8") as handle:
            handle.write("\n")
        with self.assertRaisesRegex(ValueError, "hash"):
            ingest_options(self.study, self.run / "gm-options-ingest", "fixture")

    def test_rejects_unknown_contract_multiplier(self) -> None:
        path = self.study / "option_legs.csv"
        text = path.read_text(encoding="utf-8").replace(",100\n", ",\n", 1)
        path.write_text(text, encoding="utf-8")
        manifest_path = self.study / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["exported_tables"]["option_legs"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "multiplier"):
            ingest_options(self.study, self.run / "gm-options-ingest", "fixture")

    def test_missing_exact_score_reports_absent_date(self) -> None:
        ingest_options(self.study, self.run / "gm-options-ingest", "fixture")
        scores_path = self.run / "scores.parquet"
        pq.write_table(pa.table({"date": ["2024-01-09"], "ticker": ["ABC"], "view": ["B"],
            "estimator": ["mahalanobis"], "depth": [999.0], "pvalue": [0.0], "inside": [False]}), scores_path)
        summary = study_options(self.run / "gm-options-ingest", self.run / "gm-options-study",
                                "fixture", scores_path)
        self.assertEqual(summary["missing_score_absent_date"], 1)
        feature = pq.read_table(self.run / "gm-options-study/event_features.parquet").to_pylist()[0]
        self.assertFalse(feature["score_present"])

    def test_mark_age_counts_exchange_sessions(self) -> None:
        self.assertEqual(_session_age("2024-01-12", "2024-01-16"), 1)  # MLK closure

    def test_databento_quotes_are_separate_and_causal(self) -> None:
        quotes = self.root / "option_quotes_daily.csv"
        rows = []
        for code, bid, ask in (("C_K", 4, 6), ("P_K", 3, 5)):
            for session, instant, factor in (("2024-01-05", "2024-01-05T21:00:00Z", 1),
                                             ("2024-01-09", "2024-01-09T21:00:00Z", 100)):
                rows.append({"contract_ticker": f"O:ABC-{code}", "session": session,
                    "mark_time_utc": instant, "mark_time_et": session + "T16:00:00-05:00",
                    "bid": str(bid * factor), "ask": str(ask * factor),
                    "mid": str((bid + ask) * factor / 2), "bid_size": "3", "ask_size": "4",
                    "spread": str((ask - bid) * factor),
                    "relative_spread": str((ask - bid) / ((bid + ask) / 2)),
                    "minutes_before_1600": "0", "source_job_id": "fixture-job"})
        write_csv(quotes, rows)
        manifest = ingest_options(self.study, self.run / "gm-options-ingest", "fixture", quote_path=quotes)
        self.assertEqual(manifest["quote_rows"], 4)
        self.assertIn("quotes.parquet", manifest["output_hashes"])
        self.assertEqual(pq.read_table(self.run / "gm-options-ingest" / "bars.parquet").num_rows, 4)
        study_options(self.run / "gm-options-ingest", self.run / "gm-options-study", "fixture")
        feature = pq.read_table(self.run / "gm-options-study" / "event_features.parquet").to_pylist()[0]
        self.assertTrue(feature["atm_quote_present"])
        self.assertAlmostEqual(feature["atm_straddle_bid"], 7)
        self.assertAlmostEqual(feature["atm_straddle_ask"], 11)
        self.assertAlmostEqual(feature["atm_straddle_mid"], 9)
        self.assertAlmostEqual(feature["atm_straddle_relative_spread"], 4 / 9)

    def test_tampered_quote_parquet_is_rejected(self) -> None:
        quotes = self.root / "option_quotes_daily.csv"
        write_csv(quotes, [{"contract_ticker": "O:ABC-C_K", "session": "2024-01-05",
            "mark_time_utc": "2024-01-05T21:00:00Z", "mark_time_et": "2024-01-05T16:00:00-05:00",
            "bid": "4", "ask": "6", "mid": "5", "bid_size": "3", "ask_size": "4",
            "spread": "2", "relative_spread": "0.4", "minutes_before_1600": "0",
            "source_job_id": "fixture-job"}])
        ingest_options(self.study, self.run / "gm-options-ingest", "fixture", quote_path=quotes)
        path = self.run / "gm-options-ingest" / "quotes.parquet"
        pq.write_table(pq.read_table(path).slice(0, 0), path)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            study_options(self.run / "gm-options-ingest", self.run / "gm-options-study", "fixture")

    def test_null_score_values_have_presence_flags_and_no_arrow_nulls(self) -> None:
        ingest_options(self.study, self.run / "gm-options-ingest", "fixture")
        scores_path = self.run / "scores.parquet"
        pq.write_table(pa.table({"date": ["2024-01-05"], "ticker": ["ABC"], "view": ["B"],
            "estimator": ["mahalanobis"], "depth": pa.array([None], type=pa.float64()),
            "pvalue": pa.array([None], type=pa.float64()), "inside": [True]}), scores_path)
        study_options(self.run / "gm-options-ingest", self.run / "gm-options-study", "fixture", scores_path)
        table = pq.read_table(self.run / "gm-options-study/event_features.parquet")
        self.assertEqual(table.column("score_depth").null_count, 0)
        feature = table.to_pylist()[0]
        self.assertTrue(math.isnan(feature["score_depth"]))
        self.assertFalse(feature["score_depth_present"])
        self.assertFalse(feature["score_pvalue_present"])

    def test_study_rejects_tampered_ingest_parquet(self) -> None:
        ingest_options(self.study, self.run / "gm-options-ingest", "fixture")
        path = self.run / "gm-options-ingest" / "bars.parquet"
        table = pq.read_table(path)
        pq.write_table(table.slice(0, 3), path)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            study_options(self.run / "gm-options-ingest", self.run / "gm-options-study", "fixture")

    def test_cli_runs_from_another_working_directory(self) -> None:
        script = Path(__file__).resolve().parents[1] / "tools" / "options_native.py"
        result = subprocess.run([sys.executable, str(script), "ingest", "--study-dir", str(self.study),
            "--output-dir", str(self.run / "gm-options-ingest"), "--run-id", "fixture"],
            cwd=self.root, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
