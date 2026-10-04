# REIT real-filing pilot implementation plan

> **For agentic workers:** Use superpowers:executing-plans and superpowers:test-driven-development. Track steps with checkboxes. Preserve unrelated shared-workspace changes.

**Goal:** Measure whether the existing REIT money analyzer finds and correctly distinguishes selected loan and cash facts in actual company documents.

**Architecture:** Build a small source-checked answer key, run the existing offline analyzer on retained public documents, and compare its records and review candidates against the key. Separate retrieval of evidence from correct financial interpretation. Use the existing four-issuer list for the SEC extension; a locally retained Realty Income annual report permits an immediate PDF pilot without SEC requests.

**Tech Stack:** Python standard library, pypdfium2 for selected digital-text PDF pages, existing REIT analyzer, unittest, official company and SEC filings.

**Spec:** The user's direction to assume OCR is accurate and test the money interpretation layer; `docs/reit-money-extraction-research.md` defines the current layer and its limits.

## Global constraints

- Do not audit OCR accuracy or treat a recognized number as a verified financial meaning.
- Count capacity, undrawn availability, outstanding debt, loan assets, and actual period cash movements separately.
- Preserve issuer, entity, source URL/hash, page or table location, date, currency, unit scale, and sign.
- Report both evidence retrieval and automatic classification, with denominators from the checked answer key.
- Do not infer every bank transfer from public reports.
- A real SEC contact email is required before live SEC collector requests. Do not invent one.
- Keep the bounded pilot local; no bulk download, remote compute job, training, or paid API.

## Files

- `scripts/run_reit_filing_pilot.py`: prepare a manifest from a retained local PDF and score answer-key assertions against analyzer outputs.
- `tests/test_run_reit_filing_pilot.py`: targeted tests for evidence matching, classification scoring, and source hash/provenance.
- `configs/reit_pilot_gold.json`: manually checked answer key for sampled pages.
- `data/processed/reit_filing_pilot/`: generated run artifacts and reviewed result; no hand edits to analyzer output.
- `docs/reit-real-filing-pilot.md`: source-checked answer key, results, limitations, and next fixes.

### Task 1: Source-checked answer key and bounded input

- [x] Verify the retained Realty Income 2025 annual report hash and official URL; confirm the cash-flow and credit-facility pages in the source.
- [x] Record 14 specific assertions spanning borrower cash inflow/outflow, loan investment outflow, facility capacity, availability, and outstanding balance. Store normalized values and page references, not long verbatim text.
- [x] Add a small local manifest builder with tests first; validate PDF hash and cached text source identity.

### Task 2: Run and score existing analyzer

- [x] Write failing evaluator tests for evidence found/missed, correct classification, unknown/review status, and false promotion of a capacity to a cash flow.
- [x] Implement exact source/page/amount matching on sampled assertions; run existing analyzer once on the retained PDF with a bounded candidate limit.
- [x] Write machine-readable score plus human-readable examples, including candidate truncation and every checked assertion's result.

### Task 3: Focused improvement and extension

- [x] Inspect misses and false classifications; make the smallest safe fix with a regression test if the failure has a clear cause.
- [ ] If a SEC contact email is provided, run the four configured issuers within the collector's document/rate bounds, then inspect representative 10-K, agreement, and mortgage-REIT evidence. Otherwise retain the four-issuer extension as pending, not as an achieved live result.
- [x] Rerun focused tests and the pilot; self-review output provenance and report exact measured coverage, unresolved cases, and recommended next change.

## Rulings and execution record

- Ruling: use 14 assertions instead of 8–12, because the two pages provide six distinct facility meanings in addition to eight cash-flow rows. This slightly expands the manual denominator without adding document processing.
- Ruling: extract native text from only pages 69 and 85. Full-document extraction called for unavailable local Tesseract on other pages; selected pages have embedded text. This limits coverage to two pages and does not evaluate OCR.
- Initial score: 12/14 review candidates, 2 misses from line wrapping, 0 structured classifications.
- Fix: retain bounded two-line candidate spans where a PDF wrap separates a currency amount from its magnitude or financial noun. Regression test failed before the fix and passed after it.
- Final score: 14/14 review candidates, 0 misses, 0 structured classifications; 72 total candidates and 0 omitted at a 100-candidate cap. Focused suite: 69 tests passed.
- Final review found no important issue. Its minor conflicting-parsed-match finding was fixed with a failing-then-passing regression test.
- Pending dependency: a real SEC contact email for live collector requests. Four-issuer coverage is not included in the achieved score. An issuer-hosted AMT PDF was found, but its local download timed out.
