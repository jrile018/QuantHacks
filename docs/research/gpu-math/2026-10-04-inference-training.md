# GPU inference and training implementation plan

Date: 2026-10-04. Status: planning only; no runtime, package, backtest, or economic result is claimed.

> **For implementers:** use the approved owner-specific execution workflow and verify each task independently. This
> plan coordinates with the shared GPU backend plan; it does not authorize opening a protected holdout or starting
> a parameter search.

**Goal:** Accelerate repeated bootstrap statistics and registered ridge fits only when the same inputs, sampled
paths, scientific decisions, and outputs are validated against the CPU reference.

**Architecture:** The coordinator owns one optional array backend and deterministic kernels in
`src/math_backend.py` and `src/math_kernels.py`. Existing evaluation modules retain cohort construction, RNG,
report semantics, and acceptance gates. CPU generates every sampled index path; an eligible GPU only evaluates
fixed arrays in bounded chunks. Training computes train-only preprocessing and reusable per-cohort sufficient
statistics once, then evaluates the existing registered candidates under a stable fit rule.

**Tech stack:** Python, existing NumPy/pandas, optional GPU array runtime in a separate
`requirements-gpu-math.txt`; float64 is required for comparisons. `requirements-training.txt` currently makes NumPy
optional for `--fit` and must not become a mandatory GPU installation.

**Specification and boundaries:** Read `docs/research/2026-10-04-sharpe-confidence-and-monte-carlo.md`,
`docs/superpowers/plans/2026-10-04-sharpe-confidence-and-monte-carlo.md`,
`docs/coordination/first-pilot-decision-register.md`, and `docs/research/lattice-math-audit/consumer-handoff.md`.
Research Sharpe confidence intervals owns inference method and coverage claims; Lattice owns numerical diagnostic
adapters; Post Benchmark owns accepted economic ledger/replay; Benchmark owns feature production. The small
wording-only, realistic-cost pilot is independent of this optional optimization.

## Current code and measurable opportunity

- `src/lattice_strategies/evaluation.py::paired_interval` draws circular date-block starts inside a Python loop and
  computes one mean per replicate. `summarize_risk` calls it on a common complete date cohort for `mst_tree` versus
  each control. The paired forecast path uses the same helper. These are exploratory loss diagnostics; allocation
  `net_proxy_return` remains a gross-one research mark, not an accepted account ledger.
- `src/multi_market/evaluation.py::calendar_block_interval` already constructs a full CPU NumPy matrix of
  noncircular calendar-block indices, then means each row. Dates bundle simultaneous instruments; a fixed block
  length is explicitly unvalidated and the interval is exploratory. `_ridge_predictions` centers/scales the train
  matrix and solves a ridge system per registered packet. `evaluate_forecasts` uses one common complete train/test
  cohort, an availability cutoff, a purged pre-holdout span, and at most three candidate families.
- `src/options_learning.py::train_model` uses train-only median imputation, missingness indicators,
  centering/scaling, a train mean baseline and registered `ridge_alphas`. It currently recomputes `x.T @ x` and
  `x.T @ (y-means)` inside the alpha loop and solves a regularized normal-equation system. Validation selects;
  `evaluate_final_test` consumes the final split once. `scripts/train_options_model.py` reserves the test in a
  persistent ledger. The math change must not weaken those guards or silently enlarge a candidate grid.
- Focused tests already exist in `tests/test_lattice_strategy_evaluation.py`,
  `tests/test_multi_market_evaluation.py`, and `tests/test_options_learning.py`. No current measured GPU advantage,
  equivalence evidence, accepted economic return series, or GPU runtime is established by these files.

## Interfaces and owner map

| Deliverable | Owner | Exact files | Dependency |
|---|---|---|---|
| Optional backend selection, float64 capability, bounded transfer/chunk contract | GPU coordinator | `src/math_backend.py`, `tests/test_math_backend.py`, `requirements-gpu-math.txt` | CPU reference baseline; remote GPU feasibility owner packet |
| Fixed-index batched statistics and reusable current-behavior ridge fit primitive | GPU coordinator with Lattice numerical review | `src/math_kernels.py`, `tests/test_math_kernels.py` | Backend contract; conditioning diagnostics agreed before use |
| Exploratory interval adapters | Lattice numerical owner | `src/lattice_strategies/evaluation.py`, `src/multi_market/evaluation.py`, matching existing tests | Kernels pass CPU equivalence; existing cohorts and labels unchanged |
| Options learning fit adapter | Lattice/options-learning owner, coordinating any protected-test review with Post | `src/options_learning.py`, `tests/test_options_learning.py`, `scripts/train_options_model.py` only if interface requires it | Stable primitive; existing holdout ledger remains authoritative |
| Sharpe inference integration, if eligible economic ledger arrives | Research Sharpe confidence intervals owner | In that owner's declared checkout: `src/research_validation/simulation.py`, `tests/test_strategy_sharpe_inference.py` as specified in its existing plan; these are not shared-root edit targets | Post accepts regular costed account returns and owner freezes method |
| Bounded performance receipt | GPU coordinator | `scripts/benchmark_gpu_math.py`, `tests/test_math_kernels.py`, `docs/research/gpu-math/` receipt | All focused correctness gates pass |

No second GPU backend, inference method, source adapter, or portfolio ledger should be created here. A shared
numerical API or dependency change receives maintainer review in its own scope; producer/consumer owners
acknowledge their adapter changes separately.

## Task 1 — freeze CPU witnesses and backend contract

- [ ] In `tests/test_math_backend.py`, specify `resolve_backend(mode='cpu', device=None, dtype='float64',
  profile=...) -> BackendSpec` for `cpu`, `gpu`, and `auto` when the optional runtime/device is absent or lacks
  usable float64. `auto` must choose CPU with a recorded reason; an
  explicitly requested unsupported GPU must fail clearly rather than silently change precision.
- [ ] In `tests/test_math_kernels.py`, use synthetic daily vectors with unequal paired outcomes, ties, all-constant
  values, one row, missing rows, and a block longer than the series. Store tiny exact CPU sampled-index and
  statistic witnesses, including circular and noncircular semantics. No market data is needed.
- [ ] Define that backend API in `src/math_backend.py` so data movement is explicit, input/output arrays have
  float64 dtype, chunk size and memory budget are arguments or documented defaults, and returned report scalars are
  Python numbers. In `src/math_kernels.py`, use the shared names `centered_covariance`, `quadratic_forms`,
  `symmetric_eigvalsh`, `bootstrap_means(values, indices, backend, max_batch_bytes)`, and
  `ridge_solve(gram, cross, ridge, backend)`. Preserve caller-visible field names and JSON shape.
- [ ] Add `requirements-gpu-math.txt` as an isolated, pinned optional runtime only after the remote feasibility
  owner verifies exact device/driver/runtime compatibility. Keep CPU import and test collection working with that
  runtime absent.
- [ ] Run `python -m unittest discover -s tests -p 'test_math_*.py'` in the CPU environment;
  record version/platform and fixture hash before any GPU comparison.

## Task 2 — fixed-index bootstrap arithmetic

- [ ] Keep RNG and resampling topology in the caller or an explicitly CPU-only index function. Use
  `np.random.default_rng(seed)` as the existing reference for the current diagnostics; compare exact sampled-index
  arrays before comparing results. Changing draw order is a behavior change and needs separate review.
- [ ] Implement `bootstrap_means(values, indices, backend, max_batch_bytes)` in `src/math_kernels.py`; it accepts the already generated integer index matrix and one
  or more aligned float64 series, evaluates per-replicate means/statistics in chunks, and returns results in
  original replicate order. Do not transfer a full large index matrix to GPU in one allocation when it exceeds the
  budget.
- [ ] For `paired_interval`, share each generated circular date-block index path across all paired controls on the
  same common cohort when their sample axes truly match. For `calendar_block_interval`, keep its noncircular starts
  and date grouping. Never combine these two sampling definitions under one ambiguous method label.
- [ ] For future Sharpe studentization, the acceleration boundary is deterministic per-replicate arithmetic on the
  accepted net account-return vector and a fixed sampled path. Recompute each replicate's documented
  dependence-aware standard error; a GPU speedup cannot replace `se_b` with `se_hat`, discard invalid draws, or
  turn a percentile interval into the registered studentized 95% procedure.
- [ ] Test constant and zero-variance paths, zero/one session, block truncation, invalid/nonfinite replicates,
  paired strategy/baseline covariance, and calendar dates containing multiple issuers. Undefined Sharpe and
  insufficient effective event support must retain their explicit states and reasons, even if arithmetic returns
  finite values.
- [ ] Verify exact index equality on CPU/GPU. Initial continuous float64 comparison gates are `rtol=1e-10` and
  `atol=1e-12`, retaining any tighter existing checks; log maximum error and count of changed invalid states.
  Require identical cohorts, draw counts, ordering, reason codes, and quantile convention. Do not infer 95%
  coverage from device agreement.

## Task 3 — stable reusable ridge work

- [ ] Keep `split_dataset`, purging, label-availability checks, train-only `_preprocessing`, `TARGET_NAMES`,
  validation selection, and final-test ledger as the source of truth in `src/options_learning.py`. Build the
  transformed training matrix and centered multi-target matrix once per exact train cohort.
- [ ] Compute reusable `X.T @ X` and `X.T @ Y_centered` only as sufficient statistics for the existing registered
  alpha list; cache them by a content digest that includes ordered train event IDs/groups, feature order,
  preprocessing version, target rule, dtype, split/embargo parameters, and source evidence version. A changed
  cohort must miss the cache.
- [ ] Keep current `np.linalg.solve(X.T @ X + alpha I, X.T @ Y_centered)` behavior, including its existing
  failure behavior, while reusing the sufficient statistics. Use augmented least-squares/QR/SVD only as a CPU
  diagnostic reference for ill-conditioned, singular, and near-zero alpha fixtures. Record condition estimates
  and residuals; if the GPU path is unsuitable, fall back to the existing CPU path. A new QR/SVD fit or failure
  policy requires a separate correctness change and review. Preserve unpenalized intercept and train-mean baseline.
- [ ] Allow a batched GPU solve via `ridge_solve(gram, cross, ridge, backend)` only where float64 capability and
  residual checks (`||A W-B||`, predictions, validation loss) pass against the current CPU path. GPU validation
  chooses among the same registered candidates, in the same deterministic tie order. It never reads test outcomes
  while selecting.
- [ ] In `src/multi_market/evaluation.py`, reuse train-only statistics when candidate packets have an identical
  cohort and feature matrix; matrices with different selected columns may share a full-cohort transformed base but
  must retain their own column order and fit. Keep its existing one-to-three family cap, simple substitute and zero
  controls, common complete cohort, label cutoff, purge, and exploratory report wording.
- [ ] Test an exactly collinear feature pair, near-zero positive ridge, a missingness indicator constant in train
  but variable in validation, alpha order/ties, changed training evidence, appended future/test rows, and candidate
  packets with overlapping feature sets. Assert no test leakage and one final evaluation.
  `tests/test_options_learning.py` and `tests/test_multi_market_evaluation.py` own these focused cases.

## Task 4 — bounded checkpointable sweep DAG, only after protocol approval

- [ ] First inventory the registered configurations and freeze a development-only candidate set with the trial
  owner. The present request does not authorize adding a search protocol, opening the protected final holdout, or a
  full Monte Carlo campaign. A no-sweep mode that only benchmarks existing candidates is the default.
- [ ] If a later bounded sweep is authorized, represent each fit as a content-addressed node: input
  evidence/cohort/split/preprocessing digest → transformed train matrix → sufficient statistics → `(alpha, solver,
  version)` fit → validation score → selected policy. De-duplicate only nodes with identical complete keys;
  preserve every attempted candidate, failure, and trial count in an append-only registry.
- [ ] Set a fixed maximum number of configurations, replications, wall time, memory, and independent RNG streams
  before running. Derive named seed substreams from a recorded master seed and stable candidate ID, so worker count
  and task order do not change paths. A resume skips only verified completed nodes and appends, never overwrites,
  receipts.
- [ ] Write atomic checkpoints containing code/input hashes, method/backend versions, float64 mode, seed/substream
  IDs, candidate status, numerical warnings, result hashes, and exit code. Keep the protected final holdout outside
  development cache keys and tasks; one frozen selected policy reaches the existing final-test ledger once.
- [ ] Test a killed-and-resumed synthetic two-candidate run: no duplicate fit, identical output/order with one
  versus two workers, changed source hash invalidates reuse, and failed candidates remain visible. A future sweep
  runner may be proposed separately; do not add one as part of this plan alone.

## Task 5 — benchmark and promotion gate

- [ ] `scripts/benchmark_gpu_math.py` should first run correctness witnesses, then time CPU and GPU on the same
  bounded synthetic shapes representing short/long daily histories, multiple paired series, varying `B`, train
  rows, feature counts, targets, and alpha counts. Report transfer and startup cost separately from kernel time,
  peak host/device memory, chunk count, warm/cold timings, repetitions, and exact environment versions.
- [ ] Compare end-to-end caller wall time, including CPU index generation, transfers, statistic/fit, and
  serialization. Promotion requires at least `1.25x` median end-to-end speedup versus optimized CPU in two bounded
  runs on the target workload, not just a fast kernel. If the
  workload is too small, unavailable, unstable, or numerically divergent, retain CPU as the automatic path and
  report the reason.
- [ ] CPU/GPU equivalence gates: same eligible rows/dates and policy/evidence IDs; bit-identical sampled indices
  and independent seed streams; matching invalid states and final-test count; float64 statistic, coefficient,
  prediction, validation-loss, and report-field `rtol=1e-10`/`atol=1e-12` initial gates (or tighter existing
  checks). Discrete decisions and selected candidate IDs match exactly. Investigate any result whose
  policy selection changes near a tie rather than accepting a looser tolerance.
- [ ] Run focused tests with `python -m unittest discover -s tests -p 'test_math_*.py'`, then the same command
  with patterns `test_lattice_strategy_evaluation.py`, `test_multi_market_evaluation.py`, and
  `test_options_learning.py`. In the Sharpe owner's declared checkout, use the same discover command with pattern
  `test_strategy_sharpe_inference.py` only when that implementation exists. Run a bounded script
  smoke using synthetic fixture files; do not use source originals or an economic result as a performance fixture.
- [ ] For a genuinely heavy benchmark or later calibration, use `home-pc` through Tailscale only, in detached
  `tmux`, under `flock /home/john-riley/.cache/quanthaxs-heavy-compute.lock`, capped at two CPU threads and 4 GiB
  host RAM. Poll a log with explicit exit status; keep bulk arrays/output remote and retrieve a compact hashed
  receipt. Do not use a LAN fallback. No remote execution or installation is part of this planning task.

## Review focus and release criteria

1. A reported numerical speedup does not change information eligibility, cohort membership, paired dependence,
costs, capital accounting, or acceptance of the account ledger.
2. A positive or negative Lattice mark diagnostic remains exploratory. Neither forecast loss nor `net_proxy_return`
can be converted into a USD 1,000,000 account Sharpe or P&L.
3. Economic Sharpe remains unavailable until Post accepts regular, costed, same-capital candidate/baseline account
returns and Research Sharpe validates its registered 95% inference method. Cash-only/zero-variance excess returns
give undefined Sharpe; inadequate support is insufficient evidence.
4. A GPU failure, no float64 device, excessive transfers, conditioning concern, or changed decision selects the
existing CPU reference with a visible reason. No silent result substitution, new fit policy, or package import
requirement is allowed.
5. The protected final period is evaluated only through its existing single-use ledger after policy freeze. Bounded
development benchmarks and a hypothetical later sweep do not reopen it.

Completion is a reviewed implementation plus focused CPU/GPU equivalence and useful bounded end-to-end speedup
receipts on the exact workload. It is not an economic promotion claim or a prerequisite to the first wording-only
costed pilot.
