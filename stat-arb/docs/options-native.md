# QuantHaxs option contracts in Lattice

The optional `gm-options-ingest` and `gm-options-study` stages read an export made by
QuantHaxs after it saves selected option contracts and their observed bars.
They write Arrow Parquet tables that Lattice's `gm-io` reader can consume. The
existing nine equity stages run unchanged when `[options].study_dir` is absent.

## Run

Install `tools/requirements-options.txt` into the Python environment used by
Lattice. Add to a copy of the run config:

```toml
[options]
study_dir = "../data/processed/smoke-options-native"
python_exe = "../.venv/Scripts/python.exe" # Windows example, relative to the Lattice root
```

`gm-run` locates `tools/options_native.py` from the config or build path before
running equity stages. Set `options.script_path` to an absolute path if it
cannot be found. A relative `study_dir` is resolved from the Lattice root.
Then run `gm-run` as usual. It launches the Python option stages after
`gm-report`. The study stage reads that run's `gm-boundaries/scores.parquet`.
For an option-only import without an equity run:

```text
python -m tools.options_native ingest --study-dir STUDY --output-dir runs/ID/gm-options-ingest --run-id ID
python -m tools.options_native study --ingest-dir runs/ID/gm-options-ingest --output-dir runs/ID/gm-options-study --run-id ID
```

To add Databento OPRA quotes, pass the daily quote CSV made by
`scripts/build_databento_daily_quotes.py` to ingest:

```text
python -m tools.options_native ingest --study-dir STUDY --quotes OPTION_QUOTES_DAILY.csv --output-dir runs/ID/gm-options-ingest --run-id ID
```

This writes `quotes.parquet` in addition to the existing tables. The study
uses only quotes from the exact pre-event session for the ATM call and put.
It adds `atm_straddle_bid`, `atm_straddle_ask`, `atm_straddle_mid`,
`atm_straddle_relative_spread`, and a presence flag to the feature table.
The full daily quote table remains available for per-leg execution analysis.

Pass `--scores runs/ID/gm-boundaries/scores.parquet` to the second command
when a matching equity run exists. A score joins only on the exact ticker,
pre-event session, View B, and estimator. Missing scores remain missing.

## Artifacts and limits

`gm-options-ingest` writes `events`, `contracts`, `bars`, `outcomes`, and
`capacity` Parquet tables, plus optional `quotes`. It checks source SHA-256 hashes and row counts, records
output hashes, and
rejects missing or adjusted contract multipliers. `gm-options-study` writes
`event_features.parquet`, `event_outcomes.parquet`, `coverage.json`, and a
Lattice-compatible stage manifest. Every feature uses bars dated no later
than `t_pre`; realized returns and strategy P&L are kept in the outcome file.

The original bars are daily last-trade bars. Databento CBBO-1m adds minute
consolidated bid/ask quotes; its quoted sizes are not daily traded volume.
The pre-event quote features describe possible execution costs but do not
establish an IV surface, Greeks, a trading signal, or realizable P&L. Check
same-day quote coverage, spread, and future-date holdout performance before
making a strategy claim.
