# OPRA OHLCV-1d Acquisition Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to carry out the checked steps.

**Goal:** Acquire and verify Databento daily option trade bars for the 654 contracts in the CFO study without exceeding the user's $250 Databento purchase limit.

**Architecture:** Derive the exact OCC symbols from the saved Massive option-leg export. Quote the same 2023-12-26 through 2026-04-17 coverage via Databento's free metadata endpoint, then fetch only that scope. Retain the raw file, its request parameters, cost, hash, and a small schema/coverage report.

**Tech Stack:** Python 3, requests, Databento historical HTTP API, CSV, SHA-256.

**Spec:** User request in this chat to get `ohlcv-1d`; existing selected contracts and budget ledger in `data/processed/cfo-2024-2025-massive/option_legs.csv` and `data/raw/databento/acquisition_ledger.json`.

## Global Constraints

- Total actual plus committed/quoted Databento purchases must remain below $250.
- Do not broaden the order to full parent option chains or a wider date range.
- Do not treat Databento daily bars as identical to Massive's Eastern-time, qualifying-trade bars.
- Preserve all existing data and the independent CBBO batch/finalizer.

## Review Focus

- Confirm all 654 contract symbols are translated correctly from Massive to OCC notation.
- Confirm the exclusive end date includes the last 2026-04-17 session.
- Verify any quote covers the exact same symbols, dates, and `ohlcv-1d` schema as the eventual request.
- Verify the downloaded file is complete before calling the acquisition complete.
- Keep actual billed cost distinct from a metadata estimate.

### Task 1: Trace and quote

- [x] Verify the saved study's event, contract-selection, and result-generation code.
- [x] Quote `OPRA.PILLAR` `ohlcv-1d` for the 654 exact OCC symbols from 2023-12-26 to exclusive 2026-04-18, chunking metadata calls because the full URL is too long.
- [x] Save the $11.74521 quoted cost and request scope; the existing ledger plus the quote is $23.13917, below $250.

### Task 2: Acquire

- [x] Request only the quoted `ohlcv-1d` scope with mapped symbols and compressed output: job `OPRA-20261003-3QFKGVKXNA`.
- [x] Download the resulting data to `data/raw/databento/` and retain Databento's request metadata.

### Task 3: Verify and report

- [x] Confirm file size, hash, schema header, nonzero records, observed contract and date coverage, and final billed cost.
- [x] Update the acquisition ledger with the final job state and cost.
- [x] Explain contract and result provenance in plain language and state any remaining difference from Massive daily bars.
