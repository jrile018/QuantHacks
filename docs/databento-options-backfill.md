# Databento options backfill for the CFO event study

The QuantHaxs 2024–2025 CFO event export selected 654 distinct option
contracts across 89 event/expiry groups. Databento OPRA.PILLAR `cbbo-1m`
provides historical minute consolidated bids and asks for those contracts.
The contract key is converted from Massive `O:GD240202C00260000` to OPRA/OCC
`GD    240202C00260000` when requesting the data, then restored in the daily
output so it joins to `option_legs.csv` by `contract_ticker` and `session`.

## Budget and requests

The user authorized total Databento purchases below $250. The local ledger is
`data/raw/databento/acquisition_ledger.json`. As of 2026-10-03:

| Request | Scope | Cost |
| --- | --- | ---: |
| `OPRA-20261003-TGXMYMA56Q` | Full GD option chain, 2023-12-27 through 2024-05-17 | $6.38346 actual |
| `OPRA-20261003-4APD3MDYPJ` | Exact 654 selected contracts, 2023-12-26 through 2026-04-17 | $4.7966 quote; processing |
| Direct GD pilot | 16 selected GD contracts over the first request's dates | $0.05792 quote |
| Five-row schema check | One GD contract on 2024-01-04 | under $0.0001 quote |
| Direct streaming benchmark | January 2024 for the selected contracts | $0.15592 quote |
| `OPRA-20261003-3QFKGVKXNA` | `ohlcv-1d` for the exact 654 selected contracts, 2023-12-26 through 2026-04-17 | $11.74521 actual; complete |

Actual plus quoted cost is approximately **$23.14**, leaving about
$226.86 under the cap if the pending batches land near their quotes. These
figures are the project's acquisition ledger, not the account credit balance.

The full GD chain has 42,838,678 minute records. All 102 batch files were
downloaded and SHA-256 verified under
`data/raw/databento/OPRA-20261003-TGXMYMA56Q/`. The 16-contract direct pilot
is under `data/raw/databento/gd-pilot-direct/`.

## Daily quote table

`scripts/build_databento_daily_quotes.py` keeps the latest valid quote between
9:30 a.m. and 4:00 p.m. New York time for each contract and date. It rejects
zero bids, crossed markets, missing sizes, and invalid prices. It does not
carry a quote forward from another session. Its output includes the quote
timestamp, bid, ask, midpoint, displayed bid/ask sizes, and relative spread.

`option_quotes_daily.csv` is **not** a replacement for `option_bars.csv`:
the latter is a daily last-trade close and volume from Massive. Databento's
`size` is quote depth or last-trade size, not daily option volume. The quote
table is meant for a spread-aware backtest. Buying at the ask and selling at
the bid is a conservative starting point; actual fills require separate
assumptions.

The GD pilot output is
`data/processed/cfo-2024-2025-databento/gd-pilot-direct/option_quotes_daily.csv`.
It has 886 contract-day marks. On the event's pre-date, 15 of 16 selected
contracts had a valid quote. The missing one was a far out-of-the-money
one-month call. Both ATM call/put pairs were present, but only one of the two
eight-leg groups was complete. The median relative spread for the 15 quoted
contracts was 42.1%, so an apparent edge based on trade closes alone would
need careful execution-cost testing.

A January 2024 direct-stream benchmark took **1,316 seconds (about 22
minutes)** for one month. It produced 12.7 MB compressed and 2,607 daily
marks. The full study spans over two years; streaming it again would incur a
second charge and has no demonstrated reliable time advantage over the batch
already processing. The benchmark's quote table is under
`data/processed/cfo-2024-2025-databento/streamed-exact-contracts/`.

## Reproduce and connect to Lattice

Use the project's `.venv` Python on Windows:

```powershell
.venv\Scripts\python.exe scripts\download_databento_options.py OPRA-20261003-4APD3MDYPJ
.venv\Scripts\python.exe scripts\build_databento_daily_quotes.py OPRA-20261003-4APD3MDYPJ
.venv\Scripts\python.exe stat-arb\tools\options_native.py ingest --study-dir data\processed\cfo-2024-2025-massive --quotes data\processed\cfo-2024-2025-databento\OPRA-20261003-4APD3MDYPJ\option_quotes_daily.csv --output-dir data\processed\lattice-databento-full\gm-options-ingest --run-id databento-full
.venv\Scripts\python.exe stat-arb\tools\options_native.py study --ingest-dir data\processed\lattice-databento-full\gm-options-ingest --output-dir data\processed\lattice-databento-full\gm-options-study --run-id databento-full
```

Run the first command after the exact-contract job reaches `done`. The GD
pilot has already passed the same Lattice ingest/study path under
`data/processed/lattice-databento-gd-pilot/`; its study reports 2 of 89
event/expiry groups with ATM quote pairs because the pilot intentionally
contains only GD.

The detached `scripts/finalize_databento_options.py` process is watching the
already purchased exact-contract job and will perform those four commands
automatically. Its current stage is saved in
`data/raw/databento/finalize_status.json`; its logs are in the same folder.
The manual commands above are for recovery if that process fails. The
finalizer submits no new data request.

## Where the selected contracts and results came from

`src/data.py` requests CFO appointment disclosures and an as-of options
reference chain from Massive. `src/implementation.py` selects an expiration
near each configured 1-month, 2-month, or 3-to-6-month target, estimates stock
price from a call/put pair, then chooses near-the-money and out-of-the-money
calls and puts from the chain. It keeps standard 100-share contracts and
exports the chosen legs in `option_legs.csv`. The 712 leg assignments represent
89 event/expiry groups and reuse 654 distinct contracts.

`results.csv` is calculated from Massive daily last-trade option closes for
those legs at hypothetical entry and exit dates. It contains theoretical
returns for the configured strategies and horizons, not broker fills. Its
synthetic stock marks come from put-call parity, and its P&L columns do not
subtract observed bid/ask spreads; the separate capacity table applies a
configurable sizing haircut. The Databento CBBO data is intended to test this
execution-cost gap.

## Daily trade-bar request

`OPRA-20261003-3QFKGVKXNA` acquired Databento `ohlcv-1d` for the same 654
contracts, with raw OCC symbols, symbol mapping, CSV/zstd output, and monthly
files. Databento billed $11.74521. The completed job contains 29 CSV files and
375,337 venue-level daily bars from 2023-12-26 through 2026-04-17. All file
hashes matched Databento's manifest; a full scan matched its record count and
found the expected ten-column header. Data was observed for 651 of the 654
requested contracts. Of 31,510 contract/date pairs in the Massive option-bar
export, 31,506 have at least one Databento daily bar. The three contracts and
four contract/date pairs without rows are listed in the validation report;
their absence has not been attributed to a specific cause.

The raw files, request receipt, and validation report are in
`data/raw/databento/OPRA-20261003-3QFKGVKXNA/`. The completed watcher status
is in `data/raw/databento/ohlcv1d_finalize_status.json`; it made no further
purchase.

Databento daily OHLCV contains trade-derived `close` and `volume`, but it is
not an exact replacement for Massive option bars: Databento uses UTC-day bar
boundaries and publishes `publisher_id` venue identity, while Massive uses
Eastern-time qualifying-trade aggregation. Some contract/date pairs have
multiple venue rows, so one Databento row must not be treated as the
whole-market daily close. Compare venue aggregation and trade rules before
substituting one source for the other.

Sources: [Databento historical batch API](https://databento.com/docs/api-reference-historical?historical=http),
[CBBO schema](https://databento.com/docs/schemas-and-data-formats/bbo),
[OHLCV schema](https://databento.com/docs/schemas-and-data-formats/ohlcv),
[OPRA dataset](https://databento.com/docs/venues-and-datasets/opra-pillar).
