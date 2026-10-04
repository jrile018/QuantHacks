# Remote AMD GPU math runtime and benchmark plan

Status: planning only, 2026-10-04. Owner: Check remote desktop GPU access. The [master optimization plan](../../superpowers/plans/2026-10-04-remote-gpu-math-optimization.md) is authoritative for CLI, tolerances and promotion gates. No runtime install, driver change, GPU job, or benchmark has run under this plan.

## Decision and boundaries

- Target only `home-pc` over its Tailscale SSH alias. Keep large artifacts and all raw benchmark output on that host; return a bounded manifest and summary.
- Prefer one ROCm + PyTorch HIP backend after support is proven. Do not add CUDA-only dependencies or install several competing array frameworks for a feasibility pilot.
- Preserve the CPU implementation as the reference. GPU acceleration becomes optional only after numerical equivalence, reproducible device selection, and end-to-end speedup on a representative workload.
- Lattice owns numerical kernel choices and scientific acceptance; Post Benchmark owns canonical integration and active remote jobs. This plan changes neither owner’s contracts or active run.
- The first costed wording-only pilot and financial benchmark retain priority. GPU feasibility is not a prerequisite for either.

## Observed state and first failing boundary

The root coordinator’s read-only `home-pc` preflight found Ubuntu 24.04.4, kernel `7.0.0-30-generic`, an AMD dGPU at PCI `1002:7550` with subsystem `1458:2424` and about 15.92 GiB VRAM, and an AMD iGPU with about 0.5 GiB. `amdgpu` is loaded; `/dev/kfd` and render nodes exist. Exact retail GPU model and `gfx` target are **unknown**; a shared PCI ID is not a model proof. There is no `nvidia-smi`, `/opt/rocm*`, OpenCL vendor directory, or `clinfo` platform. System Python has no `torch`, `cupy`, `jax`, `numba`, or `numpy`. This is device detection, not a working compute runtime.

The login user is not in `render` or `video`; `/dev/kfd` and `renderD128`/`renderD129` were reported `crw-rw----` and group `render`. Effective ACL access must still be checked. Thus device access is the first unresolved layer. `tmux`, `flock`, `timeout`, and `systemd-run` exist. The shared heavy-job lock is `/home/john-riley/.cache/quanthaxs-heavy-compute.lock`; current host limits are two CPU threads and 4 GiB host RAM per heavy job. GPU VRAM is a separate budget, initially capped at 4 GiB in this pilot.

AMD’s [ROCm 7.14.1 compatibility matrix](https://rocm.docs.amd.com/en/docs-7.14.1/compatibility/compatibility-matrix.html) (dated 2026-09-02) lists Radeon RDNA 2/3/4 with Ubuntu 24.04.4 **HWE kernel 6.17**, and requires a matched GPU, driver, OS, firmware, and user-space stack. The observed `7.0.0-30-generic` kernel is not that documented tuple. The matrix lists PyTorch 2.10.0–2.12.0 in its ecosystem table, subject to the selected hardware configuration. The older [Radeon-specific 7.0.2 matrix](https://rocm.docs.amd.com/projects/radeon-ryzen/en/docs-7.0.2/docs/compatibility/compatibilityrad/native_linux/native_linux_compatibility.html) is specific to older Ubuntu point releases/kernels; do not carry its support claim forward. The exact SKU, `gfx` target, loaded driver version and current support combination must be checked against the current selector before any install.

## Stage 1 — identity, access, and supported tuple (read only)

Run these on `home-pc` and retain unredacted output in a remote, timestamped probe directory. Commands are proposed; the root coordinator is handling any present SSH probes.

```bash
date -u +%FT%TZ
hostnamectl; uname -a; cat /etc/os-release
lspci -Dnnk | grep -A5 -Ei 'VGA|Display|3D'
for x in /sys/class/drm/card*/device; do
  printf '%s ' "$x"; readlink -f "$x"
  for n in vendor device subsystem_vendor subsystem_device; do printf '%s=' "$n"; cat "$x/$n"; done
done
modinfo amdgpu | grep -E '^(filename|version|vermagic):'
cat /proc/driver/amdgpu/version 2>/dev/null || true
id; getfacl -p /dev/kfd /dev/dri/renderD* 2>/dev/null
python3 - <<'PY'
import os, glob
for p in ['/dev/kfd', *glob.glob('/dev/dri/renderD*')]:
    print(p, 'read=', os.access(p, os.R_OK), 'write=', os.access(p, os.W_OK))
PY
df -h /home/john-riley; free -h
cat /sys/fs/cgroup/cgroup.controllers 2>/dev/null
systemctl --user show -p ControlGroup -p Delegate 2>/dev/null
```

Use `lspci` subsystem/VBIOS or vendor hardware inventory to establish the exact board; map it to AMD’s selected GPU and `gfx` target. If model remains ambiguous, record it as unknown and stop. Check that the effective user can read/write `/dev/kfd` and the dGPU render node. If access fails, arrange a user/group/ACL change with the host owner, then start a **new login session** and repeat the access check. Do not run privileged compute or loosen device-node permissions globally. Confirm that the user cgroup can enforce `MemoryMax=4G` with a harmless bounded probe before any GPU job.

The selected GPU, `gfx`, Ubuntu point release, running kernel, driver, Python and PyTorch/ROCm versions must appear together in a current official support path. A matrix mismatch is a stop gate. Discuss any kernel or driver change with Post and other remote-job owners, identify active `tmux` processes first, schedule downtime, and define rollback to the prior boot/kernel/driver. Never reload `amdgpu`, reboot, or replace its driver while another job is running.

## Stage 2 — isolated user-space setup, only after Stage 1 passes

AMD’s [7.14.1 install guide](https://rocm.docs.amd.com/en/docs-7.14.1/install/rocm.html) offers GPU-architecture-specific Python ROCm packages and separates the kernel driver from user-space installation. The [PyTorch HIP guide](https://docs.pytorch.org/docs/stable/notes/hip.html) confirms that HIP builds use `torch.cuda` APIs and that `torch.version.hip` distinguishes them from CUDA builds. Select one *versioned*, supported ROCm/PyTorch recipe for the confirmed `gfx` target and Python ABI from the AMD matrix and install page. Save the exact URL and wheel hashes before installing. No system Python modification.

Proposed user-space layout after support confirmation:

```bash
run_root=/home/john-riley/QuantHacks/gpu-math-20261004
selection="$run_root/runtime-selection.env"
test -s "$selection"
set -a; source "$selection"; set +a
: "${ROCM_VERSION:?verified ROCm version required}"
: "${GFX_TARGET:?verified dGPU target required}"
: "${PYTHON_ABI:?verified Python ABI required}"
mkdir -p "$run_root/envs" "$run_root/runs" "$run_root/wheels"
"python${PYTHON_ABI}" -m venv "$run_root/envs/rocm-${ROCM_VERSION}-${GFX_TARGET}"
py="$run_root/envs/rocm-${ROCM_VERSION}-${GFX_TARGET}/bin/python"
"$py" -m pip install --require-hashes -r "$run_root/requirements-rocm.lock"
"$py" -m pip freeze --all > "$run_root/environment.freeze.txt"
"$py" -m pip inspect > "$run_root/environment.inspect.json"
sha256sum "$run_root/requirements-rocm.lock" "$run_root"/wheels/* > "$run_root/wheel-sha256.txt"
```

`runtime-selection.env` is a reviewed Stage 1 receipt containing the verified version, `gfx` target, Python ABI, official matrix/install URLs, driver/kernel tuple and selection rationale. The unresolved host tuple prevents creating this receipt today. Generate `requirements-rocm.lock` as a Stage 2 deliverable from the verified vendor wheel URLs and their SHA-256 values; include only the minimum runtime, `torch`, and benchmark dependencies. If AMD’s 7.14.1 architecture-specific Python package path is the selected supported recipe, use its matching device extra and approved PyTorch build, with no version mixing. Avoid `sudo`, apt repository changes, Docker privileges, or driver packages for this isolated attempt.

Rollback for the user-space attempt: keep frozen manifests, stop only this pilot’s job, then remove only its owned selected environment and wheel cache after result checks. Do not remove shared ROCm, Python, driver, or another owner’s files. A required host driver/kernel change is a separate maintenance decision with a prior-version boot and package rollback plan.

## Stage 3 — minimum live HIP proof

In a fresh login, run the selected environment’s Python under the shared lock. Verify `torch.version.hip`, `torch.cuda.is_available()`, `torch.cuda.device_count()`, device name, properties, memory and a small `float32` vector add with `torch.cuda.synchronize()`. Record all outputs and failures. A package import alone is insufficient. Enumerate every HIP device and map each runtime index to sysfs PCI bus and, when provided, UUID. Identify the dGPU by the *confirmed PCI bus/UUID*, not by assuming `cuda:0`. If HIP and sysfs identifiers cannot be mapped confidently, stop before measurement. Do not use an architecture spoof such as `HSA_OVERRIDE_GFX_VERSION` to turn an unsupported device into a supported claim.

Run a separate FP64 gate: compare a deterministic `float64` reduction and 128×128 matrix product against a CPU high-precision reference; record numerical error and synchronized wall time. Confirm operations execute on the chosen dGPU rather than silently on CPU. FP64 functional support alone does not imply useful throughput. If absent, unstable, or slower after transfer at relevant sizes, exclude GPU from double-precision research math and keep that path on CPU.

## Stage 4 — bounded benchmark protocol

Use two levels of workload, selected with the Lattice numerical owner before coding:

1. **Small first kernel:** deterministic `float64` elementwise add and sum, sizes `2^12`, `2^18`, and `2^22`; fixed seed and generated host arrays. A separate `float32` smoke check may help diagnose the runtime but cannot qualify research math. This reveals launch and transfer overhead and exercises the FP64 gate.
2. **Representative kernel:** one actual project math path, initially `covariance` at a frozen real-shape fixture with synthetic values. The owner specifies axis semantics, precision, missing-value behavior, and exact CPU reference before GPU work. No market fit, simulation campaign, or retraining.

For each size and dtype, record CPU single-run wall time, GPU cold first call, five warm-ups, 20 synchronized repeats, median and p95. Count host-to-device transfer, kernel, device-to-host transfer, and full caller-visible wall time separately. Synchronize before and after timed GPU regions; include allocation and output materialization in end-to-end time. Repeat on one process with stable device mapping and disclose concurrent GPU use. Compare GPU end-to-end latency to the existing two-thread CPU reference, and report speedup as CPU median / GPU median with an interval or range across independent batches; never use kernel-only timing as the adoption number.

Use the master plan's first-version `float64` continuous gate, `rtol=1e-10` and `atol=1e-12`, unless an existing operation has a stricter bound; discrete decisions and bookkeeping must agree exactly. Record `max_abs`, `max_rel`, nonfinite count, shape/order, and distribution of error. Avoid treating a single `allclose=True` as proof. Reduction order may differ; inspect tail error and decision-boundary examples. Recheck deterministic input hashes, output hashes, and version/seed before comparing. A NaN, silent precision downgrade, indexing mismatch, or fallback to iGPU fails the gate.

The master plan's promotion gate is at least **1.25× median end-to-end speedup** versus optimized CPU in **two bounded runs**, with no violated numerical gate. Report p95 as a useful tail-risk measure, including any regression; the owner decides whether it precludes adoption. Tiny arrays may be slower on GPU and are retained as negative evidence. GPU memory use must remain below the 4 GiB pilot cap and leave capacity for active owners.

## Detached execution and receipt contract (proposed)

Stage a small immutable source/config bundle, its SHA-256 manifest and a literal runner script in a unique remote run directory. Hash the actual code and input capsule bytes, not merely the repository's possibly dirty `HEAD`. The runner must log `started_utc`, hostname, `uname -r`, Git/source hash, input hash, wheel/lock hash, selected PCI bus/UUID/runtime index, session name, PID, CPU/RAM/VRAM caps, command, phase timings, peak memory, completion timestamp and actual exit code. If a launch, lock acquisition, or timeout fails, retain a failure receipt. Separate raw CSV/JSON from the bounded summary.

Example launch shape; create the literal `run-gpu-math.sh` first and review it before using these commands:

```bash
run_root=/home/john-riley/QuantHacks/gpu-math-20261004
run_id="$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"
run_dir="$run_root/runs/$run_id"
session="quanthaxs-gpu-math-$run_id"
ssh home-pc "tmux new-session -d -s '$session' \"bash '$run_dir/run-gpu-math.sh' '$run_dir'\""
ssh home-pc "tmux has-session -t '$session' 2>/dev/null && echo RUNNING || echo DONE"
ssh home-pc "tail -n 40 '$run_dir/run.log'"
```

Runner skeleton, with lock **inside** the detached job so it covers probing, benchmarking, and receipts:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
run_dir=${1:?run directory required}
exec >"$run_dir/run.log" 2>&1
finish() { status=$?; printf 'EXIT_CODE:%s\n' "$status" >>"$run_dir/exit.txt"; date -u +%FT%TZ >>"$run_dir/exit.txt"; }
trap finish EXIT
printf 'SESSION=%s PID=%s START=%s\n' "${TMUX:-unknown}" "$$" "$(date -u +%FT%TZ)" >"$run_dir/receipt.txt"
exec 9>/home/john-riley/.cache/quanthaxs-heavy-compute.lock
flock -n 9 || { echo 'LOCK_BUSY: shared heavy job is active'; exit 75; }
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
# Enforce a 4 GiB host-memory cgroup; record the cgroup memory peak.
# Monitor chosen dGPU VRAM and abort allocation before the 4 GiB pilot ceiling.
py=$(<"$run_dir/python-path.txt")
test -x "$py"
systemd-run --user --scope -p MemoryMax=4G \
  timeout --signal=TERM --kill-after=30s 15m "$py" "$run_dir/scripts/benchmark_gpu_math.py" \
  --backend gpu --case covariance --input-manifest "$run_dir/input-manifest.json" \
  --output-dir "$run_dir/gpu-results" --batch-bytes 134217728 --seed 7301 \
  --warmups 5 --repeats 20
```

The benchmark program and its exact CLI are specified in the [master plan](../../superpowers/plans/2026-10-04-remote-gpu-math-optimization.md). Stage it in the immutable code capsule before invoking this runner; the snippet is a proposed future command, not evidence that the file or environment exists today. Use the same input manifest, `covariance` case, seed, batch size, warm-ups and repeats for the optimized CPU invocation, changing only `--backend cpu` and `--output-dir "$run_dir/cpu-results"`. `--backend auto` is an application fallback check, not a replacement for explicit CPU/GPU comparison. Keep the smoke vector-add separate from the registered benchmark CLI.

The input manifest should identify each array's shape, dtype, ordering, generator seed and byte hash. Capture the CPU and GPU output manifests separately. Compare output arrays and decisions before calculating speedup. Run the bounded matched comparison twice with distinct run IDs and identical frozen code/data capsules. Store both successful and failed attempts; never overwrite a run directory. If a third run is needed because of interference or thermal behavior, state why and retain all runs rather than picking the best one.

For observability, sample device memory and host cgroup peak during each run, and note GPU clocks/temperature if a supported tool exposes them. Missing telemetry is marked unknown; the 4 GiB VRAM cap still requires a preallocation bound from the benchmark code. Record whether another non-QuantHaxs process occupied the dGPU. If the device is already busy, defer the benchmark instead of interpreting the timing as capacity proof.

Before launch, verify that the user cgroup actually accepts and enforces `MemoryMax=4G`; stop if it does not. Do not use `ulimit -v 4194304` as an RSS cap: ROCm virtual mappings can be much larger than resident host memory. Bound CPU threads to two, timeout to 15 minutes, and VRAM allocations to 4 GiB. Check other owner jobs and GPU occupancy before launch; the shared lock serializes QuantHaxs heavy jobs but does not reserve the GPU against outside processes. A busy lock produces an explicit non-success receipt and a later retry, never an unlocked run. Cancel only this session on failure. Once output checks and bounded retrieval pass, remove only this completed `tmux` session.

## Acceptance, publication, and stop conditions

- Publish a compact result manifest with run ID, exact command, Git commit, environment/driver/kernel/GPU mapping, SHA-256 of inputs/output, selected precision, per-case timing and errors, CPU/GPU device memory, failed cases, and verdict per gate. Preserve raw output remotely and return only bounded summaries due to local disk pressure.
- If permissions, `gfx` identity, matrix support, runtime device mapping, kernel execution, numerical equivalence, host/VRAM bound, or end-to-end speedup fails, record the first failing layer and smallest next probe. Do not promote a partially passing result.
- A successful benchmark permits a narrow implementation proposal to Lattice and Post. It does not change accepted source/evaluation contracts, qualify a trading feature, authorize a full Monte Carlo campaign, or establish financial/backtest readiness.

## Source and local contract references

- AMD [ROCm 7.14.1 compatibility matrix](https://rocm.docs.amd.com/en/docs-7.14.1/compatibility/compatibility-matrix.html), 2026-09-02; [installation guide](https://rocm.docs.amd.com/en/docs-7.14.1/install/rocm.html).
- PyTorch [HIP semantics and verification](https://docs.pytorch.org/docs/stable/notes/hip.html) and [local install selector](https://pytorch.org/get-started/locally/).
- Local [shared resource contract](../../coordination/objects/handoffs-and-resources.md), [skills/remote rule](../../coordination/skills-usage.md), [Lattice owner packet](../../coordination/handoffs/lattice.md), and [remote heavy-job runner precedent](../../../hpc/lattice_strategies/audit_math.sh).
