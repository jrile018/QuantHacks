# REIT money record extraction design

## Intent and scope

The user explicitly requested improving step 3 (organizing loan and money details) and deep research before a live collection pilot. Deliver inexpensive local extraction of source-backed reported facts plus clearly unresolved loan-table/agreement candidates. No paid OCR, model training, corpus ingestion, live SEC collector run, deployment or unrelated cleanup is authorized by this step.

Success means values retain their entity, concept, period, dimensions, unit, amount meaning and original evidence. Unknown fields remain unknown. A commitment, debt balance, loan asset, fair value, derivative notional and cash movement are not interchangeable. A duration context alone never establishes a cash movement. Public disclosure is not a complete bank transaction ledger.

## Selected approach

Use existing CompanyFacts as a cheap standard entity-wide comparison source. Inspect retained original HTML/Inline XBRL locally for custom and dimensional monetary facts and actual table structure. Preserve scanned/PDF evidence from the existing extraction cache without re-running OCR. Escalation to table OCR or a model is a later measured decision, not an implicit part of this implementation.

Alternatives considered: CompanyFacts alone omits material custom/dimensional detail; a model over every page adds cost without establishing numerical accuracy. A full XBRL processor is the preferred future fallback for unsupported transformations/taxonomy validation, but is not installed. The local adapter therefore supports an explicitly bounded subset and flags unsupported content; it does not claim full XBRL conformance.

## Data contract

- Reported monetary observations store issuer CIK, context entity, accession, filing/report dates, concept namespace/local name, exact period type/start/end/instant, explicit/typed dimensions, unit, reported precision and normalized decimal value as a string.
- Amount kind is independent of period type. Standard curated concepts classify flows or balances; custom concepts retain unknown meaning and review flags.
- Inline facts apply only supported QName-resolved numeric transformations, scale, then sign. Nil is unknown, not zero. Unsupported transformations, invalid contexts/units, fractions or target attributes stay unresolved.
- Duplicate identity includes accession, concept namespace, context entity/period/dimensions and unit. Complete or rounded-consistent duplicates retain all evidence; inconsistent duplicates are withheld from ready records. Do not combine different concepts or reporting scopes. Across filings, observations remain distinct; no inferred transaction deduplication.
- HTML table candidates retain real cells and spanning-cell grid structure, source character offsets, raw cell text, captions/context and unresolved semantics. No guessed unit, date, borrower, maturity, amount basis or column association becomes an accepted fact.
- Narrative/PDF candidates retain bounded relevant quotes, page/character evidence and quality flags. Interest rates and maturity references are not attached to another amount merely by proximity.
- Every record includes source URL/path/hash and evidence locator; no inferred aggregate totals, derived quarterly flows, automatic refinancing links or currency conversion.

## Integration and cost

Add a separate offline analyzer that consumes the collector manifest, original files, cached extracted text and standard facts. Write money_records.jsonl, review_candidates.jsonl, comparison_facts.jsonl and analysis_manifest.json. Standard CompanyFacts observations remain in the separate comparison file rather than appearing as additional filing movements. Validate source hashes before use, constrain source paths to the collection root and publish files atomically. Cache each document analysis by source and extraction hashes, settings and analyzer revision; expose cache reuse and incomplete coverage. Keep original facts.csv/checks.csv formats stable.

Bound review candidates per document with explicit truncation counts; parsing limits must be visible rather than silently claiming complete coverage. Original 15-source URL guide remains unchanged. Default implementation uses Python standard-library parsers only; no new dependencies.

## Verification

Use synthetic fixtures modeled on actual AAT/BXMT/AGNC disclosure shapes: facility capacity vs balance, lender loan principal vs book value, repo exposure vs commitment, multi-level table headers, exact periods, currency/scale/sign/nil, QName aliases, inconsistent duplicates, source mutation and repeated offline runs. Test meaningful field/evidence behavior, not just implementation mirrors. A representative real-document benchmark remains required before claiming measured REIT accuracy or a best OCR engine.
