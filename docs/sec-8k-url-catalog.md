# SEC 8-K URL catalog

Generated 2026-10-03 from the 1,630 distinct CIKs in `data/processed/tiger_8k_company_names.csv`. The full local output is `data/processed/sec_8k_urls/filings.csv`; `coverage.csv` lists every input company, and `manifest.json` records the run. These data files are ignored by Git. The public source is the [SEC EDGAR Submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

The catalog contains **285,831 unique CIK/accession rows**: 277,812 Form 8-K and 8,019 Form 8-K/A, dated 1994-01-05 through 2026-10-02. All 1,630 CIKs have complete Submissions API history coverage in this run. The audit found no duplicate CIK/accession pairs, malformed accession numbers, or non-SEC URL hosts.

Each row has CIK, local company name/ticker, form, filing/report/acceptance dates where available, accession, filing-index URL, primary-document URL when SEC metadata supplies a usable filename, complete-text URL, and source Submissions JSON URL. Archive links are **constructed from SEC metadata**, not individually checked. Spot checks returned HTTP 200 for index and complete-text URLs from 1994 and 1999, plus a 2024 index and primary document. The 4,280 blank primary-document cells include early filings and missing/unsafe filenames; the index and complete-text URLs remain present for those rows.

To regenerate, provide a real SEC contact email in `SEC_CONTACT_EMAIL`, then run `python scripts/export_sec_8k_urls.py`. The script caches SEC responses, defaults to five requests per second, includes older history files as well as the recent array, and stops on SEC access blocks. The cache and output are local research artifacts, not model-ready training data. SEC [fair-access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) sets a maximum of ten requests per second and asks automated clients to identify themselves.

The 1,630 filing CIKs are a source universe. Historical option quote coverage and dated tradable-symbol mappings must be checked separately before constructing option-reaction labels.
