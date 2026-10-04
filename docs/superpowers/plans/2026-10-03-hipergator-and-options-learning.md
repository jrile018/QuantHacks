# HiPerGator and options learning implementation plan

**Goal:** Verify the document pipeline against real filings, run it on allocated HiPerGator compute, and build the chronological supervised options-response pipeline in parallel.

**Authorization:** User explicitly requested both workstreams on 2026-10-03, including beginning HiPerGator processing and building the price model. This extends the earlier first-build boundary. Ordinary implementation and job setup are authorized; no repeat design approval needed.

**Architecture:** GPU OCR produces source-grounded transcripts, then frozen language features. A separate learner joins eligible as-of features to observed call/put quotes and learns four targets: call/put midpoint returns and call/put after-cost returns. Training and evaluation remain chronological, with event grouping and purging of overlapping outcome intervals.

**Tech:** Python, existing native/OCR interfaces, pinned GLM-OCR/Transformers on Slurm compute, official LoRA recipe, JSON model artifacts, NumPy ridge baseline.

**Spec:** docs/superpowers/specs/2026-10-03-8k-document-analysis-design.md plus the user's current explicit continuation.

## Constraints and ownership

- GPU worker owns GLM adapter, finite/resumable batch CLI, reviewed OCR training-pair exporter, hpc scripts, GPU requirements/config/tests/docs.
- Options worker owns market dataset/label/training module and CLI, training config/tests/docs/dependencies.
- Root owns integration, actual SSH/submission, real-data verification, acquisition/coverage checks and final review.
- No heavy inference or training on the local laptop or cluster login node; use Slurm for HiPerGator. Use home-pc only for separately suitable heavy work via detached tmux.
- Preserve unrelated concurrent repo edits. Never transmit .env, private SSH keys or unrelated home files to the cluster.
- Explicit checkpoint revisions, datasets and allocation values; no inferred accounts, fabricated labels or claimed training without job evidence.

## Tasks

- [x] Inspect live cluster access, allocations and remote environment; record actual output/status.
- [x] Verify existing pipeline on a finite real filing selection; prepare document batch manifest.
- [x] Implement native-first GLM GPU adapter, batch/Slurm launch and reviewed LoRA dataset path; offline tests.
- [x] Define strict market-data contracts and deterministic labels; implement chronological train/validation/test baseline and saved predictions; offline tests.
- [x] Stage explicit safe files and submit initial allocated cluster job where access permits; collect submission job IDs (setup44610314, pilot44610315).
- [x] Collect actual setup/GPU completion status and output; repair runtime failures. Integrated retry44620388 verified locally:25 artifact hashes,5 completed inputs, OCR acceptance passed,2 FinBERT reports, no failures. See data/processed/hipergator/local-processor-v1-verification.json. This completes bounded foundation execution; it does not complete training/table validation.
- [x] Review integration, fix failures, run relevant tests, record completed versus externally blocked work.

## Review focus

Wrong issuer/accession, timestamp leakage, mismatched quote/contract deliverables, GPU jobs accidentally running on login/local CPU, resumed outputs from changed sources or checkpoints, train/test contamination, synthetic records misrepresented as empirical validation.
