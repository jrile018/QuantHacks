# Feature matrix foundation while industry research is pending

Status: design contract, 2026-10-03. No model, multi-company options backtest, or trading signal is claimed here. Read with `docs/8k-anticipation-research-concept.md` and `docs/trading-data-api-catalog.txt`.

## Research question

At a fixed decision time, use only information already public to compare the **net future return** of a prespecified call, a prespecified put, and no trade over the same holding horizon. A forecast of company quality or stock direction is not enough: option premium, time decay, spread, and contract selection affect the result. This is a research design, not a recommendation to trade.

No matrix is literally free of bias. The practical goal is to make eligibility, information timing, missing data, contract choice, costs, and evaluation rules explicit before seeing the answers.

## Row and storage contract

One matrix row represents `(CIK, decision_timestamp_utc, horizon_id, feature_version)` for an **eligible issuer at a scheduled decision time**. Generate rows on the same calendar rule for firms with and without a subsequent 8-K; do not select only dates that later had news. Keep historically effective ticker, option root, security identifier, SIC/industry, and listing status in dated mapping tables. Treat the 53 SIC-6798 filers as a source cohort, not an automatically tradable REIT universe.

Keep a long-form observation table before making a wide model matrix. Each observation needs `cik`, `feature_name`, `value`, `unit`, `source_id`, `source_record_id`, `source_url`, `period_end`, `public_at_utc`, `retrieved_at_utc`, `valid_from_utc`, `definition_version`, and `quality_status`. The wide matrix takes the latest valid observation whose `public_at_utc < decision_timestamp_utc`. Record missingness as `not_applicable`, `not_published_yet`, `unmatched`, or `source_error`; never silently replace a missing value with zero or a later revision. Keep original as-filed versions when a filing is amended.

| Matrix block | First candidate fields | Source and timing rule |
| --- | --- | --- |
| Identity and eligibility | CIK, dated ticker/FIGI, industry, optionable flag | Dated issuer/security crosswalk; do not use today's membership in old rows |
| Issuer history | Prior 8-K count and days since prior comparable item | Only accessions public before decision; future item code is a label, never a predictor |
| Financial condition | Latest as-filed revenue growth, cash/debt, interest coverage where meaningful | SEC accession, exact fiscal period/unit/scope, acceptance/public time; no later restatement in old rows |
| Market and options | Prior stock return, volume, call/put premium, spread, DTE, implied move if supported | Snapshot or executable quote at/before decision; never compute historical IV from future realized volatility |
| General context | Rates, credit, local activity and peer results | Preserve each source's actual publication time and revision vintage |
| Industry overlay | REIT occupancy, FFO/AFFO, debt maturity; defense award backlog; other approved sector fields | Add only where the issuer and measure match; store non-applicable separately from missing |
| Data quality | Source age, mapping confidence, quote staleness, extraction method | These describe what was knowable then; review whether missingness was created by later data collection |

Each of the 30 cataloged APIs is a **candidate source**, not a required column. Make a source-to-feature registry with: source ID, issuer or market scope, applicable industry, join key, update frequency, historical coverage, publication lag, revision policy, exact feature formula, unit, missing policy, and a reason the feature might add information beyond option prices. Reject a source if its past publication times or entity mapping cannot be established. Industry-specific research can add rows to this registry without changing the common row key.

## Freeze the target before constructing labels

1. Fix the decision calendar and time (for example, a stated close or next session after data release), the holding horizon, and the permitted event types. A pre-filing model must include ordinary no-event dates. A post-release model needs separate rows and a later decision time.
2. Fix the **same ex-ante contract rule** for calls and puts: expiry/DTE range, moneyness or delta rule, minimum liquidity, and how ties are broken. Select contracts using only quotes available at the decision time. Do not choose the option that later performed best.
3. Define each label as the call or put's exit value minus entry cost, commissions, and stated slippage, divided by the cash or risk capital committed. Keep the no-trade payoff at zero. If historical bid/ask quotes are unavailable, mark the result `pricing_proxy` and do not call it executable P&L.
4. Compare the three choices on the **same issuer-decision rows**. A put/call-only classifier forces a trade when neither option is attractive. Track both direction accuracy and after-cost option return; they answer different questions.

## Work that can start now

1. **Coverage ledger.** From the 1,630-CIK filing export, record dated ticker/issuer mappings, active listing and option-data availability. For the 53 SIC-6798 filers, separate equity REITs, mortgage REITs, nonlisted trusts, and stale/inactive entities before any options study. Report counts and reasons for exclusion.
2. **Source registry.** Turn the API catalog into feature candidates with join keys, publication times, coverage, and applicability. Start with EDGAR, Massive, rates, and identifier mapping; do not ingest all APIs just because they are listed.
3. **Timing audit.** Use the saved GD event as a small trace: show the decision time, every proposed value's source/public time, the selected contract using the fixed rule, and the label window. The current cache has only a GD option chain and a few daily option-bar series; it lacks historical option bid/ask and a broad REIT option sample.
4. **Null and provenance checks.** Verify that a row cannot contain a later filing, revised macro value, future industry classification, post-event option bar, or outcome-derived feature. Preserve source links and hashes so individual cells can be audited.
5. **Baseline protocol.** Before adding sector features, freeze a simple no-trade baseline and a market-only/option-only baseline. Reserve a later time window for final testing, use forward-moving training windows, account for overlapping holding periods, and log every feature/strategy trial. Add an industry feature only if it improves the after-cost result outside the tuning window.

## Current readiness gate

The repository has 1,630 distinct filing CIKs and 53 SIC-6798 REIT-labeled filers. Its saved option-chain underlying is GD; no saved REIT option contracts or option bars are available. The existing runner is a retrospective 8-K event study, not a matrix over all eligible issuer-days. It uses daily last-trade option marks rather than historical executable bid/ask quotes. Therefore, a multi-company put/call verdict is **not yet supported**. The next evidence gate is dated option coverage and a fixed contract/decision rule; industry data can be slotted in afterward.

## Evidence and cross-references

- Local: `README.md`, `data/README.md`, `data/processed/options_volatility_analysis.md`, `docs/reit-source-map.md`, `docs/8k-anticipation-research-concept.md`.
- SEC filing/XBRL API scope: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Option price drivers and time value: https://www.optionseducation.org/referencelibrary/faq/option-price-behavior
- Backtest search/overfitting risk: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659
