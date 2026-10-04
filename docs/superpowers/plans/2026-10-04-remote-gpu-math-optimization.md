# Remote GPU and math optimization implementation plan

> **For agentic workers:** use `superpowers:subagent-driven-development` for independently owned implementation tasks or `superpowers:executing-plans` for a checkpointed execution. Complete the checkbox gates and retain evidence; this planning packet does not establish implementation or measured acceleration.

**Goal:** Optimize every identified numerical workload through causal CPU reuse, vectorization and bounded batching, then use the remote AMD GPU only where equivalent outputs and useful total-runtime gains are demonstrated.

**Architecture:** One optional ROCm/PyTorch backend for pure FP64 kernels, with CPU as the default and reference. Existing owners retain adapters, chronology, inference, source provenance and canonical replay. Independent preparation proceeds in parallel; shared-file edits and heavy remote jobs remain serialized.

**Tech stack:** Existing NumPy, pandas, SciPy and scikit-learn; optional isolated PyTorch/ROCm; unittest discovery; SSH `home-pc`, detached tmux, flock and enforced cgroup limits.

**Status:** Implementation plan only. Hardware identification probes and parallel planning are complete; GPU runtime installation, access proof, backend implementation, numerical benchmarks and consumer acceptance are pending. The master document was restored after a disk-full write; this is not runtime proof.

Read [the design](../specs/2026-10-04-remote-gpu-math-optimization-design.md), [numerical details](../../research/gpu-math/2026-10-04-numerical-kernels.md), [inference and training details](../../research/gpu-math/2026-10-04-inference-training.md), [runtime and benchmark details](../../research/gpu-math/2026-10-04-runtime-benchmarks.md), and [agent delivery ledger](../../research/gpu-math/2026-10-04-agent-notifications.md). These extend the existing owner plans; do not replace root `task_plan.md`, `progress.md` or the shared coordination register.

## Scope and preserved contracts

| Family | First optimization | Optional GPU work | Initial CPU boundary |
|---|---|---|---|
| Risk and portfolio scores | Reuse complete causal windows and covariance estimators across books/policies | Homogeneous covariance and quadratic-form batches | Ledoit-Wolf until exact reproduction; SciPy SLSQP; portfolio drift/rebalance |
| Correlations, peers and spectra | Cache valid-node windows, correlations and peer products | Covariance precursors and symmetric eigenvalues | MST construction, signed edges/ties, residual OLS/AR and eligibility decisions |
| Context features | Group/cache prior-shifted per-ticker scales and relationships | No initial GPU adapter | Futures/equity units, clocks, filing coverage and source joins |
| Bootstrap comparisons | Generate reference CPU indices once, reuse matched loss vectors and block metadata | Indexed sample reductions | Dependence, block construction, cohort selection and statistical interpretation |
| Options/multi-market ridge | Reuse training-only preprocessing and sufficient statistics | Independent large compatible solve/prediction batches | Current intercept/regularization/solver/failure behavior and holdout controls |
| Registered parameter evaluations | Versioned DAG, immutable cache keys and resumable bounded chunks | Independent approved configurations in compatible batches | Registration/family caps, final-test closure and experiment policy |
| Producer and canonical consumers | Consume equivalent outputs through unchanged contracts | No GPU rewrite of producer/replay logic | Identities, provenance, availability, quarantine, market/account acceptance |

The current wording-only post-release equity pilot can proceed independently. Financial columns still require their existing clock/definition gates. Existing OCR/HiPerGator, text inference and broader training plans retain their owners and separate environments; a mathematical backend does not authorize new training, paid data, protected-test access or economic promotion.

Use float64 for inputs, accumulation and outputs. Preserve ddof/normalization, Ledoit-Wolf, regularization, intercepts, preprocessing order, solver behavior, missingness, node order, chronology, cutoffs, source revisions, masks and abstentions. No lower precision or altered covariance/graph/solver objective is part of the first implementation.

Continuous finite parity starts at `rtol=1e-10`, `atol=1e-12`, with existing stricter operation bounds authoritative. Identities, row keys, masks, eligible cohorts, graph topology/order, thresholds and policy decisions agree exactly. Nonfinite/insufficient states preserve the reference behavior. Tolerance cannot excuse a different decision.

## Ownership, dependency waves and shared API

| Lane | Owner | Exclusive responsibility |
|---|---|---|
| Shared backend, kernels and runtime evidence | Check remote desktop GPU access | Proposed backend/kernel/test/dependency/benchmark/runner files |
| Numerical adapters | Assess Lattice repo fit | Risk, graphs/residuals, multi-market features/evaluation, contextual caches and options-learning integration |
| Inference method | Research Sharpe confidence intervals | Dependence/block/method decisions; accepted-ledger Sharpe integration in its declared checkout |
| Canonical consumer | Post Benchmark | Registry/replay/account acceptance in its owned worktree |
| Financial/source producer | Benchmark | Definitions, source bytes, provenance, output coverage and financial clocks |
| Industry/market producer | Benchmark pt. 2 industry spec | Market/source quarantine, clocks, costs/actions and instrument identity |
| Packaging | Organize Benchmark Data Push | Optional package/runbook and separate shared-PR publication rules |
| Coordination | Track work across project chats | Shared ownership, prerequisites and remote scheduling |

Wave A: Task 0 read-only runtime feasibility, Task 2 CPU witnesses/caches, and Task 5/6 CPU preparation proceed independently. Wave B: Task 1 backend and Task 7 benchmark infrastructure proceed while owner CPU adapters are prepared. Wave C: Tasks 3-6 optional GPU integrations require Task 0 runtime success, Task 1 backend and the corresponding CPU witnesses. Wave D: Task 8 qualification then Task 9 consumer acceptance. One writer owns `src/math_kernels.py`; merge independent contributions through that owner. Tasks touching the same adapter file execute sequentially. The global heavy-job lock serializes all expensive execution.

Proposed `src/math_backend.py` selection and atomic execution interface:

```python
from dataclasses import dataclass
from typing import Callable, Literal, TypeVar

@dataclass(frozen=True)
class BackendSpec:
    requested: Literal['cpu', 'gpu', 'auto']
    selected: Literal['cpu', 'gpu']
    device: str | None
    dtype: str
    reason: str | None

class GpuCapabilityError(RuntimeError):
    pass

class GpuMemoryError(RuntimeError):
    pass

T = TypeVar('T')

def resolve_backend(mode='cpu', *, device=None, dtype='float64',
                    profile: dict | None = None) -> BackendSpec: ...
def batch_slices(n: int, *, bytes_per_row: int,
                 max_batch_bytes: int) -> list[tuple[int, int]]: ...
def execute_batch(operation: Callable[[BackendSpec], T],
                  selection: BackendSpec
                  ) -> tuple[T, BackendSpec, list[dict]]: ...
```

`BackendSpec` has exactly five fields. Runtime/library versions, profile hash, physical device identity and attempt details belong to the separate versioned Task 7 receipt. CPU selection does not import torch. Explicit `gpu` fails on unavailability/capability/memory failure. `auto` selects CPU before launch for a missing/stale qualification or unusable runtime.

An operation is a pure closure over immutable inputs, including pre-generated CPU indices. After a typed capability/OOM error in `auto`, `execute_batch` discards all uncommitted outputs of the entire logical batch and recomputes that entire batch once on CPU before any adapter publication/state update. It returns the actual final selection and every attempt. Previously completed separate batches retain their own receipts. A smaller device chunk may be attempted only while the entire logical batch remains unpublished; retain every failed attempt. Only known vendor capability/OOM errors map to the typed errors: invalid input, parity failure, nonfinite numerical divergence and arbitrary `RuntimeError` do not trigger recovery. Kernels do not hide fallback or publish partial results.

Proposed public `src/math_kernels.py` operations:

```python
def centered_covariance(windows, *, ddof, backend): ...
def quadratic_forms(weights, covariances, *, backend): ...
def symmetric_eigvalsh(matrices, *, backend): ...
def bootstrap_means(values, indices, *, backend, max_batch_bytes): ...
def ridge_solve(gram, cross, *, ridge, backend): ...
```

Public consumer outputs are NumPy arrays. Adapters own masks, dates, valid-node tuples and grouping; kernels receive homogeneous complete float64 batches, without valid-looking zero padding. A private compound batch keeps covariance/quadratic/eigen tensors device-resident until one materialization. Do not force a host transfer between every sub-kernel. Budget windows, matrices, indices, outputs and measured temporaries; never allocate an entire research sweep at once.

## Task 0 — establish runtime feasibility

**Owner:** GPU/runtime coordinator. **Files:** runtime appendix and a bounded remote preflight receipt; future `requirements-gpu-math.txt`. **Dependencies:** none for read-only inspection.

- [ ] Through Tailscale `home-pc`, record exact retail GPU/gfx target, dGPU identity, driver/kernel, ACL/effective device access, existing owner environments and active jobs. Distinguish dGPU PCI `0000:03:00.0`, `1002:7550`, subsystem `1458:2424`, about 15.92 GiB VRAM, from the small iGPU.
- [ ] Resolve the observed Ubuntu 24.04.4/kernel `7.0.0-30-generic` tuple against official AMD support before setup. The examined ROCm 7.14.1 Radeon matrix lists Ubuntu 24.04.4 HWE 6.17; observed kernel/device access are unresolved gates. Do not infer exact SKU from shared PCI ID.
- [ ] Check whether ACLs already permit access; reported SSH groups omit render/video. If a driver/kernel/group change is needed, coordinate affected owners/jobs before applying it. Keep CPU progress available.
- [ ] After supported tuple/access are proven, freeze a reviewed `runtime-selection.env` and isolated hashed dependency lock matching device, Python ABI and official wheel recipe. Keep CUDA OCR requirements separate; do not install competing array frameworks.
- [ ] Run one bounded FP64 HIP smoke under detached tmux/global lock; record `torch.version.hip`, selected physical dGPU, result, runtime versions, memory and exit status. A vector-add is access proof only, not speed/parity/financial acceptance.

Observed nodes `/dev/kfd` and renderD128/renderD129 plus bound amdgpu establish hardware detection only. No ROCm tools/runtime or system-Python torch/numpy were found; owner venvs remain to inspect. If the supported tuple/access cannot be established, publish a CPU-only feasibility result with the exact blocker.

## Task 1 — implement selection, bounded slicing and atomic execution

**Owner:** one shared-backend writer. **Create:** `src/math_backend.py`, `tests/test_math_backend.py`, `requirements-gpu-math.txt`. **Dependencies:** CPU witnesses and this frozen contract; actual GPU selection additionally requires Task 0.

- [ ] Write independent behavior tests first: CPU import without torch; invalid mode/dtype rejection; explicit unavailable GPU failure; deterministic missing/stale-profile auto CPU selection; dGPU identity and FP64 capability checks.
- [ ] Implement positive-byte bounded slices with exact coverage/no overlap; reject an unsplittable row exceeding budget rather than exceeding it. Account for operation-specific temporary/output storage in caller estimates.
- [ ] Implement pure-batch wrapper tests injecting capability and OOM errors after an intermediate device chunk. Require full discard/recompute, identical immutable inputs/RNG indices, no partial publication, actual selected backend and both attempts in receipt.
- [ ] Assert explicit GPU errors propagate; invalid input, numerical/parity failure and unrelated exceptions never become CPU recovery. Verify prior separate successful batches retain correct receipts.
- [ ] Implement lazy runtime imports and qualification invalidation keyed to code/runtime/device/input/config/dtype. Run `python -m unittest discover -s tests -p 'test_math_backend.py'` in a CPU-only environment.

## Task 2 — freeze CPU references and causal reuse

**Owner:** Lattice adapter owner, coordinating shared cache identity with backend owner. **Modify:** `src/lattice_strategies/risk.py`, `graphs.py`, `residuals.py`, `src/multi_market/features.py`, `src/contextual_lattice/context.py`; corresponding `tests/test_lattice_risk.py`, `test_lattice_graphs.py`, `test_lattice_residuals.py`, `test_multi_market_features.py`, `test_contextual_lattice_context.py`. **Dependencies:** existing CPU behavior; GPU setup is independent.

- [ ] Freeze small independent fixtures and current CPU outputs/statuses for complete, incomplete, constant, single-node, tied and ill-conditioned cases. Capture estimator normalization, thresholds, row keys and chronological eligibility.
- [ ] Reuse valid-window flags, centered arrays, covariances and estimator outputs across already registered policies/books/costs. Cache Ledoit-Wolf/tree estimates once per exact date/input/config rather than replacing their estimators. Keep SLSQP/state loops CPU.
- [ ] Group/copy reusable peer, OLS and AR fits only where formation/calibration windows, masks/node sets and current rank rules agree. OLS refusal and AR insufficiency remain observable; no ridge substitute.
- [ ] In `context.py`, cache/group prior-shifted per-ticker rolling scales and relationships after preserving information clocks, coverage and futures/equity units. Do not combine unlike units or shift the formation boundary.
- [ ] Keys include code/input/config hashes, cutoff/fold membership, asset order/masks, estimator, dtype, preprocessing and RNG recipe where relevant. Test stale keys, changed source revision/node order/fold/cutoff and no future leakage.
- [ ] Run relevant unittest discovery patterns above and benchmark a bounded current-versus-optimized CPU baseline. Preserve witnesses for later device parity.

## Task 3 — covariance, quadratic forms and estimator adapters

**Owner:** shared kernel writer plus Lattice risk adapter owner. **Create/modify:** `src/math_kernels.py`, `tests/test_math_kernels.py`, risk adapter/tests. **Dependencies:** Tasks 1/2; optional GPU branch requires Task 0.

- [ ] Implement CPU batch covariance with centered two-pass arithmetic and explicit ddof; preserve panel/subset eligibility outside the kernel. Bucket different T/N/node tuples separately.
- [ ] Use independent sample witness `X=[(1,3),(2,5),(3,7)]`: covariance `[[1,2],[2,4]]`; `w=(0.25,0.75)` gives `w.T @ C @ w = 3.0625`. Test constant/single-node/chunk/missing-boundary behavior and original masks.
- [ ] Batch quadratic forms over reused matrices and registered weights. Keep covariance estimator outputs/variance floors/QLIKE semantics identical; retain sklearn Ledoit-Wolf until an exact implementation has separate acceptance.
- [ ] Add optional float64 ROCm kernels and private compound execution only after CPU references pass. Transfer/materialize once per compound batch; enforce all host/device bounds and atomic wrapper.
- [ ] Run `python -m unittest discover -s tests -p 'test_math_kernels.py'` and the risk adapter pattern; GPU tests are explicit opt-in and CPU CI remains usable without torch.

## Task 4 — correlation, peer, eigenspectrum and contextual adapters

**Owner:** kernel writer and Lattice owner, one writer per adapter. **Modify:** kernel/tests, `src/multi_market/features.py`, `src/lattice_strategies/graphs.py`, `residuals.py`, `src/contextual_lattice/context.py` and Task 2 matching tests. **Dependencies:** Tasks 2/3; GPU branch also Task 0.

- [ ] Reuse same-eligible-node rolling covariance/correlation and vectorized peer products. Preserve prior-edge updates only for the existing identical-node condition.
- [ ] Implement bounded symmetric eigvalsh; independent witness `[[2,1],[1,2]]` has eigenvalues `[1,3]`. Check symmetry/nonfinite handling, ordering and single-node/constant cases.
- [ ] Keep MST/Kruskal signed-edge tie ordering, path products, OLS rank checks/AR state and sequential policy decisions on CPU. Changed topology or abstention fails parity even if continuous values are close.
- [ ] Complete CPU context-cache integration with future sentinels, missing first/middle/last/just-expired-window values, delayed-source clocks, filing coverage and cross-instrument unit cases against `test_contextual_lattice_context.py`.
- [ ] Run each relevant adapter's unittest discovery pattern; preserve exact keys/masks and compare continuous values under stated bounds before timing.

## Task 5 — deterministic paired/block bootstrap arithmetic

**Owner:** Lattice implementation with Sharpe methodology review. **Modify:** `src/lattice_strategies/evaluation.py`, `src/multi_market/evaluation.py` and their existing matching tests; shared kernel/tests via its writer. **Dependencies:** Tasks 1/2; GPU arithmetic additionally Task 0.

- [ ] Freeze reference CPU RNG indices, seed/sample count and matched losses. Retain Lattice circular date blocks separately from multi-market noncircular calendar/date blocks; never silently unify their topology.
- [ ] Implement `bootstrap_means` on supplied integer indices, preserving index/sample order under chunking. For values `[1,2,9]`, indices `[0,0,1]` give `4/3`, `[2,1,2]` give `20/3`; verify direct indexed means.
- [ ] Preserve existing count/defaults (including Lattice 500), quantiles, common strategy/baseline rows, dependence and insufficient/constant-series outputs. Test block wrap/boundaries, multiple issuers per calendar date, length/count/seed and chunk invariance.
- [ ] Optimize reductions only; loss intervals remain exploratory diagnostics. Future Sharpe integration waits for Post's accepted regular costed account returns and the inference owner's frozen method, in that owner's declared `src/research_validation/simulation.py` checkout/tests.
- [ ] Run focused evaluation and kernel discovery tests. No newly generated rows/configurations become independent economic observations.

## Task 6 — training-only ridge reuse and registered sweep DAG

**Owner:** Lattice/options owner with Post holdout review. **Modify:** `src/options_learning.py`, `src/multi_market/evaluation.py`, `tests/test_options_learning.py` and matching multi-market tests; `scripts/train_options_model.py` only if interface requires it. **Dependencies:** Tasks 1/2, Task 5 sequencing where the same evaluation file is owned; GPU additionally Task 0.

- [ ] Freeze existing train/test/embargo/fold membership, missingness, train-only means/scales, intercept, target scaling and ridge conventions. Reuse compatible training Gram/cross statistics across registered alphas/targets without merging unlike cohorts.
- [ ] Implement matching `ridge_solve`; witness `gram=diag(2,4)`, `cross=(6,10)`, `ridge=1` gives `(2,2)`. Preserve current solution/failure policy. QR/SVD is an independent diagnostic reference, not a silent production solver replacement.
- [ ] Test collinearity, near-zero positive ridge, constant-in-train indicators, missing/empty folds, future perturbations and well-conditioned reference cases. Conditioning diagnostics must not conceal a changed estimator.
- [ ] Build bounded checkpoint DAG keyed by exact inputs/code/config/fold/preprocessing/estimator/dtype/RNG. Resume only completed hash-verified chunks; invalidate changed dependencies, refuse partial/incompatible results and preserve configuration family caps.
- [ ] Run options/multi-market/kernel focused discovery tests before any registered fit. Protected final test remains closed; no additional training/sweep is inferred from benchmark registration.

## Task 7 — benchmark CLI, receipts and detached runner

**Owner:** shared benchmark/runtime writer. **Create:** `scripts/benchmark_gpu_math.py`, `tests/test_gpu_math_benchmark.py`, `hpc/run_gpu_math_job.sh`; small `configs/compute/` profiles; ignored remote receipt/output directories. **Dependencies:** Tasks 1 and CPU witnesses; staged alongside adapter preparation.

- [ ] CLI: `--backend cpu|gpu|auto --case covariance|features|bootstrap|ridge|registered --input-manifest --output-dir --batch-bytes --seed --warmups --repeats --dtype float64`. Refuse missing/unverified input/config hashes or unsupported cases rather than executing another recipe.
- [ ] Versioned run/batch receipts record code/input/config/profile hashes, cutoff/fold/masks/order, RNG recipe, exact runtime/framework/library versions, driver/kernel/physical device, requested/actual backend and all attempts/reasons, shapes/chunks, cold/warm timing, max absolute/relative error, exclusions, host/GPU memory and exit status. Hash-pin output files. Five-field BackendSpec stays unchanged.
- [ ] Validate immutable resume/chunk records and separate successful/failed attempts. Tests cover changed-hash invalidation, partial output refusal, invalid-input/parity propagation, CPU retry metadata, lock contention, timeout/memory non-success and no partial publication.
- [ ] Use Tailscale alias only, unique task/run tmux session and immutable remote code/input capsule. Inside the detached job acquire `/home/john-riley/.cache/quanthaxs-heavy-compute.lock`; no unlocked run on contention. Capture logs/exit receipt and poll rather than blocking foreground SSH.
- [ ] Enforce two CPU threads and 4 GiB host RAM through a verified user cgroup `MemoryMax=4G`; stop if enforcement cannot be established. Do not use `ulimit -v` as an RSS proxy for GPU virtual mappings. Initial GPU allocation ceiling is separately 4 GiB, with temporary headroom and selected-dGPU occupancy checks. Initial run timeout: 15 minutes.
- [ ] Keep bulk inputs/results remote; pull bounded hash-verified receipts. Clean only the completed task's own tmux session after successful collection. Use the reviewed runner recipe in the runtime appendix after its runtime-selection gate passes.
- [ ] Run `python -m unittest discover -s tests -p 'test_gpu_math_benchmark.py'` and shell validation of the new runner. A full suite/build, if required by the eventual shared PR, runs remotely under the same lock.

## Task 8 — qualify each workload and register routing profiles

**Owner:** GPU coordinator with Lattice numerical and Sharpe review. **Files:** benchmark receipts and small versioned `configs/compute/` profiles. **Dependencies:** relevant Tasks 0-7 gates, with CPU-only completion permitted if Task 0 is blocked.

- [ ] Compare current CPU, optimized CPU and optional explicit GPU using identical frozen synthetic representative shapes or already registered inputs. Record one small/one representative batch per family, resource estimates and actual input/config hashes; do not inspect protected test to choose thresholds.
- [ ] Run correctness before timing. Include input preparation/conversion, allocation/transfers, synchronization, reductions and NumPy materialization in end-to-end time. Separate cold first call from warmed repeats; record host cgroup peak and selected-dGPU memory separately.
- [ ] Proposed GPU promotion: at least 1.25x median end-to-end speedup over optimized CPU, repeated in two bounded runs, exact discrete parity, continuous bounds and compliant memory. This threshold is engineering policy only; no speedup is claimed in this plan.
- [ ] Register a passed profile only for its verified code/runtime/device/shape/input/config/dtype/estimator envelope. Invalidate changed dependencies/failed parity; no general auto GPU selection from hardware detection alone.
- [ ] For every family publish GPU-qualified, optimized-CPU-selected or blocked with concrete evidence/reason. Slower or unreliable GPU work stays CPU. Do not expand threads/RAM/VRAM or run concurrent heavy jobs to force a pass.

## Task 9 — canonical consumer, documentation and review

**Owner:** Post consumer, with producer/industry/packaging/coordinator input. **Files:** Post's declared worktree `src/research_validation/` and its existing tests; package/runbook docs via their owner. Root checkout paths are not assumed to be that consumer's files. **Dependencies:** relevant accepted parity/routing receipts.

- [ ] Consume optional accelerated math through unchanged identity/provenance/clocks/masks/definitions/source-version/quarantine and registry interfaces. Check exact statuses/row keys/outputs against CPU; never promote unknown clocks or invalid economic labels because compute ran.
- [ ] Keep producer responsibilities with Benchmark and industry. Preserve first wording-pilot/account recipe and protected-test controls; math acceptance alone establishes no forecasting value or after-cost result.
- [ ] Independent code review examines causal cache keys, float64/tie/solver parity, atomic retry/receipt accuracy, transfer-inclusive timing, limits and dependency isolation. Repair concrete findings and rerun affected gates before final review.
- [ ] Shared backend/pipeline/workflow changes use separate maintainer-reviewed PRs from clean exclusively owned `codex/` branches. Source-only merge permission does not cover these changes. Retain base/head, explicit-path staging, commands/results and exact tested-head receipts; no admin bypass or force-push of shared branches.
- [ ] Publish CPU fallback/runbook and qualification boundaries. Record delivery, acknowledgment, owner acceptance, implemented/merged code, measured acceleration and canonical/economic readiness separately.

## Completion evidence and handoff

Implementation is complete only when each scoped family has verified CPU optimization/reference behavior and a documented GPU/CPU decision, the optional dependency is isolated, bounded jobs produce verified receipts, independent review clears and relevant owners accept their consumers. A CPU-only decision is valid when supported by evidence. Unresolved access/kernel/runtime or data/economic gates remain explicit.

The parallel planning contributors completed numerical, inference/training and runtime appendices. All seven peer chats were notified; notification is not scheduling or consumer acceptance. Consult the linked delivery ledger for attempts and subsequent acknowledgments. No driver/runtime changes, benchmark or production backend implementation was performed by this planning chat.

Runtime primary references: [AMD ROCm 7.14.1 compatibility](https://rocm.docs.amd.com/en/docs-7.14.1/compatibility/compatibility-matrix.html), [AMD installation documentation](https://rocm.docs.amd.com/en/docs-7.14.1/install/rocm.html), [PyTorch HIP semantics](https://docs.pytorch.org/docs/stable/notes/hip.html). Recheck support at actual setup time.
