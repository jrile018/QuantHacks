# REIT market acquisition status

Current retained checkpoint: 2026-10-04. The existing six development jobs for January 2024 through December 2025 (exclusive end January 1, 2026) are settled and their deliveries complete. No new paid order, holdout acquisition, return analysis, or backtest occurred. The [budget checkpoint](../data/processed/reit_build/20261004-continuation/budget_checkpoint.json) records a $249.99 cap, including $31.67 legacy high-water spend, $79.07 total commitments and $170.92 remaining. Provider job costs and ledger settlements are not confirmed invoices or an account-wide reconciliation.

## Delivery and storage

All six saved deliveries are verified: 162 files and 1,992,219,328 compressed bytes. The OPRA minute job reports 259,852,151 provider records; provider records are not eligible research samples. Full compressed raw data and uncompressed/SQLite working data remain on `home-pc`. Only compact hash-matched results were copied locally. Earlier partial local downloads, held reservations and remote-resume notes are superseded historical snapshots. A URL or receipt does not substitute for downloaded bytes.

The frozen [quality rule](../data/processed/reit_build/20261003/market/quality_exclusion_rule.json) excludes a joint feature, decision or holding window that touches any of the 21 degraded dates. Excluded windows and missing days must remain visible; no zero-return imputation or outcome-based reinstatement is allowed. Provider dataset conditions do not prove per-symbol coverage.

## Bounded market qualification

The [collection receipt](../data/processed/reit_build/20261004-continuation/market-v2-results/collection_receipt.json), [qualification report](../data/processed/reit_build/20261004-continuation/market-v2-results/qualification_report.json), [frozen selection](../data/processed/reit_build/20261004-continuation/market-v2-results/frozen_selection.json), [producer exit](../data/processed/reit_build/20261004-continuation/market-v2-results/producer-exit-v2.txt) and [test log](../data/processed/reit_build/20261004-continuation/market-v2-results/tests-producer-v2.log) retain the current result. Verification passed 112 code pins and 18 auxiliary metadata files without mismatch; 349 producer tests passed. The producer scanned 98 selected CSV quote files and explicitly left 46 derivative quote files unscanned. EQUS covers 2024–2025; OPRA and GLBX diagnostics cover January 2024 only. This is not whole-delivery coverage.

| Feed | Diagnostic marks | Scanned rows |
| --- | ---: | ---: |
| EQUS.MINI | 957,736 | 1,028,190 |
| OPRA.PILLAR | 10,419,098 | 14,103,960 |
| GLBX.MDP3 | 174,433 | 235,288 |

Definition `contract_multiplier` fields are sentinel/unknown. EQUS.MINI aggregates component venues and does not establish national executable NBBO. `ts_event` is the **last trade** timestamp, possibly empty or forward-filled, not quote-update time. `ts_recv` is the minute interval end. Quote-update time, freshness and observed market availability remain **unknown**. `historical_interval_endpoint_replay` is an explicit replay assumption, not observed tradable availability or synchronized execution.

The 128 AMT screening candidates use a frozen persistence baseline with a 60-second lookback and 3,600-second holding window. They are unscored: outcomes were not read, costed labels and matched trial registration are absent, and canonical consumer readiness and acceptance are false. Adjusted deliverables, multipliers, action history, exercise/assignment, borrow, dividends, financing, margin, costs, fills and leg risk remain unresolved for derivative repricing and strict arbitrage. No profitability or trading claim follows.

## Next bounded use

Finish frozen fragment measurements and register the one aggregate/decision rule still pending for a wording-only equity-first trial. The retained scoring has 15 text versions across eight unique accessions, all from 2023; two BXMT versions share one quarantined accession. There is no scored 2024 or 2025 release text yet. A January 2024 onward release-wording event test first needs minimal existing-provider scoring of dated, qualification-matched retained 2024–2025 text. Then compare a matched baseline and cash under a hypothetical USD 1 million scale; financial-surprise context follows. Broader acquisition, loan-network claims and option/futures layers wait until after the pilot. Financial and derivative gates are not prerequisites for carefully bounded equity wording.
