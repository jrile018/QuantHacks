# Native Options Integration Implementation Plan

## Execution status (2026-10-03)

Task 1 is implemented in the parent QuantHaxs repository. Lattice now has a
working Python/pyarrow implementation of the Task 2–4 data contract under
`tools/options_native.py`, which writes native Parquet and is conditionally
invoked by `gm-run`. This is an implementation change from the C++ plan below:
the local checkout lacks its pinned vcpkg toolchain, the available global
vcpkg installation lacks tomlplusplus, and the `home-pc` SSH alias did not
resolve. The C++ task checkboxes below remain open. The Python stages have
synthetic offline tests and a one-event real-data smoke run; the C++ dispatch
has not been compiled or exercised, and score coverage and multi-event
evaluation remain pending.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest QuantHaxs option contracts, bars, events, outcomes, and capacity as native Lattice Parquet artifacts and study them against causal equity scores.

**Architecture:** QuantHaxs exports explicit selected-leg and bar tables. An optional C++ `gm-options-ingest` stage validates all QuantHaxs tables and writes Lattice Parquet plus a native manifest. A separate `gm-options-study` stage computes pre-event features, joins equity View B scores at `t_pre`, then evaluates outcomes without feeding labels into features.

**Tech Stack:** QuantHaxs Python/pandas and unittest; Lattice C++20, gm-core, gm-data, gm-io, Arrow Parquet, Catch2, CMake.

**Spec:** [Native options design](../specs/2026-10-03-native-options-design.md)

## Global constraints

- Paths in Task 1 are relative to the parent QuantHaxs repository. Paths in Tasks 2–5 are relative to the nested `stat-arb` Lattice repository.
- Keep raw Massive responses and generated Parquet/CSV under ignored data or `runs/` paths.
- Treat CIK as issuer identity and the OCC option ticker as contract identity.
- Do not fill absent contract trading sessions or infer bid/ask, IV, or Greeks from last-trade closes.
- Every feature for an event must use data dated no later than its `t_pre`; outcome labels remain in a separate table.
- Preserve Lattice's current equity pipeline when `[options].study_dir` is absent.
- Run a full C++ build/test on `home-pc` through detached `tmux` once its SSH alias resolves; the alias did not resolve on 2026-10-03. Do not substitute a LAN address.

## Review focus

1. A contract reused across event buckets must not duplicate a bar's `(contract_ticker, session)` key.
2. An option bar after `t_pre` must never enter an event feature.
3. An unknown or adjusted contract must fail or be counted explicitly, not silently map to a standard 100-share contract.
4. A missing Lattice score must remain missing; no next-session or nearest-date fill.
5. The one-event fixture may prove plumbing but cannot be used to claim predictive value.

## Task 1 — Export the option records QuantHaxs currently discards

**Files:** `src/data.py`, `src/implementation.py`, `src/main.py`, new `tests/test_option_export.py`, `README.md` in QuantHaxs.

**Interface:** `option_leg_rows(events, priced) -> pandas.DataFrame` and `option_bar_rows(priced) -> pandas.DataFrame`; `write_outputs` adds `option_legs.csv` and `option_bars.csv` and includes their hashes and counts in `manifest.json`.

- [ ] Write an offline `PricedEvent` fixture with an ATM call, ATM put, and one OTM leg; assert exact event-to-contract keys from the matching `events` row, expiry, strike, parity-derived `spot_pre`, preserved contract multiplier, selection date, and one bar per `(contract_ticker, session)` even when a leg is reused.
- [ ] Run `python -m unittest tests.test_option_export -v`; verify the test fails because the exports do not exist.
- [ ] Implement the two exporters from in-memory `PricedEvent.legs`; keep only selected contracts and their observed daily bars. Update chain selection to carry `shares_per_contract` through to each leg, rejecting absent or nonstandard values instead of defaulting absent values to 100. Do not reconstruct contract mapping from hashed cache filenames.
- [ ] Extend `write_outputs` and the manifest. Verify `python -m unittest discover -s tests -v` passes and rerun the one-event smoke study to produce the two new CSVs.

## Task 2 — Validate a typed options study in Lattice

**Files:** `libs/gm-data/include/gm-data/options.hpp`, `libs/gm-data/src/options.cpp`, `libs/gm-data/tests/options_test.cpp`, `libs/gm-data/CMakeLists.txt`, `libs/gm-data/tests/CMakeLists.txt`.

**Interface:** `gm::data::load_options_study(study_dir) -> Result<OptionStudy>`, using `gm::io::read_csv_file`; `OptionStudy` holds typed events, selected contracts, bars, outcomes, capacity, and validation counters.

- [ ] Add failing Catch2 cases for duplicate contract/day bars, truncated CSV, bad date ordering, nonstandard multiplier, missing referenced event/contract, and a valid reused contract with de-duplicated bars.
- [ ] Implement parsing and validation. Require `(contract_ticker, session)` uniqueness, positive price, nonnegative volume, `selection_date == t_pre`, and expiration after selection. Derive each outcome's event ID from `(ticker, event_date, t_0)` and each capacity row's event ID from `(ticker, event_date)` plus its entry date; reject ambiguous or missing event matches.
- [ ] Run the targeted `gm-data-tests`; inspect every failure and make the suite green. Add an exact row-count test against the exported one-event fixture.

## Task 3 — Write native Parquet and a Lattice manifest

**Files:** `apps/gm-options-ingest/main.cpp`, `apps/gm-options-ingest/CMakeLists.txt`, root `CMakeLists.txt`, `config/params.toml`, `tests/golden/options_ingest_test.cpp`, `tests/golden/CMakeLists.txt`.

**Interface:** `[options].study_dir` selects a QuantHaxs study directory. Direct invocation of `gm-options-ingest --config ... --output-dir ... --manifest-out ...` writes `events.parquet`, `contracts.parquet`, `bars.parquet`, `outcomes.parquet`, `capacity.parquet`, and `manifest.json` under `gm-options-ingest/`.

- [ ] Add a failing golden fixture that invokes the real binary on a small synthetic study in the QuantHaxs export schema and reads every Parquet schema back through `gm::io::read_parquet`; keep licensed study rows out of the repository.
- [ ] Implement the stage with `gm::io::Table`, `write_parquet`, and `gm::Manifest`, recording source file hashes, row counts, and rejection counts. Fail before writing if a required source is malformed.
- [ ] Verify targeted C++ tests and the frozen import. Compare counts with the QuantHaxs producer manifest. Keep generated licensed rows out of Git.

## Task 4 — Join causal equity state to option features and outcomes

**Files:** `libs/gm-data/include/gm-data/options_study.hpp`, `libs/gm-data/src/options_study.cpp`, `libs/gm-data/tests/options_study_test.cpp`, `apps/gm-options-study/main.cpp`, `apps/gm-options-study/CMakeLists.txt`, root `CMakeLists.txt`.

**Interface:** `gm-options-study` reads `gm-options-ingest/*.parquet` and `gm-boundaries/scores.parquet`; writes `event_features.parquet`, `event_outcomes.parquet`, and `coverage.json` under `gm-options-study/`.

- [ ] Add failing tests where an after-event bar and next-session score have extreme values; prove neither can affect `event_features.parquet`.
- [ ] Compute label-free features from selected legs and bars at `t_pre`: DTE, strike/`spot_pre` moneyness, ATM straddle implied move, observed volume, and age of the marks. Missing numeric inputs get NaN plus a presence flag and coverage count; mark age uses trading sessions, not calendar days.
- [ ] Join each View B estimator on exact ticker and `t_pre`, retaining estimator identity and missingness. Put realized return and strategy P&L only in `event_outcomes.parquet`.
- [ ] Verify an independent frozen fixture and inspect a real multi-event output before statistical interpretation.

## Task 5 — Make options optional in `gm-run`, then evaluate

**Files:** `apps/gm-run/main.cpp`, `tests/golden/m0_pipeline_test.cpp`, `tests/fixtures/golden_run.toml.in`, `README.md`, `ADR.md`.

- [ ] Add a failing orchestration test: no `[options].study_dir` must produce the original nine-stage run; setting it must invoke `gm-options-ingest` and `gm-options-study` after `gm-report` and include both manifests.
- [ ] Implement conditional stage dispatch and document the run command, artifacts, data lineage, and limits in README/ADR.
- [ ] Run the focused golden test, then the full C++ suite on `home-pc` in detached `tmux` when the alias is available. Retrieve logs and results; do not report a green suite from README claims.
- [ ] Run a non-smoke QuantHaxs study and a Lattice equity run over the matching dates. Report event count, selected-contract coverage, mark staleness, exact-score join rate, and unmatched reasons before testing any signal.
- [ ] Only after sufficient coverage, compare score-conditioned option outcomes with a baseline using option features, recent equity return/volatility, sector, and event category on a sealed calendar holdout. Treat a null result as a valid finding.
