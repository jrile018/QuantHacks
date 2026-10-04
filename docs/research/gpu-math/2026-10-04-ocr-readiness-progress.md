# Desktop OCR readiness checkpoint

Owner: Check remote desktop GPU access. Date: 2026-10-04, America/New_York.

## Goal and bounded scope

Support the first Post-owned wording-equity backtest by establishing desktop GPU access and checking whether its exact retained source documents require OCR. This lane preserves Benchmark scoring, Industry sources/clocks/market qualification and Post canonical replay ownership. It does not start the ten-task [GPU math implementation plan](../../superpowers/plans/2026-10-04-remote-gpu-math-optimization.md).

The direct human authorization was verified by reading the actual user message in Organize Benchmark Data Push: message `01a10613-7192-7c52-82a5-7e8aa7b8779c`, turn `01a10613-693c-7ba1-bfb5-63a88a66bffa`. Needed desktop GPU/OCR and parallel completion were authorized. Device-group/ACL/kernel/driver changes remain subject to their separate concrete approval; none were made here.

## Named checkpoints

| Checkpoint | State | Evidence |
|---|---|---|
| 1. Verify authorized scope and source owners | Complete | Actual human message read; scoped Benchmark/Industry requests accepted |
| 2. Prove current first hardware/access boundary | Complete; GPU access blocked | Successful render-node opens; `/dev/kfd` O_RDWR fails EACCES13 |
| 3. Check exact retained native source bindings | Complete | Two raw and two native-text hashes match; HTML sniff and nonempty UTF-8 checks pass |
| 4. Decide whether an actual OCR job is justified | Complete for current named inputs | Both releases already have native text; no failed-native PDF/image has been supplied |
| 5. Verify existing interfaces and deliver compact report | Complete | Parallel read-only interface check, collected hash-matched receipts and scoped owner handoff |

Bounded checkpoint completion is 5/5. GPU runtime and economic readiness remain separate, unaccepted gates. This supporting report is local/unpublished, with no claimed total-project percentage or estimated implementation completion time.

## Verified device and resource evidence

At 04:46:53 local / 08:46:53 UTC, `home-pc` through Tailscale resolved to `john-riley-X870-GAMING-WIFI6`, kernel `7.0.0-30-generic`. Discrete GPU PCI identity is AMD `1002:7550`, subsystem `1458:2424`, bound to amdgpu, with 17,095,983,104 bytes VRAM. Exact retail SKU/gfx and supported runtime tuple remain unproven.

The SSH user is `john-riley`, uid1000. Group `render` is GID992; `/dev/kfd` is mode660 root:render and the user lacks group992 and a user ACL. Python `os.open(..., O_RDWR|O_CLOEXEC)` fails with errno13/Permission denied. Both renderD128 and renderD129 open successfully through their per-user ACLs. Their accessibility does not grant KFD access.

At 04:49:44 local / 08:49:44 UTC, `sudo -n -l` was unavailable/password-required. No interactive password was requested. User-space package installation cannot fix this access boundary. `rocminfo`, `amd-smi`, `rocm-smi`, system-Python torch and OCR engines were not available in the probed environment. Native `pdftotext` exists. No GPU kernel, OCR model, runtime install or host change was performed.

The first 08:46:02 UTC read-only snapshot listed `qh-lattice-completion-v2-20261004`; the subsequent 08:46:53 UTC snapshot listed no tmux sessions or QuantHaxs lock holder. These are point-in-time observations, not a reservation. No owner job/session was stopped or restarted. This lane reserved no GPU/CPU heavy slot; its small read/hash probes were not heavy compute. Future necessary heavy work must use detached tmux, the shared `/home/john-riley/.cache/quanthaxs-heavy-compute.lock`, two CPU threads and enforced 4GiB host RAM, retaining bulk remotely.

## Current native source decision

The [Industry source handoff](../../reit-2024-pilot-source-handoff.md) provides the two retained SEC HTML releases, their native text and source/provenance bindings. This lane independently read and hashed those exact remote bytes, without downloading originals or rerunning scoring/extraction.

| AMT accession | Raw SHA256 | Native-text SHA256 | Native characters / bytes |
|---|---|---|---|
| 0001053507-24-000009, February27 | d3e0d2b13d9b4ff50cb104362855975b96dfc354804343f5bdfe1a9c842c3a62 | 281856042cd75a0d40c79a76679a679d5c4a6e11cf2d1cdb51679c5e46e9cdb5 | 73,521 / 75,159 |
| 0001053507-24-000128, October29 | 277d4f5aba88de6a0d7a52476fa39ad37de581d5d2a46ef06faf60d44e6e6789 | 9f2ccab518018fc703d929ce22dd272905c93941bc6ab9af8f358f171c5baf81 | 74,179 / 75,318 |

Each input was bounded below2MiB, sniffed as HTML, hash-matched and its native text decoded as nonempty UTF-8. This proves native-text availability/bindings. It is not a semantic gold audit, original-page OCR benchmark, model completeness check, historical public-clock qualification or economic acceptance. OCR confidence is null because no OCR ran.

No actual OCR task is justified by these currently named inputs. Benchmark can continue its existing native-text scoring lane independently of GPU permissions. If an exact necessary retained image/PDF later fails native extraction, its source owner supplies raw path/hash and page set, followed by a separately bounded qualified OCR decision. No unrelated data expansion is part of this checkpoint.

## Exact compact receipts

- [Collected preflight receipt](../../../data/processed/gpu_ocr_readiness/20261004/preflight.json), SHA256 `3b5aaa811cca65724de2cc43dbb04984eb7f9e03c09b3e7bd0878891da1f56aa`.
- [Collected native-text receipt](../../../data/processed/gpu_ocr_readiness/20261004/native-text-check.json), SHA256 `2663f0a068e386944190591baa17d0b4efda12b10fb54765d4dfb1cac50c7ddd`.
- Remote receipts remain at `/home/john-riley/.cache/quanthaxs-gpu-ocr-readiness-20261004-01a105bb/{preflight.json,native-text-check.json}`. Collection hashes matched remote receipts; originals/native text remain in Industry's `/tmp/quanthaxs-reit-pilot-repair-20261004-v1/source-pack`.
- Preflight command used Python stdlib `os.open`/`os.access`, sysfs identity, executable discovery and read-only tmux/lslocks snapshots. The initial shell wrapper reported exit1 from CRLF/absent remote `rg`; its successful device-open evidence was repeated in the corrected recorded exit0 probe. Native availability used direct `hashlib.sha256`, bounded reads and existing text decoding; exit0. No OCR job/result receipt exists.

These are local, unpublished supporting artifacts. No implementation PR/merge, new paid request, protected-final-test access, capital deployment, new model fit or accepted economic result was produced by this lane.

## Existing interface check

The parallel read-only explorer found the existing batch interface in `scripts/run_document_batch.py:179`: `python scripts/run_document_batch.py --manifest <existing-JSONL> --output-dir <owned-output-directory> --engine native`. This is a reusable existing interface, not a new invocation performed by this lane. `src/document_transcript.py:190` exposes `extract_path(path, document_id, source_sha256=None)` and handles HTML/text natively. Images require an explicit OCR engine; batch-native PDF processing refuses pages needing OCR rather than silently reporting native success.

`src/document_ocr.py:71` uses pypdfium2 text-layer checks with scan/hybrid guards. Native PDF pages retain `native_text_completeness_unverified`; native availability alone does not establish semantic/layout/table completeness. Tesseract is a CPU fallback, not GPU proof.

The existing GLM provider in `src/glm_document_ocr.py:27` uses CUDA-style device names and `torch.cuda` checks; `requirements-gpu-ocr.txt` documents the allocated CUDA deployment. AMD/ROCm execution has not been verified. CUDA API spelling is not itself proof of incompatibility: PyTorch HIP uses the same CUDA namespace, with `torch.version.hip` distinguishing the runtime ([official PyTorch HIP semantics](https://docs.pytorch.org/docs/2.14/notes/hip.html)). A future actual AMD OCR task requires supported runtime/access, an explicit model/device proof and source/page/span validation before claiming GPU success. No framework rewrite or new OCR training is justified by the present native sources.

## Next boundary and readiness

GPU readiness remains blocked at `/dev/kfd` access; exact runtime/support/SKU proof is a later distinct gate. Organize Benchmark Data Push owns the pending human access decision and will send verified approval/state if it changes. This lane does not change permissions or bypass sudo while pending.

The minimal pilot's actual dependencies remain source historical availability, the Benchmark frozen loaded-model/complete aggregate, Industry accepted execution/short-cost/action inputs and Post accepted account replay. Native text availability is useful support; neither OCR nor GPU installation repairs those evidence gates. The report and current compact receipts support the no-OCR-required decision for the currently retained pair, with no production restart merely to count progress. Reopen this bounded lane when a named necessary failed-native input or verified access state changes.
