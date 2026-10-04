# Numerical kernels implementation plan — 2026-10-04

> **For agentic workers:** Execute the tasks in dependency order with tests and review at each boundary. This is a planning artifact; no runtime or performance claim follows from it.

**Goal:** Make repeated Lattice and multi-market numerical work faster where measured, while preserving existing diagnostic rows, clocks, abstentions, and CPU behavior.

**Architecture:** Optimize complete trailing windows and cache shared per-date intermediates on CPU first. Offer an explicit, optional float64 PyTorch/ROCm backend for eligible batches of pure covariance, correlation, symmetric eigenspectrum, and regression work. Keep pandas orchestration, graph topology/tie decisions, SciPy SLSQP, portfolio state, and canonical replay on CPU.

**Tech stack:** NumPy, pandas, scikit-learn, SciPy; optional PyTorch/ROCm installed through a separate opt-in requirement. **Spec/constraints:** [architecture contract](../../coordination/architecture-contract.md), [Lattice audit](../lattice-math-audit/README.md), [consumer handoff](../lattice-math-audit/consumer-handoff.md). Root may be ahead/behind owners' worktrees. No GPU speedup or extraction/economic readiness is asserted.

## Ownership and file map

| Unit | Exact path and responsibility | Owner |
|---|---|---|
| Backend contract | Proposed `src/math_backend.py`; public `cpu`/`gpu`/`auto` choice, availability probe, float64 conversion, atomic batch retry and transfer/chunk/error policy | GPU coordinator |
| Pure kernels | Proposed `src/math_kernels.py`; batched complete-window statistics and symmetric eigenspectrum, CPU reference and optional device implementation | GPU coordinator |
| Kernel tests | Proposed `tests/test_math_backend.py`, `tests/test_math_kernels.py`; value/status/mask/parity and device opt-in | GPU coordinator |
| GPU dependency | Proposed `requirements-gpu-math.txt`; platform-pinned optional install recipe, never import requirement for CPU users | GPU coordinator |
| Benchmark | Proposed `scripts/benchmark_gpu_math.py`; deterministic shape matrix, synchronization, transfer-inclusive timings and memory | GPU coordinator |
| Risk adapter | Existing `src/lattice_strategies/risk.py`, `tests/test_lattice_risk.py` | Assess Lattice repo fit |
| Graph/residual adapters | Existing `src/lattice_strategies/graphs.py`, `residuals.py`, `tests/test_lattice_graphs.py`, `tests/test_lattice_residuals.py` | Assess Lattice repo fit |
| Multi-market adapter | Existing `src/multi_market/features.py`, `tests/test_multi_market_features.py` | Assess Lattice repo fit |
| Context adapter | Existing `src/contextual_lattice/context.py`, `tests/test_contextual_lattice_context.py` | Assess Lattice repo fit |
| Consumer gate | Existing Post Benchmark worktree `src/research_validation/` and its tests; no competing registry/replay backend | Post Benchmark |

The GPU coordinator owns only the proposed shared files. Assess Lattice owns adapter edits after agreeing interface signatures. Post Benchmark owns opt-in canonical integration and acceptance; shared schema/registry changes need its separate review. Do not start a second implementation in this planning lane.

## Current code boundaries and invariants

- `risk.py:24-46` computes sample, diagonal, Ledoit-Wolf, one-factor, and tree covariance from one complete window. `risk.py:136-138` requires every element in `[t-window+1,t]` finite, and `risk.py:136,139-152` only uses `t+1` for marks. Retain five estimator rows, `VARIANCE_FLOOR=1e-12`, QLIKE formula, and return units.
- `risk.py:64-83` runs CPU SciPy SLSQP with sum-to-one, `[0,cap]`, `ftol=1e-12`, `maxiter=500`; accepted weights need sum error `<=1e-7`, lower bound `>=-1e-8`, cap overshoot `<=1e-8`. `risk.py:126-240` keeps weekly rebalance, live-book drift, missing-mark quarantine, hold after failed rebalance, and exit charges. Do not batch this state machine or silently replace its optimizer.
- `graphs.py:11-68` validates a finite symmetric matrix, sorts signed-correlation edges by `(-rho,i,j)`, and multiplies clipped edge correlations along MST paths. Ties and signed edges are observable. Keep Kruskal/topology on CPU; only covariance/correlation precursors are a candidate device operation.
- `residuals.py:24-46` refuses rank-deficient OLS and invalid AR(1). `residuals.py:47-82` forms peer sets from the *earlier formation* window; `residuals.py:84-126` fits hedge on formation and state on later calibration. `residuals.py:129-219` emits every date/ticker/model/horizon row and never bridges missing formation/calibration days. Distinct future raw and own-hedge marks remain separate.
- `features.py:20-66` rejects unavailable prices, absent contract identity, rolls and missing sessions. `features.py:78-154` uses beta from prior returns, current-session shocks, current-ended correlation windows, eligible nodes, and previous-edge turnover only for an identical node tuple. `features.py:156-165` obtains next panel-session targets and their own availability clock.
- `context.py:98-158` has prior-shifted gap/relationship scales and futures/equity unit distinctions; `context.py:160-269` gates filings, links and source shocks by availability and coverage. Vectorize only within the same date/identity and after constructing the same masks. `evaluation.py:130-139` defines training/holdout/embargo and label-availability gates outside the math backend.
- Existing tests cover future append, missing windows, graph sign/ties, rank-deficient hedges, cap/turnover, futures rolls, unavailable prices and context clocks. Extend these rather than weaken the guards.

## Shared mathematical contract

For a complete window `X` of shape `(T,N)`, `T>=2`, use `mu_j=sum_t X_tj/T` and sample covariance `S=(X-mu)^T(X-mu)/(T-1)`; preserve `np.cov(...,ddof=1)` for reference. For rolling windows, define `valid[t,j]=all(isfinite(X[t-T+1:t+1,j]))`, and use the adapter's panel-level or subset-level eligibility rule before calling a kernel. Never replace nonfinite with zero or drop rows: an incomplete risk window abstains, whereas multi-market excludes affected nodes. Keep that distinction in adapter-owned masks.

For `features.py` correlation, `rho_ij=S_ij/(sqrt(max(S_ii,1e-20))*sqrt(max(S_jj,1e-20)))`, nonfinite off-diagonals become zero, diagonal is set to one, and `R=(1-lambda)rho+lambda I`. Preserve exact `eligible` ordering, `abs(R_ij)>=threshold`, the prior identical-node edge comparison, and `lambda` bounds. Residual concentration is `lambda_max(R)/N`; device `eigh/eigvalsh` is eligible only after symmetric finite input and scalar tolerance checks. Do not use a new global PSD repair or alter the edge graph.

For one-factor risk, `f_t=mean_j(X_tj-mu_j)`, `v_f=var(f,ddof=1)`, `beta_j=cov(X_j,f)/v_f` when `v_f>1e-12` else zero, and `C=v_f beta beta^T + diag(var(X-mu-f beta^T,ddof=1))`. The current factor includes the scored book; this is a diagnostic definition, not a hedge interpretation. Ledoit-Wolf remains scikit-learn on CPU until its shrinkage coefficient and centering convention are reproduced exactly and separately accepted.

For residual OLS, use intercept-augmented `A=[1,P]`, require finite `A,y` and `rank(A)=columns(A)`, then solve least squares with the existing `rcond=None` convention; singular cases return no fit, never a pseudoinverse trade. `state=[0,cumsum(calibration_residual)]`; AR(1) is a fit of `state[1:]` on `[1,state[:-1]]`, requiring positive finite innovation variance, `0<phi<1`, finite `tau=-1/log(phi)<=max_tau`, and finite equilibrium. Keep model/horizon forecast formulas and every abstention reason. Initial residual OLS and AR fits stay on CPU, with cached/grouped existing fits. A later GPU OLS proposal requires its own kernel/API, exact rank and `rcond` semantics, measured benefit, and separate diagnostic acceptance; `ridge_solve` cannot substitute for OLS.

## Tasks and dependency graph

`K1 backend contract -> K2 CPU kernels -> K3 adapter CPU caches -> K4 optional ROCm kernels -> K5 measured dispatch -> K6 consumer gate`. `K3` can progress in Lattice's owned files after K2's signatures freeze; K4 is independent of K3. A measurable speedup is the criterion for enabling `auto`; explicit CPU remains the default during rollout.

### K1 — Freeze interface and CPU availability behavior (GPU coordinator)

**Files:** Create `src/math_backend.py`, `tests/test_math_backend.py`; document opt-in install in `requirements-gpu-math.txt` when K4 becomes executable.

**Interfaces:** `resolve_backend(mode='cpu', device=None, dtype='float64', profile=...) -> BackendSpec`; requested/selected modes are `cpu`, `gpu`, or `auto`, with `gpu` implemented through PyTorch/ROCm when available. `BackendSpec` has exactly five fields: `requested`, `selected`, `device`, `dtype`, `reason`. Framework/runtime/library versions and qualification-profile hash belong in the separate versioned Task 7 run/batch JSON receipt. CPU selection returns without importing torch. Explicit GPU probes import, ROCm availability, device identity and float64 operations, then raises a typed availability error on failure. `auto` selects CPU before launch if its qualification is missing/stale or the runtime is unavailable. After a launched GPU batch fails with a typed capability/OOM error, `auto` discards *all* uncommitted outputs of that entire logical pure-kernel batch and retries the entire batch on CPU using identical immutable inputs and CPU RNG indices before any adapter publication or state update. Record the failed attempt and CPU selection in the batch receipt. Explicit `gpu` fails clearly. Invalid inputs, parity failures and nonfinite/numerical divergence invalidate qualification and fail/quarantine; they never trigger automatic CPU retry.

- [ ] Write tests proving CPU import without PyTorch, explicit ROCm absence error, deterministic pre-launch auto CPU selection, invalid-name rejection, and atomic whole-batch auto recovery from injected typed capability/OOM errors. Assert identical immutable inputs/CPU RNG indices, no partial publication, and a per-batch receipt recording both attempts. Invalid input and numerical/parity errors must fail without retry.
- [ ] Implement only the selector and run those tests; publish exact signatures to Lattice/Post owners before adapter work.

### K2 — Batched CPU reference kernels (GPU coordinator)

**Files:** Create `src/math_kernels.py`, `tests/test_math_kernels.py`.

**Interfaces:** Freeze the master plan's public pure functions:
`centered_covariance(windows, ddof, backend)`,
`quadratic_forms(weights, covariances, backend)`,
`symmetric_eigvalsh(matrices, backend)`,
`bootstrap_means(values, indices, backend, max_batch_bytes)`, and
`ridge_solve(gram, cross, ridge, backend)`.
The adapters construct chronological complete windows and exact masks; kernels receive a homogeneous float64 batch of shape `(K,T,N)` or `(K,N,N)` as appropriate, never padded zeros represented as valid data. Bucket differing `T,N` or eligible-node tuples separately. Return NumPy arrays at the public consumer boundary. A private compound call may retain device tensors across adjacent covariance, quadratic-form and eigenspectrum operations; avoid a host round trip after every sub-kernel. `bootstrap_means` uses explicit sampled indices and no RNG state on device; `ridge_solve` is available only for existing matching ridge algebra and must not replace `residuals.py` OLS or rank refusal.

- [ ] Test `T=window`, missing at first/middle/last window element, just-expired missing value, `N=1`, constant column and chunk boundary; compare covariance/eigenvalues to direct `np.cov`/`np.linalg.eigvalsh` with `atol=1e-12`, `rtol=1e-10`. Adapter masks must be exactly equal. Test `quadratic_forms` against `w @ C @ w`, `bootstrap_means` against indexed NumPy means, and `ridge_solve` against a direct CPU solve only when positive regularization is explicitly requested by its caller.
- [ ] Construct windows via bounded chunks without crossing decision boundaries, then use centered two-pass covariance within each batch. Never allocate all `K*T*N` windows at once. Keep integer sampled indices stable and preserve sample order.
- [ ] Test scaling and row/column permutation equivariance where mathematics permits; document cases where MST tie ordering is intentionally not permutation invariant.

### K3 — Adapter CPU caching/vectorization (Assess Lattice repo fit)

**Files:** Modify `src/lattice_strategies/risk.py`, `residuals.py`, `graphs.py`, `src/multi_market/features.py`, `src/contextual_lattice/context.py`; modify their corresponding tests named above. Use K2 only where it matches exact masks and node sets.

- [ ] Risk: precompute complete-window flags and sample/diagonal/one-factor inputs once per date; cache `LedoitWolf` and tree covariance once per date; share across all five estimator rows, four policies, and cost scenarios. Preserve covariance values and `None` on zero-variance tree input. Keep SLSQP and all allocation state in the existing date loop.
- [ ] Residuals: cache formation/calibration slices, `_peer_sets` and CPU OLS/AR fit results per `(date,target,model)`, outside the horizon loop. Group existing full-finite formation fits without changing `np.linalg.matrix_rank`, `np.linalg.lstsq(rcond=None)`, or AR checks; avoid recomputing the same future cumulative sums for each model while retaining each model's own hedge weights. The current structure already caches several items; profile before adding code.
- [ ] Features: cache rolling validity and covariance for an identical eligible-node tuple; update `previous_edges` only under the existing identical-node rule. Keep pandas shifted beta/vol/momentum and label clocks as the parity oracle. Context: cache/group shifted rolling scales and relationships in `src/contextual_lattice/context.py` only after checking the same per-ticker, prior-session and information-clock masks; test against `tests/test_contextual_lattice_context.py` for exact futures/equity units, source availability and filing coverage. Do not merge across futures/equity units.
- [ ] For each adapter, compare complete ordered DataFrames against frozen CPU reference fixtures: keys, status/reason/null masks, clocks, features, forecasts, marks, weights/costs. Numeric values use `atol=1e-12`, `rtol=1e-10` unless conditioning requires a documented tighter or looser per-field limit; categorical/masks/times are exact.

### K4 — Optional batched ROCm implementation (GPU coordinator)

**Files:** Extend `src/math_backend.py`, `src/math_kernels.py`, `tests/test_math_backend.py`, `tests/test_math_kernels.py`; create `requirements-gpu-math.txt` with a tested ROCm/PyTorch platform pin and installation instructions once a usable runtime is confirmed.

- [ ] Add device batches for covariance, quadratic forms, eigvalsh, bootstrap means, and only algebraically matching ridge solves using `torch.float64`, preserving K2 masks and order. Keep private fused tensors device-resident within one compound batch, returning arrays to CPU only at its public boundary. Do not move pandas objects, graph path search, OLS rank decisions, SLSQP, or stateful policy loops to device.
- [ ] Set `chunk_windows` by `(window*N + N*N)*8 bytes` plus measured temporary-factor budget and cap device allocation to a conservative fraction of free VRAM. A smaller GPU chunk retry after typed OOM is allowed only while the entire logical batch remains unpublished. If that retry still fails, explicit `gpu` fails clearly; `auto` discards every uncommitted output of the logical batch, recomputes that whole batch on CPU with the same immutable inputs/CPU RNG indices, and records both attempts in the per-batch receipt before publishing any result. No retry can mask invalid input, nonfinite output or failed parity.
- [ ] Compare GPU with K2 across random seeds and adversarial near-collinear/low-variance windows; exact masks and categories, symmetric matrices and finite PSD tolerance, initial `atol=1e-12`, `rtol=1e-10` for continuous float64 results, plus the existing stricter constraint checks. Any looser numerical gate needs a separately reviewed algorithm change. Any difference that changes eligibility, graph edge threshold, rank/AR validity, or SLSQP feasibility blocks GPU dispatch for that case. Threshold-adjacent cases receive explicit CPU recomputation before discrete decisions.

### K5 — Performance gate and dispatch policy (GPU coordinator)

**Files:** Create `scripts/benchmark_gpu_math.py`; add benchmark metadata tests only if parsing/report logic merits them.

- [ ] Measure existing baseline, K3 cached CPU, K2 pure CPU, and K4 GPU for representative `(T,N,K)` including the current small panels and larger synthetic batches; fixed seeds, warmup, 5+ measured repetitions, median and spread. Include host-to-device transfer, synchronization, device-to-host return, mask construction, and peak host/VRAM, not just kernel time.
- [ ] Under equal output parity, enable `auto` only above an empirically documented batch/shape threshold and only if total median GPU time is at least 1.25× faster than optimized CPU in two bounded runs with no memory failures. Otherwise stay CPU. Report no claim for small matrices where launch/transfer overhead dominates.
- [ ] Heavy benchmark runs use `ssh home-pc` over Tailscale, detached unique `tmux`, `/home/john-riley/.cache/quanthaxs-heavy-compute.lock`, at most 2 CPU threads and 4 GiB host RAM, separate logs/output SHA. The host has a detected 16 GiB AMD GPU but user-space ROCm was not found at this checkpoint; runtime setup is a prerequisite and a failure is a bounded feasibility finding, not a reason to install silently or change CPU defaults. Pull results before cleaning the tmux session.

### K6 — Canonical consumer acceptance (Post Benchmark)

**Files:** Post Benchmark's declared worktree `src/research_validation/` modules and relevant tests; modify only with that owner's agreement after K1–K5 receipts.

- [ ] Integrate an opt-in backend field into existing run provenance, preserving registered feature/target definitions, decision clocks, source hashes, quarantine states, and as-of masks. Do not create a second registry, replay path, or eligibility definition.
- [ ] On a frozen identical input snapshot, compare CPU and opt-in outputs through canonical records and matched forecast scoring. Assert no row gained eligibility from missing data, later labels, revised clocks or backend errors. Future-append and label-delay metamorphic checks must leave all earlier features/forecasts unchanged; only earlier outcomes may become known when their future rows arrive.
- [ ] Publish a separate versioned Task 7 run/batch JSON receipt with framework/runtime/library versions, qualification-profile hash, backend attempts and selection reasons, driver/device, code/input hashes, shape/chunk parameters, timing/memory, exact parity exclusions and readiness status. Keep `BackendSpec` limited to its five declared fields. Acceptance of math parity does not establish forecast value, after-cost performance, options/futures lifecycle, or permission to trade.

## Review focus and stop conditions

1. Missing value just inside vs just outside a trailing window must flip only that date's validity; test K2 and adapter output masks.
2. A future price/filing/label append must not alter prior decisions; test K3/K6 with changed future values, not merely extra identical rows.
3. Nearly tied signed graph edges and threshold-adjacent correlations must preserve the CPU-selected topology; test K3/K4 discrete recomputation.
4. A rank-deficient hedge, near-unit `phi`, zero factor variance, or zero asset variance must keep the old abstention/defined-estimator split; test K3/K4.
5. Device absence or stale qualification must select CPU before auto launch; typed capability/OOM after launch must cause an atomic whole-batch CPU retry before publication, while explicit GPU fails; test K1/K4 and the versioned receipt.

Stop promotion on any changed row key, chronology, mask, status/reason, graph topology, accepted constraints, clock, or canonical eligibility. Numerical tolerances apply only to finite continuous outputs; they cannot excuse a changed decision. Re-run only the affected gate after a correction, then perform a final independent review of the diff and benchmark receipt.
