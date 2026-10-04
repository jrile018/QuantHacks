# Financial feature provenance and source design

Research/access date: 2026-10-03. Scope: planning only. This supplements [feature-matrix readiness](../feature-matrix-readiness.md), whose older quote-readiness statements predate later acquisitions. Use the [dated market audit](2026-10-03-event-timing-and-options-data.md) for current coverage.

## What “English into math” means here

Keep the exact document, text/cell evidence and extraction confidence, then compute defined measurements. Examples include negative-word share, uncertainty, novelty against an earlier same-family release, signed debt change, revenue growth and coverage ratios. These are features whose definitions can be audited. A model's sentiment score does not establish future option-price direction, and generated arithmetic cannot replace observed financial numbers.

Use native machine-readable documents before OCR. OCR extends coverage to images/scans and difficult layouts. Treat native/OCR disagreement as a review signal; do not use one to certify the other by assumption. Existing REIT interpreters already represent units, period and evidence; extend their adapters instead of creating a second interpretation system.

## Source design supported by primary documentation

SEC submissions include recent filings and links to additional history. Companyfacts aggregates standard-taxonomy entity facts; custom/segment measures need source-document handling. Frames uses last-filed observations matching a calendar period. **Design inference:** a current frames download is unsafe as an automatic historical feature source because later versions may replace what was known earlier. Preserve accession-level as-filed context instead. [SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

FRED defaults to today's real-time period; ALFRED supports information known during an earlier period. Vintage dates identify revisions or newly released values. Use the version available at the decision, with separate release-clock evidence when intraday ordering matters. A date vintage alone cannot establish receipt at 15:30. [Real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html), [vintage dates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html).

Industry measures differ in economic definition. For example, reported FFO/AFFO and adjustments need issuer definition and source evidence rather than being treated as interchangeable GAAP profit. Sector source maps are candidate registries, not claims that all APIs have reliable issuer-level historical availability. Reuse [REIT source map](../reit-source-map.md) and [financial-profile research](../financial-profile-research.md), keeping scope/rights/coverage gaps explicit.

## Candidate registry and immutable observations

For each source: provider/source ID, rights basis, issuer versus market scope, historical coverage, join keys, applicable industries, update cadence, publication timezone, revision behavior, retrieval method, cache hashes, rate/cost budget and known outages. For each feature: name/version, economic mechanism, formula, inputs, units, fiscal-period/scope alignment, missing policy, availability rule and expected gain over a market/calendar baseline.

Each long-form observation retains CIK/stable security; value and raw string; currency/unit/scale; duration or instant and fiscal period; entity/segment scope; accession/source record; URL/hash; evidence offsets/page/cell; extraction/model version; public/dissemination and actual retrieval/receipt/processing times; validity/revision interval; quality and missing reason.

Separately record historical-replay availability and latency assumptions where actual local receipt is unknown. Do not fill those nulls with filing timestamps or change today's processing date. Promotion to a retrospective replay requires documented public availability and assumed latency; promotion to observed prospective evaluation requires actual logs.

The matrix key is a decision identity with horizon/feature revisions. As-of joins accept only observations eligible at the decision under the experiment's availability basis. Source periods ending earlier are not sufficient: a December balance can first become public in February. Future amendments remain separate versions. Current industry labels and eventual event-family labels cannot enter older predictors.

## Small feature blocks before broad API expansion

| Block | Initial candidates | Constraint |
|---|---|---|
| History | Prior comparable items, days since prior release, prior schedule versions | Earlier economic events only; no future item code |
| Financial | As-filed revenue/growth, cash/debt, appropriate coverage | Match fiscal periods, scope and units; no revision overwrite |
| Market | Lagged returns/volatility, quotes/spread, DTE, supported IV | Decision-time market clock and stable contract selection |
| Wording | Counts, uncertainty, issuer-relative change, calibrated frozen text scores | Earlier text for anticipation; current released text only after release/processing |
| Industry | Small explicit sector registry | Meaningful applicability; pooled comparison before separate models |
| Macro | Vintage rates/credit/context | Release/version evidence; date-only intraday ambiguity flagged |
| Quality | Age, missing reason, source conflict, extraction method | Avoid using outcome-dependent collection failure as a predictive signal |

Industry labels should organize measurements and support pooled interactions first. Separate sector models require demonstrated coverage and precision. Standardize/impute on training only; a numerical column does not imply comparability or predictive importance.

## Audit examples and promotion gates

The eventual join tests must reject: a restated value inserted into an older row; later macro vintage; opposite signed value; millions treated as units; wrong quarter/row attachment; segment debt treated as entity debt; current ticker after a merger; future actual sentiment in anticipation; and missing values turned into zero. Fixtures should test real failure modes rather than reproduce the formula.

Keep descriptive and eligible exports distinct. Unknown history may remain useful source research with a visible limitation. Promote a feature only when mapping, availability, formula and evidence can be checked; retain an exclusion waterfall so apparent performance does not hide selected data coverage.

Then compare the new block with a frozen market/calendar baseline on the same observations, using development-only selection and paired uncertainty. Do not rank the 30 APIs by the highest full-history correlation or choose industries after inspecting profits. A source can improve data quality without improving prediction; report those as different outcomes.
