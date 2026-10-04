# REIT market acquisition and frozen research contract

The market builder provides a quote-first Databento HTTP client and command line interface, a durable total-spend reservation flow, verified downloads, and explicit research readiness gates. It does not provide a validated strategy or an out-of-sample result. The frozen design is in `configs/reit_cross_asset_experiments.json`.

## Acquisition flow

Read the actual dataset list, schema list, range and daily condition metadata before constructing requests. Discover equity, option and futures availability independently. A schema name alone does not establish stock consolidated NBBO; preserve venue scope and audit quotes before claiming executable cross-asset inequalities.

The implementation follows the official [Databento Python metadata API source](https://github.com/databento/databento-python/blob/main/databento/historical/api/metadata.py) and [batch API source](https://github.com/databento/databento-python/blob/main/databento/historical/api/batch.py). The gateway is `https://hist.databento.com/v0/`, with Basic authentication using the key as username and an empty password. Metadata discovery and job inspection use GET. `metadata.get_cost` is a free form POST in the official implementation, despite its GET docstring. `batch.submit_job` is the paid form POST. The key is loaded from the environment or the single `DATABENTO_API_KEY` field in `.env`; `.env` contents are never executed.

Examples from the project directory:

```powershell
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py metadata --metadata-operation list_datasets --output data/processed/reit-market/datasets.json
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py metadata --metadata-operation list_schemas --dataset DATASET
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py metadata --metadata-operation get_dataset_range --dataset DATASET
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py metadata --metadata-operation get_dataset_condition --dataset DATASET --start-date 2024-01-01 --end-date 2026-10-02
```

Use an unfiltered catalog for product discovery and explicit per-schema ranges for coverage. The October 3 live check returned an empty broad date-filtered catalog despite 29 unfiltered products. Dataset listing uses exclusive end dates; daily conditions use inclusive end dates. Requests require explicit start and exclusive end, January 2024 onward, selected symbols, schema, and dataset. All-symbol purchases are disabled. A request JSON has this shape, with `DATASET` and `SCHEMA` replaced by actual discovered values:

```json
{"dataset":"DATASET","symbols":["O","PLD"],"schema":"SCHEMA","start":"2024-01-01","end":"2026-01-01"}
```

The client freezes defaults including CSV, zstd, instrument-ID output, mapped symbols and monthly file splits. List symbols become the exact comma-separated provider selector. Both the full batch payload and the data-selection filters are frozen in a fingerprint; no format or selector changes are silently accepted after quoting. Provider conditions are retained for review, without inventing an audit from their presence.

The live coverage receipt at `data/processed/reit_build/20261003/market/coverage_metadata.json` shows why schema ranges matter: OPRA `cbbo-1s` begins February 20, 2025, while `cbbo-1m` extends to 2013 and `cmbp-1` to March 2023. A January 2024 request for `cbbo-1s` is rejected even though the dataset's overall history is longer. Missing bounds in a returned schema map also fail closed. Minute snapshots can support screens and repricing research; strict simultaneous executable claims still require their own finer timing and quote-quality evidence.

The official [EQUS.MINI feed specification](https://databento.com/docs/venues-and-datasets/equs-mini) describes BBO aggregation across component venues with anonymized venue origin and sizes including odd lots. Publisher ID is fixed, and sequence and `ts_in_delta` are zero. Databento's [equities product explanation](https://databento.com/equities) calls it synthetic mini-NBBO and describes internal tests finding it close to NBBO. Treat this as independently acquired component-venue aggregation for screens/repricing. Full national executable NBBO remains unproven, so the readiness gate rejects a strict claim even if a manifest relabels EQUS.MINI as consolidated executable quotes.

```powershell
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py quote --payload data/processed/reit-market/request.json --output data/processed/reit-market/quote.json
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py submit --payload data/processed/reit-market/request.json --quote-receipt data/processed/reit-market/quote.json --request-id reit-equity-v1
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py budget
```

Quote is the default mode. Submit checks the exact payload identity and a 15-minute quote lifetime, then obtains a fresh exact quote and refuses a changed price. The shared SQLite budget ledger caps total authorization at **$249.99**, including previous purchases. It uses an external-spend high-water mark and at least the known **$23.14** prior spend. It rereads `data/raw/databento/acquisition_ledger.json` immediately before reservation and again before entering submitting; a custom path can be supplied with `--legacy-ledger`. Actual invoices replace reservations when settled. Other account activity must also be recorded in the shared legacy ledger; the application cannot discover unrelated spend by assumption.

Each quote reserves cost plus a conservative 5% buffer and rounding allowance. A transaction durably records reservation and submitting state before the paid network request. No provider idempotency is assumed. Reusing a local request ID after submission is rejected, including when the provider acknowledgement is lost.

If timeout, malformed response, server error or interrupted submission makes the outcome uncertain, money stays held as `unknown_held` or `submitting`. Do not repeat the paid POST. Inspect jobs, then reconcile a specific provider job against all exact selectors and its receive timestamp:

```powershell
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py jobs --since 2026-10-03
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py job --job-id JOB_ID
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py reconcile --request-id reit-equity-v1 --job-id JOB_ID
```

Reconciliation refuses a different already-bound job ID before provider access, missing or differing provider selectors and representation fields, and jobs already bound elsewhere. It compares encoding, compression, formatting/mapping flags, splitting and delivery in addition to data selectors. Only optional `limit`/`split_size` with the official SDK's documented None defaults accept equivalent missing/null values; other missing fields are not invented. Identical payloads under a new request ID cannot retry an unresolved purchase. If the provider does not expose enough fields to prove identity, keep the reservation and investigate through provider support; an empty job search is insufficient proof of non-submission. Only reservations that never reached submitting can be released. Completed reconciled jobs settle their reported actual cost. An invoice above the reservation is recorded truthfully and prevents further buying if the ceiling is exceeded.

The sanitized live provider shape at `data/processed/reit_build/20261003/market/provider_job_shape.json` exposes all required representation fields, proper JSON booleans, comma-separated symbols, UTC ISO timestamps and null optional `limit`/`split_size`. It is compatible with the client's exact comparison; no inferred missing formatting defaults were necessary.

## Verified files and receipts

```powershell
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py files --job-id JOB_ID
.venv/Scripts/python.exe scripts/acquire_reit_market_data.py download --job-id JOB_ID
```

Downloads accept only HTTPS URLs on the explicitly authorized Databento API hosts, reject credentials embedded in URLs, and disable redirects. Every listed entry is validated before selecting any file. Filenames reject traversal, Windows devices, alternate streams, trailing aliases, collisions and the reserved generated `download_manifest.json` name. Sizes must be nonnegative integers and SHA-256 hashes must be well formed. The disk guard requires pending bytes plus 1 GB spare. Streaming stops at the declared size; truncated or hash-mismatched downloads cannot become verified files. Existing files are reused only after size and hash checks. Final files replace unique temporary files atomically.

Sanitized metadata, quote, reservation, submission, job, file and download receipts live under `data/processed/reit-market/receipts/`. Credentials returned by the provider are removed recursively, and known key values are redacted from strings. The final per-job `download_manifest.json` contains verified sizes, hashes, request selectors, selection scope, and counts. A filtered download explicitly records whether the complete job was downloaded; total provider record count is not a measured count for a selected subset.

## Readiness contract

`market_readiness()` consumes an evidence manifest with independent `equity`, `options`, and optional `futures` entries in `inputs`, plus explicit `evidence_gates`. Run `readiness --manifest PATH` to inspect blockers. Inputs require nonzero measured record counts, verified files, measured coverage and documented quality audits. Equity must be independently acquired. A downloaded receipt alone supplies acquisition integrity, not synchronized quote quality, contract correctness or a validated result.

For a strict lane, equity and option entries must document `quote_scope: consolidated_executable`, bid/ask sizes, timestamps and contract definitions. Evidence gates cover synchronized quotes, dividends, American exercise, borrow, financing, margin, assignment, leg risk and exact contract identity, plus a trial register, cost/capital stress and holdout audit. Predictive label readiness is assessed separately. Futures readiness applies to index/rate hedges and cannot establish company-contract equivalence.

The evidence manifest declares the result of audits; its booleans are not an audit engine. Keep the underlying quote-quality, coverage, feature-time, execution and contamination reports with their receipt references. Missing inputs and missing evidence fail closed.

## Frozen experiments

The strict lane considers same underlying and expiry conversions/reversals, vertical bounds and cashflow matched boxes. American stock options require bounds across permitted exercise paths, dividends, deliverables, borrow and funding. An apparent European parity residual alone proves no American arbitrage. Immediate execution and contractual settlement are its horizons.

The repricing lane tests financing events at 30 minutes, next session and five sessions; counterparty propagation at one, five and 21 sessions; and maturity pressure at five, 21 and 63 sessions. These horizons are justified by dissemination, propagation and financing response, then frozen before evaluation. Equity and option effects remain probabilistic; index/rate futures hedge exposure with measured basis risk.

Development covers 2024–2025 with strictly past-only folds. Features, universe decisions, transformations and hedge ratios may use only information public before the fit cutoff and labels that have matured. Purge overlapping label intervals, keep related event/counterparty clusters together, and embargo the largest frozen horizon. A fold with too few eligible observations is reported as unavailable rather than producing an invented estimate.

2026 is only a candidate holdout until prior access and decision influence are audited. Consumed periods become development. A new prospective holdout begins after a documented final freeze and access audit, and results wait until labels mature. Every trial is registered before execution with contract/code/data identities, feature and cost recipes, fold and contamination status. Failed and abandoned trials remain in the register.

Fills buy the ask and sell the bid within executable size. Net results include fees, spread, slippage, funding, borrow, margin, assignment, dividends, hedge rolls and leg risk. Report a stress frontier across net return, drawdown, capital and capacity; do not choose a drawdown target retrospectively because it fits the preferred history. Long backtests, sweeps and large data processing run on `home-pc` in detached tmux jobs; this client itself performs only acquisition and gate evaluation.

## Verification

The local safety tests use simulated provider responses and the real SQLite ledger; they buy no data. Run `.venv/Scripts/python.exe -m unittest tests.test_reit_market_data -v`. They exercise exact quote identity, changed costs, competing reservations, external-spend refresh, ambiguous submissions without retries, unsafe URLs and filenames, truncated downloads, receipt redaction and insufficient evidence. The parent integration task is responsible for the complete repository suite and live metadata receipts.
