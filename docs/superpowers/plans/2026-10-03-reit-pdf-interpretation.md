# REIT PDF interpretation implementation plan

> **For agentic workers:** Use superpowers:executing-plans and test-driven-development. Track steps below and preserve unrelated shared-workspace changes.

**Goal:** Replace the zero automatic classifications in the retained real PDF pilot with source-supported money records and run the authorized bounded SEC extension.

**Architecture:** A separate rule adapter consumes cached page text. It recognizes explicit annual cash-flow table and credit-note shapes, retaining amount-specific evidence and contextual evidence. The existing analyzer consolidates those records alongside XBRL observations and keeps unresolved candidates.

**Tech Stack:** Python standard library, existing pypdfium2 native text and REIT collector/analyzer, unittest.

**Spec:** `docs/superpowers/specs/2026-10-03-reit-pdf-interpretation-design.md`.

## Constraints and review focus

- Runtime never reads `configs/reit_pilot_gold.json`; that remains the evaluation key.
- Currency, period, scale, amount sign, instrument/entity scope and financial basis are independently required.
- Reject column-count/header conflicts and do not turn unknown dashes into numeric zero.
- Conditional capacity, committed capacity, undrawn availability and debt balance are separate concepts.
- Numeric evidence names the selected cell/amount; context evidence cannot masquerade as the selected amount during scoring.
- No OCR audit or compute-intensive job; this bounded run stays local.
- Preserve original baseline outputs and unrelated concurrent edits; no shared-workspace commits.

### Task 1: Bounded money rules

**Files:** create `src/reit_pdf_money.py`, `tests/test_reit_pdf_money.py`.

**Interface:** `extract_pdf_money(pages: list[dict], document: dict) -> dict` returns `records` and `issues`; each record has evidence and explicit money/context fields. It does not run OCR or fetch sources.

- [x] Write failing tests for annual table year columns, units, signs, mixed loan/equity investments, and missing/contradictory metadata.
- [x] Implement explicit currency-declaration recognition and strict supported cash-flow rows.
- [x] Write failing tests for facility commitments, conditional expansions, availability and outstanding debt across issuer/Fund sections.
- [x] Implement exact narrative rules, scope/date requirements, and source evidence.
- [x] Run the adapter tests and inspect unresolved cases.

### Task 2: Integrate and verify the real PDF

**Files:** modify `src/reit_money_records.py`, `scripts/analyze_reit_money.py`, `scripts/run_reit_filing_pilot.py`, corresponding tests.

- [x] Write failing integration/cache/scoring tests; selected amount evidence must distinguish different year columns in one row.
- [x] Add page 70 as currency context, preserving the original gold assertions on pages 69/85.
- [x] Integrate the adapter and new implementation hash; keep candidates and records in separate outputs.
- [x] Run to a new `realty_income_2025_meaning_v2` output directory and compare to all 14 unchanged assertions.
- [x] Fix concrete discrepancies with regression tests; inspect record evidence and each sampled financial meaning.

### Task 3: Authorized live extension and review

- [x] Run `collect_reit_financials.py` using the supplied contact email, 4 companies, 4 primary filings/company, 2 exhibits/filing, rate 2/second, to a fresh output directory.
- [x] Analyze retained live filings if collection succeeds; if SEC/network blocks, record receipts and stop that path while finishing the local fix.
- [x] Run focused REIT tests, fresh pilot, source/output hash checks, and final code review; fix meaningful findings.
- [x] Update the user report with exact automatic versus review counts, representative correct examples, and remaining supported-layout limits.

## Rulings

- The user explicitly authorized the planned fix and execution. Proceed with routine reversible design decisions instead of asking again for design approval.
- Add the reporting-currency note as a third input page; the scored financial sample remains the original two pages and original 14 facts.

## Execution record

Completed 2026-10-03.

- Added bounded PDF interpretation, currency context, selected amount/year evidence, analyzer integration and cache invalidation. Original 14 assertions and candidate-only baseline preserved.
- Fresh real PDF result: 14 correct automatic classifications, zero sampled misclassifications, review-only outcomes or misses; 44 generated records (41 parsed, 3 review), 74 candidates, zero omitted candidates.
- Authorized live SEC collection completed for AMT, AAT, BXMT and AGNC: 35 documents, 187 CompanyFacts observations. Offline analysis processed all 35; 638 parsed XBRL records, 4,470 review records, 1,927 review candidates. Coverage remains partial with 4,051 cap omissions and explicit format/quote warnings.
- Independent review found table-header leakage, ambiguous facility association and subsequent-capacity-state failures. Reproductions failed before fixes; regressions pass afterward. Final read-only review found no remaining material issue in its scope.
- Final focused suite passed 116 tests. Verified source/output/implementation hashes for both runs and 136 exact PDF evidence references.
- Report: docs/reit-real-filing-pilot.md. No OCR audit, paid model call, heavy compute, bulk ingestion or shared-workspace commit.
