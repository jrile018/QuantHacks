# Native options data in Lattice — design

## Intended outcome

QuantHaxs' Massive 8-K option contracts, daily bars, event dates, strategy outcomes, and capacity estimates become first-class, versioned Lattice run artifacts. Lattice can then measure whether its **pre-event equity state** adds information to an options event study. The existing equity geometry remains an equity model; option contracts are not disguised as equities.

## Current boundary

The Python bridge in `tools/options_bridge.py` writes CSV beside a Lattice run. It is not invoked by `gm-run`, writes no Lattice Parquet tables, and does not make option data visible to Lattice's C++ stages. The available manifested QuantHaxs run has one event, 102 outcome rows, and 12 capacity rows. The local Massive cache has 28 option-bar pages (932 rows) and one contract-reference page; the saved run does not say which selected contract served which event leg. The current data contains daily last-trade close and volume, not synchronized bid/ask snapshots.

## Data contract

QuantHaxs must export two additional tables from its existing `PricedEvent` objects, joined to the study's event table by `(ticker, event_date, t_pre, t_0)`:

- `option_legs.csv`: `event_id`, `bucket`, `leg_code`, `contract_ticker`, `underlying_ticker`, `contract_type`, `strike`, `expiration_date`, `selection_date`, `spot_pre`, `shares_per_contract`. `event_id` is `CIK:<10-digit CIK>:<accession>:<ticker>` and comes from the matched event row; `selection_date` is `t_pre`. `spot_pre` is QuantHaxs' parity-derived estimate at that session, with the source assumption recorded; it is not an independently observed stock quote. A contract has its own identity (`contract_ticker`); the issuer CIK is not a contract identifier. Preserve the chain's `shares_per_contract` on selection and reject missing or nonstandard values instead of treating a missing value as 100.
- `option_bars.csv`: `contract_ticker`, `session`, `close`, `volume`. One row per contract and traded session. Absence means no observed trade, never a zero-price bar. Do not prefill missing sessions.

Existing `events.csv`, `results.csv`, `capacity.csv`, and `manifest.json` remain inputs. `results.csv` rows map to an event by `(ticker, event_date, t_0)` and `capacity.csv` rows by `(ticker, event_date)` plus a valid entry date; reject ambiguous or missing matches. The producer manifest records row counts and SHA-256 hashes for all exported tables. Raw licensed Massive responses remain outside Git.

## Lattice run shape

When `[options].study_dir` is configured, `gm-options-ingest` reads the six QuantHaxs files, validates them, and writes `runs/<run_id>/gm-options-ingest/{events,contracts,bars,outcomes,capacity}.parquet` plus a native Lattice manifest. It is optional; a run without that key has exactly the current equity stages.

`gm-options-study` reads those Parquet tables and `gm-boundaries/scores.parquet`. It writes `event_features.parquet` from information available by each event's `t_pre`, and separately writes `event_outcomes.parquet` and a coverage report. Missing numeric features use explicit presence flags alongside a NaN placeholder, matching Lattice's current table types. It joins View B equity scores on **exact `(ticker, t_pre)`**; a missing score stays missing. `results.csv` is used only for outcome evaluation, never for feature construction. The stage must report unmatched events by reason: absent ticker, absent date, or missing estimator.

## Research limits

The first native study uses selected option legs, their daily close/volume, DTE, moneyness, implied move, volume, and mark age. It does not calculate an IV surface, Greeks, executable spread costs, or a trade recommendation from these data. Those require historical synchronized chain quotes and a separate validation plan. The one-event smoke run proves plumbing only; any incremental-value claim requires a larger run and a sealed calendar holdout against simple option and equity controls.
