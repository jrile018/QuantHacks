import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import collect_reit_financials as collector


class CollectorTests(unittest.TestCase):
    def test_default_pilot_starts_with_options_universe_reit(self):
        self.assertTrue(collector.DEFAULT_COMPANIES.is_absolute())
        companies = collector.load_reit_companies(collector.DEFAULT_COMPANIES)
        self.assertEqual(companies[:1][0]["tickers"], "AMT")

    def test_company_ciks_normalized_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "companies.csv"
            path.write_text("company_name,cik,sic\nFirst, 123456 ,6798\nDuplicate,0000123456,6798\n")
            rows = collector.load_reit_companies(path)
            self.assertEqual([(r["company_name"], r["cik"]) for r in rows], [("First", "0000123456")])

    def test_cofilers_keep_distinct_source_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            companies, out, cache, recent = self.fixture(Path(tmp))
            companies.write_text("company_name,cik,sic\nIssuer,123456,6798\nPartner,123457,6798\n")
            partner = out / "cache" / "0000123457"
            partner.mkdir()
            (partner / "submissions.json").write_bytes((cache / "submissions.json").read_bytes())
            accn = recent["accessionNumber"][0]
            (partner / (accn + ".htm")).write_bytes((cache / (accn + ".htm")).read_bytes())
            manifest = collector.collect(companies, out, offline=True, max_companies=2, max_exhibits_per_filing=0)
            self.assertEqual(len({d["text_path"] for d in manifest["documents"]}), 2)
            for doc in manifest["documents"]:
                saved = json.loads(Path(doc["text_path"]).read_text())
                self.assertEqual(saved["source_url"], doc["url"])
                self.assertEqual(saved["source_path"], doc["source_path"])
                self.assertIn(doc["cik"], doc["text_path"])
                saved["source_url"] = "https://www.sec.gov/wrong"
                Path(doc["text_path"]).write_text(json.dumps(saved))
            repeated = collector.collect(companies, out, offline=True, max_companies=2, max_exhibits_per_filing=0)
            self.assertTrue(all(not d["extraction_reused"] for d in repeated["documents"]))

    def test_requested_attempted_completed_counts_and_malformed_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            companies, out, cache, _ = self.fixture(Path(tmp))
            companies.write_text("company_name,cik,sic\nIssuer,123456,6798\nPartner,123457,6798\n")
            (cache / "submissions.json").write_text('{"filings": {"recent": {"accessionNumber": ["x"]}}}')
            manifest = collector.collect(companies, out, offline=True, max_companies=2)
            self.assertEqual(manifest["run_status"], "error")
            self.assertEqual(manifest["requested_company_count"], 2)
            self.assertEqual(manifest["attempted_company_count"], 1)
            self.assertEqual(manifest["completed_company_count"], 0)
            self.assertEqual(manifest["company_count"], 0)
            self.assertEqual(manifest["companies"][0]["status"], "error")
            (cache / "submissions.json").write_text('{"filings": {"recent": {}}}')
            manifest = collector.collect(companies, out, offline=True)
            self.assertEqual(manifest["run_status"], "complete")
            self.assertEqual(manifest["companies"][0]["coverage"]["filing_history"], "none_found")
            self.assertEqual(manifest["companies"][0]["coverage"]["periodic_forms_missing"], ["10-K", "10-Q"])
            self.assertTrue(any(w["stage"] == "periodic_coverage" for w in manifest["warnings"]))

    def test_checks_csv_preserves_reported_tolerance(self):
        with tempfile.TemporaryDirectory() as tmp:
            companies, out, _, _ = self.fixture(Path(tmp))
            with patch.object(collector, "cash_bridge_checks", return_value=[{"cik": "0000123456", "tolerance": 2500}]):
                collector.collect(companies, out, offline=True)
            with (out / "checks.csv").open(newline="") as handle:
                self.assertEqual(next(csv.DictReader(handle))["tolerance"], "2500")

    def fixture(self, root, forms=("10-Q",)):
        companies = root / "companies.csv"
        companies.write_text("company_name,cik,sic\nTrust A,123456,6798\n", encoding="utf-8")
        out = root / "out"
        cache = out / "cache" / "0000123456"
        cache.mkdir(parents=True)
        recent = {"accessionNumber": [f"0000123456-26-{i:06d}" for i in range(1, len(forms)+1)],
                  "form": list(forms), "filingDate": [f"2026-05-{i:02d}" for i in range(1, len(forms)+1)],
                  "primaryDocument": [f"doc{i}.htm" for i in range(1, len(forms)+1)]}
        (cache / "submissions.json").write_text(json.dumps({"filings": {"recent": recent}}))
        for accn in recent["accessionNumber"]:
            (cache / f"{accn}.htm").write_text("<p>Loan agreement</p>")
        return companies, out, cache, recent

    def test_periodics_reserved_and_amendment_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, recent = self.fixture(Path(tmp), ("10-K", "10-Q", "10-K/A", "8-K", "8-K"))
            recent["items"] = ["", "", "", "5.02", "2.03"]
            submissions = {"filings": {"recent": recent}}
            self.assertEqual([f["form"] for f in collector.select_filings("123456", submissions, 2)], ["10-Q", "10-K"])
            self.assertEqual(collector.select_filings("123456", submissions, 1)[0]["form"], "10-Q")
            selected = collector.select_filings("123456", submissions, 4)
            self.assertEqual({f["form"] for f in selected}, {"10-K", "10-Q", "10-K/A", "8-K"})
            self.assertEqual([f["items"] for f in selected if f["form"] == "8-K"], ["2.03"])

    def test_missing_facts_and_index_are_explicit_and_text_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            companies, out, _, _ = self.fixture(Path(tmp))
            with patch.object(collector, "document_text", wraps=collector.document_text) as extract:
                first = collector.collect(companies, out, offline=True)
                collector.collect(companies, out, offline=True)
                self.assertEqual(extract.call_count, 1)
                collector.collect(companies, out, offline=True, extraction_settings={"dpi": 180})
                self.assertEqual(extract.call_count, 2)
                with patch.object(collector, "EXTRACTION_REVISION", "changed"):
                    collector.collect(companies, out, offline=True, extraction_settings={"dpi": 180})
                self.assertEqual(extract.call_count, 3)
            self.assertEqual(first["companies"][0]["coverage"]["companyfacts"], "unavailable")
            self.assertTrue(first["warnings"])
            self.assertIn("collected_at", first)

    def test_index_exhibits_are_safe_bounded_and_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            companies, out, cache, recent = self.fixture(Path(tmp))
            accn = recent["accessionNumber"][0]
            rows = [("Earnings", "earn.htm", "EX-99.1"), ("Credit agreement", "loan.htm", "EX-10.1"),
                    ("Indenture", "note.htm", "EX-4.1"), ("Unsafe", "../evil.htm", "EX-10.2")]
            html = '<table summary="Document Format Files">' + ''.join(
                f'<tr><td>1</td><td>{desc}</td><td><a href="{name}">{name}</a></td><td>{kind}</td></tr>'
                for desc, name, kind in rows) + '</table>'
            (cache / f"{accn}-index.html").write_text(html)
            exhibit_dir = cache / accn / "exhibits"
            exhibit_dir.mkdir(parents=True)
            for name in ("loan.htm", "note.htm", "earn.htm"):
                (exhibit_dir / name).write_text("<p>Financing evidence</p>")
            manifest = collector.collect(companies, out, offline=True)
            exhibits = [d for d in manifest["documents"] if d["document_role"] == "exhibit"]
            self.assertEqual([d["filename"] for d in exhibits], ["loan.htm", "note.htm"])
            self.assertEqual(exhibits[0]["sec_type"], "EX-10.1")
            self.assertEqual(exhibits[0]["description"], "Credit agreement")
            self.assertEqual(len({d["text_path"] for d in manifest["documents"]}), 3)

    def test_block_is_sticky_and_partial_outputs_survive(self):
        for code in (403, 429):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                companies, out, cache, _ = self.fixture(root)
                (cache / "companyfacts.json").write_text('{"facts": {}}')
                calls = []
                def blocked(request, timeout):
                    calls.append(request.full_url)
                    raise HTTPError(request.full_url, code, "Blocked", {}, None)
                with patch.object(collector, "urlopen", side_effect=blocked):
                    manifest = collector.collect(companies, out, contact_email="research@example.org")
                    client = collector.SecClient(out, "research@example.org")
                    for name in ("a", "b"):
                        with self.assertRaises(collector.SecAccessBlocked):
                            client.read("https://www.sec.gov/a", root / name)
                self.assertEqual(len(calls), 2)
                self.assertEqual(manifest["run_status"], "blocked")
                self.assertEqual(manifest["document_count"], 1)
                self.assertTrue(manifest["errors"])
                self.assertTrue((out / "facts.csv").exists())
                self.assertTrue((out / "manifest.json").exists())

    def test_http404_facts_still_collects_and_other_errors_preserve_receipt(self):
        for code in (404, 500):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                companies, out, _, _ = self.fixture(Path(tmp))
                def failure(request, timeout):
                    raise HTTPError(request.full_url, code, "Missing", {}, None)
                with patch.object(collector, "urlopen", side_effect=failure):
                    manifest = collector.collect(companies, out, contact_email="research@example.org",
                                                 max_exhibits_per_filing=0)
                self.assertEqual(manifest["run_status"], "complete" if code == 404 else "error")
                self.assertEqual(manifest["document_count"], 1 if code == 404 else 0)
                self.assertIn(code, [r.get("http_status") for r in manifest["companies"][0]["metadata_receipts"]])

    def test_invalid_extracted_cache_and_changed_raw_are_reprocessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            companies, out, cache, recent = self.fixture(Path(tmp))
            collector.collect(companies, out, offline=True)
            text_path = out / "text" / "0000123456" / recent["accessionNumber"][0] / "doc1.htm.json"
            text_path.write_text("[]")
            manifest = collector.collect(companies, out, offline=True)
            self.assertEqual(manifest["run_status"], "complete")
            (cache / (recent["accessionNumber"][0] + ".htm")).write_text("<p>Changed source</p>")
            manifest = collector.collect(companies, out, offline=True)
            self.assertFalse(manifest["documents"][0]["extraction_reused"])
            self.assertIn("Changed source", text_path.read_text())

    def test_stale_or_corrupt_metadata_refreshes_online(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "submissions.json"
            cache.write_text('{"old": true}', encoding="utf-8")
            os.utime(cache, (1, 1))
            responses = []

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self, limit):
                    return b'{"new": true}'

            def fetch(request, timeout):
                responses.append(request.full_url)
                return Response()

            client = collector.SecClient(Path(tmp), "research@example.org", rate=2)
            url = "https://data.sec.gov/submissions/CIK0000123456.json"
            with patch.object(collector, "urlopen", side_effect=fetch):
                self.assertEqual(client.read_json(url, cache, max_age_seconds=3600), {"new": True})
                cache.write_text("broken JSON", encoding="utf-8")
                self.assertEqual(client.read_json(url, cache, max_age_seconds=3600), {"new": True})
            self.assertEqual(len(responses), 2)

    def test_direct_script_help_runs(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "collect_reit_financials.py"
        result = subprocess.run([sys.executable, str(script), "--help"],
                                cwd=script.parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--offline", result.stdout)

    def test_reit_filter_and_safe_filing_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "companies.csv"
            path.write_text("company_name,cik,sic,tickers\nTrust A,0000123456,6798,AAA\nOther,0000000001,6021,BBB\n", encoding="utf-8")
            self.assertEqual([row["cik"] for row in collector.load_reit_companies(path)], ["0000123456"])
        recent = {"accessionNumber": ["0000123456-26-000001", "0000123456-26-000002", "bad"],
                  "form": ["10-Q", "8-K", "10-K"], "filingDate": ["2026-05-01"] * 3,
                  "primaryDocument": ["quarter.htm", "current.htm", "../evil.htm"]}
        selected = collector.select_filings("0000123456", {"filings": {"recent": recent}}, 1)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["url"], "https://www.sec.gov/Archives/edgar/data/123456/000012345626000001/quarter.htm")

    def test_offline_run_writes_source_linked_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            companies = root / "companies.csv"
            companies.write_text("company_name,cik,sic,tickers\nTrust A,0000123456,6798,AAA\n", encoding="utf-8")
            out = root / "output"
            cache = out / "cache" / "0000123456"
            cache.mkdir(parents=True)
            (cache / "submissions.json").write_text(json.dumps({"filings": {"recent": {
                "accessionNumber": ["0000123456-26-000001"], "form": ["10-Q"],
                "filingDate": ["2026-05-01"], "primaryDocument": ["quarter.htm"]}}}), encoding="utf-8")
            fact = {"val": 100, "accn": "0000123456-26-000001", "start": "2026-01-01",
                    "end": "2026-03-31", "filed": "2026-05-01", "form": "10-Q"}
            (cache / "companyfacts.json").write_text(json.dumps({"facts": {"us-gaap": {
                "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [fact]}}}}}), encoding="utf-8")
            (cache / "0000123456-26-000001.htm").write_text("<html><body><p>Debt repayment of $100 million.</p></body></html>", encoding="utf-8")
            manifest = collector.collect(companies, out, offline=True, max_companies=1, max_filings_per_company=1)
            self.assertEqual(manifest["company_count"], 1)
            self.assertEqual(manifest["document_count"], 1)
            self.assertEqual(manifest["documents"][0]["source_method"], "html_native_text")
            self.assertIn("Debt repayment", Path(manifest["documents"][0]["text_path"]).read_text(encoding="utf-8"))
            with (out / "facts.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["accession"], "0000123456-26-000001")
            self.assertEqual(rows[0]["metric"], "operating")
            self.assertEqual(rows[0]["data_sha256"], manifest["companies"][0]["coverage"]["companyfacts_sha256"])
            self.assertEqual(Path(rows[0]["data_path"]), (cache / "companyfacts.json").resolve())
            self.assertTrue((out / "checks.csv").exists())

    def test_live_403_stops_without_retry(self):
        calls = []

        def blocked(request, timeout):
            calls.append(request.full_url)
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)

        with tempfile.TemporaryDirectory() as tmp, patch.object(collector, "urlopen", side_effect=blocked):
            client = collector.SecClient(Path(tmp), "research@example.org", rate=2)
            with self.assertRaises(collector.SecAccessBlocked):
                client.read("https://data.sec.gov/submissions/CIK0000123456.json", Path(tmp) / "submissions.json")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
