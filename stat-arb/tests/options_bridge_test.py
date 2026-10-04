import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.options_bridge import build_options_artifact


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class OptionsBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.study = self.root / "study"
        self.study.mkdir()
        (self.study / "manifest.json").write_text(json.dumps({"tag": "cfo_appointment", "event_count": 1}), encoding="utf-8")
        self.event = {"cik": "0000040533", "accession_number": "0001193125-24-003197", "ticker": "GD",
                      "filing_date": "2024-01-05", "event_date": "2024-01-05", "t_pre": "2024-01-04", "t_0": "2024-01-08"}
        write_csv(self.study / "events.csv", [self.event])
        write_csv(self.study / "results.csv", [{"ticker": "GD", "event_date": "2024-01-05", "t_0": "2024-01-08",
                                                  "bucket": "1m", "entry": "post", "entry_date": "2024-01-08",
                                                  "horizon": "5", "otm": "0.05", "long_call": "0.12"}])
        write_csv(self.study / "capacity.csv", [{"ticker": "GD", "event_date": "2024-01-05", "entry_date": "2024-01-08",
                                                   "bucket": "1m", "strategy": "long_call", "capacity_contracts": "2"}])

    def test_joins_only_exact_pre_event_view_b_scores(self) -> None:
        scores = self.root / "scores.csv"
        write_csv(scores, [
            {"date": "2024-01-04", "ticker": "GD", "view": "B", "estimator": "mahalanobis", "depth": "1.5", "inside": "0"},
            {"date": "2024-01-04", "ticker": "GD", "view": "B", "estimator": "kde", "depth": "0.8", "inside": "1"},
            {"date": "2024-01-08", "ticker": "GD", "view": "B", "estimator": "fastmcd", "depth": "99", "inside": "0"},
            {"date": "2024-01-04", "ticker": "GD", "view": "A", "estimator": "fastmcd", "depth": "88", "inside": "0"},
        ])
        out = self.root / "artifact"
        summary = build_options_artifact(self.study, out, scores)
        with (out / "outcomes.csv").open(newline="", encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row["event_id"], "CIK:0000040533:0001193125-24-003197:GD")
        self.assertEqual(row["score_date"], "2024-01-04")
        self.assertEqual(row["mahalanobis_depth"], "1.5")
        self.assertEqual(row["mahalanobis_inside"], "0")
        self.assertEqual(row["kde_depth"], "0.8")
        self.assertEqual(row["fastmcd_depth"], "")
        self.assertEqual(summary["scored_events"], 1)
        self.assertEqual(summary["outcome_rows"], 1)
        with (out / "capacity.csv").open(newline="", encoding="utf-8") as handle:
            self.assertEqual(next(csv.DictReader(handle))["event_id"], row["event_id"])

    def test_output_is_immutable(self) -> None:
        out = self.root / "artifact"
        build_options_artifact(self.study, out)
        with self.assertRaises(FileExistsError):
            build_options_artifact(self.study, out)

    def test_accepts_capacity_at_pre_event_entry_when_manifest_says_pre(self) -> None:
        (self.study / "manifest.json").write_text(
            json.dumps({"tag": "cfo_appointment", "event_count": 1, "entry": "pre"}), encoding="utf-8")
        write_csv(self.study / "capacity.csv", [{"ticker": "GD", "event_date": "2024-01-05", "entry_date": "2024-01-04",
                                                   "bucket": "1m", "strategy": "long_call", "capacity_contracts": "2"}])
        summary = build_options_artifact(self.study, self.root / "artifact")
        self.assertEqual(summary["capacity_rows"], 1)

    def test_rejects_result_with_no_event(self) -> None:
        write_csv(self.study / "results.csv", [{"ticker": "AAPL", "event_date": "2024-01-05", "t_0": "2024-01-08",
                                                  "bucket": "1m", "entry": "post", "entry_date": "2024-01-08",
                                                  "horizon": "5", "otm": "0.05", "long_call": "0.12"}])
        with self.assertRaisesRegex(ValueError, "no matching event"):
            build_options_artifact(self.study, self.root / "artifact")

    def test_rejects_duplicate_score_key(self) -> None:
        scores = self.root / "scores.csv"
        row = {"date": "2024-01-04", "ticker": "GD", "view": "B", "estimator": "kde", "depth": "1", "inside": "0"}
        write_csv(scores, [row, row])
        with self.assertRaisesRegex(ValueError, "duplicate score"):
            build_options_artifact(self.study, self.root / "artifact", scores)

    def test_rejects_event_date_before_pre_event_session(self) -> None:
        self.event["t_pre"] = "2024-01-09"
        write_csv(self.study / "events.csv", [self.event])
        with self.assertRaisesRegex(ValueError, "t_pre"):
            build_options_artifact(self.study, self.root / "artifact")

    def test_rejects_truncated_capacity_row(self) -> None:
        (self.study / "capacity.csv").write_text(
            "ticker,event_date,entry_date,bucket,strategy,capacity_contracts\n"
            "GD,2024-01-05,2024-01-08,1m,long_call\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing fields"):
            build_options_artifact(self.study, self.root / "artifact")


if __name__ == "__main__":
    unittest.main()
