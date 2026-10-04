import unittest

from src.reit_inventory import build_inventory


def columns(rows):
    keys = ["accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "form", "primaryDocument"]
    return {key: [row.get(key, "") for row in rows] for key in keys}


def filing(year, n, form="10-K"):
    return {"accessionNumber": f"0000000123-{str(year)[2:]}-{n:06d}",
            "filingDate": f"{year}-03-01", "reportDate": f"{year - 1}-12-31",
            "acceptanceDateTime": f"{year}-03-01T16:10:00.000Z", "form": form,
            "primaryDocument": f"report{n}.htm"}


class InventoryTests(unittest.TestCase):
    def metadata(self, recent=None, pages=None):
        return [{"cik": "123", "submissions": {"cik": "123", "filings": {
            "recent": columns(recent or [filing(2026, 1)]), "files": [
                {"name": "CIK0000000123-submissions-001.json", "filingFrom": "2022-01-01",
                 "filingTo": "2025-12-31"}]}}, "historical_pages": pages or []}]

    def test_historical_pages_amendments_opening_context_and_exact_urls(self):
        page = {"name": "CIK0000000123-submissions-001.json", "data": columns([
            filing(2023, 1), filing(2024, 2), filing(2024, 3, "10-K/A"), filing(2022, 4)])}
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"}, self.metadata(pages=[page]))
        self.assertEqual(len(result["selected"]), 4)
        opening = next(row for row in result["selected"] if row["filing_date"] == "2023-03-01")
        self.assertEqual(opening["selection_reason"], "opening_context")
        amendment = next(row for row in result["selected"] if row["form"] == "10-K/A")
        self.assertEqual(amendment["url"], "https://www.sec.gov/Archives/edgar/data/123/000000012324000003/report3.htm")
        self.assertFalse(result["coverage"]["history_complete"])
        self.assertIn("document_inventory_unverified", result["coverage"]["gaps"])

    def test_missing_and_malformed_history_pages_are_visible(self):
        result = build_inventory({"ciks": ["123", "456"], "end_date": "2026-10-03"}, self.metadata())
        self.assertEqual(result["coverage"]["missing_history_pages"][0]["name"], "CIK0000000123-submissions-001.json")
        self.assertEqual(result["coverage"]["missing_ciks"], ["0000000456"])
        bad = {"name": "CIK0000000123-submissions-001.json", "data": {"accessionNumber": ["bad"]}}
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"}, self.metadata(pages=[bad]))
        self.assertEqual(len(result["coverage"]["metadata_errors"]), 1)

    def test_duplicate_pages_deduplicate_but_conflicts_are_not_hidden(self):
        row = filing(2026, 1)
        page = {"name": "CIK0000000123-submissions-001.json", "data": columns([row])}
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"}, self.metadata(pages=[page]))
        self.assertEqual(len(result["selected"]), 1)
        page["data"]["primaryDocument"][0] = "other.htm"
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"}, self.metadata(pages=[page]))
        self.assertIn("conflicting_filing_metadata", result["coverage"]["gaps"])

    def test_predecessor_and_externally_supplied_exhibit_evidence(self):
        doc = {"cik": "123", "accession": filing(2026, 1)["accessionNumber"],
               "url": "https://www.sec.gov/Archives/edgar/data/123/000000012326000001/ex101.htm", "type": "EX-10.1"}
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03", "predecessor_ciks": ["456"],
                                  "document_evidence": [doc]}, self.metadata())
        self.assertIn("0000000456", result["coverage"]["missing_ciks"])
        self.assertTrue(any(row["url"] == doc["url"] for row in result["documents"]))

    def test_primary_document_path_and_identity_rejected(self):
        row = filing(2026, 1)
        row["primaryDocument"] = "../outside.htm"
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"}, self.metadata(recent=[row]))
        self.assertEqual(result["selected"], [])
        self.assertTrue(result["coverage"]["metadata_errors"])

    def test_invalid_optional_array_and_page_cik_are_accounted(self):
        metadata = self.metadata()
        metadata[0]["submissions"]["filings"]["recent"]["reportDate"] = []
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"}, metadata)
        self.assertEqual(result["selected"], [])
        self.assertTrue(result["coverage"]["metadata_errors"])
        metadata = self.metadata()
        metadata[0]["submissions"]["cik"] = "456"
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"}, metadata)
        self.assertEqual(result["coverage"]["missing_ciks"], ["0000000123"])

    def test_no_opening_annual_is_explicit_coverage_gap(self):
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"}, self.metadata())
        self.assertIn("missing_opening_context", result["coverage"]["gaps"])

    def test_missing_end_date_is_deterministic_input_error(self):
        with self.assertRaises(ValueError):
            build_inventory({"ciks": ["123"]}, [])

    def test_metadata_provenance_retains_source_receipt(self):
        metadata = self.metadata()
        metadata[0]["source_sha256"] = "a" * 64
        metadata[0]["retrieved_at"] = "2026-10-03T12:00:00Z"
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"}, metadata)
        self.assertEqual(result["selected"][0]["metadata_sources"][0]["retrieved_at"], metadata[0]["retrieved_at"])

    def test_missing_requested_context_accession_remains_visible(self):
        accession = "0000000123-20-000001"
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03",
                                  "context_accessions": [accession]}, self.metadata())
        self.assertEqual(result["coverage"]["missing_context_accessions"], [accession])

    def test_safe_relative_sec_primary_paths_do_not_drop_whole_page(self):
        ownership = filing(2026, 2, "4")
        ownership["primaryDocument"] = "xslF345X05/ownership.xml"
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"},
                                 self.metadata(recent=[filing(2026, 1), ownership]))
        self.assertEqual(len(result["selected"]), 1)
        self.assertEqual(result["excluded"][0]["exclusion_reason"], "form_out_of_scope")

    def test_unsafe_exhibit_urls_are_not_selected(self):
        base = "https://www.sec.gov/Archives/edgar/data/123/000000012326000001/"
        for url in [base.replace("https://", "https://u:p@") + "ex.htm",
                    base.replace("www.sec.gov", "www.sec.gov:444") + "ex.htm",
                    base + "ex\n.htm", base + "ex\x7f.htm"]:
            with self.subTest(url=url):
                doc = {"cik": "123", "accession": filing(2026, 1)["accessionNumber"], "url": url}
                result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03",
                    "document_evidence": [doc]}, self.metadata())
                self.assertFalse(any(row["url"] == url for row in result["documents"]))
                self.assertTrue(any(row.get("source") == "document_evidence"
                    for row in result["coverage"]["metadata_errors"]))

    def test_conflicted_latest_annual_uses_last_unconflicted_opening(self):
        latest = filing(2023, 1)
        variant = {**latest, "primaryDocument": "other.htm"}
        page = {"name": "CIK0000000123-submissions-001.json",
                "data": columns([variant, filing(2022, 2)])}
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"},
            self.metadata(recent=[latest, filing(2026, 1)], pages=[page]))
        opening = [row for row in result["selected"] if row["selection_reason"] == "opening_context"]
        self.assertEqual([row["filing_date"] for row in opening], ["2022-03-01"])

    def test_only_conflicted_annual_leaves_opening_gap(self):
        latest = filing(2023, 1)
        page = {"name": "CIK0000000123-submissions-001.json",
                "data": columns([{**latest, "primaryDocument": "other.htm"}])}
        result = build_inventory({"ciks": ["123"], "end_date": "2026-10-03"},
            self.metadata(recent=[latest, filing(2026, 1)], pages=[page]))
        self.assertEqual(result["coverage"]["missing_opening_context_ciks"], ["0000000123"])


if __name__ == "__main__":
    unittest.main()
