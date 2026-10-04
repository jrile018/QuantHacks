# Storage inventory — 2026-10-04

Inventory captured 2026-10-04T08:21:43.677342+00:00 under `C:\Users\johnp\OneDrive\Documents\ChatGPT\QuantHaxs`.

The JSON file records every scoped file path, byte size, modification time, classification, reason, and provenance evidence. Classification is a review aid; no files were removed during inventory. Markdown files are always retained. Unknown provenance remains on hold.

Scope total: 8,176 files, 4,554,778,472 bytes.

## Disposition totals

| Classification | Files | Bytes |
|---|---:|---:|
| `candidate_remove` | 6,949 | 3,991,229,636 |
| `hold_mixed_provider` | 67 | 16,294,481 |
| `hold_unknown` | 352 | 265,740,792 |
| `retain_code` | 560 | 6,288,864 |
| `retain_databento` | 179 | 256,822,631 |
| `retain_databento_derived` | 45 | 17,424,114 |
| `retain_markdown` | 24 | 977,954 |

## Storage groups

| Root | Files | Bytes | Classification breakdown |
|---|---:|---:|---|
| `.massive_cache` | 980 | 14,138,192 | candidate_remove: 980 files/14,138,192 bytes |
| `.pytest_cache` | 5 | 1,967 | candidate_remove: 4 files/1,665 bytes, retain_markdown: 1 files/302 bytes |
| `__pycache__` | 1 | 366 | candidate_remove: 1 files/366 bytes |
| `artifacts` | 134 | 250,850,558 | hold_unknown: 134 files/250,850,558 bytes |
| `data` | 6,879 | 4,286,367,956 | candidate_remove: 5,787 files/3,973,669,980 bytes, hold_mixed_provider: 67 files/16,294,481 bytes, hold_unknown: 218 files/14,890,234 bytes, retain_code: 560 files/6,288,864 bytes, retain_databento: 179 files/256,822,631 bytes, retain_databento_derived: 45 files/17,424,114 bytes, retain_markdown: 23 files/977,652 bytes |
| `hpc` | 7 | 63,875 | candidate_remove: 7 files/63,875 bytes |
| `scripts` | 37 | 735,475 | candidate_remove: 37 files/735,475 bytes |
| `src` | 57 | 1,207,352 | candidate_remove: 57 files/1,207,352 bytes |
| `stat-arb` | 4 | 91,949 | candidate_remove: 4 files/91,949 bytes |
| `tests` | 72 | 1,320,782 | candidate_remove: 72 files/1,320,782 bytes |

## Provenance findings

- `data/raw/databento/` has explicit acquisition ledgers, request records, provider metadata, download manifests, validation reports, receipts, and Databento `.csv.zst` originals; retained.
- `data/processed/cfo-2024-2025-databento/` and `data/processed/lattice-databento-gd-pilot/` are explicitly named Databento-derived trees; retained.
- `data/processed/multi_market/full-options-v1/` has `staged_provenance.json` with `run_id=databento-full-20261003`; the ingest manifest repeats that run id and contains output hashes. Retained.
- Other `data/processed/multi_market/` paths are held for review because the tree combines equity, futures, and options results and provider evidence does not establish provenance per file.
- `artifacts/contextual-lattice/` source manifests prove the run includes SEC context and equity/futures inputs, but do not map every data file to a provider. Held for review.
- Identified non-Databento SEC/REIT/OCR/Massive/Sunbiz data, Massive cache, pytest cache and Python bytecode are listed as removal candidates; nested Markdown is retained.
- Other unclassified data (including option quotes, team-source onboarding and chat-tracking data) remains held for review.

## Candidate removal scope

The JSON identifies each candidate file individually. Once authorized, remove only those listed candidate files after checking their resolved paths remain under the repository. Do not recursively remove candidate directories because Markdown and retained material may be nested.
