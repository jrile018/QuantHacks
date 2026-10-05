"""Synthetic tests for the biologics-fds-daily adapter."""

from pathlib import Path
import tempfile
import unittest

from src.biologics_fds_daily_adapter import describe_csv, validate_folder, validate_keys


class BiologicsFdsDailyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_valid_keys_and_describe(self):
        path = self.write("fds_features.csv", "cik,date,x\n1,20240102,0.5\n1,20240103,0.6\n")
        self.assertEqual(validate_keys(path), [])
        info = describe_csv(path)
        self.assertEqual(info["rows"], 2)
        self.assertEqual(info["columns"], ["cik", "date", "x"])

    def test_bad_date_and_duplicate(self):
        path = self.write("fds_features.csv", "cik,date\n1,2024-01-02\n1,20240103\n1,20240103\n")
        errors = validate_keys(path)
        self.assertEqual(len(errors), 2)

    def test_missing_key_column(self):
        path = self.write("fds_features.csv", "ticker,date\nA,20240102\n")
        self.assertEqual(len(validate_keys(path)), 1)

    def test_folder_reports_missing_files(self):
        self.write("fds_features.csv", "cik,date\n1,20240102\n")
        self.assertEqual(len(validate_folder(self.root)), 2)


if __name__ == "__main__":
    unittest.main()
