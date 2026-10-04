# Remote GPU and math optimization design

Owner: Check remote desktop GPU access. Date: 2026-10-04, America/New_York.
Status: design and implementation-planning deliverable; production optimization and GPU compute acceptance are pending.

## Intended outcome

The human requested optimization of the previously identified numerical workloads, an implementation plan covering all of them, parallel work, and notification of the other project agents. Improve total workload throughput while preserving the current numerical objectives, causal information boundaries, and consumer contracts. Optimize CPU execution as well as GPU execution; a workload can complete this design successfully with a faster CPU path when the GPU is unsuitable.

This design extends the existing owner plans. It does not replace Post Benchmark's root task_plan.md/progress.md or the shared coordination register. The first wording-only post-release equity pilot remains independent of optional GPU conversion; the financial benchmark remains its subsequent arm.

## Observed hardware and environment

Read-only SSH probes in this chat, through the authorized home-pc alias, established:

| Boundary | Observed evidence | Conclusion |
|---|---|---|
| Host | john-riley-X870-GAMING-WIFI6; Ubuntu 24.04.4 LTS | SSH host access works |
| Kernel | 7.0.0-30-generic | Match this exact kernel against current official runtime support before installation |
| Discrete GPU | PCI 0000:03:00.0; AMD 1002:7550; subsystem 1458:2424; amdgpu bound | AMD hardware and kernel driver detected; exact retail model remains unconfirmed |
| Discrete VRAM | 17,095,983,104 bytes, approximately 15.92 GiB | Separate GPU memory budget from the host RAM limit |
| Integrated GPU | AMD 1002:13c0, 536,870,912 bytes | Do not accidentally select this device for benchmarks |
| Kernel compute interface | /dev/kfd exists; renderD128/renderD129 exist | Compute device nodes exist; successful access still requires a probe |
| Permissions | Device nodes group render, mode crw-rw----; SSH user's reported groups omit render/video | Check ACLs and actual access; do not claim permission from detection |
| User-space runtime | No /opt/rocm* found; no rocminfo/amd-smi/rocm-smi in PATH; no OpenCL vendor directory/platforms | ROCm/OpenCL readiness was not established |
| Python | System Python cannot find torch, cupy, jax, numba or numpy | Inspect owner virtual environments before deciding what must be installed |
| Job controls | tmux, flock, timeout, systemd-run available | Existing detached-job architecture can be reused |

Absence of nvidia-smi is expected evidence of an unavailable NVIDIA tool, not a test of AMD compute capability. Marketing model, currently supported runtime/kernel combination, device access, a successful FP64 kernel, numerical equivalence and useful acceleration are distinct unresolved gates.

## Chosen approach and alternatives

Choose CPU-first numerical reuse with a single optional ROCm/PyTorch backend for eligible pure kernels. Keep NumPy/pandas/scikit-learn/SciPy consumers and their defaults intact. Cache expensive immutable intermediates, vectorize repeated work, and use bounded batches; then measure whether the GPU improves representative workloads.

Alternative 1 is CPU-only optimization: lowest setup risk and a valid final route for small or precision-sensitive work. Alternative 2 is a broad GPU rewrite, multiple array frameworks or immediate custom Triton kernels: more maintenance, dependency and numerical risk before a bottleneck has been measured. Defer that expansion until the simple backend has passed useful-workload gates.

ROCm/PyTorch is a candidate, not an installed capability. Existing CUDA-oriented OCR/HiPerGator dependencies remain a separate environment. An isolated user-space environment is preferred where the current supported kernel/driver/device permissions permit it. Driver, kernel or group changes must be coordinated with affected owners and active jobs; incompatibility leaves the CPU path operational.

## Numerical scope

| Workload | Initial optimization | GPU boundary | Existing owner |
|---|---|---|---|
| Risk covariance, shrinkage and portfolio scores | Reuse causal windows/centered arrays and covariance estimates across books and estimators | Batch same-shape covariance and quadratic forms; require exact shrinkage semantics | Assess Lattice repo fit |
| Rolling correlations, peer features, symmetric eigenspectra | Reuse masks/windows/correlations; vectorize peer products | Batch only groups sharing shape and the correct eligible-node ordering | Assess Lattice repo fit |
| Bootstrap forecast/risk comparison intervals | Reuse matched losses, deterministic CPU index draws and block metadata | Batched sample reductions with identical indices; final inference rules remain owner-defined | Lattice implementation, Sharpe methodology |
| Options ridge fits and predictions | Reuse training-only preprocessing and per-fold sufficient statistics across already registered configurations/targets | Large independent solve/prediction batches after conditioning checks | Lattice implementation; Post consumer acceptance |
| Repeated parameter evaluations | Cache a versioned computation DAG, bounded chunks and resumable receipts | Parallel independent configurations under the same frozen experiment protocol | Existing numerical/research owner |
| Canonical producer/replay workflows | Accept accelerated outputs only through unchanged provenance and masks | No GPU rewrite of clocks, joins, source quarantine or cash-ledger control flow | Benchmark / industry / Post |

Keep sequential rebalance/drift/quarantine logic, deterministic graph construction, SciPy SLSQP, small standalone solves, network collection, source parsing and registry acceptance on CPU unless a later distinct measured bottleneck warrants a reviewed change.

## Shared implementation boundary

Proposed files, not current implementation:

- src/math_backend.py: lazy optional runtime selection, CPU/GPU/auto policy, capability receipts and physical device identity.
- src/math_kernels.py: pure bounded array kernels; host NumPy output at consumer boundaries; no feature, clock or trading policy.
- requirements-gpu-math.txt: optional dependency instructions pinned to the successfully verified runtime/framework environment; separate from requirements-gpu-ocr.txt.
- scripts/benchmark_gpu_math.py: bounded synthetic/registered-workload timing, parity and memory receipts.
- tests/test_math_backend.py and tests/test_math_kernels.py: selection, chunking and independent numerical reference checks.
- hpc/run_gpu_math_job.sh: detached-job payload with shared flock, thread/memory/timeout controls and exit receipts.

One coordinator-owned backend is reused by owner-maintained adapters. Backend choice defaults to cpu. Explicit gpu fails clearly if unavailable or incapable. Auto may choose CPU before launch for a missing/stale qualification or unavailable runtime. After a typed capability/device-memory failure, the atomic execution wrapper discards every uncommitted output of the entire logical pure-kernel batch and retries that entire batch on CPU with identical immutable inputs and CPU-generated sampled indices, before adapter publication or state updates. It returns the actual final selection and a per-attempt receipt; prior successful separate batches retain their own backend receipts. Invalid input, failed parity or numerical divergence fails/quarantines under the existing owner policy and cannot be concealed by this retry. Auto GPU routing requires a versioned passed workload profile, not merely device detection.

BackendSpec is the five-field selection object in Task 1. Runtime/framework/library versions, qualification profile hash, physical device identity and per-attempt status belong to the separate versioned run/batch receipt owned by Task 7; they are not undeclared fields added to BackendSpec.

## Preserved mathematics and information

Start with float64 inputs, accumulation and outputs for the existing numerical workloads. Preserve estimator-specific ddof/normalization, Ledoit-Wolf shrinkage, regularization, intercept handling, order of preprocessing, threshold/tie rules and numerical solver behavior. Do not replace a covariance estimator with an approximate one or alter graph topology to obtain speed. Do not introduce lower precision without a separate comparison and owner acceptance.

Missingness, validity masks, asset order, expanding/rolling endpoints, strict/as-of cutoff comparators, publication/version evidence, quarantine and matched comparison denominators survive all batching. Cache keys include exact input/code/config versions, masks/node order, cutoff/fold membership, estimator and dtype. Training data transformations and sufficient statistics belong to the training fold only.

Generate bootstrap indices through the existing CPU reference RNG sequence. Reuse those same indices for CPU/GPU comparisons and chunked runs. Dependence is determined by events/sessions and the accepted ledger, not by the number of resampled or configuration rows. Constant/empty/insufficient series retain their current undefined or insufficient states.

## Resource and acceptance contract

- Heavy jobs use home-pc through Tailscale, detached tmux, the shared /home/john-riley/.cache/quanthaxs-heavy-compute.lock, unique owner/run directories, logs and explicit exit status.
- Retain the current two CPU thread and 4 GiB host RAM bounds. Initially cap this pilot's VRAM allocation at 4 GiB, independently of host RAM and currently free VRAM, with headroom and chunking; a 16 GB card does not authorize 16 GB of host allocations.
- Parallelize planning, review and independent file work. The shared heavy-job lock serializes expensive remote execution. Keep bulk inputs/results remote and retrieve bounded hash-verified receipts.
- Compare current CPU, optimized CPU and optional GPU on the same immutable inputs and configuration; include conversion, transfers, synchronization, reduction and materialization in total runtime.
- Pin eligibility/masks/identities exactly. For continuous FP64 outputs, start with rtol=1e-10 and atol=1e-12 where existing semantics permit; report maximum errors and conditioning. Existing stricter constraints remain authoritative. No threshold/graph/order/eligibility change is waived by allclose.
- A proposed promotion rule is at least 1.25x median end-to-end speedup over optimized CPU on a representative registered batch, repeatable across two bounded runs, with equivalent outputs and memory within bounds. This is an engineering rule, not a claimed measurement or economic hurdle.
- Insufficient speed or FP64/runtime support keeps that workload on optimized CPU and records the result. A successful kernel or faster diagnostic never establishes accepted features, net profit or a canonical economic replay.

## Ownership and review

Check remote desktop GPU access owns hardware/runtime evidence, the proposed shared backend/benchmark boundary and this plan. Assess Lattice repo fit owns numerical adapter changes. Research Sharpe confidence intervals owns dependence-aware inference choices. Post Benchmark owns registry, canonical replay and consumer acceptance. Benchmark and industry preserve their producer/source/market contracts. Organize Benchmark Data Push owns packaging/publication policy. Track work across project chats reconciles shared ownership and scheduling.

Use one writer per source file and clean exclusively owned branches at implementation time. Backend/pipeline/workflow changes belong to separate maintainer-reviewed PRs; source-only auto-merge permission does not cover them. Delivery, acknowledgment, acceptance, consumed output, merged code and measured speedup are recorded separately.

## Linked implementation plan

Execute the tasks and parallel dependency schedule in [the implementation plan](../plans/2026-10-04-remote-gpu-math-optimization.md). The numerical, inference/training and runtime appendices provide the source-specific details. The delivery ledger records exactly which project chats were notified.
