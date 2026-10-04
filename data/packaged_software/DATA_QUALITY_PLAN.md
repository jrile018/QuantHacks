# Dataset quality improvement plan

Target: improve reliability of published observations, while reporting coverage separately. A passed source check is not an independent audit of the issuer or a guarantee of an unbiased backtest. No undisclosed amounts are imputed. Raw datasets remain intact.

| Order | Work | Acceptance criteria | Status |
|---|---|---|---|
| 1 | Audit current canonical datasets | Check entity keys, duplicates, dates, source matching, lineage references, arithmetic, coverage and artifact hashes; save actionable failures | Core audit complete; independent accounting and auxiliary datasets remain outside certification |
| 2 | Review financial derivations at metric level | Reconcile reported and derived values; separate cross-filing accounting uncertainty; recompute ratios only from passing dependencies; retain exact availability dates | Conservative layer complete; unresolved accounting basis remains queued |
| 3 | Price identity and corporate actions | Preserve quarantines; identify missing sessions and extreme returns; check adjusted-price basis, splits/dividends and remaining identity issues before total-return research | Target ID metadata repaired and interval checks complete; event/corporate-action review remains |
| 4 | Historical EPSS attribution | Check score ranges, missing snapshots, CVE eligibility and ownership intervals; separate known historical score vintages from retrospective vendor mappings | Structural checks complete; historical attribution certification remains unresolved |
| 5 | Property and data-center events | Retain collected evidence as an archive; exclude this block from the planned feature matrix | Dropped from feature scope at the user's request; reviewed event coverage is too sparse |
| 6 | Cloud and employee AI evidence | Review reported scope, dates and internal-use evidence; distinguish costs, commitments, balances and announcements; leave undisclosed values missing | Planned |
| 7 | Publish reviewed research inputs | Per-observation validation status and availability, source hashes, dependency gates, coverage and explicit exclusions; frozen reproducible release | Planned |

Start with financial derivations because a questionable dependency can affect multiple ratios and TTM metrics. Then investigate price and attribution risks before adding more weakly attributed narrative candidates. Review source candidates in batches; do not promote them solely because a company name or dollar amount appears nearby.

Limits: independent provider verification may require additional access; private cloud bills and AI contract prices may remain unavailable; current registry snapshots do not prove historical availability; the fixed current company universe is not a historical investable universe. Such limitations remain explicit rather than being converted into favorable quality scores.

## Completed October 4, 2026

- All 125,666 financial facts match cached SEC values; all 86,550 lineage records pass source/arithmetic/date checks. No duplicate fact IDs or company-period keys.
- Conservative financial layer retains 52,050 metric observations and withholds 34,500 with unresolved cross-filing dependencies. It preserves 2,807 company-quarter rows across 168 companies, but deliberately has lower numerical coverage. Derived ratios require passing inputs and compatible periods.
- This includes withholding 621 revenue-growth observations whose raw ratio quality label did not express their unresolved input accounting basis.
- Canonical price bars now have target CIKs, separate original source CIK metadata and explicit price-identity review status. All 178,220 retained OHLCV values remain unchanged. There are no duplicate price keys, invalid OHLCV rows, missing target CIKs or target CIK mismatches.
- Price review queue: 135 large close changes, 1,931 absent-date candidates based on the observed universe calendar, and 339 nonadjacent close pairs. Those 339 pairs are not published as one-session returns in the interval-checked research table. Legitimate large returns are not automatically removed.
- EPSS has 9,744 company-month status rows, 2,887 numeric company-month scores, no duplicate keys or out-of-range probabilities, and no imputed unavailable snapshots. Historical company attribution remains uncertified.
- All 31 audited publication artifact hashes match. Eight new validation tests pass.

## Feature-matrix readiness

A first exploratory producer matrix can use conservative financial observations and interval-checked prices, with CIK as the issuer identifier, metric-specific assumed availability dates, quality statuses and missingness flags. CIK is not a dated security identity. The producer is diagnostic-only until the shared consumer accepts definitions, clocks and identities. Do not backfill values before publication, merge unresolved narrative amounts as expenditure, treat the EPSS mapping as proven historical knowledge, or call the current price series a certified total-return/options dataset. Reviewed event tables remain separate until their date and entity policies are enforced in the join.

Next priorities: reconcile the highest-impact financial basis cases; review the 135 price events and corporate-action coverage; then review historical CVE ownership/knowledge dates and scoped cloud/employee-AI evidence. Property activity is excluded from the planned matrix at the user's request. The matrix structure need not wait for all of those reviews, but its use must respect their flags.

## Architecture alignment — supplied project synthesis, October 4, 2026

The packaged-software work is a Benchmark producer feeding the shared validation spine. It does not own another registry, experiment splitter, label generator, spending gate or account evaluator. Consumer acceptance belongs to Post Benchmark under the coordination arrangement supplied by the user. The coordination and strategy-validation documents named in that synthesis are absent from this checkout, so this alignment is based on the supplied context, not a verified reading of those local contracts.

- Primary evaluation starts January 2024; retain 2022–2023 for financial history, warm-up and other protocol-approved context. Neither 2024 nor 2025 is designated an untouched final holdout here.
- The shared issuer decision grid is 15:30 America/New_York. A company-month table may be a coverage view; it is not a substitute for the shared decision records or an exchange-session calendar.
- Our next-day `available_date_conservative` is an assumed historical replay policy. It is not an actual receipt, processing-completion timestamp or proof of first-public release timing. Keep those clocks separate; unknown clocks remain unknown.
- A source/accounting check does not qualify an intraday predictor. The shared native consumer currently accepts only four specifically defined instant entity-scope USD GAAP facts; their exact registered definitions must be read before mapping our wider metric set.
- CIK identifies an issuer. Assigned target CIKs on price bars do not independently certify a dated share class, option deliverable or futures contract. Preserve identity-review status and original metadata.
- Keep USD balances, period flows, commitments, probabilities, adjusted-close fractional returns and executable account cash flows distinct. Correlation and a shared company name do not establish economic exposure.
- Property/cloud/AI candidates, restatement uncertainty, retrospective EPSS attribution, missing outcomes and source conflicts propagate to consumer exclusions. No diagnostic-only input receives trading authority by passing extraction tests.
- Publish an immutable producer packet with definitions/schema version, checkout fingerprint, input/output hashes, grain, units, clocks/assumptions, exclusions and a small actual-row fixture. Acceptance remains pending until the consumer returns evidence.

See `PACKAGED_SOFTWARE_HANDOFF.md` for the producer boundary and the next handoff sequence.

## Feature scope decision — October 4, 2026

User requested dropping property activity because only three event records have been individually reviewed. Exclude property-event features and permit/deed candidates from the planned matrix and handoff feature payload. Retain raw sources, audit history and event tables as archived research evidence. This decision does not remove the separately reported SEC asset-balance metrics; those retain their balance-versus-spending definitions and quality gates. Financials and prices remain the proposed core; EPSS, cloud commitments/expenses and employee-AI evidence remain separately qualified research blocks, not universally available predictors or confirmed trading signals.
# Matrix rebuild milestone — October 4, 2026

The authorized local diagnostic rebuild is complete: `final/feature_matrix_backtest.csv`
uses conservative financial observations, reviewed price bars, corrected tied ranks
and matched 63-session price-return labels, and separately scoped reviewed cloud
disclosures. Every cell has provenance or a missing reason. The full 168 × 19 grid
contains 3,192 rows and 83 raw feature definitions; 2,300 diagnostic labels are
populated. Seven matrix tests, five financial tests and 13 independent artifact checks
pass. See `final/REVIEWED_MATRIX_REPORT.md`. Historical clocks, accounting semantics,
membership, corporate actions and consumer acceptance remain open gates. Government
award inputs are withheld; legacy events/annual data remain diagnostic only. Property
activity remains excluded. The original final files are archived; SQLite/root/output
copies have not been synchronized. This milestone does not complete the shared
consumer publication stage or qualify an executable backtest.
# Financial density milestone — October 4, 2026

Version 2 of the diagnostic matrix adds strict direct/same-filing recovery and
separately defined quarterly ratios. All 125,666 retained source facts were rechecked.
The gain is 17,622 populated cells, chiefly derived quarterly ratios; existing
definitions gain 21 cells and lose none. Population is 40.08% over 94 definitions.
Quarterly R&D/revenue and gross margin are each approximately 75% populated.
Five additional individually reviewed cloud records raise selected cloud coverage
to 25 issuers. Source hashes, late availability and mixed/exceptional scope are
preserved. Seventeen focused tests pass. Original cross-filing gates and raw files
remain unchanged. Historical price gaps/actions were not interpolated or certified.
See `final/FINANCIAL_DENSITY_REPORT.md`; earlier matrix milestones are historical.
