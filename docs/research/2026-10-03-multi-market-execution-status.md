# Multi-market testing execution record

Plan: `docs/superpowers/plans/2026-10-03-multi-market-lattice-research.md`.
Design: `docs/research/2026-10-03-multi-market-lattice-design.md`.

## User authorization

2026-10-03: The user authorized testing all proposed futures families and numerical roles, starting with the best recommendations, and thoroughly evaluating valuable extensions of Lattice's underlying approach. Daily decisions, next-session outcomes, separate futures profit/hedging evaluation and historical evidence followed by frozen forward paper testing remain accepted. Databento spending must remain below the standing $250 total cap.

## Execution order and decisions

- ES/MES index futures first; treat them as one economic exposure with different execution economics.
- Treasury rates next, then energy/metals. Product-specific data and outcome rules apply.
- Forecast improvement is the primary first comparison; risk/filter benefit and direct trading signal are separately registered comparisons, not discarded alternatives.
- Ruling: implementation continues in the existing `codex/options-export` checkout using newly owned paths. Concurrent work and untracked data/configuration would not be preserved by a fresh checkout. Shared existing files and sibling workstreams remain under their existing owners.
- Ruling: historical studies on previously inspected Lattice/CFO data are exploratory. New permutations of existing data are not independent confirmation. Final model/policy promotion requires genuinely reserved evidence and a prospective paper period.
- Ruling: safe defaults for research clocks, trial budgets and economic accounting will be recorded before runs. A missing execution/cost/lifecycle input yields a scientific pricing study or an explicit blocked test, never an invented executable profit result.

## Task status

1. Protocol/feature registry: initial diagnostic frozen in `configs/experiments/multi-market-v1.json`; former grill choices resolved by explicit user authorization.
2. Existing data/provider audit: real remote Lattice files audited; nine bounded futures/equity batches purchased for $8.53021915629506 and finalized by Databento. Download verification is running remotely.
3. Lattice extension research and numerical harness: six economically distinct extensions critically assessed; two small initial numerical packets implemented with ordinary controls, same-row comparisons and retained failures.
4. Market labels/execution/accounting: cash, negative-price, roll-leg, quote-side/size/freshness failure fixtures implemented. Executable account economics await product lifecycle, fees, capital and exposure evidence.
5. Historical comparisons: equity, all four futures exposures, registered simple/risk controls and full matched option diagnostic complete with verified artifacts. Large runs used detached remote tmux.
6. Forward paper: pending historical promotion; the passage of a paper period cannot be simulated as observed evidence.

## Environment evidence

- Local passwordless `ssh home-pc` initially failed because the sandbox could not access SSH configuration. An authorized unsandboxed read-only check succeeded: hostname `john-riley-X870-GAMING-WIFI6`, home `/home/john-riley`, tmux `/usr/bin/tmux`.
- Original remote Lattice appears at `/home/john-riley/projects/geomarket`; inspection pending. Existing QuantHacks remote directory is `/home/john-riley/QuantHacks`.
- The current ledger snapshot is $23.13916580583627 actual plus quoted of $250. Existing exact-contract OPRA batch is still processing; no duplicate request has been submitted by this execution.

Record each actual acquisition, test command, remote run, exclusion and result below. Do not infer a successful run from a plan or job launch.

## Actual equity diagnostic

- Detached session `qh-lattice-eq-20261003`, exit 0. Remote output `/home/john-riley/QuantHacks/multi-market-20261003/results/native-equity-v1`; copied to `data/processed/multi_market/native-equity-v1` with its log.
- Fixed 12 names, training 2018–2023, diagnostic 2024–2025, 63-session window, fixed ridge and no parameter search. 6,024 paired observations across 502 sessions. SPY was absent from the native panel; the factor is explicitly the equal-weight internal panel.
- Graph stability: 0.1327% relative forecast error reduction; residual state: -0.3177% (worse). Historical ticker mean: 0.8281% improvement; zero-change forecast: 0.4470% improvement. Neither Lattice packet clears the 1% floor or beats the simple substitute. Both packet improvement intervals include zero under the fixed exploratory calendar-block assumption.
- Risk and direct mappings were computed as uncosted mark diagnostics. Their economic gates remain blocked, and risk exposures differ. No profitability, filtering superiority or independent confirmation follows.
- Decision: **do not promote** these equity packets on this evidence. Retain results and do not retune the window after inspecting them.

## Actual acquisition and review

- Nine finalized requests: GLBX.MDP3 statistics/definitions/daily/BBO for ES, MES, ZN, CL, GC; rank-one BBO/definitions for ES, ZN, CL, GC to recover same-contract observations across switches; SPY/QQQ MINI daily, SPY MINI BBO and overlapping SUMMARY daily. Rank-one data is a distinct scope, not another independent market hypothesis.
- Shared ledger preserves six earlier purchases and adds nine individual job IDs, each with scope hash and actual cost. Conservative actual-plus-reserved total: **$31.669384962131893**, below the exclusive $250 cap. Aggregate pilot reservations are not added a second time.
- Independent review found two acquisition defects: stale actual costs before later submissions and provider duplicate history limited to today. Both reproduced with failing tests and fixed; provider retained history and financial reconciliation are now checked. Concurrency/idempotence ledger regressions also pass. No extra paid orders were placed for these fixes.
- Focused suite at this checkpoint: 47 tests passed in 6.5 seconds. This checkpoint is not the final futures/options adapter verification.
- Downloader completed exit 0: **5,169 files, 202,464,684 compressed/support bytes** across all nine jobs; provider size/SHA-256 checks passed and the temporary remote credential was removed. Local status/nine manifests were retrieved and all ten remote/local hashes matched. Evidence: `data/processed/multi_market/pilot-download-verification/`. The original project credential remains outside artifacts.
- Equity retrieval verified all eight remote/local hashes (six outputs, log and native metadata). Evidence: `data/processed/multi_market/native-equity-v1/retrieval-verification.json`.
- Contract selection uses Databento's previous-day-volume ranking; [primary symbology specification](https://databento.com/docs/standards-and-conventions/symbology). Actual contracts and missing same-contract exits remain explicit. A documented holiday mapping concern and historical-vintage limitations prevent treating provider mappings as an audited execution rule.
- Calendar review correction: use independent observed SPY daily bar dates, rather than dropping dates with missing/invalid SPY interval quotes. Missing interval exits must remain missing, not become a longer holding period.

## Actual futures diagnostic

Run: detached `qh-lattice-futures-20261003`. An initial interpreter-path failure occurred before parsing or outcomes and is preserved; corrected absolute Python path completed `EXIT_CODE:0`. No statistical rerun or tuning. Local output: `data/processed/multi_market/futures-v1/`.

Train 2024 after fixed 63-session warmup; diagnostic 2025. Each economic root is fitted separately. Target is a same-contract next-session midpoint change divided by prior point-change risk. Positive percentages below mean lower forecast MSE than the ordinary six-input baseline; they are **not trading returns**.

| Exposure | Paired diagnostic sessions | Residual packet | Graph packet | Simple past mean |
|---|---:|---:|---:|---:|
| ES index | 249 | +3.900% | -0.137% | +23.214% |
| ZN rates | 249 | -29.917% | +6.898% | +22.919% |
| CL energy | 249 | +8.892% | -0.284% | +21.561% |
| GC metals | 245 | -0.134% | +0.454% | +20.960% |

Decision: **no forecast packet promoted**. Several clear the 1% baseline floor, but every packet loses to the registered simple substitute. Zero-change forecasts also outperform the Lattice packets. Ordinary-model complexity therefore explains some apparent incremental wins; they do not establish useful forecasting skill. Fixed calendar-block intervals are exploratory and are not multiple-testing-adjusted significance proof.

- Risk/filter and direct sign policies computed for every root. Risk exposures differ (residual policy about 0.84 versus ordinary policy about 0.99); lower risk at lower exposure cannot prove better filtering. Direct values are uncosted normalized point-change diagnostics, not account returns. No economic or hedge promotion.
- MES is only an implementation diagnostic of the index exposure. No second independent alpha cell is added.
- Calendar independently verified against official NYSE schedules: exactly 502 sessions, 252 in 2024 and 250 in 2025, zero unexpected/weekend dates, including the 2025-01-09 closure.
- Same-contract exits missing: CL 3, GC 7. These remain missing, not later exits. Rank-one data recovers legitimate same-contract observations across switches; no roll gap is counted as profit.
- All 15 derived artifact hashes and seven source/configuration/runner hashes match local and remote. Source hashes are explicitly **post-run retrieval** evidence, not fabricated pre-run timestamps. Evidence: `local_retrieval_verification.json`, `source_config_postrun_hashes.json`, `calendar_audit.json`.

## Actual initial options diagnostic

Detached `qh-lattice-options-20261003` completed exit 0. Seven report artifacts retrieved and SHA-256 verified under `data/processed/multi_market/options-matched-v1/`.

- 34 events, 20 exact pre-event View B / mahalanobis scores; no filling with another date or estimator.
- Actual one-session post-event outcome rows separated from source horizon-1 pre-event rows that held multiple sessions. 1,566 strategy rows collapse by expiry and event instead of becoming independent observations.
- Six quote-qualified event/strategy groups all belong to one GD event whose exact 2024-01-04 pre-event score is absent. **Zero primary matched event groups**.
- Fresh last-trade secondary cohort: 108 event/strategy groups over 18 distinct events and 16 tickers. Stale/missing trade marks remain excluded. The minimum-20-event heuristic is not met and is not a statistical power guarantee.
- Initial decision: **inconclusive**, no fitted options forecast or economic conclusion. The subsequent full quote results are recorded below; the initial sparse report is preserved.

## Verification and remaining gates

Fresh focused command `.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_multi_market*.py'`: **55 tests passed**, exit 0, 10.8 seconds. Independent code review found no remaining material defect; its bundled runtime could only run futures fixtures, while the parent configured environment ran all relevant tests. No whole-repository pass is claimed.

All registered forecast/risk/direct roles have either an initial diagnostic or an explicit data/economic gate. Separate exposure-specific hedge experiments remain blocked on a fixed underlying portfolio, measured exposures and account/cost/lifecycle contract. No existing evidence meets the forecast promotion gate; consequently a winning strategy has not been frozen for forward paper trading.

The six assessed extensions remain mechanisms to test, not validated strategies. Factor residuals and graph stability were tested here. Futures curve state, constrained hedge policy, synchronized option IV/skew residuals and dated economic-link surprises require separately frozen product-appropriate comparisons; existing equity-coordinate plots or failed H1 peer reversion are not evidence for them. Prioritize term structure and option surfaces over a broader coordinate/topology search.

## Full existing options backfill continuation

- Existing provider job reached 99%, then completed; **no second option order** was created.
- Heavy processing handed to isolated `/home/john-riley/QuantHacks/multi-market-20261003/full-options`, detached `qh-full-options-20261003`. Staged source hashes and dependencies verified before launch. The prior readiness freeze is preserved after a provider-ID guard correction.
- Local waiting processes 142440/207420 were stopped only after their workspace interpreter, script arguments, parent relation and exact waiting job state were verified. Original data and logs remain. Handoff receipt: `data/raw/databento/multi-market-pilot/options_remote_handoff.json`.
- Remote continuation polls this existing job, downloads/verifies it, deletes its protected temporary credential, normalizes quote marks, runs native ingest/study with exact native scores, and repeats the unchanged matched diagnostic. The dedicated namespace avoids overwriting the completed nine-batch pilot status.
- Background heartbeat `finish-purchased-options-backfill` was created for the pending completion and is now **PAUSED** after verified completion. The parent collected results before its next run. No ongoing watcher is needed for this completed job.
- Fresh suite including persisted finalizer guards: **60 tests passed**, exit 0, 10.5 seconds. Wrong real provider `id` was reproduced failing before the guard correction; both `id` and legacy `job_id` now bind the fixed purchased scope.

## Full options completion and final registered controls

- Full remote continuation completed exit 0. Purchased OPRA batch: 32 verified files, 32,189,610 records, 2,575,168,800 binary bytes; actual cost **$4.7966256737709**. Normalized **82,843 daily quote marks**. Temporary credential removal verified.
- Reduced native ingest/study and fixed matched diagnostic are available under `data/processed/multi_market/full-options-v1/`. All **22 indexed stable artifact hashes** and **six remote/local receipt hashes** match. Raw compressed files remain remote.
- Full coverage: 34 events, 20 exact pre-event scores, 192 quote/size-qualified event-strategy groups. Primary comparison has **108 groups over 18 distinct events** after matching/quality gates. The fixed 20-event coverage heuristic is still unmet; distinct events are not guaranteed independent. Result: **inconclusive**. No forecast model, lowered threshold or profit claim.
- Shared acquisition ledger retains 15 individual purchases and now reconciles this existing job's actual charge. Conservative total **$31.669410635902793**. Completion receipt: `data/raw/databento/multi-market-pilot/options_remote_completion.json`.
- Registered simple controls completed from original frozen predictions without refitting: `data/processed/multi_market/role-comparisons-v1/`. All ten candidate-versus-simple-mean forecast effects are negative. CL residual direct-sign increment versus simple mean is +0.024737 prior-risk mark units, interval [-0.102562,+0.151042]; versus zero, +0.070121 with interval [-0.018076,+0.189793]. An apparent gain versus the ordinary model is not evidence of a useful direct signal.
- Registered risk comparison recovered exact original training cohorts/constants from saved features, with no forecast refit: `data/processed/multi_market/risk-comparisons-v1/`. Original row keys, counts, feature means and risk statistics reproduce. Ordinary-control scaling is fixed using **training** average exposure, not heldout averages. Row exposures and constants are saved. This supersedes the earlier aggregate-only `inconclusive_stateless` risk gate while preserving that original diagnostic.
- All four futures graph filters have worse observed downside variation than the training-scaled ordinary control, with mean increments/intervals below zero under the fixed block assumption. Their average heldout gross exposures differ by less than 0.004. Residual filters and equity policies have larger exposure mismatches, explicitly flagged; no equal-exposure or economic superiority claim follows.
- Final focused command `.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_multi_market*.py'`: **69 tests passed**, exit 0, 9.8 seconds. Original forecast fits, reports and source files remain unchanged; no lookback/threshold search was added after results.

**First diagnostic pass complete.** ES/MES remains the recommended implementation pilot and forecast comparison remains the recommended first test. None of these tested forecasting/filtering variants is promoted; direct results and options evidence are inconclusive. Exposure-specific hedging, validated execution/account returns, product-specific curve/surface hypotheses and genuinely reserved/forward evidence remain separate research gates rather than completed strategy proof.
