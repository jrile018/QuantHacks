# REIT Document Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect recent SEC financial documents for REIT CIKs, reuse digital text, OCR scanned PDF pages only, and produce source-linked cash-flow facts with arithmetic checks.

**Architecture:** Extend the existing OCR module with per-page text detection. Add a small SEC collector that uses CIKs from the local REIT export, caches submissions and Company Facts, downloads selected recent primary filings, and writes extracted text and fact/check CSVs. Keep original files and source URLs. The run is bounded by explicit company and filing limits.

**Tech Stack:** Python 3.10+, standard library, existing optional pypdfium2/Pillow/pytesseract.

**Spec:** `docs/reit-loan-and-money-movement-sources.md` and the user-approved four-step collection rule in this chat.

## Global Constraints

- Use SIC 6798 only as a candidate filter; a CIK identifies the issuer.
- Require a real contact email for live SEC requests and cap the single-process request rate below 10/second.
- Keep raw downloads and derived results under ignored `data/` directories.
- Distinguish commitments, flows and balances. Never claim Company Facts includes all custom/dimensional facts.
- Preserve exact filing accession, period, unit, URL and extraction method.

## Review Focus

- A born-digital PDF page must not invoke Tesseract.
- A mixed PDF must OCR only the image-only page while retaining page order.
- Missing Company Facts tags must yield an explicit incomplete check, not a zero.
- Two facts from different periods or accessions must never be combined in one cash bridge.
- SEC access denial must stop the live run without a flood of retries.

---

### Task 1: Selective PDF extraction

**Files:** Modify `src/document_ocr.py`; modify `tests/test_document_ocr.py`.

**Interfaces:** `extract_document(path, ...) -> OCRDocument` remains callable; each page gains an extraction method field.

- [x] Write tests with a fake PDFium document for one native page and one scanned page; assert the OCR call count is one and page order is preserved. Also assert native-only PDFs work without Tesseract.
- [x] Run `python -m unittest tests.test_document_ocr -v`; confirm the new tests fail for the missing behavior.
- [x] Extract native page text through PDFium's text page, rasterize only pages with insufficient native text, and record per-page `native_pdf_text` or `tesseract_ocr`.
- [x] Run `python -m unittest tests.test_document_ocr -v`; expect zero failures.

### Task 2: Source-linked financial facts and cash bridge

**Files:** Create `src/reit_cash_facts.py`; create `tests/test_reit_cash_facts.py`.

**Interfaces:** `cash_flow_rows(cik, companyfacts) -> list[dict]`; `cash_bridge_checks(rows) -> list[dict]`.

- [x] Write tests using synthetic Company Facts: select cash/debt movement tags, preserve accession/period/unit and CIK, and reconcile operating + investing + financing + FX to reported cash change only within one matching context.
- [x] Run `python -m unittest tests.test_reit_cash_facts -v`; confirm missing-module/behavior failure.
- [x] Implement the tag map and arithmetic-only checks; mark missing or mismatched contexts `incomplete` instead of inventing values.
- [x] Run `python -m unittest tests.test_reit_cash_facts -v`; expect zero failures.

### Task 3: Bounded SEC collection command

**Files:** Create `scripts/collect_reit_financials.py`; create `tests/test_collect_reit_financials.py`; update `README.md`.

**Interfaces:** CLI accepts `--companies-csv`, `--output-dir`, `--contact-email`, `--max-companies`, `--max-filings-per-company`, `--rate`, and `--offline`. Outputs a manifest, original downloaded filings, per-page text, facts CSV and checks CSV.

- [x] Write offline fixture tests for SIC filter, filing selection, URL construction, cached downloads, source/provenance outputs and SEC 403 handling.
- [x] Run `python -m unittest tests.test_collect_reit_financials -v`; confirm missing-command/behavior failure.
- [x] Implement the CLI with safe URL construction, bounded recent 10-K/Q/8-K selection, caching, per-document extraction and CSV/JSON outputs. Add usage to the README.
- [x] Run the targeted tests, then `python -m unittest discover -s tests -v`; expect zero failures.
- [x] Run an offline pilot fixture and inspect output. If a real SEC contact email is available, run one live REIT and inspect the manifest, text methods, facts and checks. (No contact email was provided; offline fixture and 49-test suite passed.)
