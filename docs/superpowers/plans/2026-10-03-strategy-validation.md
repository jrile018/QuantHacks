# Whole-strategy validation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Establish whether dated company information and optional prediction-market observations improve forecasts and an explicitly chosen trading or hedging objective after realistic execution costs.

**Architecture:** One versioned decision/cohort contract feeds separate pre-release and post-release experiments. Company facts, text, odds and geometry retain independent provenance. Forecast evaluation precedes economic evaluation under a frozen decision policy and a shared portfolio ledger; each event track receives its own accept, reject or inconclusive result.

**Tech stack:** Existing Python/pandas pipeline, JSONL/CSV artifacts, existing options learner and provider adapters from the prediction-market plan. No new ML framework is required. Exact dependency versions will be frozen with each experiment.

**Spec:** [Research and evidence contract](../../strategy-validation-research-2026-10-03.md). Existing [prediction-market adapter plan](2026-10-03-prediction-market-benchmark.md) supplies provider-specific mechanics; [options-learning contract](../../options-model-training.md) supplies existing selection, quote and split rules.

**Status:** Proposed implementation, not executed by this research request. The literature review and this plan are complete documents; the experiments below remain open. This plan extends the earlier plans' validation requirements. It does not change other chats' code, submit jobs or assign their work without coordination.

**Shared context:** [GitHub Discussion 2: detailed validation program and cross-chat handoffs](https://github.com/jrile018/QuantHacks/discussions/2#discussioncomment-18737094).

## Global constraints

- All three tracks remain in scope: earnings/guidance, FDA/deals, and REIT/rates. FDA and deals have separate event definitions within their shared workstream.
- Preserve the 34-event CFO study as exploratory evidence. Its dependent variants do not establish a large independent sample or executable profits.
- Keep public, receipt, processing, mapping, model-version and outcome-availability evidence. Unknown is not a backdated timestamp or a zero value.
- Do not use future filings, resolved prices, later rules, retrospectively selected cohorts or future labels as predictors or selection criteria.
- Distinguish observed forward history from assumed historical replay. Preserve existing owners' branches and shared edits.
- Resolve provider use/retention/model rights before ingestion. Disabled/no-coverage states must work without fabricated odds.
- Freeze the experiment and numerical thresholds before final holdout inspection. Current evidence supplies no expected return, universal blend weight or automatic position size.
- Run bounded fixtures locally. Heavy panel builds, training, simulations and backtests follow the user's detached-tmux `home-pc` workflow, or an already authorized HiPerGator job under its owner's workflow. Record input hashes, command, environment, logs and outputs. Do not use a LAN fallback if Tailscale is unavailable.

## Review focus

1. An issuer press release precedes EDGAR: classify the decision by the actual public boundary; do not call it anticipation.
2. Many variants or issuers share one catalyst: preserve grouping in splits, inference and trial accounting.
3. Historical records arrive today: preserve observed receipt versus replay assumptions; never silently backdate.
4. A bid/ask exists but lacks usable size, synchronization or deliverable mapping: refuse an executable label and retain a reason.
5. A contract's precise event differs from company-value exposure: keep the market signal unmatched/contextual until the mapping and scenario bridge are reviewed.

## Common records and interfaces

Proposed new modules live in `src/research_validation/`. These are planned files, not implemented capabilities. Provider adapters remain in the existing proposed `src/prediction_markets/` package; avoid a second collector.

| Record | Required content |
| --- | --- |
| Decision | `decision_id`, dated CIK/security/universe evidence, track, mode, independent schedule, decision UTC, information cutoff, horizon, exposure/mandate ID |
| Realized event | economic group ID, issuer/product/transaction, source evidence, occurrence/publication intervals, EDGAR acceptance separately, eventual labels and label-available time; linked only during outcome labeling |
| Feature | decision ID, source and definition versions, value/null reason, raw hash, public/receipt/processing/effective times, mapping evidence, observed-versus-replay basis |
| Quote | existing learner contract plus provider/schema time semantics, conditions, sizes, actual underlying, source/receipt basis, deliverable and action history |
| Forecast | experiment/model/fold hashes, decision, exact target/horizon, probability or distribution, calibration version and creation time |
| Trade/ledger | frozen contracts, intended/filled sizes, quote evidence, entry/exit, costs, holdings, cash/collateral, equity and rejected/no-fill reasons |

Proposed callable boundaries, with record classes defined centrally in `records.py`:

```python
build_decisions(universe, calendar, registry) -> DecisionPanel
audit_clocks(decisions, releases, sources) -> ClockAudit
export_features(decisions, source_records, registry) -> FeaturePanel
build_quote_labels(decisions, quotes, sessions, experiment) -> LabelPanel
evaluate_forecasts(features, labels, folds, experiment) -> ForecastReport
replay_portfolio(forecasts, quotes, sessions, experiment) -> PortfolioReport
```

Each report includes eligible/excluded counts and reasons, input hashes, protocol version and uncertainty method. Adapt these records to `src/options_learning.py`; do not overwrite its clock fields or assume a daily quote table meets its intraday contract. The Benchmark feature matrix lives in its separate feature checkout; integrate its export through a reviewed adapter rather than copying or overwriting another branch.

**2026-10-04 implementation/placement clarification:** Benchmark's implemented `build_matrix` emits a wide `(CIK, decision_timestamp_utc, horizon_id, feature_version)` snapshot and long cell provenance. It selects earlier-public/valid facts, but does not gate on retrieval or provide canonical receipt/processing availability. Post Benchmark's implemented `export_features` remains the canonical typed/available FeaturePanel consumer. The native source-hash-locked readiness exporter currently invokes it using bridge long observations and its own registry; no general `matrix.csv` consumer acceptance is established. Pin the chosen route and `sec-native-xbrl` / `sec_as_filed` / `benchmark_native_as_filed` source/feature/definition mapping per capsule. Keep producer matrix/definition versions, values/units, scope/period, evidence and missing reasons. This clarification updates current local implementation status without declaring economic qualification. See [feature matrix integration](../../coordination/feature-matrix-integration.md) for the placement, grill iterations and disconfirming acceptance checks. Task4 materializes qualified observations; Task5 tests their incremental forecast value; Task6 owns costs/risk/cash replay. Optional source families do not block a qualified smaller baseline.


## Task 1: Freeze mandate, comparisons and experiment ledger

**Files:** create `configs/strategy_validation.json`, `docs/strategy-validation-ledger.md`, `src/research_validation/records.py`; tests `tests/test_strategy_validation_registry.py`.

**Consumes:** user's mandate/risk choices and the current research evidence. **Produces:** versioned registry and typed records for every later task.

- [ ] Record whether each experiment targets standalone profits, a named existing portfolio's hedge, or separately reported experiments for both. Specify assets, account/risk budget, overnight/short-option permissions and primary comparison.
- [ ] Register exact event families, decision schedule, horizons, old-study versus new-learner contract rules, primary forecast/economic metrics, development folds, untouched holdout and all attempted variants.
- [ ] Test rejection of missing mandate, mixed metric denominators, backdated freeze claims and unregistered choices. No capital promotion while risk limits are unspecified.
- [ ] Review and commit the registry/schema as one deliverable. Collection can continue while mandates are clarified; numerical economic promotion criteria depend on this task.

## Task 2: Dated universe, risk set and event-clock audit

**Files:** create `src/research_validation/{cohort,clocks}.py`, `scripts/export_strategy_decisions.py`, `docs/strategy-event-clock.md`; tests `tests/test_strategy_event_clock.py`, `tests/test_strategy_cohort.py`.

**Consumes:** dated issuer/security eligibility, public calendars/releases, Task 1 registry. **Produces:** immutable DecisionPanel, later event links and ClockAudit.

- [ ] Construct eligible ordinary company-days and scheduled-event decisions from contemporaneously known evidence, including no-event/missing cases. Use dated security mappings and liquidity screens. Keep coverage of excluded/delisted issuers explicit.
- [ ] Collect release evidence across issuer IR/newswire, regulator, transaction sources and EDGAR. Record precision/uncertainty, receipt, parsing and decision clocks; separate event occurrence from publication.
- [ ] Group announcements, amendments, repeated review cycles and shared macro events. Distinguish deadline outcomes from eventual outcomes; pending eventual cases are censored.
- [ ] Test release-before-8-K, date-only time uncertainty, holidays/DST, source revisions, later receipt, and prospective decisions without a future accession. A pre-release entry must precede the earliest plausible release; a post-release decision needs demonstrably available processed input.
- [ ] Deliver family-specific counts and a missingness/selection report. Review the clock protocol before selecting features or scoring returns. Any historical latency assumption remains labeled replay.

## Task 3: Quote and portfolio feasibility foundation

**Files:** create `src/research_validation/{quotes,portfolio}.py`; tests `tests/test_strategy_quote_labels.py`, `tests/test_strategy_portfolio.py`. Integrate through existing quote collectors and `src/options_learning.py` after owner coordination.

**Consumes:** DecisionPanel, provider-audited quotes, complete session calendar and frozen position rules. **Produces:** LabelPanel, feasible simulated transactions and one cash/equity ledger.

- [ ] Audit acquired CBBO data, schema timestamp semantics, underlying synchronization, conditions, sizes, mapping and coverage. Daily venue OHLCV is a cross-check only. Quantify whether the old 654-contract request covers newly eligible decisions.
- [ ] Select contracts using only decision-time data, freeze IDs, and apply the existing learner's 90–180-day/near-120-day selection and next-session exit as one registered candidate. Evaluate the older CFO horizon rules separately.
- [ ] Build bid/ask labels with fees, declared latency and additional slippage. Refuse stale, absent, crossed, undersized or unsynchronized quotes; report no/partial fills and rejected rows. Do not silently advance exits to a more convenient session.
- [ ] Implement overlapping cash, holdings, margin/collateral, dividends, financing, assignments, deliverable changes and expiry. Exercise short/hedge paths only under the registered mandate.
- [ ] Test two simultaneous trades competing for cash, quote size exhaustion, halt/gap exits, split/merger deliverables and one-time cost charging. Report simulated equity separately from trade marks and actual fills.
- [ ] Review the coverage and feasible-price report before accepting an economic experiment. A completed download does not pass this gate by itself.

## Task 4: Evidence-backed facts and optional expectations cards

**Files:** reuse planned provider modules/configs in `2026-10-03-prediction-market-benchmark.md`; create `docs/strategy-track-coverage.md` and `scripts/report_strategy_expectations.py`; tests `tests/test_strategy_expectations_mapping.py`.

**Consumes:** Tasks 1–2 contracts, reviewed FDS/industry facts, licensed consensus and permitted market snapshots. **Produces:** FeaturePanel and readable card per eligible decision.

- [ ] Establish intended-use permissions and exact contract availability in all tracks, with explicit disabled providers and unmatched decisions.
- [ ] Produce direct/context/unmatched mappings and versioned rules. Match earnings threshold/accounting basis/quarter; FDA indication/review cycle/deadline; deal announcement versus close and consideration; Fed outcome and dated issuer exposures.
- [ ] Build scenario evidence: earnings cash/margin/guidance changes; FDA ownership/label/launch/runway; deal close/break/terms; REIT debt resets/refinancing/hedges/property demand. Preserve uncertainty rather than generating unsupported company probabilities.
- [ ] Collect bounded forward snapshots with source/receipt/processing times, bid/ask/age/depth, raw hashes, rule revisions and capture gaps. Show FDS disagreement only for comparably defined calibrated forecasts.
- [ ] Test threshold/period mismatch, approved-after-deadline versus eventual approval, pending deals, stock/CVR consideration, ambiguous issuer mapping, missing odds and one macro event affecting many issuers. Show market-open constraints on immediate options action.
- [ ] Deliver coverage/cost/precision audit and expectations cards; each card labels facts, expectations, scenario assumptions, quality and no-data reasons. No automatic trading influence.

## Task 5: Frozen forecast ablations

**Files:** create `src/research_validation/{experiments,evaluate}.py`, `scripts/evaluate_strategy_validation.py`; tests `tests/test_strategy_ablation.py`, `tests/test_strategy_splits.py`.

**Consumes:** FeaturePanel, independently available outcomes, registered folds. **Produces:** paired forecast report and source-specific accept/reject/inconclusive results.

- [ ] Establish base-rate/calendar and simple market controls, then a **CORE** baseline containing dated FDS, consensus/guidance/news, stock/options and conventional macro information. Keep its fitted forecasts out-of-sample when used downstream.
- [ ] Compare CORE with one added group at a time: richer industry facts, TEXT (post-release only), ODDS_DIRECT, ODDS_CONTEXT and GEOMETRY. Evaluate odds-only as a diagnostic. The original prediction-market plan's B0–B5 remain its odds subexperiment; CORE corresponds to its strong odds-free B1, avoiding conflicting baseline names.
- [ ] Use identical decisions, target definitions and tuned model complexity for paired comparisons. Report covered subset and full universe with baseline fallback. Do not restrict the headline universe to issuers that happen to have markets.
- [ ] Fit calibration, imputation, transformations and feature selection only in training/validation. Freeze checkpoints/prompts/LoRA candidates on development. Keep issuers/common events grouped, purge overlapping labels and enforce label availability before fitting.
- [ ] Evaluate arrival, exact outcomes, amount surprise and stock response separately. Use proper scores/calibration and event-level uncertainty. Test both odds/stock lead-lag directions; add frozen stale/delayed-feature and block-placebo diagnostics with their assumptions stated.
- [ ] Estimate precision/collection needs before opening the final holdout. Limit searches, retain losing trials, and diagnose issuer/regime/liquidity concentration. Never fit a new blend from holdout results.
- [ ] Test a shared-Fed-event split leak, a later resolved odds feature, full-universe denominators, in-sample FDS forecasts and holdout refitting. Deliver negative/inconclusive results alongside positive ones.

## Task 6: Economic increment and risk evaluation

**Files:** extend new `portfolio.py` and `evaluate.py`; extend `tests/test_strategy_portfolio.py`. Use current learner's feature export interface; coordinate any actual learner modifications with its owner.

**Consumes:** frozen forecasts, Task 3 quotes/ledger, chosen mandate and economic thresholds. **Produces:** source/track decision report.

- [ ] Keep the candidate universe, contract-selection rule, entry/exit rules, execution assumptions, sizing function and risk budget identical between CORE and each added source. Let their frozen out-of-sample forecasts choose different allowed actions/quantities under that same policy, including no trade. Preserve all decision rows, not only overlapping trades; compare account results on the same calendar. A matched fixed-trade calculation can remain a diagnostic, not the primary economic test. Isolate information value before searching new policy parameters.
- [ ] Model and validate scenario-dependent stock response, exit IV/time value, spread and actual deliverable. At an exit before expiry, do not substitute intrinsic value. Report sensitivity to forecast and volatility errors.
- [ ] For alpha, compare after-cost account results and no trade, controlling ordinary stock/volatility/carry exposures. For hedging, compare the same underlying portfolio with no hedge and simple hedges, using preregistered loss/utility and hedge-cost measures.
- [ ] Include provider/maintenance costs, liquidity rejection, financing, portfolio concentration, common shocks and gap/stop failures. Compare uncertainty bounds on the paired economic increment to the preregistered useful threshold.
- [ ] Test the “correct event but expensive option” case, repeated collateral and forecast-only improvements. Treat useful forecast gains without useful economic gains as context only.
- [ ] Deliver accept/reject/inconclusive by track, source, mode and mandate. No pooled result may promote a failing track.

## Task 7: Forward paper gate and shared evidence updates

**Files:** create `docs/strategy-validation-results.md`; retain immutable reports under `data/processed/strategy_validation/<experiment_id>/` and update the ledger.

**Consumes:** all previous reports. **Produces:** forward paper evaluation and a documented promotion decision.

- [ ] Register the next untouched forward interval and measurement protocol. Record decisions, receipt/processing latency, proposed orders, quote availability, no fills and outcomes without retroactive edits.
- [ ] Compare observed behavior with replay assumptions. Evaluate calibration, economic increment, risk and failure rates at preregistered checkpoints; do not repeatedly search the same final data for success.
- [ ] Keep the GitHub discussion current with dates, hashes, counts, limitations and exact local/merged/runtime state. Publish corrections when clock or execution repairs reverse a claim.
- [ ] Promote only within user-defined capital/loss/liquidity limits after the forward gate; otherwise retain context, collect for precision or reject. Capital deployment is a later concrete decision, not implicit in finishing this plan.

## Cross-chat handoffs

These are proposed responsibilities and interfaces for coordination, not claims the chats accepted new assignments.

| Exact chat title | Contribution to this plan | Required handoff / blocker |
| --- | --- | --- |
| Benchmark | Dated FDS, economic-event risk set, feature matrix availability adapter | Universe/sources/mapping/receipt/processing evidence; exclude future accession selection; separate software/OCR quality from forecasting |
| Benchmark pt. 2 industry spec | REIT cash/debt/loan identities and source-linked economic exposures | History linkage across filings, units/signs, issuer roles, debt reset/maturity and coverage/review reasons; processed is not financially complete |
| Post Benchmark | Released facts/text, calibrated forecasts and options learner | No pre-release target text; fixed model/prompts/LoRA on development; distinct arrival/content/market labels and alpha-versus-hedge mandate |
| Assess Lattice repo fit | Contract quote coverage, executable-cost diagnostics, geometry ablation | CBBO/underlying/session/time-basis audit; venue OHLCV consolidation; unproven geometry remains optional |
| OCR / HiPerGator | Extraction benchmarks and reliable bounded processing | Held-out issuer/pages, table fidelity/provenance, numeric/semantic accuracy and downstream error audit; successful job alone is insufficient |
| Track work across project chats | Research ledger and GitHub Discussion 2 | Maintain evidence freshness, distinguish plans/local/main/runtime and prevent duplicate or premature performance claims |

## Current state and precedence

The independently checked CPU extraction and daily-bar milestones are in [the October 3 discussion update](https://github.com/jrile018/QuantHacks/discussions/2#discussioncomment-18736885). New Benchmark commentary reports recovered Paddle output from job 44624229 scoring 16/16 after HTML-row normalization, while the job failed after output saving; its corrected end-to-end rerun remains pending. This is owner-reported progress in this plan, not a new independently verified GPU benchmark. It supersedes the earlier “GPU submission pending” next-action snapshot without establishing completed execution or comparative speed.

Post Benchmark's verified integrated pilot 44620388 supports bounded processing, with options forecasts still not established. The four active workstreams are also drafting their own reviews/plans. Read those alongside this plan; do not overwrite them. This master plan owns shared validation gates; the existing prediction-market plan owns adapters, and each branch owner owns implementation details. Any conflicting event, quote or split contract must be reconciled before a combined experiment.

## First useful delivery and dependency order

Tasks 1–2 establish the research contract and decision clock. Tasks 3 and 4 can then proceed independently. Task 5 requires dated outcomes and a coverage/precision audit. Task 6 requires feasible quotes and a frozen mandate; Task 7 requires all prior gates. The immediate useful package is **a clock/coverage audit, one reconstructable decision card per available track, and the frozen experiment registry**, including explicit unavailable tracks. It requires no promise of returns or new large model.
