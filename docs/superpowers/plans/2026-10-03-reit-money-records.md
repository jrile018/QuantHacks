# REIT money records implementation plan

> **For agentic workers:** Use executing-plans and test-driven-development. Preserve unrelated shared-workspace changes. Tasks use checkbox tracking.

**Goal:** Improve step 3 with inexpensive, auditable financial observations and reviewable loan-table evidence before a live pilot.

**Architecture:** A bounded Inline XBRL adapter and a source-preserving HTML table parser feed a separate offline money-record analyzer. Existing SEC CompanyFacts and cash checks remain comparison outputs. Unsupported semantics and formats become explicit review items.

**Tech Stack:** Python standard library, unittest, existing collector/OCR artifacts; no new dependencies or model calls.

**Spec:** docs/superpowers/specs/2026-10-03-reit-money-records-design.md.

## Global constraints

- No live collection, paid OCR, training, corpus ingestion or deployment.
- No inferred totals, currency conversions, quarterly-flow derivations or loan links.
- Keep period type separate from amount kind, preserve unknown values and all reporting scopes.
- Parse only explicitly supported Inline XBRL transformations; fail closed on ambiguity.
- Preserve source hashes, locators, units, dimensions, date context and precise decimal strings.
- Preserve unrelated files and existing output formats; do not commit shared concurrent work.

## Review focus

- Namespace aliases or spoofed namespaces cannot change numeric/semantic interpretation.
- Nil/blank/dash values, units, scale, signs and precision must not become guessed amounts.
- Parent/OP contexts, distinct dimensions, year-to-date periods and different filings stay separate.
- Span/nested HTML tables cannot silently merge wrong rows or columns.
- Changed/missing/outside-root sources invalidate reuse and remain explicit incomplete coverage.

### Task 1: Original source adapters

**Files:** create src/reit_inline_facts.py and tests/test_reit_inline_facts.py; create src/reit_tables.py and tests/test_reit_tables.py. Inline owner root; tables may be assigned independently.

**Interfaces:** `extract_inline_facts(raw: bytes) -> dict` returns facts and issues; `extract_html_tables(text: str) -> list[dict]` returns tables with cells/grid/flags and exact HTML character spans. Facts retain concept/context/unit/evidence and decimal values; semantic classification is owned by Task 2.

- [x] Write numeric/context tests first, including supported QName aliases, unsupported formats, sign/scale/precision independence, nil, units, instant/duration, typed dimensions and malformed XML.
- [x] Run `.venv/Scripts/python.exe -m unittest tests.test_reit_inline_facts -v`; expect missing-feature failure before implementation.
- [x] Implement the bounded adapter without external taxonomy fetching; unsupported input returns issues.
- [x] Write table tests first for colspan/rowspan grid alignment, nested tables, character spans and ambiguous structures.
- [x] Run `.venv/Scripts/python.exe -m unittest tests.test_reit_tables -v`; verify missing-feature failure, implement, then rerun both modules.

Example expected behavior:

```python
facts = extract_inline_facts(fixture_with_value_1234_scale_3_sign_minus)
assert facts['facts'][0]['value'] == '-1234000'
assert facts['facts'][0]['decimals'] == '-3'
assert facts['facts'][0]['period_type'] == 'duration'
```

### Task 2: Typed records and offline analysis

**Files:** create src/reit_money_records.py, scripts/analyze_reit_money.py, tests/test_reit_money_records.py and tests/test_analyze_reit_money.py. Owner root.

**Interfaces:** `build_document_records(raw: bytes, document: dict, extracted: dict) -> dict` consumes Task 1 adapters and cached pages, returns records/candidates/coverage. `analyze_collection(collection_dir: Path, output_dir: Path | None = None, *, max_candidates_per_document: int = 100) -> dict` consumes collector manifest/facts, writes outputs and returns analysis manifest.

- [x] Write record tests for distinct balances/flows/custom unknowns, dimension/context identity, consistent-rounding duplicate consolidation with retained evidence and inconsistent duplicate withholding.
- [x] Write evidence tests that custom table and agreement candidates retain raw quotes and uncertainty without invented loan terms; PDF candidates reuse cached page text.
- [x] Run new focused modules and verify missing-feature failures.
- [x] Implement standard concept classification from the existing curated tags, context-aware duplicate handling, bounded candidate extraction and coverage counts.
- [x] Write runner tests first for populated offline fixture, source mutation/missing source, outside-root paths, unchanged reuse and settings invalidation.
- [x] Implement atomic outputs and per-document fingerprint reuse. Validate original and cached text hashes, and export ready/review counts distinctly.
- [x] Rerun new tests and existing 42 REIT tests. Use a synthetic end-to-end manifest rather than live SEC requests.

Example expected behavior:

```python
result = build_document_records(original_html, metadata, cached_pages)
assert all(r['amount_kind'] != 'flow' for r in result['records']
           if r['concept_local_name'] == 'CustomLoanCommitment')
assert result['candidates'][0]['source_sha256'] == metadata['sha256']
```

### Task 3: Research evidence, verification and review

**Files:** create docs/reit-money-extraction-research.md; update only REIT README section and append workflow-audit continuation. Owner root.

- [x] Record primary-source findings, alternatives, actual issuer disclosure traps, implemented scope and unsupported cases; keep original 15 URL source guide intact.
- [x] Run focused tests, py_compile, analyzer CLI help and git diff --check; run one synthetic offline demonstration and record counts/reuse.
- [x] Obtain independent focused review, fix concrete material findings with failing regression first, and rerun the affected gates.
- [x] Write execution ledger with exact outcomes and live-document accuracy limits; mark completed tasks. No unrelated repairs, pushes or deployment.
