"""Offline contract checks for the SEC 8-K URL export."""

import tempfile
import unittest
import csv
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from scripts.export_sec_8k_urls import SecAccessBlocked, collect, fetch_json, filing_rows


def payload(accessions, forms, documents, dates=None):
    return {
        "accessionNumber": accessions,
        "form": forms,
        "filingDate": dates or ["2024-01-05"] * len(accessions),
        "reportDate": dates or ["2024-01-04"] * len(accessions),
        "primaryDocument": documents,
    }


class FilingRowsTests(unittest.TestCase):
    def test_recent_and_older_histories_include_amendment_once(self):
        accession_a = "0001193125-24-000001"
        accession_b = "0001193125-23-000002"
        recent = payload([accession_a, accession_b], ["8-K", "10-Q"], ["a.htm", "b.htm"])
        older = payload([accession_a, "0001193125-22-000003"], ["8-K", "8-K/A"], ["a.htm", "amend.htm"])

        rows = filing_rows("0001090872", "Example Inc", {"filings": {"recent": recent}}, [older])

        self.assertEqual([row["form"] for row in rows], ["8-K", "8-K/A"])
        self.assertEqual(len({(row["cik"], row["accession"]) for row in rows}), 2)
        self.assertEqual(
            rows[0]["primary_document_url"],
            "https://www.sec.gov/Archives/edgar/data/1090872/000119312524000001/a.htm",
        )
        self.assertEqual(rows[0]["source_submissions_url"], "https://data.sec.gov/submissions/CIK0001090872.json")

    def test_no_8k_and_unsafe_primary_name(self):
        no_events = filing_rows(
            "0001090872", "Example Inc",
            {"filings": {"recent": payload(["0001193125-24-000001"], ["10-K"], ["annual.htm"]) }}, [],
        )
        self.assertEqual(no_events, [])
        bad_name = filing_rows(
            "0001090872", "Example Inc",
            {"filings": {"recent": payload(["0001193125-24-000001"], ["8-K"], ["../wrong.htm"]) }}, [],
        )
        self.assertEqual(bad_name[0]["primary_document_url"], "")
        self.assertTrue(bad_name[0]["index_url"].endswith("0001193125-24-000001-index.html"))

    def test_pre_2000_archive_uses_root_paths(self):
        old = payload(["0001005477-99-005774"], ["8-K"], ["old.htm"], ["1999-12-09"])
        rows = filing_rows("0001084869", "Example Inc", {"filings": {"recent": old}}, [])

        self.assertEqual(
            rows[0]["index_url"],
            "https://www.sec.gov/Archives/edgar/data/1084869/0001005477-99-005774-index.html",
        )
        self.assertEqual(
            rows[0]["complete_text_url"],
            "https://www.sec.gov/Archives/edgar/data/1084869/0001005477-99-005774.txt",
        )
        self.assertEqual(rows[0]["primary_document_url"], "")


class FetchTests(unittest.TestCase):
    def test_sec_access_block_stops_request(self):
        with tempfile.TemporaryDirectory() as directory:
            def forbidden(*_args, **_kwargs):
                raise HTTPError("https://data.sec.gov/example", 403, "Forbidden", {}, None)

            with self.assertRaises(SecAccessBlocked):
                fetch_json(
                    "https://data.sec.gov/example", Path(directory) / "response.json",
                    "QuantHaxs Research researcher@example.org", lambda: None, opener=forbidden,
                )


class CollectionTests(unittest.TestCase):
    def test_blocked_history_preserves_current_company_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "companies.csv"
            input_path.write_text("cik,company_name,tickers\n0001090872,Example Inc,EX\n0001084869,Other Inc,OT\n",
                                  encoding="utf-8")
            older = "CIK0001090872-submissions-001.json"
            recent = {"filings": {"recent": payload(["0001193125-24-000001"], ["8-K"], ["recent.htm"]),
                                  "files": [{"name": older}]}}

            with patch("scripts.export_sec_8k_urls.fetch_json",
                       side_effect=[recent, SecAccessBlocked("SEC returned HTTP 429")]) as fetch:
                manifest = collect(input_path, root / "output", "researcher@example.org")

            with (root / "output" / "filings.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(manifest["companies_processed"], 1)
            self.assertEqual(manifest["companies_complete"], 0)
            self.assertIn("HTTP 429", manifest["stopped"])
            self.assertEqual(fetch.call_count, 2)

    def test_later_history_failure_keeps_successful_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "companies.csv"
            input_path.write_text("cik,company_name,tickers\n0001090872,Example Inc,EX\n", encoding="utf-8")
            first = "CIK0001090872-submissions-001.json"
            second = "CIK0001090872-submissions-002.json"
            recent = {"filings": {"recent": payload(["0001193125-24-000001"], ["8-K"], ["recent.htm"]),
                                  "files": [{"name": first}, {"name": second}]}}
            older = payload(["0001193125-22-000003"], ["8-K/A"], ["old.htm"])

            with patch("scripts.export_sec_8k_urls.fetch_json", side_effect=[recent, older, URLError("offline")]):
                manifest = collect(input_path, root / "output", "researcher@example.org")

            with (root / "output" / "filings.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            with (root / "output" / "coverage.csv").open(encoding="utf-8", newline="") as handle:
                coverage = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(coverage[0]["status"], "incomplete_history")
            self.assertEqual(manifest["companies_complete"], 0)

    def test_malformed_main_payload_is_not_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "companies.csv"
            input_path.write_text("cik,company_name,tickers\n0001090872,Example Inc,EX\n", encoding="utf-8")

            with patch("scripts.export_sec_8k_urls.fetch_json", return_value={}):
                manifest = collect(input_path, root / "output", "researcher@example.org")

            self.assertEqual(manifest["companies_complete"], 0)

    def test_malformed_older_payload_keeps_recent_but_is_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "companies.csv"
            input_path.write_text("cik,company_name,tickers\n0001090872,Example Inc,EX\n", encoding="utf-8")
            older = "CIK0001090872-submissions-001.json"
            recent = {"filings": {"recent": payload(["0001193125-24-000001"], ["8-K"], ["recent.htm"]),
                                  "files": [{"name": older}]}}

            with patch("scripts.export_sec_8k_urls.fetch_json", side_effect=[recent, {}]):
                manifest = collect(input_path, root / "output", "researcher@example.org")

            with (root / "output" / "filings.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(manifest["companies_complete"], 0)

    def test_missing_first_history_does_not_shift_second_history_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "companies.csv"
            input_path.write_text("cik,company_name,tickers\n0001090872,Example Inc,EX\n", encoding="utf-8")
            first = "CIK0001090872-submissions-001.json"
            second = "CIK0001090872-submissions-002.json"
            recent = {"filings": {"recent": payload([], [], []),
                                  "files": [{"name": first}, {"name": second}]}}
            historical = payload(["0001193125-22-000003"], ["8-K"], ["amend.htm"])

            with patch("scripts.export_sec_8k_urls.fetch_json", side_effect=[recent, None, historical]):
                manifest = collect(input_path, root / "output", "researcher@example.org")

            with (root / "output" / "filings.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["source_submissions_url"], f"https://data.sec.gov/submissions/{second}")
            self.assertEqual(manifest["companies_complete"], 0)
            self.assertEqual(manifest["companies_processed"], 1)


if __name__ == "__main__":
    unittest.main()
