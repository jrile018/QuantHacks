# Canonical Post evidence audit

Observed at 2026-10-04 07:58:35 UTC. Canonical checkout: `C:/Users/johnp/.codex/worktrees/8k-cross-asset-validation/QuantHaxs`. This scoped audit inspected existing metadata and did not run jobs, suites, economic replay or protected tests. The shell was unavailable at first, briefly recovered, then again failed with OS error 112 (C: full). Current Git commit and fresh SHA256 recomputation remain unknown. Declared hashes below are copied from inspected receipts, not recomputed by this audit.

## Actual cohort and calendar

- `data/processed/8k_validation/wording_inputs_v2/manifest.json` contains 15 documents, eight unique accessions, four CIKs, eight primary 8-Ks and seven linked release exhibits. CIK document counts: AMT 4, BXMT 4, AGNC 3, AAT 4. Primary acceptance spans 2023-01-05T21:40:33Z to 2023-03-01T11:38:13Z; exhibit acceptance is null. These administrative acceptance clocks are not event/public clocks. Earliest-public and historical-receipt fields remain null. Seven linked exhibits are not seven independent accepted economic events.
- The new protocol permits 2024 only (`date_from=2024-01-01`, `protected_from=2025-01-01`); the inspected existing wording accession cohort contains no 2024 accession. This is a direct text/market-window dependency, not proof that all current owner work is unavailable. No substitute signal or new model is commissioned.
- `remote-v3/results/integrated-v3/sessions.json` contains 502 distinct dates, 2024-01-02 through 2025-12-31: 252 in 2024 and 250 in 2025. `decisions.json` contains 2,008 document-only issuer decisions, four CIKs each with exactly the same 502-date set. Equity/option/future eligibility is false in the sampled canonical issuer record. These are issuer/session decisions, not disclosure, prediction, fill or NAV denominators.
- Six early closes are retained: 2024-07-03, 2024-11-29, 2024-12-24, 2025-07-03, 2025-11-28, 2025-12-24. The 2025-01-09 mourning closure is excluded. Fresh metadata comparison found zero canonical decisions after their session close. Exact early-close local decision times were not printed before storage failed again.
- America/New_York sessions preserve DST: 2024-03-08 open/close 14:30/21:00 UTC; 2024-03-11 13:30/20:00 UTC; 2024-11-01 13:30/20:00 UTC; 2024-11-04 14:30/21:00 UTC. The 2025-03-07 to 03-10 shift is likewise 14:30/21:00 to 13:30/20:00 UTC. Calendar use is `retrospective_realized_horizon_only`; it does not establish historical schedule knowledge or quotes.

## Wording, availability and price diagnostic

Primary accession/acceptance chronology (all UTC second precision, administrative only):

| Accession | CIK | SEC accepted |
| --- | --- | --- |
| 0001500217-23-000003 | 0001500217 | 2023-01-05T21:40:33Z |
| 0001423689-23-000003 | 0001423689 | 2023-01-30T21:09:12Z |
| 0001193125-23-021619 | 0001061630 | 2023-02-01T21:31:09Z |
| 0001423689-23-000008 | 0001423689 | 2023-02-03T21:14:28Z |
| 0001500217-23-000006 | 0001500217 | 2023-02-07T21:19:40Z |
| 0001061630-23-000011 | 0001061630 | 2023-02-08T11:48:40Z |
| 0001053507-23-000021 | 0001053507 | 2023-02-23T12:06:38Z |
| 0001053507-23-000037 | 0001053507 | 2023-03-01T11:38:13Z |

The seven linked exhibits share their corresponding accession identities and have null SEC acceptance fields. AGNC accession 0001423689-23-000008 has no exhibit in this 15-document manifest. BXMT accession 0001193125-23-021619 has its primary and exhibit quarantined: two conflicted documents leave seven conditional primary documents and six conditional exhibits, spanning seven conditionally retained accessions. Eight total accessions, seven conditional accessions, thirteen conditional documents and 2,248 conditional fragments are distinct counts. Conditional availability is not verified public availability.

The fresh calendar/cohort metadata check loaded only sessions.json and decisions.json and evaluated `len(s)`, per-year counts, early-close lists, named exceptional-closure membership, per-instrument `{session_id}` sets and `sum(decision_at_utc > own_session.close_at_utc)`. It returned 502, 252/250, four identical 502-date sets and zero late decisions. No suite or model run was executed. The tool did not expose a stable shell command ID in the captured audit output; command ID remains unknown rather than fabricated.

`wording_results_v2/results/wording-v2/run-report.json` records 15 documents and the retained owner summary reports 2,391 scored fragments, zero failures and one truncated fragment. Actual completion is 2026-10-04T02:22:47.209449+00:00. Model cache metadata pins `ProsusAI/finbert` revision `db38d3727cbaed87c9aed72df7b3519e2ba5cca1` at `/home/john-riley/QuantHacks/8k-validation-20261003/wording-v1/models/models--ProsusAI--finbert/snapshots/db38d3727cbaed87c9aed72df7b3519e2ba5cca1`. This proves a retained runtime/model pointer, not historical model availability, training cutoff or contamination clearance. This audit did not reread all fragment spans or the cached weights.

`publication-replay-v3/lane-report.json` records 22 sources: 20 conditional and two quarantined BXMT conflicts; seven historical primaries, six historical exhibits and seven native sources. It reports 13 wording documents / 2,248 fragments conditionally source-time eligible, but zero historically qualified wording features. `observed_ready`, `canonical_handoff_ready`, `monitoring_verified` and `first_public_verified` are false; monitoring intervals are empty. The SEC filing-day-end dissemination rule plus historical-byte-equality assumption remains conditional. It is not an independently verified exact-text historical public upper bound. Actual first publication and historical receipt remain unknown.

`stock_bars_2023_2025/collection-report.json` records Massive unadjusted daily candidates, 3,008 bars = 752 per AMT/AAT/BXMT/AGNC, 2023-01-03 through 2025-12-31. Retrieval occurred 2026-10-04; processing report time is 01:31:35.633740 UTC. Bars remain unqualified for 15:30 features or execution, with historical coverage completeness false. Source hashes and exact local paths remain in that report; aggregate daily-bar timestamps do not prove final availability or executable quote updates.

The retained price diagnostic recipe in `conditional-diagnostic-run-v2/stage/prepared/recipe.json` predicts fractional **unadjusted close change excluding dividend cash**, using lagged close return and trailing 5/20-return volatility. It excludes financial/text/options features. Three separate quarterly folds train Q1→Q2, Q2→Q3, Q3→Q4 of 2024; each interval endpoint is UTC midnight and the final validation end is 2025-01-01. Freeze created 2026-10-04T03:59:57.689098+00:00; 1,008 opportunities and 920 prepared rows, with 4 missing prior contexts, 4 missing/protected labels and 80 warmup exclusions. The retained next-stage report records six fits, 752 predictions /188 dates/four stocks and ridge MSE 4.26% worse than zero. That is a conditional forecast diagnostic, not P&L, win rate or Sharpe. Matrix rows, predictions and decision/session denominators must stay separate.

## Protocol and economic chain

`configs/wording_equity_pilot-v1.json` is frozen at 2026-10-04T07:48:23.407632+00:00 (declared SHA256 `4828922c88a423c41326578b715b1feae59bb451d86eced97dc363875a1095d9`). It selects one Item 2.02 linked earnings release exhibit per accession; nonoverlapping character-weighted FinBERT positive-minus-negative aggregate; exclude failed, truncated, duplicate, overlapping or incomplete coverage; threshold zero and zero signal no-trade. Frozen model revision is the cache pin above. Historical model vintage and supported exact-version public bound are required, with a named 60-second processing assumption.

Decision/entry is first qualifying session open+60 seconds, exit actual close−60 seconds, flat by close. Hypothetical USD1m, longs and shorts, at most 100% gross equal-dollar integer-share targets, zero idle-cash yield, no outside yield, restricted short proceeds not reusable deployment cash. Always-long and zero-yield-cash baselines share opportunities. Raw quote updates ≤60 seconds old, evidenced fees/spread/slippage/borrow/collateral, dated identities and corporate-action checks remain required. Missing exit/fill evidence invalidates headline metrics rather than selecting survivors. Regular account marks are required each session, including flat/no-trade days. The protocol's minimum Sharpe periods of 30 is a software rule, not a human usefulness threshold.

Human recipe/long-short/equal-gross/zero-passive decisions were independently verified by the parent audit; no repeated questions were asked. Protocol stores message IDs. The existing final capsule states no costed result or economic Sharpe. No accepted USD1m marked net return ledger, orders or qualified fills were inspected by this audit. Their metrics and no-fill/unknown/censored outcomes remain unknown pending the active owner replay.

## Retained native final gate

`native-v7-acceptance-v1/collected-final-v1/run.json` records completion 2026-10-04T07:08:15.952644+00:00: 690 tests, zero skips, exit zero, 196 frozen files. `collection-verification-final-v1.json` records 07:19:19.208151 UTC, 237,346 collected bytes, eight thin receipts, and 196 source-file checks. `acceptance-capsule-final-v1.json` freezes at 07:25:48.933189 UTC. These are inspected runtime receipt contents; this audit could not freshly compare file bytes before C filled again.

Declared final hashes: collection `2c63d5f3a35a66e5b692855b8bcd123db94c09c25f575f5acd44fe7ed93bd553`; run `808da15b3d7c90a8a9f21255025647bd3cac4d54545c36d67e74947f6ff2942f`; source manifest `3850d35b2ed9eaafb57869a6232791cc80cbb125851da78d2fb259d261213ead`; regression log `15f8458de46d5ca8a630b3b8ed36a1af73b2fa9024322d955957e05de715cf8a`; mapping `b62e33d88b0d8d9fe7cb2d654ac9093563b5a23e34e63e916cf78ef1189abb76`.

The consumer checked 110 packet outputs /109 input bindings /eight proof roles. Three AMT Assets groups, four raw XML nodes and one state candidate from 10-Q accession 0001053507-23-000161, filed 2023-10-26, describe balances at 2022-09-30, 2022-12-31 and 2023-09-30. Zero canonical observations, zero eligible 2024 cells and zero human gold remain. Public/first-public clocks are unknown; SEC acceptance was not promoted. The separate `benchmark_native_as_filed` route and financial features remain disabled. The larger 45 originals/424 groups/500 XML nodes/844 states are producer proof denominators, not this fixture. Financial-only verification remains P1 for the first wording arm.

## Gaps and next acceptance evidence

DD01/DD02: calendar/count audit is partial verified; no observed date-set discrepancy. Text taxonomy is verified at document/accession/CIK grain; actual qualifying independent Item2.02 event and economic episode/NAV denominators await owner event aggregation. Post owns accepted cohort; Benchmark owns event producer. Acceptance: hash-pinned event manifest, deduplication/exclusions and matched dated calendar/security set.

DD03/DD09: conditional Post day-end clocks and historical model qualification remain open P0 for wording. Acceptance: exact source-version public-by evidence, preserved unknown earliest/receipt clocks and demonstrated frozen model availability/training cutoff, or explicit conditional retrospective classification.

DD04/DD05: new protocol's 2024 window has no inspected existing 2023 wording accessions; price diagnostic is raw-close development with different horizon and no text. Acceptance: dated admissible event-price/identity/action intersection, explicit missing/unknown/censored rows and matched target/fold definition. No finance-only coverage expansion is promoted to P0.

DD21: verified existing-candidate period mismatch. The frozen protocol begins 2024-01-01 and excludes endpoints from 2025-01-01. Every primary in the inspected exact wording input manifest has a 2023 acceptance instant and 2023 accession. This proves the inspected existing accession-event candidate period has no 2024 event, without claiming all owner text or quote data is globally empty. A public-bound qualification or model-vintage proof alone cannot fix this date-window mismatch. Post owns the explicit window decision; Benchmark owns the event handoff. Acceptance requires the same frozen candidate's actual dated eligible event set within the registered protocol, or an explicit owner-approved study-window revision preserving development exposure and protected-test boundaries.

DD08/DD10/DD11: frozen policy is inspected; current accepted order→fill/no-fill→regular USD1m net account ledger and baseline are uninspected/pending active Post. Acceptance: exact protocol/input manifest, preserved exclusions/no-fill outcomes, realistic cost/borrow/collateral evidence and regular net marks. Unsupported metrics stay null.

DD17: final native descriptive gate metadata is inspected and supersedes stale 659/187 gate, but fresh local hash and current source comparisons are incomplete because shell startup again failed. Acceptance: small SHA256 comparisons of final eight receipt files and corresponding frozen source bytes without suite rerun. No economic promotion follows this gate.
