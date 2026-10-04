# Graph Report - source  (2026-10-04)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 940 nodes · 2275 edges · 23 communities (22 shown, 1 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 22 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21

## God Nodes (most connected - your core abstractions)
1. `utc()` - 33 edges
2. `BudgetLedger` - 18 edges
3. `export_features()` - 15 edges
4. `stamp()` - 15 edges
5. `DatabentoClient` - 14 edges
6. `build_relationships()` - 14 edges
7. `evaluate_forecasts()` - 14 edges
8. `_EvidenceIndex` - 13 edges
9. `import_financial_handoff()` - 13 edges
10. `run()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `run()` --calls--> `sha()`  [INFERRED]
  validation/scripts/run_8k_validation.py → root/scripts/multi_market/finalize_options_remote.py
- `replay_portfolio()` --uses--> `Quote`  [INFERRED]
  validation/src/research_validation/portfolio.py → root/src/multi_market/labels.py
- `price()` --calls--> `executable_price()`  [INFERRED]
  validation/src/research_validation/portfolio.py → root/src/multi_market/labels.py
- `_publication_reasons()` --calls--> `validate_sec_url()`  [INFERRED]
  validation/src/research_validation/financial_handoff.py → validation/src/research_validation/release_evidence.py
- `import_financial_handoff()` --calls--> `validate_sec_url()`  [INFERRED]
  validation/src/research_validation/financial_handoff.py → validation/src/research_validation/release_evidence.py

## Import Cycles
- None detected.

## Communities (23 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (51): main(), _read(), run_import(), _write(), audit_clocks(), _cik(), _coverage(), link_outcomes() (+43 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (23): _ledger(), main(), parser(), _read(), BudgetExceeded, BudgetLedger, _cents(), legacy_spend() (+15 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (35): main(), read(), _read(), _reject_output_collisions(), _rows(), _adapt_lineage(), availability(), _decimal() (+27 more)

### Community 3 - "Community 3"
Cohesion: 0.06
Nodes (28): complete_risk(), _hash(), _key_hash(), _keys(), main(), _utc(), compare_frozen(), daily_mean() (+20 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (35): main(), load(), reference_sessions(), run(), build_matrix(), file_sha(), _finite(), frozen_recipe() (+27 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (32): main(), read_rows(), sha256(), write_rows(), build_matrix(), _cik(), _iso(), _required() (+24 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (25): main(), run(), status(), safe_job_details(), sha(), source_hashes(), staged_check(), write_json() (+17 more)

### Community 7 - "Community 7"
Cohesion: 0.05
Nodes (20): digest(), main(), write_csv(), compare_prior(), DictionaryProvider, FinBertProvider, has_public_evidence(), utc_timestamp() (+12 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (26): main(), _price_subset(), run_study(), _score_subset(), _sha(), _write_json(), association(), build_rows() (+18 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (16): extract_path(), _HTMLText, _normalize(), normalize_ocr(), _record(), _text_tables(), extract_document(), GLMConfig (+8 more)

### Community 10 - "Community 10"
Cohesion: 0.12
Nodes (18): _available_record(), build_histories(), _cik(), _document_id(), _eligibility(), _EvidenceIndex, _series_key(), _stable_id() (+10 more)

### Community 11 - "Community 11"
Cohesion: 0.10
Nodes (21): main(), _read_optional(), _sha256(), clean(), main(), packet(), prepare(), run() (+13 more)

### Community 12 - "Community 12"
Cohesion: 0.09
Nodes (17): main(), build_contract_panel(), build_futures_features(), _csv_files(), _csv_stream(), fixed_interval_rows(), load_sampled_marks(), _mark_time() (+9 more)

### Community 13 - "Community 13"
Cohesion: 0.15
Nodes (27): load_table(), main(), reserve_holdout(), write_json(), build_dataset(), _calendar(), _choice(), _decision_pair() (+19 more)

### Community 14 - "Community 14"
Cohesion: 0.09
Nodes (19): BinaryExpression, Compilation, compile_phrase(), _date(), evaluate_formula(), Evaluation, FactRef, _number() (+11 more)

### Community 15 - "Community 15"
Cohesion: 0.12
Nodes (17): annotation_label_digest(), _bbox(), build_review_queue(), canonical_digest(), _decimal(), export_training_pairs(), _file(), file_digest() (+9 more)

### Community 16 - "Community 16"
Cohesion: 0.13
Nodes (14): build_report(), _hydrate(), _load(), main(), _resolve(), _rows(), audit_registry(), audit_source() (+6 more)

### Community 17 - "Community 17"
Cohesion: 0.21
Nodes (18): canonical(), check_budget(), check_remaining_pilot(), commitment(), current_reservations(), ensure_disjoint(), financial_rows(), frozen_scopes() (+10 more)

### Community 18 - "Community 18"
Cohesion: 0.15
Nodes (11): _active(), build_universe(), _date(), _evidence(), _fingerprint(), _known(), _matches(), normalize_cik() (+3 more)

### Community 19 - "Community 19"
Cohesion: 0.22
Nodes (16): build_request_plan(), canonical_bytes(), _clock_value(), collect(), _coverage(), _date(), _fetch(), parse_bls() (+8 more)

### Community 20 - "Community 20"
Cohesion: 0.26
Nodes (12): _clock(), _day(), export_fixture(), _four_pm(), _id(), _jsonable(), main(), _prices() (+4 more)

### Community 21 - "Community 21"
Cohesion: 0.31
Nodes (4): audit_universe(), _cik(), configured_symbols(), _symbols()

## Knowledge Gaps
- **1 isolated node(s):** `Recipe`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 276 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What connects `Recipe` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.060144346431435444 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.06862745098039216 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.07562136435748282 - nodes in this community are weakly interconnected._
- **Should `Community 3` be split into smaller, more focused modules?**
  _Cohesion score 0.06187202538339503 - nodes in this community are weakly interconnected._
- **Should `Community 4` be split into smaller, more focused modules?**
  _Cohesion score 0.06821787414066631 - nodes in this community are weakly interconnected._
- **Should `Community 5` be split into smaller, more focused modules?**
  _Cohesion score 0.07441016333938294 - nodes in this community are weakly interconnected._