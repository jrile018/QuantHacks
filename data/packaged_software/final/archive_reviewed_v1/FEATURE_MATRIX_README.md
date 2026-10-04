# Reviewed diagnostic feature matrix

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
