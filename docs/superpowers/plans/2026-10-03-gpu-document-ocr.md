# GPU Document OCR Implementation Plan

> Execute in this session under the approved GPU OCR scope; no commits or Slurm submissions from the implementation worker.

**Goal:** Explicit, resumable document OCR on allocated CUDA compute plus reviewed image/transcript LoRA inputs.

**Architecture:** Lazy pinned GLM provider returns the existing OCRDocument schema. Native PDF pages use the existing extraction boundary. Finite JSONL batch inputs produce immutable, hashed outputs and durable completion records. A dry-run Slurm launcher requires actual allocation and environment configuration.

**Spec:** `docs/superpowers/specs/2026-10-03-8k-document-analysis-design.md`

**Constraints:** No GPU computation or model download implicitly; no full corpus selection; no fabricated labels; no account guesses; source and provider provenance retained. Mock CUDA inference in short local tests.

**Review focus:** changed source/output during resume, malformed/torn journal, native PDF without torch, split leakage across document/company/time, adapter cache and checkpoint provenance.

## Task 1: GLM provider

- [x] Write and run failing validation/native/fallback/model-contract tests in `tests/test_glm_document_ocr.py`.
- [x] Implement `GLMConfig`, `GLMOCRProvider`, `extract_document` in `src/glm_document_ocr.py` using the official Transformers recipe.
- [x] Run the targeted tests; no weights loaded.

## Task 2: Batch and reviewed pairs

- [x] Write and run failing explicit manifest/resume/failure/export tests in `tests/test_document_batch.py`.
- [x] Implement `scripts/run_document_batch.py` and `scripts/export_ocr_training_pairs.py`.
- [x] Verify immutable hashes, durable checkpoints and rejected leakage.

## Task 3: Slurm launch and documentation

- [x] Add launcher dry-run validation tests.
- [x] Implement `hpc/submit_document_job.py`, allocated-node shell scripts and LoRA config generation from official LLaMA-Factory fields.
- [x] Add `configs/hipergator.example.json`, `requirements-gpu-ocr.txt`, exact setup and source citations in `docs/hipergator-document-processing.md`.
- [x] Run all owned short tests and CLI help/dry-run checks; report remote execution prerequisites to the parent.


Verification: 18 owned unittest tests passed; 43 related OCR/transcript/accession/GPU/batch tests passed in 1.178s. Compileall and CLI help checks passed. Actual weights/GPU/training/Slurm execution belong to deployment and have not run. Review requested from the parent worker. No commits made.
