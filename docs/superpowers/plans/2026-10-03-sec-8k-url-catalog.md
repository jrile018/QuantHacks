# SEC 8-K URL Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export every SEC Submissions-listed historical 8-K and 8-K/A URL for the 1,630 CIKs in `data/processed/tiger_8k_company_names.csv`.

**Architecture:** A standalone standard-library CLI fetches each CIK's Submissions JSON and every older history file listed in `filings.files`. It caches exact responses, stops on SEC access blocks, deduplicates accessions, and writes a single sortable CSV plus coverage metadata. No SEC document bodies, OCR, or model training occur in this catalog step.

**Tech Stack:** Python 3.10+ standard library, SEC public EDGAR Submissions API, `unittest`.

**Spec:** `docs/8k-anticipation-research-concept.md` and `docs/company-source-map.md`.

## Global Constraints

- Use the 1,630 CIKs from the local company-name export; never substitute today's ticker list.
- Send a real contact email only in the request User-Agent; never write it to catalog outputs.
- Remain below the SEC's 10-request-per-second aggregate ceiling; default to 5 per second in one process.
- Include 8-K/A amendments and preserve exact SEC accession, filing date, report date, and source metadata.
- Mark archive URLs as constructed from SEC-listed accessions and primary document names; do not call them individually verified.
- Keep local downloaded SEC responses and outputs under ignored `data/processed/`.

## Review Focus

- A CIK with no 8-Ks produces a coverage row and no false filing URL.
- Older `filings.files` histories are included, not just the `recent` arrays.
- Duplicate accessions from recent/older files appear once.
- Malformed or missing primary-document names never create unsafe or invented document URLs.
- HTTP 403/429 stops collection and preserves cached progress for resumption.

---

### Task 1: Offline manifest behavior

**Files:**
- Create: `tests/test_sec_8k_urls.py`
- Create: `scripts/export_sec_8k_urls.py`

**Interfaces:**
- Consumes: SEC Submissions `filings.recent` column arrays and historical files in `filings.files`.
- Produces: `filing_rows(cik, company_name, submission, history_payloads)` returning sorted dictionaries with canonical SEC URLs.

- [x] Write offline tests for the Review Focus conditions using miniature SEC JSON fixtures and an injected fetcher.
- [x] Run `python -m unittest tests.test_sec_8k_urls -v` and observe missing-interface failures.
- [x] Implement the parser, URL construction, and cache-aware fetch workflow.
- [x] Run the targeted tests and confirm every fixture passes.

### Task 2: Real SEC collection and output audit

**Files:**
- Modify: `scripts/export_sec_8k_urls.py`
- Create at run time: `data/processed/sec_8k_urls/filings.csv`, `coverage.csv`, `manifest.json`, `cache/`.

**Interfaces:**
- Consumes: `data/processed/tiger_8k_company_names.csv` and an environment-provided SEC contact email.
- Produces: one row per unique CIK/accession and coverage for all 1,630 input CIKs.

- [x] Confirm the input CIK count and a usable SEC contact User-Agent without printing the email.
- [x] Run a one-CIK live pilot; verify a real SEC-listed accession and the CSV schema.
- [x] Run the full resumable collection; stop and report access blocks rather than fabricating a complete catalog.
- [x] Verify coverage counts, duplicate-free `(CIK, accession)` keys, allowed URL hosts, and sample links.
- [x] Provide the full CSV file link, open the smaller coverage file in Codex, and report URL count, date coverage, and unresolved CIKs.

Model training is a second plan: its prediction label, historical text availability, and OCR inputs must be defined before a truthful training/evaluation run.
