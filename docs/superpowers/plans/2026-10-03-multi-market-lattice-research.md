# Multi-market Lattice research implementation plan

> **Execution authorized 2026-10-03:** The user requested every proposed futures family and all three roles, recommendations first. Use superpowers:executing-plans. Actual runs, purchases and limitations are recorded in [execution status](../../research/2026-10-03-multi-market-execution-status.md); unchecked tasks below are not completed evidence.

**Goal:** Test whether Lattice's numerical market context adds useful information across equities, listed equity options and futures, then evaluate any surviving rules in a frozen forward paper test.

**Architecture:** Share dated observations, identities, decision features and provenance. Use market-specific forecast labels/execution adapters, separate futures alpha and hedge experiments, and one account/exposure ledger. The graphical view consumes numerical artifacts; it does not determine success.

**Tech Stack:** Existing Python/Parquet/Databento adapters and Lattice C++ exporters; simple baseline models; existing EDGAR/FDS/document artifacts; home-pc for eventual large processing/backtests.

**Spec:** [Research design](../../research/2026-10-03-multi-market-lattice-design.md). Accepted: option A, all three markets, daily/next-session horizon, separate futures alpha/hedge outcomes, historical evidence then forward paper. [Grill record](../../grill-sessions/2026-10-03-multi-market-lattice.md) holds remaining parameters.

## Global constraints

- Preserve the existing 8-K parallel plan and shared files; consume the Post Benchmark outputs rather than independently changing `src/options_learning.py`.
- The existing $250 total Databento cap remains; the last ledger showed $23.13917 actual plus quoted. Validate the live ledger and metadata quote before any later acquisition.
- Reuse the pending OPRA exact-contract batch and downloaded daily bars. Duplicate requests need an explicit technical reason and cost entry.
- Never equate UTC bars, regular-session closes, official settlement, minute quote samples and update-level quotes.
- Use historical eligibility and only observations available by decision; preserve corrections and explicit replay assumptions.
- H1 peer-reversion remains failed. New features require distinct registered hypotheses and identical-row baseline comparisons.
- Forecast value, trading value, risk-policy value and hedge value have different gates.
- Current inspected history is development material; final dates/cohorts must be genuinely reserved. Forward evidence remains required.

## Review focus

1. A final equity summary or revised futures statistic is accidentally used before publication.
2. A futures roll gap, negative price or multiplier change is misreported as a signal or return.
3. Missing Lattice coverage changes the comparison cohort and manufactures an apparent gain.
4. Shares, option delta and index futures double-count one exposure; margin-percent and premium-percent returns are compared unfairly.
5. A minute quote interval is renamed to imply original quote freshness or guaranteed execution.
6. A geometry transform/reference/threshold is fitted on the full history, including the heldout period.

## Proposed ownership and seams

| Lane | Proposed responsibility/files | Can begin independently | Final dependency |
|---|---|---|---|
| Integration | `configs/experiments/multi-market-v1.json`, versioned data contracts | Capture accepted/pending decisions | Grill answers before freeze |
| Coverage/data | `scripts/multi_market/audit_coverage.py`, `data/processed/multi_market/coverage/` | Audit purchased caches; free provider metadata | Frozen pilot scope before quote/order |
| Lattice numbers | `stat-arb/tools/export_market_context.py`, derived Parquet registry | Verify existing exports/causal windows | Dated panel and decision cutoffs |
| Market labels | `src/multi_market/instruments.py`, `calendars.py`, `labels.py` | Interface and bounded failure fixtures | Real mapping/session/quote audit |
| Features | `src/multi_market/asof.py`, observation adapters | Consume FDS/industry/release contracts | Source quality and availability |
| Research/risk | `src/multi_market/evaluation.py`, `portfolio.py`, `paper.py` | Protocol/ledger design and fixtures | Audited labels/features and frozen rules |

These paths are proposed new ownership, not files implemented by this planning turn. One integration owner maintains shared schemas and the experiment ledger. Workers are not alone in the checkout and must preserve others' changes.

### Task 1: Freeze the experiment contract

- [ ] Record futures universe and first numerical claim; settle exact daily decision/entry/exit, universe eligibility, primary option/roll policies, permissible positions and risk/reporting assumptions.
- [ ] Create an immutable experiment config with versioned IDs, data/feature formulas, costs/latency scenarios, development/validation/reserved final periods and practical promotion/rejection criteria.
- [ ] Separate scheduled anticipation, unscheduled/no-event anticipation and post-release response; keep the futures market-state baseline independent of a future filing label.
- [ ] Specify whether the first comparison concerns forecast improvement, exposure-matched net trading value or hedge/risk benefit. Other outcomes remain registered secondary tests.
- [ ] Review the contract against the accepted intent and the outstanding grill answers; do not backdate the experiment freeze or call inspected data unseen.

Deliverable: one auditable research protocol and a feature-source registry. Gate: all parameters affecting the primary comparison are fixed before heldout outcomes are inspected.

### Task 2: Audit reusable data and quote a bounded gap-fill

- [ ] Inventory raw/processed files and their schema, source hash, coverage, timestamps and license/entitlement scope. Finish the existing quote order through its existing finalizer.
- [ ] Produce a coverage waterfall for issuer-days, selected options and actual futures contracts: unavailable, inactive, unmapped, illiquid, malformed and eligible.
- [ ] Query provider dataset ranges and supported schemas. Validate EQUS.SUMMARY/session scope, OPRA symbols/definitions/OI, and GLBX actual maturities/statistics/quote-book choice.
- [ ] Write explicit candidate orders with symbols/roots, dates, schema, definitions and expected output; use free metadata estimates and the shared budget ledger. Start with a bounded panel and quote windows, not every feed/order event.
- [ ] Acquire only approved/frozen scopes under standing budget authorization, retain request receipts/costs/checksums, and scan count/schema/date/symbol coverage.

Verification cases: per-venue versus consolidated rows; holiday/early close; missing quote intervals; futures delayed/revised statistics; renamed/inactive ticker; duplicate already purchased scope.

Deliverable: matched historical data and a cost/coverage report. Gate: quote provenance and historical availability meet the chosen pricing or execution study's contract. Incompatible sampled data stays explicitly a proxy.

### Task 3: Export and audit numerical Lattice features

- [ ] Map existing `features`, `edges`, `geometry`, `scores`, `spreads`, `baskets` and `regime` artifacts into long-form observations with fit-window and available-time evidence.
- [ ] Start with ordinary controls and one predeclared Lattice scalar. Add a separately versioned eigenvalue-concentration/residual-series exporter only if that is the registered hypothesis; those are not existing standalone exports.
- [ ] Add asset-aware instrument calendars/returns adapters before using futures in geometry. Preserve raw contract differences and an ex-ante normalization scale; never apply positive-price log-return code to negative spreads/prices.
- [ ] Keep options as an underlying/IV/liquidity overlay; do not over-weight an issuer by giving every strike an equity-like vertex.
- [ ] Preserve estimator/view distinctions and causal alignment/reference versions. An output p-value measures unusualness under that fit, not a calibrated return probability.

Verification cases: future-dated input cannot alter an earlier feature; coordinate rotation/reflection cannot change an invariant feature; contract roll/negative-price fixtures; missing scores remain missing; no future score fills an earlier gap.

Deliverable: inspectable numerical Parquet features and a formula/availability audit. Gate: reproducible from decision-eligible observations, independent of future outcomes.

### Task 4: Build market-specific labels and shared cash accounting

- [ ] Equity: actual underlying quotes, corporate actions/dividends and declared financing/shorting assumptions. Preserve raw executions and dated adjustment logic.
- [ ] Options: fixed entry-time contract identities, deliverables, same-contract exits, call/put midpoint diagnostics and side-specific cash returns. Use actual contemporaneous underlying rather than treating synthetic parity spot as an observed stock fill.
- [ ] Preserve quote prices, original timestamps and displayed sizes. Reject crossed/invalid quotes and quotes lacking the capacity required by the frozen policy. Define conservative participation, partial-fill and nonfill treatment; sampled prices remain proxy evidence unless the execution contract can be met. Missing execution evidence cannot trigger a retrospectively favorable substitute contract.
- [ ] Futures: resolved contracts, multiplier/tick/currency, execution sides, settlement/variation margin, explicit roll trades and expiry/delivery rules. Continuous adjusted series supports a named feature calculation only.
- [ ] Reconcile cumulative variation margin, residual mark-to-market and entry/exit cash adjustments to quantity × multiplier × execution-price change, less costs. Do not add settlement cash flows again to total execution P&L. Separate collateral transfers from profit and count every actual roll leg once.
- [ ] Align source clocks backward to decisions while retaining market/product session calendars. Use original quote times and interval anchors for what they actually mean.
- [ ] Build one cash/exposure ledger for concurrent positions, premium/collateral, margin, financing, fees, drawdowns, liquidation constraints and beta/delta/gamma/vega concentration.
- [ ] Implement futures hedging as a separate comparison: no hedge, simple frozen beta hedge, then a Lattice-informed hedge policy. Measure portfolio-plus-hedge cost and residual risk.

Verification cases: zero-size/insufficient-size quotes, partial fills and nonfills; missing fixed-session exit cannot be skipped to a favorable later session; no favorable substitute contract; roll gap is not P&L; multiplier math; held-across-settlement-and-roll example with equal lifecycle P&L under cash-flow and execution-price representations; corrections after cutoff; same equity exposure through shares/options/futures; insufficient cash/collateral; short-side reversed cash flows.

Deliverable: matched scientific labels plus cash/account outcomes. Gate: an auditable example per market and an overlapping-position account trace. Label quality is not proof of model alpha.

### Task 5: Run paired incremental-value experiments

- [ ] Fit simple market-specific baselines first using price, volatility, liquidity, calendar and ordinary correlation/beta features. Market-data work can proceed while OCR quality work continues.
- [ ] Add eligible FDS/industry/release measurements where appropriate. Futures macro/curve predictors require their own economic mapping and availability evidence.
- [ ] Add the registered Lattice family on the same rows with the same model capacity, exposure, contracts, execution and exit rules. Replace it with its cheaper simple substitute in a paired challenger.
- [ ] Use chronological grouped splits, overlap purges, training-only transforms and a trial/holdout ledger shared across all market/feature variants. Related equity/option/futures observations do not become independent samples.
- [ ] Measure forecast losses/calibration, after-cost daily account outcomes and risk/hedge criteria separately, with dependence-aware uncertainty and multiple-trial accounting.
- [ ] Run preregistered dependence-preserving permutation tests for the paired increment before interpreting significance; preserve full economic-event bundles and shared calendar-time dependence across issuers and markets. Document the valid null/exchangeability assumption; if it cannot be met, report the limitation instead of a misleading permutation p-value.
- [ ] Report net daily account-return Sharpe with dependence-aware bootstrap confidence intervals, the capital denominator, annualization convention, trial count and effective independent observation support. Do not use pooled trade returns. Insufficient independent support produces an inconclusive result.
- [ ] Archive failures/inconclusive results. Promote only a materially useful increment that survives timing/cost/exposure/redundancy checks; additional horizon/feature searches are new trials.

Compute: actual large panels, walk-forward studies and simulations use `home-pc` detached tmux, versioned logs and result hashes. Do not start them from this draft.

Deliverable: a paired report with cohort, sample dependence, confidence/precision, exclusions and trial count. Gate: the selected primary criterion clears a predeclared meaningful threshold with informative uncertainty; otherwise reject or remain inconclusive.

### Task 6: Freeze and observe forward paper decisions

- [ ] Freeze the surviving feature/model/policy versions and data universe; retain ordinary/no-trade and missing-data decisions.
- [ ] Log real public/vendor/local receipt times, feature completion, forecasts, quoted opportunities, hypothetical order/fill assumptions and account exposures. Never label hypothetical fills as broker executions.
- [ ] Evaluate futures standalone alpha and hedging separately, with equity/options exposure counted consistently.
- [ ] Set the observation window/event coverage based on required precision and independent exposure/event support; never stop solely at the first favorable result.
- [ ] Review drift, realized costs and risk before any later capital decision. A forward result can reject the historical candidate.

Deliverable: frozen prospective evidence and a keep/reject/inconclusive decision for each feature/policy. Gate: completed protocol; live deployment requires its own risk and execution decision.

## Parallel schedule

Coverage audits, numerical exporter audits, FDS/industry observations and release/OCR quality work can run together after interface ownership is established. Label adapters and cash-ledger fixtures can develop in parallel. Final real-data joins wait for clock/mapping/coverage gates and the frozen protocol. After data and accounting gates, run the user-selected primary forecast, risk/filter or standalone-signal comparison. Register other comparisons as secondary. Forward paper follows the historical promotion gate.

The plan reuses [the existing 8-K parallel lanes](2026-10-03-parallel-8k-validation-and-learning.md). It expands market adapters and hypotheses while keeping one shared registry, experiment ledger and integration owner.
