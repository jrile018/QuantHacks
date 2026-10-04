# REIT workflow audit execution ledger

Date: 2026-10-03. Scope: improve bounded collection of public REIT loan and cash-movement evidence while preserving inexpensive extraction.

## Completed work

- Audited collector coverage, financial fact semantics and OCR independently. Checked primary SEC, FASB, XBRL US, PDFium and Tesseract documentation and an actual financing filing index.
- Used failing-then-passing focused regressions for collector selection/cache/error handling, cash bridges and PDF quality behavior.
- Implemented periodic-first filing selection, bounded agreement/supplement discovery, strict extraction reuse, CIK-scoped artifact identities and explicit coverage/error receipts.
- Corrected the pilot universe: AMT from the configured options universe is first; AAT, BXMT and AGNC are explicit comparison issuers. Retained the broader Tiger CSV as an optional input.
- Expanded standard monetary facts, labeled balances separately from flows, preserved currencies and overlapping tags, and matched cash bridges by accession/period/cash basis/FX treatment. Unknown rounding precision remains unknown; the API is not assumed to supply precision.
- Added hybrid-PDF detection, review flags, OCR word coordinates, engine/settings provenance, force-OCR/segmentation controls and resource cleanup.
- Updated the REIT/OCR README sections and wrote `docs/reit-workflow-audit.md`. Preserved unrelated shared-workspace changes.
- Reviewed the separate GLM/batch implementation read-only. It is an optional unverified GPU route, not an integrated or accuracy-proven REIT fallback.

## Verification evidence

- Focused unittest run: 42 passed, exit 0 (16 collector, 11 facts, 15 OCR).
- Three audited modules passed `py_compile`; collector `--help` and `git diff --check` passed.
- Wider unittest discovery: 130 tests, three errors in separate concurrent components (two unavailable-pytest imports; one options-learning IndexError).
- Independent code review completed; the reported tolerance-export omission was corrected. Recheck found no residual Critical/Important issue in the audited changes.

## Remaining limits and next evidence

- No live SEC API pilot ran: a real contact email for the User-Agent remains unavailable. No invented identity was used.
- Public filings cannot expose every bank transfer. Standard CompanyFacts do not cover all custom/dimensional loans or debt terms.
- Original debt/loan table and agreement-term extraction is the highest-value next implementation after a small pilot establishes the missing fields.
- OCR engines have not been ranked by actual REIT amount/sign/unit/period/row accuracy. Evaluate a small representative checked sample before additional model or cloud costs.
- No commit, push, deployment, paid OCR, training or bulk ingestion was performed for this audit.
