# Reviewed diagnostic feature matrix

Version 2 adds strict direct/same-filing financial recoveries and separately named
quarterly ratios. These ratios are not substitutions for existing TTM features.
Evidence is in `extracts/financial_density/`; raw source facts and original gates
remain intact. Later comparative disclosures retain their later availability.
The reviewed version 1 matrix/coverage/manifest are in `archive_reviewed_v1/`.

Canonical CSV: `feature_matrix_backtest.csv`. The filename is retained for compatibility;
this is diagnostic research data, not an executable backtest or accepted central capsule.
Previous files remain in `archive_before_reviewed_v1/`. `dataset.sqlite` and the other
output/root matrix copies are unchanged legacy snapshots and are NOT synchronized.

## Definitions and clocks

One row for each of the fixed 168 issuers and each ended calendar quarter since 2022.
This full grid does not establish historical listing/trading eligibility. Current
membership status is descriptive only; it cannot gate historical trades. Evaluation
scope starts 2024; 2022–2023 are warm-up. Previously inspected dates are not a holdout.

Financials use eligible observations from the conservative financial-quality layer.
For each feature choose the latest economic period available by quarter-end, then the
latest eligible availability for that period; conflicting values at that grain are
withheld. Values older than 400 days from period-end are withheld (a registered replay
assumption). Each feature has its own dates; ratios and Rule of 40 need qualified,
matching inputs. Rule of 40 uses percentage points. Source arithmetic passing is not
independent accounting certification. Asset balances remain distinct from expenditures.

Ranks use average ranks for ties within a quarter; fewer than five populated values
remain unranked. Presence flags mean populated, not historically trading-qualified.

Cloud features are disclosure-quarter observations, not forward-filled spending or
complete company contract inventories. Contract totals, annual minimums, remaining
obligations and mixed cloud/associated-services obligations remain separate. Expenses
retain source-specific segment scope. Quarter, six-month, nine-month and annual
durations remain separate; overlapping periods are never added. Appian agreement
spending does not imply cash paid. Source files are checked against reviewed hashes.
If multiple inconsistent disclosures share the selection grain, the feature stays
missing; all underlying observations remain in the observation ledger.

Government-award predictors are withheld: contract start dates and current award
amounts do not establish historical availability or historical amount vintages.
Legacy 8-K/KEV/WARN/annual observations are explicitly diagnostic; scan completeness,
original publication clocks and accounting definitions are not independently certified.
No property-activity events, unreviewed cloud tags or employee-AI cost estimates enter.

Dates are daily assumed replay availability, not historical actual receipt or processing
times. This is not a 15:30 New York adapter. End-of-day inputs cannot be used at 15:30
that same day. Consumer schema/definition acceptance remains a separate handoff.

## Outcome

Entry is the first factor-calendar session AFTER quarter-end, at that session's close.
Exit is exactly 63 factor-calendar sessions after entry. The market comparator compounds
the matching 63 daily (Mkt-RF + RF) returns. Require a stock bar at every date and the
provider issuer/share identity match status throughout. Factor dates are a proxy session
calendar, not exchange-calendar certification. Other identity statuses stay unlabelled.
If the outcome/calendar is unavailable it stays missing. See `feature_matrix_label_audit.csv`.

These are diagnostic price-return labels, not certified total shareholder returns or
executable fills. Dividend/action reconciliation, entry/exit costs, dated security
identity, borrow and portfolio accounting still require review. CIK is an issuer key,
not an instrument identifier. Equity price returns and the total-market factor return
also differ in dividend treatment; no alpha or portfolio-performance claim follows.

## Reproduction and coverage

Run `.\venv\Scripts\python.exe data/packaged_software/rebuild_reviewed_matrix.py`.
`feature_matrix_manifest.json` pins input/output hashes and assumptions.
`feature_matrix_coverage.csv` compares feature population before/after; denominators
differ because the rebuilt grid preserves all issuer-quarter missing rows.
`feature_matrix_provenance.csv` retains selected evidence, availability, economic
period, scope and missing reason per feature/cell. `feature_matrix_observations.csv`
retains candidate reviewed observations rather than silently overwriting duplicates.
Cloud exact clauses/contexts and financial source-fact lineage remain in referenced
producer tables. Sparse new features can have values but no ranks.


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
