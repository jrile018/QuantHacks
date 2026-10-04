# Packaged-software benchmark handoff

Status: local producer work, diagnostic-only; no central consumer acceptance, merge, trained predictor or profitable strategy is claimed.

## Role

Supply evidence-backed software-company observations to the shared Benchmark/Post Benchmark architecture. Retain original sources and definitions. Consumer integration owns accepted canonical records and decision contracts; this producer does not create competing registries, outcome labels, train/test protocols or portfolio accounting.

## Existing artifacts

| Artifact | Meaning | Qualification |
|---|---|---|
| `extracts/financial_quality/metric_validation.csv` | Metric-level source, arithmetic and date checks; source-fact lineage | Accounting semantics and historical knowledge are not independently certified |
| `extracts/financial_quality/fundamentals_quarterly_conservative.csv` | Sparse wide view built from passing metrics and compatible ratio dependencies | Diagnostic convenience view; per-row availability is the latest retained input, not a shared decision timestamp |
| `extracts/financial_quality/ratio_dependency_validation.csv` | Passing/missing ratio dependencies and derived availability | Registered consumer definitions remain pending |
| `extracts/quality_audit/prices_with_return_interval_checks.csv` | Preserved prices and returns between adjacent dates in the observed universe | Observed dates are not a certified exchange calendar; adjusted price returns are not executable total/account returns |
| `extracts/quality_audit/epss_quality_by_company.csv` | Score coverage and explicit historical-attribution limitation | Dated CVE probabilities do not prove historically known issuer mappings |

Property activity is excluded from the planned feature payload at the user's request on October 4, 2026 because individually reviewed event coverage is too sparse. Its collected sources and event tables remain archived for reproducibility. SEC-reported asset balances remain a separate financial block and must not be relabeled purchase spending.

## Observation envelope to map through the consumer adapter

Preserve issuer identity, source legal entity/scope, taxonomy/tag, definition version, value, unit/currency, duration versus instant basis, period/effective dates, accession/source URL, source hashes and exact evidence location, extraction version, quality status and missing/exclusion reasons. Keep publication, receipt, retrieval, processing completion and assumed replay availability as separate fields. Existing date-only availability is an assumption, not a fabricated intraday timestamp. Facts from API companyfacts require document evidence-span qualification where the accepted protocol requires it.

For tradable instruments, require a separate dated security/action adapter. Target CIK joins and endpoint identity checks are insufficient to certify full daily identity, share-class history or option deliverables.

## Next sequence

1. Obtain/read the declared central schema and the exact four instant USD GAAP definitions. The contracts referenced by the user are not present in this checkout. Do not guess these definitions or overwrite another owner’s implementation.
2. Produce a small actual-row fixture using only supported definitions, pinned source bytes and an explicit date-only replay assumption. Exclude unsupported clock/entity/scope cases.
3. Freeze an immutable packet: schema/protocol version, checkout fingerprint, environment/parser versions, input/output hashes, grain, units, clocks, exclusions and affected consumers. Hashing does not certify economic meaning.
4. Seek the shared consumer’s accepted / diagnostic-only / rejected result. Until that receipt exists, keep acceptance pending and no trading authority implied.
5. Build the issuer-decision feature view at 15:30 New York using the accepted source-clock adapter. Keep January 2024 onward evaluation distinct from earlier history. The final holdout is not selected here; inspected 2024/2025 data is not relabeled untouched.

Options/futures labels, feasible quotes/fills, account cash flows, risk permissions and paid-data submissions remain owned by the shared integration and asset lanes. The current software-company extracts do not satisfy those execution gates.
# Reviewed diagnostic matrix update — October 4, 2026

`final/feature_matrix_backtest.csv` is now the reviewed producer diagnostic matrix:
3,192 rows, 168 issuers, 19 ended quarters since 2022, 83 raw definitions and 2,300
diagnostic price-return labels. See `final/REVIEWED_MATRIX_REPORT.md` and the pinned
`final/feature_matrix_manifest.json`. Source selection/missingness is in
`final/feature_matrix_provenance.csv`; outcome checks are in
`final/feature_matrix_label_audit.csv`. All 13 independent structural/as-of/rank/label
checks pass. This is not central consumer acceptance or trading qualification.
Government award predictors are withheld; legacy event/annual fields remain
unqualified diagnostics. Source bytes for reviewed cloud inputs are hash checked.
No property-activity events enter. Daily replay assumptions do not implement the
central 15:30 New York decision clock. SQLite and other matrix copies remain legacy
snapshots. The original final CSV/docs are archived before replacement.
# Financial density producer update — October 4, 2026

The current matrix version is `reviewed-diagnostic-v2-financial-density`, with 94
definitions and 120,248 populated cells over the unchanged 3,192-row diagnostic grid.
Its 2,300 diagnostic outcomes are unchanged. New quarterly ratios require same
accession, filing date and exact duration. Later direct facts keep their later
availability. Newly reviewed Tenable/Workiva/Kaltura cloud records retain pure versus
mixed commitment and exceptional-expense definitions. Cloud spans 25 issuers.
See `final/FINANCIAL_DENSITY_REPORT.md`. Version 1 is archived separately. Additional
derived cells are not independent observations. This remains producer diagnostic
data; no central schema acceptance, 15:30 clock adapter or trading qualification is
claimed. SQLite and other matrix copies remain legacy snapshots.
