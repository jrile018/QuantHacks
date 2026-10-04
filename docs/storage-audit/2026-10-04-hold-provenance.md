# Held-data provenance review — 2026-10-04

Read-only review of 419 held files (282,035,273 bytes). This records existing provider/source manifests and the verified private backup manifest; no held files were deleted.

The initial held-file hash pass found 404 exact path/size/SHA matches, 2 size-changed files and 13 paths absent from the backup manifest. All 15 exceptions belong to active `data/processed/chat_tracking` and remain protected. Backup commit: `1799747cd8c1ae7d6df83f3e2e87879266183b9b`.

## Proven Databento data to retain

- `data/processed/multi_market/futures-v1`: 18 files / 8,826,385 bytes. `study_report.json` records 3,512 Databento GLBX/EQUS inputs (6,538,075 rows, 167,560,460 source bytes); the `contextual-lattice` manifest’s futures feature hash matches the output file.
- `data/processed/multi_market/pilot-download-verification`: 12 files / 933,600 bytes, with local/remote SHA matches and Databento job IDs.
- `data/processed/multi_market/metadata`: 1 file / 10,151 bytes, explicitly documented as read-only Databento metadata/cost quote evidence.
- `data/processed/multi_market/options-matched-v1`: 10 files / 64,720 bytes, whose bars/quotes source hashes match retained Databento full-options outputs.
- Other mixed-market and contextual-lattice results depend on vendor-unknown equity features; retain them with the mixed/unknown data.

## Non-Databento payload candidates for coordinator review

Every listed file belongs to a cohort whose local hashes matched backup path/size/SHA during the bounded read-only hash pass. Candidate SHA256 values and paths are in the JSON. Manifests, receipts, access/selection records, reports, source helpers and Markdown are excluded and remain retained.

| Cohort | Files | Bytes | Evidence |
|---|---:|---:|---|
| SEC contextual-lattice source payload | 1 | 1,585,197 | Adjacent run manifest source SEC_filings SHA256 is 631e613bd359a583b2ec7d1db3497b631828fe814b4f0decb5b28146d382bc68 and matches this file. Receipt says source is existing cache only and describes official SEC 8-K population. Receipt and coverage metadata remain retained. |
| SEC/OCR document-pilot payloads | 6 | 649,080 | documents.jsonl and native_batch/manifest.jsonl map transcript source hashes to SEC.gov 8-K filing URLs. The two calibration PNGs have documents.jsonl records identifying pages from SEC filing reports. Audit, cache coverage, quote access/collection, selection, and manifests remain retained. |
| SEC/OCR Hipergator payloads | 20 | 647,112 | Both cache-scope and local-processor transcript manifests map source_sha256 values and document IDs to the SEC filing hashes also recorded in document_pilot/documents.jsonl. Candidate paths below are only OCR/transcript payloads; manifests, run records, inventories, reports, logs, verification and Markdown are retained. |
| Massive native smoke outputs | 7 | 57,966 | Adjacent manifest.json says source=Massive 8-K disclosures and option chains. Manifest itself is excluded from candidate list and retained. |
| Massive smoke outputs | 5 | 30,327 | Adjacent manifest.json says source=Massive 8-K disclosures and option chains. Manifest itself is excluded from candidate list and retained. |
| Massive raw option quotes | 3 | 6,873 | data/raw/option_quotes/135d13f09b10ba23dda529cd3d6f54c98f51fbc3b4803279cba8d8173ffa3dac.metadata.json declares provider=Massive; response payloads reference the Massive API. Proven non-Databento raw payload. |

Total candidate payload: **42 files / 2,976,555 bytes**. No files were deleted in this review.

## Keep pending owner review

- `native-equity-v1`, risk/role comparisons and dependent contextual-lattice outputs have no complete vendor mapping for the equity inputs.
- Tiger 8-K exports are TigerDB query output with SEC filing fields, but the upstream API provider is absent from available receipts. Keep the exports and SQL helper.
- Team-source verification, live chat tracking, lattice audit records, report metadata, all Markdown, and all source/processing manifests remain retained.
- The direct SEC filing payload in contextual-lattice is separately listed as a candidate; its adjacent receipt and coverage metadata remain available.

Full per-file path, size, backup SHA256 and provenance evidence: `2026-10-04-hold-provenance.json`.
