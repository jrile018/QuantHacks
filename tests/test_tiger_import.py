"""Offline checks for the repeatable Tiger data import."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.import_tiger import collect_data, render_sql


class TigerImportTests(unittest.TestCase):
    def test_collects_cache_manifest_and_csv_without_losing_text_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / ".massive_cache"
            cache.mkdir()
            (cache / "abc.json").write_text('{"results":[{"text":"O\'Brien"}]}', encoding="utf-8")
            output = root / "data" / "processed" / "smoke"
            output.mkdir(parents=True)
            (output / "manifest.json").write_text('{"tag":"test"}', encoding="utf-8")
            with (output / "events.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["cik", "ticker"])
                writer.writeheader()
                writer.writerow({"cik": "0000012", "ticker": "ABC"})

            files, runs, rows = collect_data(root)

            self.assertEqual(len(files), 3)
            self.assertEqual(len(runs), 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].data, {"cik": "0000012", "ticker": "ABC"})
            self.assertEqual(rows[0].run_id, runs[0].run_id)
            self.assertEqual(json.loads(files[0].body), {"results": [{"text": "O'Brien"}]})

    def test_sql_preserves_exact_file_bytes_and_escapes_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / ".massive_cache"
            cache.mkdir()
            (cache / "a'b.json").write_bytes(b'{"name":"O\'Brien"}\r\n')
            files, runs, rows = collect_data(root)

            sql = render_sql(files, runs, rows)

            self.assertIn("a''b.json", sql)
            self.assertIn("decode(", sql)
            self.assertIn("'base64'", sql)
            self.assertIn("CREATE SCHEMA IF NOT EXISTS quant_hacks", sql)
            self.assertIn("ON CONFLICT", sql)

    def test_identical_manifests_in_separate_directories_are_distinct_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, ticker in (("first", "AAA"), ("second", "BBB")):
                output = root / "data" / "processed" / name
                output.mkdir(parents=True)
                (output / "manifest.json").write_text('{"tag":"same"}', encoding="utf-8")
                (output / "events.csv").write_text(f"ticker\n{ticker}\n", encoding="utf-8")

            _, runs, rows = collect_data(root)

            self.assertEqual(len(runs), 2)
            self.assertEqual(len({run.run_id for run in runs}), 2)
            self.assertEqual(len({row.run_id for row in rows}), 2)


if __name__ == "__main__":
    unittest.main()
