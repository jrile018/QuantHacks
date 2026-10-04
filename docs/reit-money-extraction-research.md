# REIT loan and money extraction: research and implementation

Research date: 2026-10-03. Scope: improve step 3 before a live collection pilot. Sources are reporting standards, official parser documentation, research papers and original issuer filings. Findings guide a local implementation; they do not establish measured accuracy on real REIT tables.

## Recommendation in plain language

Read the structured data already inside a filing, preserve the actual table cells, and retain a source reference for every observation. Separate actual cash movements from outstanding balances, borrowing capacity, loan assets and accounting values. Send unresolved tables or contract language to review. Use a stronger OCR/model only for a demonstrated failure on particular pages.

This is our engineering recommendation from the sources below. A representative benchmark is still needed to compare actual field accuracy, omissions and cost.

## Primary research findings

| Evidence | Consequence for extraction |
|---|---|
| The SEC API aggregates non-custom taxonomy facts applying to the entire filing entity. [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | CompanyFacts remains a cheap comparison source. Inspect retained filings for custom concepts and loan/facility dimensions; absence from the API is not absence of disclosure. |
| Contexts describe entity, period and additional reporting characteristics. Dimensioned disclosures can differ from consolidated amounts. [SEC context guidance](https://www.sec.gov/newsroom/whats-new/osd-announcement-contexts-september-7-2016) | Fact identity includes entity, exact period, dimensions, concept and unit. Keep parent, operating-partnership and instrument scopes separate. Never interpret a year-to-date duration as a standalone quarter. |
| Inline facts can carry a transformation, scale, sign, nil and precision; formats are namespace-resolved QNames. [Inline XBRL 1.1](https://specifications.xbrl.org/work-product-index-inline-xbrl-inline-xbrl-1.1.html), [Transformation Registry 4](https://www.xbrl.org/Specification/inlineXBRL-transformationRegistry/REC-2020-02-12/inlineXBRL-transformationRegistry-REC-2020-02-12.html) | Transform supported display text, multiply by scale, then apply sign. Decimals affects precision, not the amount multiplier. An untagged dash is unknown; an explicit supported fixed-zero transform can establish zero. Unsupported formats require review. |
| Duplicate facts can be identical, consistently rounded or inconsistent. Equivalence requires matching reporting dimensions; equal precision requires equal values. [XBRL duplicate-fact guidance](https://www.xbrl.org/WGN/xbrl-duplicates/WGN-2025-01-14/xbrl-duplicates-2025-01-14.html) | Preserve every evidence location. Consolidate equivalent same-filing observations, selecting the most precise consistent value. Withhold an inconsistent value; do not collapse different dates, instruments, concepts or accessions. Unknown precision never supplies an invented rounding tolerance. |
| The SEC guide distinguishes context-period forms and describes supported Inline XBRL constructs. [SEC XBRL Guide](https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2026-06-29.pdf) | Store period type separately from financial meaning. A duration can describe rates, averages, provisions or other noncash measures; it does not by itself mean cash moved. The bounded adapter is not a replacement for full taxonomy validation. |
| ASC 230 text reproduced in ASU 2016-15 distinguishes loan-investment cash movements from repayments of amounts borrowed; exceptions apply. [FASB ASU 2016-15](https://storage.fasb.org/ASU%202016-15.pdf) | REIT loan investments and REIT borrowings need different relationships. Preserve the original concept and filing classification rather than assigning every loan amount to debt repayment. This attribution concerns reproduced Codification text, not a new classification rule created by that ASU. |

Numeric tag extraction alone does not establish transaction identity, instrument meaning or completeness. The implementation labels a supported observation `parsed`; that word means the supported numerical/context rules succeeded, not that an accountant verified the filing.

## Actual REIT disclosure traps

1. **AAT: principal, valuation and rate hedges differ.** The 2025 report's debt schedule states its principal basis and units separately from fair-value and swap discussion. A swap notional is not additional debt principal. [AAT 2025 report](https://www.sec.gov/Archives/edgar/data/1500217/000150021726000008/aat-20251231.htm)
2. **BXMT: lending is different from borrowing.** The fourth-quarter/full-year 2023 supplement separates total loan, principal and net book value, with total-loan footnotes addressing unfunded commitments. Coupon and maximum maturity are separate portfolio attributes. Preserve those columns rather than selecting one number as the loan's cash movement. [BXMT supplement](https://www.sec.gov/Archives/edgar/data/1061630/000106163024000033/exhibit992.htm)
3. **AGNC: repo exposure, commitments and collateral differ.** Its 2025 report separates repo borrowings from forward repo commitments, collateral and derivatives. Reverse repo also has more than one purpose. A collateral or notional amount cannot automatically become cash proceeds or debt outstanding. [AGNC 2025 report](https://www.sec.gov/Archives/edgar/data/1423689/000142368926000043/agnc-20251231.htm)
4. **AAT: legal roles and amendment state matter.** The 2026 credit agreement identifies the operating partnership as borrower and the REIT as guarantor. Availability under a commitment differs from amounts actually outstanding, and an amendment/restatement is not proof that the entire facility was newly funded. [AAT agreement](https://www.sec.gov/Archives/edgar/data/1500217/000150021726000012/aatcreditagreement2026-v7.htm)

Synthetic tests use these disclosure shapes without asserting actual issuer figures or copying complete source tables.

## Cheapest useful extraction order

| Method | Useful capability | Current decision |
|---|---|---|
| CompanyFacts | Already normalized standard monetary facts | Retain as a separate comparison file; never reapply inline scale |
| Original HTML/Inline XBRL | Numeric context, custom/dimensional facts, actual table cells | Implemented locally with an explicitly supported subset |
| Digital PDF geometry | Word/cell positions, line-based or text-based table strategies | Optional future adapter for demonstrated PDF gaps; extra packages are not installed |
| Cached OCR text and boxes | Scanned-page text/evidence and quality flags | Reuse existing extraction; retain candidates without guessing columns |
| Table-aware OCR/model or targeted language model | Potential structure/meaning recovery on unresolved crops | Evaluate against checked pages first; no calls or model jobs made here |
| Human review | Resolve ambiguous legal roles, loan basis and evidence conflicts | Preserve explicit review candidates and unknown fields |

The official [pdfplumber documentation](https://github.com/jsvine/pdfplumber/blob/stable/README.md) exposes cells, bounding boxes and text/line strategies. These are useful candidates for a later PDF adapter; the current native PDF text path does not supply a verified table grid. [PubTables-1M](https://arxiv.org/abs/2110.00061) treats table detection and structure recognition as distinct tasks; its benchmark concerns its own document dataset, not REIT accuracy. [Tesseract's quality guidance](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html) also discusses table limitations without layout analysis.

## Implemented local behavior

- `src/reit_inline_facts.py`: bounded well-formed XHTML/Inline XBRL and extracted-instance parsing. Context entity, period, explicit/typed dimensions, units, precision, hidden facts, sign/scale and XML evidence locators are retained. Supported numeric transformations are whitelisted by namespace and name. Other transforms, fractions, target attributes, numeric continuations and unsupported contexts remain unresolved. Entity declarations and oversized sources are rejected.
- `src/reit_tables.py`: original cell spans, visible text, merged-cell grid, caption/context and explicit structural/resource flags. Nested tables stay separate; blanks and currency-symbol cells retain their columns. No table value is automatically promoted to a financial fact.
- `src/reit_money_records.py`: curated standard financial classifications, separate period/amount meanings, exact same-filing duplicate consolidation and bounded review excerpts. Custom meanings, nil and conflicting values remain review records. Rates/maturities/borrowers are not attached to amounts merely by proximity.
- `src/reit_pdf_money.py` (subsequent authorized fix): explicit annual cash-flow row/year/unit rules and facility-note meanings with currency and evidence requirements. Supported PDF amounts can become records; unsupported layouts remain review candidates. See [the real pilot result](reit-real-filing-pilot.md).
- `scripts/analyze_reit_money.py`: a separate offline command over the retained collector manifest. It checks original/text/CompanyFacts provenance, constrains referenced inputs to the collection directory, reuses analysis by source/text/settings/implementation hashes and writes output hashes. It never fetches documents or runs OCR or a model.

Outputs in `money_analysis/`:

- `money_records.jsonl`: filing observations, with parsed and review statuses.
- `review_candidates.jsonl`: source-linked loan-table and text candidates; unknown semantics stay unknown.
- `comparison_facts.jsonl`: separately verified standard CompanyFacts observations, avoiding an apparent second count of filing cash movements.
- `analysis_manifest.json`: coverage, omissions, errors, cache reuse and output hashes. Verify hashes when consuming outputs to detect an interrupted mixed snapshot.

Bounds include 25 MiB original sources, 50 MiB cached text artifacts, XML depth 256 and 250,000 XML elements, 500 HTML tables and document totals of 50,000 retained cells/rows and 500,000 grid slots. Candidate quotes are capped at 4,000 characters each and 256 KiB of UTF-8 quoted text per document; full span locators remain available. The default is 100 review candidates per document. Resource/candidate omissions are explicit incomplete coverage, including limits encountered in tables later filtered as unrelated. These are implementation safeguards, not measured optimal thresholds.

## Verified local result

All 102 focused tests passed: 60 new extraction/analysis tests plus the existing 42 REIT tests. Compilation, analyzer CLI help and `git diff --check` passed. Independent review found no remaining Critical/Important issue after fixes for missing references, truncation reporting, nesting/allocation limits, idempotent duplicate handling and evidence-cache identity. No full unrelated workspace suite or live SEC collection was run for this continuation.

A small **synthetic** demonstration in `examples/reit_money_analysis/input` produces two parsed records, one review record and two review candidates; a repeated run reuses its document analysis. The made-up $100 million inflow stays separate from the $100 million outstanding balance. A custom $250 million facility figure stays under review, and the repeated inflow retains two evidence references without becoming another cash movement. This verifies a trace through the implementation, not real-issuer extraction accuracy or a throughput benchmark.

Example offline use, after a retained collection exists:

```powershell
.venv/Scripts/python.exe scripts/analyze_reit_money.py --collection-dir data/processed/reit_financials
```

## Validation and remaining work

Measure exact amount, sign, currency/scale, period, reporting entity, amount basis, row/column association and source locator on manually checked examples. Also measure missed loan rows, unnecessary escalation, runtime and cache reuse. Break down results by equity/commercial-mortgage/agency-mortgage issuer and HTML/digital-PDF/scanned format. Recognition confidence is not a financial-accuracy score.

The initial synthetic/offline tests exercise numerical rules and evidence handling. They do not measure real-document recall or prove a globally best OCR engine. Full XBRL transformation/taxonomy support, general loan-term interpretation, PDF table geometry and automated refinancing links remain unimplemented. The subsequent authorized PDF fix classifies all 14 unchanged checked assertions correctly, and live SEC collection completed for four issuers using the supplied contact email. Broader analysis is partial. See [the updated pilot report](reit-real-filing-pilot.md) for counts, evidence and limits. The original 15-source URL guide is unchanged.
