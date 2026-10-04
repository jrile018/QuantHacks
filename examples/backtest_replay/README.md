# Offline selected-leg engineering replay

This directory is a **synthetic** four-leg, one-event example for the existing
8-K option engine. `DEMO` is invented. The prices, volumes, event identity, and
contracts are illustrative and are not observations of a tradeable market.
They give a deterministic check of the code path, not a backtest result or
evidence of an economic edge. No portfolio NAV or Sharpe ratio is implied.

`replay.json` pins the SHA256 of `events.csv`, `option_legs.csv`, and
`option_bars.csv`; the replay verifies these bytes before any evaluation. It
also freezes the current horizons, risk-free rate, stale-mark limit, calendar
digest and bounds, entry rule, baseline bucket, OTM level, and sizing inputs.
The output manifest records actual source-file SHA256 values, package versions,
settings, counts, and hashes of every exported table. A changed setting fails
closed. The `--compare` option checks both output manifests and table bytes,
then compares the scientific metadata while ignoring only the run timestamp.

Run from the repository root with its configured Python environment:

```powershell
.venv/Scripts/python.exe scripts/reproduce_backtest.py --output-dir data/processed/replay-one
.venv/Scripts/python.exe scripts/reproduce_backtest.py --output-dir data/processed/replay-two --compare data/processed/replay-one
```

Both output paths must be new and distinct from the snapshot. The command
reads only local snapshot bytes; it does not fetch market data or access keys.
To replay licensed real data, supply retained selected-leg CSVs with the same
contract, pin their hashes, and set `provenance.kind` to
`licensed_retained_selected_legs` with a truthful source description. The
results still require a separate market-data, event-timing, cost, and economic
qualification review. `results.csv` has gross unit P&L per dollar of synthetic
spot; `capacity.csv` reports sizing and costs separately.
