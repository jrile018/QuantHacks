# Financial density pass — October 4, 2026

The canonical matrix is now `reviewed-diagnostic-v2-financial-density`. Its 168 issuers,
19 quarters, 3,192 rows and 2,300 diagnostic return labels are unchanged. Version 1
is preserved in `archive_reviewed_v1/`; the original pre-review files remain in
`archive_before_reviewed_v1/`. The earlier `REVIEWED_MATRIX_REPORT.md` describes
version 1; this report and the current manifest supersede its current coverage counts.

## Actual gain

- Raw definitions: **83 → 94**.
- Populated feature cells: **102,626 → 120,248**, a net gain of **17,622**.
- Overall population: **38.74% → 40.08%**, with the larger feature denominator.
- Existing definitions: **21 newly populated cells; zero newly missing cells**.
- Cloud: **66 → 71 selected cells**, across **22 → 25 issuers**.

Most added cells are separately defined quarterly ratios derived from existing SEC
facts, not newly acquired independent observations. They improve usable coverage
for quarterly hypotheses without converting annual totals into invented quarters.
The narrow recovery of previously unavailable existing cells is the honest measure
of old-gap closure. Adding derivatives does not multiply the independent sample size.

| New explicit quarterly feature | Populated rows | Coverage of 3,192 rows |
|---|---:|---:|
| R&D / revenue | 2,380 | 74.56% |
| Gross margin | 2,393 | 74.97% |
| Operating margin | 2,673 | 83.74% |
| Physical-capex FCF margin | 2,275 | 71.27% |
| Stock compensation / revenue | 2,523 | 79.04% |
| Sales and marketing / revenue | 2,225 | 69.71% |
| Physical capex / revenue | 2,276 | 71.30% |
| Acquisition payments / revenue | 762 | 23.87% |

The TTM ratios remain under their existing definitions. Quarter ratios require
the exact same economic interval, accession, USD units and filing date for their
inputs. Missing capex is never zero. Software-specific R&D remains distinct.

## Recovery and source checks

All 125,666 retained financial facts were independently matched back to the 168
cached SEC Company Facts responses, whose hashes still match the prior audit.
The recovery table retains 108 direct/same-filing metric keys and 11,015 quarterly
ratio vintage observations. Candidates become matrix cells only when their
economic periods and later filing availability qualify at the decision date.
Direct later comparatives are never backdated. Cross-filing YTD subtraction and
annual/YTD bridge uncertainty are not silently promoted. Thirty-two conflicting
quarter candidate groups were withheld. Each published recovery is recomputed
from its referenced facts and retains source tags and accession.

Generic quarterly R&D remains absent for 17 issuers in the original conservative
layer. Five have separately reported software-specific R&D. The remaining-tag
inventory is `extracts/financial_density/remaining_RD_definition_review.csv`.
Tax-credit balances and capitalized development assets are not R&D expenses.
The presence of an annual R&D tag does not justify fabricating quarterly values.

## Additional cloud review

- Tenable: **$230.3m** AWS contract minimum, August 2024–July 2027, disclosed in
  November 2024. This is neither annual expense nor remaining obligations.
- Workiva: **$28.1m, $156.4m and $121.4m** reported non-cancelable commitments
  primarily for cloud services/infrastructure, disclosed in 2024, 2025 and 2026.
  These are a separate mixed-services definition, not pure cloud-only totals.
- Kaltura: **$1.312m** unused-cloud-commitment expense for 2024 Q1, disclosed in
  May 2024. The expense table is in thousands; the narrative rounds to $1.3m.
  It is exceptional termination-related expense, not recurring hosting cost.

These five records passed pinned source hashes and exact clause/table-scope checks.
The matrix now checks 56 cloud source files. They are in
`extracts/infrastructure_evidence/additional_reviewed_cloud_observations.csv`.
Broader cloud candidates remain outside model inputs until definition review.

## Verification and remaining work

Five density tests, seven matrix tests and five financial-quality tests pass.
The independent matrix verifier checks all populated outcomes, ranks, clocks,
hashes, ledger uniqueness, blank reasons and withheld award fields.

Price/action exclusions remain unchanged; no gaps or ambiguous securities were
filled by interpolation. Cloud coverage remains sparse, and actual historical
receipt times, dated membership, corporate actions, accounting semantics and
central consumer acceptance remain open. This is a diagnostic matrix, not trading
qualification. No models were fitted, paid APIs used or raw sources overwritten.

## Reproduce

```powershell
.\venv\Scripts\python.exe data/packaged_software/recover_financial_density.py
.\venv\Scripts\python.exe data/packaged_software/review_cloud_density.py
.\venv\Scripts\python.exe data/packaged_software/rebuild_reviewed_matrix.py
.\venv\Scripts\python.exe data/packaged_software/verify_reviewed_matrix.py
```

See `financial_density_comparison.csv` for per-feature gains versus version 1,
`financial_density_summary.json` for aggregate comparisons and the current
`feature_matrix_manifest.json` for the pinned matrix inputs and outputs.
