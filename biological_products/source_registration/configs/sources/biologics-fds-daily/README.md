# biologics-fds-daily

Owner: abhay (GitHub: abhay-dronavalli). Stage: discovery. Engine: native (intended; the files are CSV, not documents, so no transcript extraction is claimed).

## What it is
A point-in-time daily company snapshot ("FDS") for 139 US biologics companies (SIC 2836). One row per company per US market day, 2024-01-02 to 2026-10-02, about 89,150 rows, about 150 numeric feature columns. Labels (`fds_labels.csv`) and per-cell missing reasons (`fds_missing.csv`) are separate files. Keys: `cik` (int) and `date` (int YYYYMMDD).

## Decision clock
Market close, 16:00 America/New_York. Anything with only a date is usable from the next day. No per-row UTC availability timestamps are recorded; none are claimed.

## Files (see manifest.jsonl)
fds_features.csv, fds_missing.csv, fds_labels.csv, fds_dictionary.csv, fds_lookup_cik_ticker.csv, fds_lookup_codes.csv, README_FDS.md, fds_options.csv (option spreads at past 8-K events), fds_shelf.csv, fds_short.csv (FINRA short volume and short interest), fds_realprice.csv.

## Publisher, provenance and URLs
Built by the owner, not published by a third party. Builder: `biological_products/scripts/16_build_fds.py`, version 2 (2026-10-04). Output folder: `biological_products/data/fds/`. Upstream inputs:
- SEC companyfacts and EDGAR submissions index (filing dates)
- Massive (Polygon) daily bars adjusted for splits, plus Massive split history
- Massive 8-K events with categories
- Massive news with an ML sentiment score
- Form 4 insider transactions
- AACT monthly snapshots of ClinicalTrials.gov (Nov 2023 to Sep 2026)
- FINRA short sale files
- PDUFA dates parsed from 8-K text

The `source_url` values in manifest.jsonl are placeholders (`todo-fill.invalid`). The dataset has no public URL yet; they were not checked. Replace them when a shared location exists (see TODO.md).

## Acquisition
There is no download command. The owner copies the files from `biological_products/data/fds/` into ignored `data/raw/team_sources/biologics-fds-daily/`. Regenerate with `python biological_products/scripts/16_build_fds.py` in the owner's workspace (needs the upstream credentials below). Full-data storage is undecided; no data is committed.

Credential environment variables for upstream rebuilds: TODO_FILL (owner to name the Massive/Polygon key variable; SEC and FINRA files are public).

## Usage restrictions
Not yet reviewed. Massive/Polygon data is subject to the owner's vendor licence, so do not redistribute the raw files. Owner to confirm.

## Versions
Version 1 (before 2026-10-04) had five split-adjusted columns with look-ahead. Version 2 removed them. The manifest document IDs end in `-v2`. Do not mix v1 files with v2.

## Unknown fields and limitations
- Survivorship: the company list is today's SIC 2836 list, so delisted or acquired names are absent.
- News sentiment: model provenance and version are unknown.
- Trials: AACT snapshots are monthly, so registry edits within a month are seen late.
- Borrow availability is not covered.
- source_sha256, byte sizes and row counts per file: not recorded (files not available to the registrar).
- First-public-availability UTC times per source record: unknown.
- Identity: keyed by CIK; ticker mapping is in fds_lookup_cik_ticker.csv and is not verified here.
- Feature validity, market-data coverage and backtest eligibility are not established by this registration.

## Readiness
Discovery only. No local pilot run through `scripts/run_document_batch.py` (CSV is not a supported batch input), no accepted-consumer receipt. The adapter `src/biologics_fds_daily_adapter.py` only checks CSV headers and the cik/date key format.
