# REIT market qualification continuation

The producer streams explicitly selected, already-delivered Databento CSV files. It checks original compressed byte sizes and SHA256s, indexes dated definitions on disk, screens quote quality, and emits bounded diagnostic samples and unscored equity forecasts. It makes no provider calls or purchases. Heavy scans and SQLite files belong on `home-pc` under the root agent's detached execution and resource lock.

The development interval is January 2024 through December 2025. The CLI requires the original frozen quality rule SHA256 `8a10928738733b5756e614d4e937ed3cea02f24e5092a0728cb1f505a3b063d4`, containing the union of 21 degraded dates. The minute interval, entire feature lookback, decision, and planned holding period are excluded whenever they touch this union. Later malformed, missing, crossed, or ambiguous records add exclusions. They never remove the frozen exclusions.

The default source selection scans every supplied equity quote and definition file and only January 2024 derivative quote files. Every selected and unscanned path, size, and hash is written to `frozen_selection.json` before scanning. `--all-derivative-months` explicitly expands this selection. A successful scan establishes coverage of selected rows only; it does not establish complete per-instrument history, sessions, option chains, or survivorship coverage.

Supply an explicit manifest; generate its file descriptors from retained delivery manifests rather than guessed filenames:

```json
{
  "jobs": [
    {
      "job_id": "EQUS-20261004-NTU68UXQ59",
      "dataset": "EQUS.MINI",
      "schema": "definition",
      "provider_record_count": 2510,
      "files": [{"path": "/remote/delivered/equity.definition.csv.zst", "size": 1234, "sha256": "replace-with-retained-64-character-file-hash"}]
    }
  ]
}
```

The example path and size are illustrative. Each job's `files[]` must contain only source `.csv` or `.csv.zst` descriptors. Keep `manifest.json`, `condition.json`, `metadata.json`, and other auxiliary delivery records in a separate `auxiliary_files[]` list in that job. Their descriptors remain bound by the config content hash, but this adapter does not parse or verify their bytes; root retains separate auxiliary hash/size verification evidence. Non-CSV entries in `files[]` fail preflight with `non_csv_source_descriptor:<basename>` before creating any output directory. The low-level reader enforces the same rule before opening bytes. No metadata entry is silently skipped or interpreted as market records.

Include all actual source descriptors and the corresponding quote jobs. Supported pairs are `EQUS.MINI/bbo-1m`, `OPRA.PILLAR/cbbo-1m`, and `GLBX.MDP3/bbo-1m`, with a `definition` job for each dataset. `provider_record_count` applies to CSV records only and is checked only when that entire job is scanned. Duplicate job IDs and duplicate raw paths fail closed. Corrupted byte hashes, sizes, or CSV structures stop the run and produce a partial `failure_report.json`; no completed qualification report is written. CSV row-width checks remain strict.

```bash
python scripts/qualify_reit_market.py \
  --config /remote/frozen-market-files.json \
  --quality-rule /remote/quality_exclusion_rule.json \
  --quote-month 202401 --sample-limit 128 --candidate-symbol AMT \
  --interval-replay-assumption \
  --output /remote/fresh-market-qualification
```

The output directory must be fresh. Only the small JSON reports should be pulled back into `data/processed/reit_build/20261004-continuation/market/`; retain `definitions.sqlite` on the compute host. `zstandard` is needed only for compressed CSVs. Targeted fixture tests use tiny original CSVs and the standard library.

| Output | Meaning |
|---|---|
| `frozen_selection.json` | Exact source selection, quality-rule binding, forecast policy, sample cap, and omitted file inventory |
| `definitions.sqlite` | Every successfully indexed selected definition with original file/hash/CSV-line provenance |
| `normalized_quote_samples.json` | Bounded valid and rejected quote samples with raw and definition lineage; review remains pending |
| `equity_forecast_candidates.json` | First bounded qualifying AMT observations with a frozen persistence forecast; targets and returns remain null |
| `strict_arbitrage_rejection.json` | Explicit missing economic and execution evidence; arbitrage claim is false |
| `qualification_report.json` | All selected row counts, dated identity matches, exclusions, date counts, and per-track status |
| `failure_report.json` | Partial counts and failure reason if verification or parsing failed |

Identity lookup requires the same dataset, publisher, instrument ID, symbol, and observed UTC definition date. It selects the latest definition received no later than the quote. Previous-day definitions are not extended across unobserved dates. Conflicting identities at the same latest timestamp, deletions, unknown update actions, futures spreads, inactive/expired contracts, and incomplete option terms are excluded. Matching provider records are observed identities; independent historical corporate-action and deliverable review remains pending.

Timestamp comparisons preserve nanoseconds. In the [official BBO/CBBO field definitions](https://databento.com/docs/schemas-and-data-formats/cbbo), `ts_recv` is the minute interval endpoint and `ts_event` is the last trade timestamp. That trade timestamp may be undefined or forward-filled. The adapter retains it as optional `last_trade_at_utc`, rejects malformed or future observed trade timestamps, and never interprets its age as quote staleness. `quote_updated_at_utc` and `quote_age_seconds` remain null and `quote_freshness_verified` remains false. Quality checks cover the minute ending at `ts_recv`, rather than the time elapsed since the last trade. Observed quote public, available, received, and processed clocks remain null.

Prices and sizes must be finite and positive, sizes integral, and bid strictly below ask. Undefined scalar sentinels stay unknown. The downloaded definition audit found every contract multiplier unset; the adapter never substitutes 100 or uses unit-of-measure quantities as premium multipliers. `EQUS.MINI` quotes retain component-venue scope. Minute endpoints retain interval scope and do not become simultaneous execution or live processing evidence.

The first equity candidate uses only its current qualified interval quote: mid, spread, and displayed size imbalance. Its prediction is the current mid carried forward for one hour. It records a 60-second feature interval and checks the full planned window before constructing the forecast. Creating candidates requires explicit `--interval-replay-assumption`: this records `historical_interval_endpoint_replay` and a separate assumed availability clock. Without this opt-in, marks are still screened but no forecast candidates are emitted. Candidate `feature_available_at_utc` remains null; `feature_assumed_available_at_utc` and `feature_availability_assumption` carry the research assumption. The assumed clock must not follow the decision, and the complete quote interval must fit within the declared feature lookback. `canonical_consumer_ready` remains false on marks, candidates, and reports.

This is a frozen diagnostic baseline, without model fitting, forward target construction, scoring, net returns, holdout access, or fill claims. Source normalization scans prices for quality; `outcomes_read=false` refers to the absence of forward label construction or evaluation.

Diagnostic status can be `candidate_only`. Repricing remains `insufficient` until canonical trial registration, matured labels, past-only folds, purge/embargo, capital stress, and consumer acceptance are established. Strict arbitrage remains `rejected` because the current minute sources and definition inventory do not prove synchronized legs, national equity NBBO, independent historical identity, dollar multipliers, adjusted deliverables, financing, borrowing, dividends, fees, margin lifecycle, exercise/assignment, fills, or leg risk. No inequalities or trading profits are evaluated by this adapter.

Optional cost evidence is an object keyed by `fees`, `slippage`, `financing`, `borrow`, `dividends`, `margin`, `assignment`, `american_exercise`, `adjusted_deliverables`, and `corporate_actions`. An entry requires a nonnegative finite value, retained source path and SHA256, `verified=true`, named reviewer, retrieval/review/publication timestamps, and validity bounds covering sampled marks. Missing files, mismatched hashes, publication after the decision, expired evidence, booleans, negative values, and unreviewed zeroes stay unknown. This is a conservative quote-specific evidence gate; complete holding-period cashflows and contract lifecycle validation still belong to the canonical consumer.

The adapter inspected the existing canonical `research_validation/market_handoff.py`, `portfolio.py`, and `trials.py` without modifying them. Its producer schemas deliberately remain review-pending and do not claim to be accepted canonical artifacts. The next step is to bind independently reviewed upstream receipts, historical mappings, corporate-action coverage, sessions, and costs through the canonical market handoff; register the forecast trial before constructing or evaluating labels. No parallel evaluator was added.

Suggested historical qualification evidence is issuer/exchange action notices for equities; original OCC adjustment memos for option deliverables and dollar terms; exchange contract specifications plus dated notices and settlement records for actual futures; and dated broker schedules for financing, borrow, fees, and margins. These are evidence requirements, not audited histories or acquisition authorizations. Databento documents that its primary index clock is `ts_recv` when present in the [common fields specification](https://databento.com/docs/standards-and-conventions/common-fields-enums-types). The [OCC symbology adjustment memo](https://infomemo.theocc.com/infomemos?number=26853) explains that an adjusted symbol does not itself specify contract terms. Current documentation is supporting guidance; retain original historical evidence and hashes before marking any source qualified.

Verification: the focused suite covers 27 tests after observed RED runs. Direct regressions reproduced rejection of blank last trades as missing quote clocks and rejection of old trades as stale quotes before the semantic correction. Tests cover undefined/old trade handling, future trade rejection, minute-based quality windows, unknown observed availability, explicit replay opt-in, future assumed availability, and feature interval bounds. The later remote failure identified JSON auxiliary descriptors in the source list. Two additional RED tests demonstrated that minimal JSON metadata was accepted as empty CSV and output creation proceeded; the source-type guard now rejects it at both reader and preflight boundaries. The corruption, sentinel, identity/date, spread, degraded-window, missing-source, and cost-validity cases continue to use real tiny CSV files and SQLite. Compilation and focused tests are checked again when handing off the corrected sources. Full repository tests and actual delivered-file execution are assigned to the root agent's remote runner; fixture results do not assert those checks passed. Previous output receipts are preserved and retain their original source hashes.
