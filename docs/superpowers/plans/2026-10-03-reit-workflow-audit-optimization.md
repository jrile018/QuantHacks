# REIT workflow audit and optimization plan

> **For agentic workers:** Use the executing-plans and test-driven-development skills. Preserve unrelated shared-workspace changes.

**Goal:** Improve loan/money-movement document coverage and reuse extraction while keeping each run bounded and auditable.

**Architecture:** Retain CIK-keyed SEC collection and CompanyFacts as a cheap standard-tag first pass. Reserve periodic filing coverage, discover bounded financing/earnings exhibits, cache extraction by source hash and revision, and report source/coverage gaps explicitly. Improve PDF quality diagnostics without adding paid OCR.

**Spec:** User request to audit and optimize the existing workflow for REIT loan and money movements; docs/reit-loan-and-money-movement-sources.md.

## Constraints

- Public reports are evidence of disclosed amounts/terms; they cannot expose every bank transaction.
- Never sum debt/loan balance snapshots with cash flow amounts or overlapping detail tags.
- Missing, ambiguous, and unverified facts must remain explicit.
- Every fetch is rate limited; 403/429 stop further SEC requests and preserve completed work.
- No live SEC pilot without the real contact email; no bulk backfill or model/cloud OCR costs.

## Tasks

1. **Collector coverage and reuse** — owner: collection worker; files scripts/collect_reit_financials.py, tests/test_collect_reit_financials.py. Test-first fixes for periodic-first bounded selection, amendments, EX-10/4/99 index discovery, source-hash/revision extraction reuse, missing CompanyFacts, controlled 403/429 stop with partial manifest, and per-company coverage receipts.
2. **Facts and OCR accuracy** — owner: root for src/reit_cash_facts.py/tests; OCR worker only src/document_ocr.py/tests. Test-first fixes for alternate cash bridges, flow/balance labeling, source precision scope and diagnostics, OCR resource/provenance controls and low-confidence review flags. No inferred transaction parser.
3. **Evidence and verification** — root writes docs/reit-workflow-audit.md and updates only the REIT/OCR README sections. Test focused changed modules; run lightweight full suite once to establish shared-workspace status; final code review and fix concrete findings.

## Review focus

- Recent unrelated 8-Ks cannot displace every periodic financial report.
- Exhibits are bounded, classified using SEC document type, and stored separately.
- Identical source bytes are not re-OCRed across runs; settings/revision changes invalidate text cache.
- Missing XBRL coverage does not suppress available source documents.
- Cash-only and cash-plus-restricted-cash bridge components are not mixed; unknown precision is never invented.

## Completion evidence

All three tasks completed locally. See `2026-10-03-reit-workflow-audit-optimization-ledger.md` for changes and verification. The 42 focused tests pass and independent review has no remaining Critical/Important finding. Live collection and REIT table accuracy remain unverified until a real-contact SEC pilot and checked document sample are available.
