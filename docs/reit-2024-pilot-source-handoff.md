# First REIT equity test: 2024 source repair

## Simple explanation

The documents and market files are collected, and the research pipeline can check their contents. A realistic profitable strategy has not been demonstrated. The next small test asks whether the wording of a company release improves a long/short stock strategy after costs.

The previous wording scores were from 2023. This continuation retained two American Tower releases **published as 2024 events**: February 27 and October 29. The February release discusses financial year 2023; that financial period does not move its disclosure event back to 2023.

**What was added:** six exact SEC originals (two releases, their two 8-Ks and their two indexes), full native text and hashes, official issuer metadata binding, and a verified remote copy. Benchmark has reported reading the exact packet and selected February first for its existing frozen scorer. Scoring and canonical replay remain separate owner tasks.

## Reusable source packet

- Machine handoff: [producer_handoff_v1.json](../data/processed/reit_build/20261004-pilot-repair/producer_handoff_v1.json).
- Exact source manifest: [release-sources-v2/manifest.json](../data/processed/reit_build/20261004-pilot-repair/release-sources-v2/manifest.json), SHA256 `ce9aa507cfddaa33dc05298f7ab9f06ffdeffe2963194a5ee731f77c9b8a7ebb`.
- Remote verification and original-to-remote path map: [remote_source_verification_v1.json](../data/processed/reit_build/20261004-pilot-repair/remote_source_verification_v1.json), SHA256 `cca2658330fd8e23811087419aed2b8263c65a4521f92f114e3118047dfb36f2`.
- Official filing metadata: [issuer_metadata_binding_v1.json](../data/processed/reit_build/20261004-pilot-repair/issuer_metadata_binding_v1.json), SHA256 `2a273b908618858f222f25c554ef624749dca32cd751ee3a643e01f133a3e1e1`.

Remote source directory: `home-pc:/tmp/quanthaxs-reit-pilot-repair-20261004-v1/source-pack`. Its 147,409-byte source archive has SHA256 `ab3732f9fcc3dcee947cb700a1d651be25097096557e399db99422a0321193df`; all 22 indexed artifacts matched after transfer and extraction. The separately verified 162,218-byte issuer metadata object was also retained there. Original 2026 receipt clocks remain 2026 clocks. The path map binds exact bytes; it does not approve historical trading eligibility.

| Event | Exact SEC release | Raw release SHA256 | SEC acceptance from verified submissions |
| --- | --- | --- | --- |
| AMT 2024-02-27 | [EX-99.1, accession 0001053507-24-000009](https://www.sec.gov/Archives/edgar/data/1053507/000105350724000009/pressreleaseq42023.htm) | `d3e0d2b13d9b4ff50cb104362855975b96dfc354804343f5bdfe1a9c842c3a62` | 2024-02-27T12:05:39Z |
| AMT 2024-10-29 | [EX-99.1, accession 0001053507-24-000128](https://www.sec.gov/Archives/edgar/data/1053507/000105350724000128/pressreleaseq32024.htm) | `277d4f5aba88de6a0d7a52476fa39ad37de581d5d2a46ef06faf60d44e6e6789` | 2024-10-29T11:05:59Z |

Both exact indexes link Item 2.02 and the expected EX-99.1. The source publisher claims 07:00 Eastern releases, but those claims have not been bound to a independently verified historical copy of the entire scored wording. SEC acceptance is recorded separately and is not promoted to first-public time.

## What still prevents a qualified trading result

1. **Safe historical publication timing.** Neither complete release has an accepted exact-version public-by bound. Both issuer archive PDF requests timed out. Two precise Common Crawl index requests returned HTTP404/504; no historical capture was obtained. These failures do not prove that no historical capture exists. Date labels, filing acceptance and a 2026 download alone are insufficient under the frozen protocol.
2. **The new wording scores.** Benchmark owns complete transcript, loaded model/artifact binding and the registered aggregate. Official [Hugging Face revision history](https://huggingface.co/ProsusAI/finbert/commits/db38d3727cbaed87c9aed72df7b3519e2ba5cca1) places the pinned FinBERT revision in June2023, before these events; training cutoff and actual loaded file hashes still need their separate records. No 2024 score was produced by this source lane.
3. **Realistic trade inputs.** Existing minute snapshots do not prove raw quote-update age. Dated share identity/actions, size/capacity, short availability/rates/collateral/dividend liabilities, fees/slippage and full account marks remain unaccepted. Reuse existing deliveries and entitlements first; no new purchase was made. See [the focused execution audit](research/2026-10-04-reit-equity-execution-inputs.md).
4. **One checked replay.** Post Benchmark owns frozen protocol v2, its 252-session2024 calendar and the account engine: USD1m hypothetical, long/short, equal dollar targets, combined gross <=100%, zero idle-cash yield. Entry is the first eligible session open+60s after a supported public upper bound+latency; exit is close-60s. A premarket release may qualify that upcoming session; no trade date is selected while its bound is unknown. Compare the same opportunities with always-long and cash, retaining exclusions and missing outcomes.

The existing two-year market report is still available remotely at `/tmp/quanthaxs-reit-continuation-20261004/market-qualification-v2/qualification_report.json`, verified SHA256 `81583444a7437e9d31f769ef18569477f85ac7cb20b281b94ff3e456a508dbfe`. The authorized storage cleanup removed some old local data paths; consumers must use verified remote mappings rather than assume those files remain local.

## Scope and handoff state

Source/provenance repair is delivered locally; Benchmark reported reading its source pack and beginning the February producer lane. Canonical consumer acceptance and economic results remain pending. P&L, Sharpe and confidence intervals remain unavailable. The two events are a small pipeline check; they cannot establish a robust trading edge by themselves.

The broader loan histories, lender/company relationships, nine historical batches, delisted REIT coverage, options/futures arbitrage and untouched out-of-sample validation remain unfinished. Previously examined 2024-2025 remains development data. This continuation opened no final test, reran no finished numeric/OCR audit, launched no model or heavy job, and spent $0. Last recorded total Databento spending was $79.07 of $249.99.