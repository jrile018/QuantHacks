# Graph Report - 20261004-3f76ce20-0d77fc4d  (2026-10-04)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 579 nodes · 1056 edges · 23 communities (21 shown, 2 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 13 edges (avg confidence: 0.84)
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

## God Nodes (most connected - your core abstractions)
1. `ScoreRows` - 22 edges
2. `run_gm_boundaries()` - 15 edges
3. `ViewCRows` - 14 edges
4. `ingest_options()` - 13 edges
5. `run()` - 12 edges
6. `score_view_d()` - 12 edges
7. `SpreadRow` - 12 edges
8. `FastMCDFit` - 12 edges
9. `append_lifecycle_event()` - 11 edges
10. `KdeFit` - 11 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `paired_interval()`  [EXTRACTED]
  scripts/lattice_strategies/audit_frozen_targets.py → src/lattice_strategies/evaluation.py
- `run()` --calls--> `build_residual_forecasts()`  [EXTRACTED]
  scripts/lattice_strategies/run_study.py → src/lattice_strategies/residuals.py
- `run()` --calls--> `build_risk_forecasts()`  [EXTRACTED]
  scripts/lattice_strategies/run_study.py → src/lattice_strategies/risk.py
- `run()` --calls--> `append_lifecycle_event()`  [EXTRACTED]
  scripts/lattice_strategies/run_study.py → src/contextual_lattice/tracking.py
- `run()` --calls--> `write_frozen_manifest()`  [EXTRACTED]
  scripts/lattice_strategies/run_study.py → src/contextual_lattice/tracking.py

## Import Cycles
- None detected.

## Communities (23 total, 2 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (19): main(), clean(), main(), run(), write_json(), main(), append_lifecycle_event(), _canonical() (+11 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (30): export_boundary_mesh(), FramePoint, coords, date, load_geometry(), MeshCounters, failures, first_error (+22 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (16): build_return_panel(), filter_tickers_with_sufficient_history(), HistoryFilterResult, excluded_short_history, retained, load_ticker_universe(), ReturnPanel, dates (+8 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (30): FastMCDFit, covariance, degrees_of_freedom, inv_covariance, location, max_mahalanobis_squared_over_all_points, numerical_backstop_engaged, shrinkage_intensity (+22 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (24): compute_spread_row(), load_active_universe(), load_knn_neighbors(), load_log_prices(), run_gm_signals(), score_view_c(), SpreadRow, date (+16 more)

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (16): build_contract_panel(), build_futures_features(), _csv_files(), _csv_stream(), fixed_interval_rows(), load_sampled_marks(), _mark_time(), run_study() (+8 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (11): FastMCDScore, critical_distance, depth, distance, inside, p_value, MdsResult, coordinates (+3 more)

### Community 7 - "Community 7"
Cohesion: 0.10
Nodes (22): build_options_artifact(), _date(), _inside(), main(), _read_csv(), _read_scores(), _sha256(), _write_csv() (+14 more)

### Community 8 - "Community 8"
Cohesion: 0.09
Nodes (16): MahalanobisFit, covariance, degrees_of_freedom, inv_covariance, mad_scale, median, standardized_mean, MahalanobisScore (+8 more)

### Community 9 - "Community 9"
Cohesion: 0.12
Nodes (13): _matrix(), mst_neighbors(), tree_covariance(), _ar1(), build_residual_forecasts(), _ols(), _peer_sets(), _state_fit() (+5 more)

### Community 10 - "Community 10"
Cohesion: 0.13
Nodes (16): kde_max_level_sample_points(), KdeFit, alpha, bandwidth, level, training_points, KdeScore, density (+8 more)

### Community 11 - "Community 11"
Cohesion: 0.14
Nodes (10): Edge, distance, i, in_knn, in_mst, j, mantegna_distance(), canonical() (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.16
Nodes (8): constraint_csc(), CscArrays, i, p, x, fit_peer_basket_weights(), status_name(), upper_triangular_csc()

### Community 13 - "Community 13"
Cohesion: 0.16
Nodes (11): evaluate_contextual_hypothesis(), _interval(), _ledger(), _reason(), StudyResult, calendar_block_interval(), evaluate_forecasts(), _metrics() (+3 more)

### Community 14 - "Community 14"
Cohesion: 0.31
Nodes (6): build_context(), _clock(), _coverage(), _filing_availability(), _filing_rows(), _source_rows()

### Community 15 - "Community 15"
Cohesion: 0.23
Nodes (6): ShrinkageResult, correlation, shrinkage_intensity, demean_columns(), sample_correlation(), ledoit_wolf_shrink_correlation()

### Community 16 - "Community 16"
Cohesion: 0.18
Nodes (7): RieResult, cleaned_correlation, cleaned_eigenvalues, eta, q, sample_eigenvalues, rie_clean_correlation()

### Community 17 - "Community 17"
Cohesion: 0.22
Nodes (7): OuFit, half_life, mu, sigma, theta, fit_ou(), ou_zscore()

### Community 18 - "Community 18"
Cohesion: 0.20
Nodes (6): Excursion, end_index, peak_depth, reverted, start_index, detect_excursions()

### Community 19 - "Community 19"
Cohesion: 0.42
Nodes (5): build_audit(), _exact_scores(), _finite(), _quote_mid(), summarize_audit()

### Community 20 - "Community 20"
Cohesion: 0.22
Nodes (6): RmtResult, denoised_correlation, lambda_minus, lambda_plus, num_signal_eigenvalues, mp_denoise()

## Knowledge Gaps
- **104 isolated node(s):** `date`, `coords`, `dates`, `tickers`, `views` (+99 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 249 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FastMCDFit` connect `Community 3` to `Community 6`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **What connects `date`, `coords`, `dates` to the rest of the system?**
  _104 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.08489795918367347 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.0707070707070707 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.0573025856044724 - nodes in this community are weakly interconnected._
- **Should `Community 3` be split into smaller, more focused modules?**
  _Cohesion score 0.07632850241545894 - nodes in this community are weakly interconnected._
- **Should `Community 4` be split into smaller, more focused modules?**
  _Cohesion score 0.0743321718931475 - nodes in this community are weakly interconnected._