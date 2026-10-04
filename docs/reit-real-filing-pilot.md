# REIT money interpretation: PDF fix and live pilot

Run date: 2026-10-03.

The checked PDF interpretation gap is fixed: **14 of 14 unchanged answer-key figures are now automatically classified correctly**, compared with **0 of 14** previously. The system separates cash borrowed or repaid during a year from debt outstanding, facility size, unused capacity and conditional expansion.

The authorized SEC collection also completed for AMT, AAT, BXMT and AGNC, retaining **35 documents and 187 CompanyFacts observations**. Its broader interpretation remains **partial**. The PDF result is a selected sample, not a whole-report or industry-wide accuracy estimate.

## How the fix works

1. Select an amount from its exact cash-flow row and year column; apply stated table units and preserve the sign.
2. Require an explicit reporting-currency declaration. PDF page 70 supplies USD context for the two financial pages.
3. Read supported facility statements into distinct commitment, available-capacity, outstanding-debt and conditional-expansion records.
4. Keep issuer and Fund borrowing separate. Ambiguous multiple or subsidiary arrangements require review.
5. Retain source URL, source/text hashes, page, exact character span and selected amount. Unsupported or conflicting statements remain review items.

Each cash table owns its header; later tables or financial statements cannot inherit its years and units. Unknown dashes remain unknown. An original facility amount is withheld when subsequent changes or current figures conflict. For explicitly paired availability/debt statements, disagreement with the original commitment beyond displayed rounding increments triggers review. This consistency guard never creates a new commitment amount.

Interpretation uses local rules and cached text. It adds no model inference, OCR audit, paid extraction service or remote compute job. Source, text, settings and implementation hashes control cache reuse; changing PDF rules invalidates old analysis.

## Real PDF result

Source: [Realty Income's official 2025 annual report](https://www.realtyincome.com/sites/realty-income/files/realty-income/investors/quartely-and-annual-result/2025-annual-report.pdf), SHA-256 `3669f20ce919eef667a7485e669ac9c76720fe245e22fdba5f59201296a5e0bc`.

- PDF page 69: annual cash-flow table, 2025/2024/2023 columns, amounts in thousands.
- PDF page 70: explicit USD reporting-currency declaration.
- PDF page 85: RI and Fund credit-facility disclosures.
- The [answer key](../configs/reit_pilot_gold.json) remains the original 14 assertions on pages 69 and 85: eight cash-flow rows and six facility amounts. Runtime extraction does not read it.

The input uses embedded digital text from three selected pages of the 124-page report. Only the original two financial pages are scored. This evaluates financial interpretation with a separate currency context page; it does not test OCR.

| Outcome on 14 checked assertions | Previous candidate-only run | Implemented interpretation |
|---|---:|---:|
| Automatically classified correctly | 0 | **14** |
| Automatically misclassified | 0 | **0** |
| Found but needing review | 14 | **0** |
| Missed | 0 | **0** |
| Candidates omitted by cap | 0 | **0** |

The new run generates **44 records: 41 parsed and 3 requiring review**, plus **74 review candidates**. Three dash values are withheld. Only the 14 answer-key assertions received this financial accuracy check. The other generated records are not an independently verified accuracy sample. Candidates are excerpts for inspection and must not be added to records as extra transactions.

Examples from pages 69 and 85 of the [annual report](https://www.realtyincome.com/sites/realty-income/files/realty-income/investors/quartely-and-annual-result/2025-annual-report.pdf):

| Reported amount | Meaning stored | Period or date |
|---|---|---|
| $20,280,426,000 revolving-facility/commercial-paper borrowings | Borrowing cash inflow | 2025 |
| −$19,557,427,000 payments on those programs | Repayment cash outflow | 2025 |
| $4.0 billion RI facility size | Committed borrowing capacity | 2025-12-31 |
| $2.7 billion available | Undrawn borrowing capacity | 2025-12-31 |
| $1.3 billion outstanding | Reported debt balance | 2025-12-31 |
| $5.0 billion possible expansion | Conditional capacity, subject to lender commitments | 2025-12-31 |
| $1.38 billion Fund facility | Fund borrowing capacity, separate scope | 2025-12-31 |
| $182.0 million Fund borrowing outstanding | Fund debt balance | 2025-12-31 |

The cash-flow rows are reported in USD thousands; the first two values above are normalized to USD. Facility size and possible expansion are not reported cash receipts.

Outputs:

- [Per-figure score](../data/processed/reit_filing_pilot/realty_income_2025_meaning_v2/analysis_100/pilot_score.json).
- [Structured records](../data/processed/reit_filing_pilot/realty_income_2025_meaning_v2/analysis_100/money_records.jsonl).
- [Analysis manifest and hashes](../data/processed/reit_filing_pilot/realty_income_2025_meaning_v2/analysis_100/analysis_manifest.json).
- [Original candidate-only score, preserved](../data/processed/reit_filing_pilot/realty_income_2025/analysis_100/pilot_score.json).

## Four-company SEC extension

Collection used the supplied contact email, two requests per second, up to four primary filings and two selected exhibits per filing per company. All four companies completed with no collection errors or warnings. AMT comes from the configured options universe; AAT, BXMT and AGNC provide contrasting REIT disclosure types.

| Issuer | CIK | Parsed standard filing observations |
|---|---|---:|
| American Tower (AMT) | 0001053507 | 318 |
| American Assets Trust (AAT) | 0001500217 | 108 |
| Blackstone Mortgage Trust (BXMT) | 0001061630 | 164 |
| AGNC Investment (AGNC) | 0001423689 | 48 |
| Total | | **638** |

All 35 retained documents were processed, producing:

- **638 parsed filing XBRL records**. These include repeated periods and dimensions; this is not a count of distinct loans or transactions and has not received the PDF sample's accuracy check.
- **4,470 review records**, largely unsupported/custom meanings or contexts.
- **1,927 retained review candidates** and **4,051 candidate omissions** under the default 100-per-document cap.
- **187 CompanyFacts comparison observations**, exported separately to avoid counting them as additional money movements.

Analysis is **partial**, with no processing errors and 30 document coverage warnings. Nineteen documents have XML parsing warnings, including non-XBRL HTML exhibits; 20 hit excerpt quotation limits; 10 contain long text requiring layout-aware review. These counts overlap. Full cached documents remain available through evidence locators. Raising caps does not resolve unknown financial meanings.

Evidence:

- [Collection manifest and HTTP receipts](../data/processed/reit_financials/20261003-meaning-pilot/manifest.json).
- [Financial analysis manifest](../data/processed/reit_financials/20261003-meaning-pilot/money_analysis_v2/analysis_manifest.json).
- [Filing observations](../data/processed/reit_financials/20261003-meaning-pilot/money_analysis_v2/money_records.jsonl).
- [Separate comparison facts](../data/processed/reit_financials/20261003-meaning-pilot/money_analysis_v2/comparison_facts.jsonl).

## Verification and remaining scope

Regression tests cover year/scale association, signs, missing/conflicting currency, unknown dashes, multiple tables, statement boundaries, Fund scope, ambiguous commitments, subsequent capacity changes, source metadata, selected-amount scoring and cache invalidation. Independent review findings were reproduced before their fixes and covered by regression tests. The final review found no remaining material issue in its scope.

Final verification passed **116 focused REIT tests**. Source/output hashes and the current implementation hash were checked for both runs, along with **136 exact PDF evidence references** and the original 14 assertion IDs. The fresh PDF score is 14 correct, zero misclassified, zero review-only and zero missed.

The parser supports explicit annual cash-flow rows and specific facility sentence forms. Other row names, quarterly layouts, complex legal terms, scanned table structures and custom XBRL meanings need further adapters and checked examples. Public reports disclose selected and aggregate activity; this system does not collect every loan or bank transfer.

The next expansion should select a small set of unresolved money rows from each issuer type, create a reviewed answer key, and add only demonstrated missing patterns. That keeps compute low and gives a measurable test for each new rule.

## Reproduce locally

```powershell
.venv\Scripts\python.exe scripts/run_reit_filing_pilot.py --max-candidates 100
.venv\Scripts\python.exe scripts/analyze_reit_money.py --collection-dir data/processed/reit_financials/20261003-meaning-pilot --output-dir data/processed/reit_financials/20261003-meaning-pilot/money_analysis_v2 --max-candidates-per-document 100
.venv\Scripts\python.exe -m unittest tests.test_collect_reit_financials tests.test_reit_cash_facts tests.test_reit_inline_facts tests.test_reit_tables tests.test_reit_money_records tests.test_analyze_reit_money tests.test_run_reit_filing_pilot tests.test_reit_pdf_money -q
```

The broader analyzer exits with status 1 when coverage is partial, retaining outputs and warnings.
