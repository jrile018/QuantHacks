# REIT collection integrity audit — 2026-10-03

## Scope and method

Offline validation of every entry in the financials and Realty Income annual-report manifests. Recomputed raw SHA-256 hashes; compared extraction-cache URL, accession, source path, and hash identity; reconciled SEC URL path components; checked cached HTTP receipt records and cache files; checked CompanyFacts cache hashes and internal CIKs; and checked saved analyzer output hashes. Issuer and period context checks are limited to cues in saved extracted text. No live URL fetches, OCR audit, or financial-accuracy review was performed.

## Results

| Collection | Entries | Raw hash matches | Text metadata matches | URL identity matches | Cached source receipts | Context supported | Context unresolved |
|---|---:|---:|---:|---:|---:|---:|---:|
| financials | 35 | 35/35 | 35/35 | 35/35 | 35/35 | 34 | 1 |
| realty_income_pdf | 1 | 1/1 | 1/1 | N/A | N/A | 1 | 0 |

### Verified

- The 35 SEC document raw hashes match their manifest SHA-256 values; all 35 source and extraction files exist.
- All 35 extraction JSON files match manifest source URL, accession, source path, and raw hash.
- All 35 SEC URL paths agree with manifest CIK, accession (compact form), and document filename.
- All 59 recorded SEC HTTP receipts (including submissions, CompanyFacts, filing indexes, and documents) say HTTP 200; every referenced receipt cache exists. For all 35 manifest documents, receipt URL/cache content matches the source bytes.
- All four CompanyFacts cache hashes match their coverage metadata; embedded CIKs match their manifest CIKs. Entity names correspond to the expected companies.
- All three saved analyzer output hashes match. Its collection-manifest SHA-256 matches the current manifest; analysis metadata reports 35 documents analyzed.
- Realty Income PDF raw hash and text-cache URL/accession/source-path/hash metadata match. Extracted text contains Realty Income Corporation and 2025-12-31 cues.
- 34/35 SEC documents have issuer and report-period cues found in saved extracted text. This is a limited context check, not an independent confirmation of filed content.

### Unresolved and limitations

- For `exhibit1032fy2025.htm` (American Tower, accession `0001053507-26-000035`), the issuer cue is present but the expected report-period cue was not found in extracted text. The SEC URL, accession, cached bytes, extraction identity, and HTTP receipt all pass. The period/title match remains unresolved from this saved text.
- Analyzer metadata contains 30 incomplete parsing/candidate-coverage warnings across the 35 SEC documents. This affects analyzer coverage, not raw-source integrity; the warning details are recorded in the JSON evidence file.
- The Realty Income entry is a company-hosted PDF with a local accession label, so SEC URL path identity and SEC HTTP-receipt checks do not apply. It is explicitly unresolved for live availability.
- Live URL availability was not checked for any of the 36 source URLs. Cached HTTP 200 receipts document the collection-time requests only; they do not establish current availability.
- No integrity failures were observed. Semantic mismatch count is zero; one period cue remains unresolved. This does not establish document completeness, extraction fidelity, or financial accuracy.

## Evidence

Per-document hashes, metadata comparisons, receipt details, excerpts/context flags, CompanyFacts hashes, analyzer output hashes, and analyzer coverage warnings are in [`collection_integrity.json`](../data/processed/reit_source_validation/20261003/collection_integrity.json).
