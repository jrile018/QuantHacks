# Backtest feature matrix

**File:** `feature_matrix_backtest.csv`
**Dictionary:** `FEATURE_MATRIX_DICTIONARY.csv` (every column, its role and meaning)

## Rows
One row per company per calendar quarter: 2,334 rows, 168 companies, 2022Q1 to 2026Q3.

- 2,090 rows have an outcome (`label_excess_return_63d`).
- 244 rows are unlabelled: the 2026Q3 quarter, whose 63-day window has not closed yet. They are kept for live use and must be excluded from any test.
- 1,516 rows fall in the 2024Q1+ evaluation window. The rest are warm-up history.

## Columns
122 columns in four groups:

| Group | Columns | Use |
|---|---|---|
| Identifiers | `cik`, `ticker`, `name`, `quarter`, `quarter_end` | Join and index. Use `cik`, never `ticker`. |
| Membership | `membership_status`, `exit_date`, `survivorship_flag`, `survivorship_note`, `in_evaluation_window` | Control which rows a backtest may use. |
| Outcome | `label_excess_return_63d` | What is being predicted. |
| Features | 36 features, each with `__present` and `__rank` | Inputs. |

Each feature appears three times: the raw value, `__present` (1 = value exists), and `__rank` (cross-sectional rank within the quarter, scaled -1 to 1).

## Rules to keep when backtesting
1. Every feature was public by its quarter end. Do not join anything else without an as-of date.
2. Ranks use only that quarter's companies, so they add no future information.
3. The universe is survivors only. Every row has `survivorship_flag = 1`, so results are optimistic until acquired companies are added.
4. Connectedness, 13F common ownership and subsidiary counts are NOT in this file. They are computed over the whole sample and would leak the future.
5. Sparse features (auditor changes, federal awards, goodwill, convertibles, divestitures, contingencies) are too thin to carry a model alone.


## Public CapEx, leases and power features

Added 41 raw features with presence flags and ranks. The final matrix has 3192 rows and 419 columns.

The additive collector is `collect_power_capex.py`; integration is
`add_power_capex_features.py`. Existing matrix values, rows and outcome labels are
preserved. New source/provenance/coverage files are in `extracts/power_capex/`.

SEC standard USD tags provide lease liabilities (a reported total, or current plus
noncurrent from the SAME accession and economic period), ROU assets, undiscounted
lease payments and reported noncash additions. Liability changes are changes in
balances, not new lease additions: payments, FX, acquisitions and discounting can
affect them. Nothing establishes data-center-specific lease scope by itself.
Missing current/noncurrent components and inconsistent totals remain missing.
Quarter and annual noncash additions are separate; annual values are not divided
into quarters. Actual physical CapEx and intensity use the existing conservative
financial-quality layer and retain its eligibility/lineage restrictions.

Daily availability is the filing/publication date plus one day. Company features
select the latest economic period publicly available at quarter-end, then its
latest available version; conflicts are withheld. Financial values expire after
400 days. YoY/QoQ changes only use compatible economic periods and earlier facts
available at the current disclosure date. A zero prior value has no growth ratio.

CapEx/PPA/data-center text counts are CANDIDATES from the latest scanned annual or
quarterly filing. They are not verified guidance amounts, hardware spend, PPAs or
data-center expansion. Reviewed numeric guidance is sparse, with an exact clause,
source hash, horizon and scope. Annual, remaining-year and next-12-month amounts
are separate and used only in their disclosure quarter, before the horizon ends.
Guidance including software or offices is not relabeled PP&E-only or data-center
CapEx. Unreviewed dollar mentions never enter numeric guidance features.

FERC searches use public eLibrary full-text metadata. Search candidates can refer
to testimony, software/vendor mentions or policy proceedings. Candidate counts
are positive public metadata matches by posting quarter, not confirmed company
projects, PPAs, MW or expenditures. Failed/truncated searches and absence of
candidates never become zero interconnection demand. No confidential/CEII contents
are downloaded. `ferc_search_coverage.csv` retains errors, truncation and queries.
Unverified project MW/contract prices are not fabricated into model inputs.

PJM prices are USD per MW-day of capacity, not energy prices (USD/MWh). These are
regional macro values shared by all issuers, not company exposure or costs.
Identical macro values receive a tied rank of zero; raw values retain the time
series. Auction announcement dates are distinct from future delivery years.
Price changes can reflect supply, demand, accreditation and price caps; they do
not isolate AI/data-center demand. Shortfalls remain missing unless explicitly
reported. Other RTO/ISO auction formats are not assumed comparable to PJM.

`matrix_feature_provenance.csv` records selection, clocks, scope and missing
reasons; `matrix_feature_coverage.csv` gives observed company/row counts. Original
matrices are archived in `matrix_before_power_capex/`. CSV modelling views retain
their individual original row grids and labels; the reviewed final grid can differ
from legacy copies. New SQLite columns match new CSV values for shared keys;
legacy SQLite rows/labels are not replaced by the reviewed final CSV. Original legacy
quality, survivorship and label limitations remain. These data do not establish
an executable strategy or a historical intraday information clock.

Reproduce with the project venv: run `collect_power_capex.py --asof YYYY-MM-DD`,
then `add_power_capex_features.py`. Public reports need `pypdf` and `requests`.
