# REIT build: what is working and what remains

Updated October 4, 2026 after the bounded producer and offline preparation jobs completed. The build began October 3 in New York; retained timestamps keep their original timezones. Full historical coverage, costed trading results and final OOS remain unfinished.

## Simply put

We now have a system that collects official documents, checks their identity and integrity, separates different kinds of money figures, and stores the evidence beside each figure. Conflicting sources go into review. Heavy processing runs on home-pc.

For example, cash borrowed during a year, debt owed at year-end, and unused borrowing capacity have different meanings. They are stored separately and are not added together. A bank named as trustee or agent is not automatically treated as the lender.

## Completed

| Piece | Actual result | Practical limit |
|---|---|---|
| Original sources |[15 URLs](reit_document_urls.txt) and [their explanations](reit_document_url_explanations.txt) preserved |The original list is a starting catalog; every individual document needs its own checks |
| Expanded sources |[21 focused additions](reit_additional_document_urls.txt); [514 concrete inventory URLs](reit_source_registry_urls.txt) |521 strings in the full registry include seven templates; inventory is not a primary-source approval list |
| Source quality |334 document representations: 210 primary, 120 review, 4 quarantined |Source quality is separate from complete parsing and financial accuracy |
| Financial dataset |1,533 typed observations: 903 balances and 630 flows; 7 instrument observations |These are observations, not 1,533 separate loans; extraction omissions remain recorded |
| Company relationships |14 role records: 8 eligible and 6 requiring review |One shared-name trustee intersection remains unresolved; no proven cross-company causal exposure |
| Current universe |81 validated issuers/common securities; all 81 assigned to nine batches |Current evidence is not complete historical US REIT membership; batch histories remain incomplete |
| Peer originals |37 exact filings collected: 31 new, 6 retained; raw/metadata/source-grade bindings checked |Four issuers, 36 accessions dated before 2026; no observed first-public clocks |
| Loan-history continuation |8 events, 11 source-bound components, 2 evidence-bound relations and 14 party roles |No confirmed borrowing/repayment cash flow; missing agreements and unresolved roles remain queued |
| Offline history preparation |81 issuer main metadata records verified; nine batches prepared; 557 cached URLs verified |43 cache URLs unavailable; 49 older metadata pages pending across 48 issuers; zero batches executed |
| Verification |Latest remote combined REIT gate: 363 tests passed; market producer gate: 349 passed; exact source/output pins verified |363 includes the producer tests plus helper tests; counts are not additive or economic observations. Baseline snapshot's earlier 266-test receipt remains preserved |

The source catalog now includes free GLEIF identity/accounting-parent references and FDIC bank identity/history documentation. Their underlying entity datasets are not yet collected or joined. See [source quality and expansion](reit-data-source-quality-and-expansion.md) for the authority, acquisition status and limitations of each addition.

Subsequent focused checks passed seven peer-collector boundary tests and 21 history/snapshot runner tests, including the filing-metadata versus document-byte-count clarification. The already published snapshot is preserved; later derived records use explicit size fields.

## Use the actual dataset

The immutable [snapshot manifest](../data/processed/reit_build/20261003/integrated/snapshots/snapshot-419fe98b772e4b3116b6e29535e434dce97afcf6e4137aba75c8aaa0a0dc1f04/manifest.json) identifies JSONL, CSV and SQLite exports, source/code/input hashes and coverage gaps. Schema: `reit-dataset-3`; source paths are project relative. The raw/extraction corpus is needed to verify it.

Example from the repository root:

```powershell
.venv/Scripts/python.exe scripts/query_reit_dataset.py data/processed/reit_build/20261003/integrated/snapshots/snapshot-419fe98b772e4b3116b6e29535e434dce97afcf6e4137aba75c8aaa0a0dc1f04 --issuer-cik 1500217 --export data/processed/reit_build/20261003/aat_query.jsonl
```

The CLI verifies retained evidence before querying and creates a new output file. It refuses an existing export path. Full verification reads the corpus; route large repeated work remotely. The remote [query fixture](../data/processed/reit_build/20261003/integrated/query_smoke.json) contains three unchanged example rows from 248 AAT observations.

[Source-version evidence](../data/processed/reit_build/20261003/integrated/source_adjudication_v2.json) preserves both raw versions and their comparison. Three pairs differ only by the narrowly recognized empty final SEC script pattern. Two BXMT agreement URLs contain substantive conflicts: both versions remain quarantined. This exception is an observed byte-pattern inference, not proof of general rendered equivalence. Version 2 separates measured raw-document byte counts from incoming filing size metadata and binds the original unchanged packet. The [size-origin check](../data/processed/reit_build/20261003/integrated/source_size_metadata_origin.json) traces the BXMT metadata field to exact retained SEC JSON pointers; it does not infer aggregate-package semantics.

The original receipt/extraction clocks remain separate. A row's producer `pit_eligible` flag checks its supplied availability clock; it does not establish earliest public availability. Dataset-wide point-in-time and trading readiness remain false. Consumer adapters must preserve that restriction.

Post Benchmark accepted the three-row fixture for structural diagnostics: nine boundary tests passed; original concepts, periods, dimensions and units were preserved. Canonical joins remain zero and availability null. Its acceptance capsule SHA256 is `27efe1bee771dfc54bdc701a6ebcd4366e1e2ec3d5213df9a979643819191c79`, under its declared worktree `data/processed/8k_validation/industry-consumer-v1/`. This does not accept all 1,533 observations or establish economic readiness. Benchmark received the exact 37-original manifest for its separate native financial checks; no duplicate acquisition was requested.

## Market data and money

All six existing Databento development jobs are delivered: **162 files, 1,992,219,328 compressed bytes**. The options delivery reports 259,852,151 records. The window is January 2024 through December 2025. No new paid order or protected final-test acquisition occurred. Bulk raw data remains on home-pc.

The [completed bounded market scan](../data/processed/reit_build/20261004-continuation/market-v2-results/qualification_report.json) checked 98 selected CSVs: all equity quotes and all definitions, plus January 2024 options/futures quotes. Another 46 derivative quote files remain explicitly unscanned. Its [verified collection receipt](../data/processed/reit_build/20261004-continuation/market-v2-results/collection_receipt.json) preserves exact hashes and zero exits for verification, tests, clocks and market processing.

| Selected quote scope | Scanned rows | Diagnostic marks retained |
|---|---:|---:|
| Equities, all 24 months |1,028,190|957,736|
| Options, January 2024 |14,103,960|10,419,098|
| Futures, January 2024 |235,288|174,433|

The 128 AMT screening candidates are **unscored**. They are not trades, matured outcomes or the selected daily wording pilot. The producer report marks repricing insufficient, strict arbitrage rejected and canonical readiness false. Its cross-asset term requirements do not make derivative exercise/margin evidence a prerequisite for a plain-equity wording pilot.

The [settled budget checkpoint](../data/processed/reit_build/20261004-continuation/budget_checkpoint.json) records **$79.07**, including legacy $31.67, leaving **$170.92** under the **$249.99** cap. All six requests are settled. The older $81.01 receipt is a preserved reservation snapshot. These are recorded ledger/provider costs, not independently confirmed account-wide invoices. See [acquisition status](reit-market-acquisition-status.md) and [shared budget guide](reit-shared-budget-handoff.md).

Minute marks support screening. `ts_event` is the last trade, sometimes missing or carried forward; `ts_recv` is the interval endpoint. Neither is an observed quote-update time. Freshness and observed market availability remain unknown; interval replay uses an explicit assumption. EQUS.MINI covers component venues rather than proven national NBBO. Contract multipliers remain sentinel/unknown and 21 degraded dates remain frozen exclusions. Actions, applicable costs, capacity and canonical acceptance still gate an economic replay.

## Next execution gates

The latest human choice is **finish bounded work, then a wording-only post-release equity pilot**, with a matched price/calendar/public-metadata baseline and cash in a **USD 1,000,000 hypothetical account**. Financial-benchmark surprise is next. The canonical consumer owns the signal registration, calendar, quotes, costs, quantities and account ledger. See the [concrete handoff](reit-first-alpha-pilot-handoff.md).

1. Freeze one simple document aggregate using the existing wording provider. The retained 15 text versions are from eight 2023 accessions, with 2,391 fragment measurements and one truncated fragment; none is a 2024–2025 release and no registered trading signal exists. Select a small retained 2024–2025 cohort and perform bounded scoring under the canonical protocol after its text/public-bound checks. Carrying 2023 scores forward would test a different persistent-tone hypothesis.
2. Verify a conservative public upper bound for the exact scored text/version and declare historical processing latency. The [37-row clock packet](../data/processed/reit_build/20261004-continuation/clocks/historical-qualified-v3/manifest.json) supplies acceptance-plus-24-hour proxies, not that verified bound; observed first-public times remain zero.
3. Accept one dated equity opportunity slice with entry/exit bid-ask, applicable actions, costs, quantities and regular account marks. Compare signal and baseline on identical opportunities; missing inputs remain inconclusive.
4. Produce net dollar/return, win/loss, cost, drawdown and eligible Sharpe uncertainty results through Post Benchmark's existing implementation. Previously inspected 2024–2025 remains development. Final OOS stays unopened until contamination review and strategy freeze.

The broader nine-batch collection, historical/delisted US REIT validation, loan-network trading layers and options/futures strategy studies remain unfinished and are deferred until the small pilot supplies evidence. Preparation is not collection completion. Failed runs, quarantine and negative results remain retained.

No returns, predictor fit, executable portfolio replay, final-test opening or live trade was produced by this build. The concrete output is an auditable foundation and a visible queue of remaining work.

Local storage is constrained. A 94,215,359-byte duplicate packaging archive was removed after verifying its checksum against the remote retained copy and the completed extraction. The [cleanup receipt](../data/processed/reit_build/20261003/remote/duplicate_archive_cleanup.json) records the restore location. Subsequent bulk outputs remain remote.

A later disk-full recovery removed a root-owned 137,381,885-byte generated prepared-input file after confirming its remote restore hash. The [recovery receipt](../data/processed/reit_build/20261004-continuation/disk_recovery.json) retains the exact restore location. Raw documents and the immutable snapshot were preserved.

A subsequent recovery removed two duplicate peer packaging archives totaling 10,031,861 bytes after fresh local/remote SHA256 matches. The [packaging recovery receipt](../data/processed/reit_build/20261004-continuation/duplicate_packaging_storage_recovery_v2.json) records restore locations; extracted sources remain unchanged. The interrupted market status document is being restored and checked for nonempty bytes.
