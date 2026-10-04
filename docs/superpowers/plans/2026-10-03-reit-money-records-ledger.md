# REIT step 3 execution ledger

Date: 2026-10-03. User authorized improving step 3 and deep research before a live collection pilot.

## Research and rulings

- Used parallel primary-source research for reporting semantics, extraction methods and actual REIT disclosure shapes. Corrected BXMT source date to Q4/full-year 2023; distinguished reproduced ASC 230 text from a new ASU 2016-15 rule.
- Ruling: retain the inexpensive CompanyFacts comparison, add bounded native source adapters, and keep uncertain financial meanings for review. No literature result establishes a universally best REIT OCR engine.
- Ruling: use a separate offline analyzer to preserve existing collector outputs and avoid re-running OCR. No new dependencies, network collection, models or training.
- Ruling: amount kind is separate from period type; custom names do not inherit standard concepts' meanings. No guessed loan identity, borrower, rate/maturity link, amount basis or transaction total.
- Ruling: preserve original duplicate observations for idempotent same-filing consolidation. Separate API comparisons from filing records rather than presenting them as extra movements.

## Delivered

- Task 1 complete: bounded context-aware Inline XBRL/extracted-instance adapter and HTML cell/grid adapter with source spans.
- Task 2 complete: typed reported observations, explicit review candidates, rounding-aware duplicate handling, hash-checked offline analysis and separate comparison export.
- Task 3 complete: primary-source research report, scoped README/audit continuation, portable synthetic fixture, focused verification and independent review.

## Regression evidence

- New modules started with missing-feature test failures, then implementation and passing focused runs.
- Review reproductions failed before fixes: missing context/unit references, unreported table truncation, deep XML recursion, second-pass duplicate metadata loss and nested quote amplification.
- Subsequent residuals also received regression fixes: truncated numeric prefixes, empty-row quota bypass and stale cached evidence paths after text artifact relocation.
- Additional source checks cover UTF-8 quote budgets, source/text mutations, outside-root paths, exact manifest-byte snapshot hash and cached text artifact path/hash.

## Final verification

- Fresh combined unittest: 102 tests passed in 2.016 seconds, exit 0 (15 inline, 18 tables, 16 records, 11 runner, plus 42 existing REIT/OCR tests).
- Four new modules compiled; analyzer CLI help and git diff --check passed.
- Synthetic offline run: complete processing, two parsed records, one review record and two candidates; repeated analysis reused one document. This is not a real-data accuracy or throughput benchmark.
- Independent final review: no remaining Critical or Important findings in the reviewed changes.
- Original source-guide URL count remains exactly 15.

## Remaining scope

- Out of scope: live collection, full XBRL taxonomy/transform support, verified interpretation of every loan term, native PDF table geometry, model/cloud OCR jobs, training and inferred refinancing links.
- Next verification: manually checked representative actual loan/cash tables across issuer/source types to measure amount/period/scope/row accuracy and missed disclosures before expanding.
- Live SEC requests still require a real contact email; no email was invented. No commit, push or deployment was performed. Unrelated shared-workspace changes were preserved.
