# HiPerGator and options-learning status

Status recorded 2026-10-03. Updated integrated pilot successfully deployed and verified on HiPerGator. No LoRA adapter or options predictor has been trained.

## Verified integrated pilot: job44620388

Job44620388 completed on NVIDIA L4 with Slurm0:0 in80 seconds. Authenticated collection retrieved1,289,416 bytes. All25 collected artifact hashes were independently rechecked locally. The pipeline's own run record reports completed, batch exit0, no failures and OCR acceptance passed for its one image. Five batch inputs completed: four native SEC HTML documents (Apple/GD primary filings and EX99.1 exhibits) and one annual-report prose calibration image. This was not OCR over five scanned8-Ks.

The retrieved OCR text exactly matches the previously checked251-word heading/body transcription; only footer45 is absent relative to the complete native PDF page. Frozen FinBERT produced294 Apple and114 GD fragment assessments, with both selected documents per report complete and no provider errors. Both reports retain options status not_ready and null forecasts. Dictionary provider remains unconfigured. These outputs verify the bounded processing pipeline, not predictive performance or general OCR accuracy.

Verification: `data/processed/hipergator/local-processor-v1-verification.json`. Actual logs/reports/transcripts: `data/processed/hipergator/local-processor-v1/results`. Remaining work: financial-table/negative-sign validation, independently reviewed OCR training pairs and compatible LoRA training runtime, plus matched point-in-time features/option quotes/mappings/calendar/provenance for price-model training. No backtest or model training ran in this pilot.

This section supersedes older deployment/rerun-pending statements below; previous failures are preserved as history.

## Successful prose OCR: user-run job44619171

The user-pasted GPU log shows the explicit Glm46VProcessor and model loading from the same pinned local checkpoint, receiving pixel_values[10208,1176] and image_grid_thw[1,3], then generating305 tokens without truncation. The source image hash matches the local calibration page53. All251 heading/body words match the PDF native text exactly after whitespace normalization. The footer45 was omitted, so the whole page is not exact. This is a one-page smoke check against native PDF text, not an independent annotated benchmark or evidence of table accuracy. Raw remote result has not been downloaded; supplied output and comparison are saved in `data/processed/hipergator/ocr-image-check-44619171-user-evidence.json` and its neighboring comparison JSON.

The earlier diagnostic44618007 confirmed that text-only inputs caused the empty Markdown output, and prompt slicing was correct. A later processor check fetched processor_config.json and then supplied image tensors. Exact lower-level cache/fallback behavior has not been independently reproduced locally; the verified workaround explicitly loads from the pinned local snapshot.

Local adapter revision3 implements that loading path, requires processor_config.json, and refuses missing/empty pixel or grid tensors. Setup/pilot/LoRA share the same inference-file resolver. Retry deployment now includes the adapter.37 focused tests passed and independent review found no P1/P2 issue. The original remote source and prior artifacts remain unchanged. To deploy this fix and rerun the combined pilot, run `scripts/retry_hipergator_pilot.py --repair-name local-processor-v1` from the local repository using its .venv Python. It requires interactive SSH authentication and automatically collects results.

The historical failures and intermediate states below are retained for traceability; this section supersedes their current-status statements.

## Observed GPU retry: process completed, OCR acceptance failed

Job **44612514** completed on NVIDIA L4 with Slurm exit **0:0** in35 seconds. The same authenticated connection retrieved1,278,452 bytes of hash-verified artifacts under `data/processed/hipergator/cache-scope-v1/results`.

- Frozen FinBERT produced294 Apple fragment assessments (281 neutral,9 positive,4 negative) and114 General Dynamics assessments (108 neutral,6 positive), with no provider errors. Fragments include headers/boilerplate, so these counts are not whole-document scores or forecasts.
- The GLM calibration output contains only an empty Markdown fence. The batch previously counted this as completed, which was an insufficient acceptance check. GPU process completion does not establish usable OCR. The local pilot now rejects empty/formatting-only OCR while retaining successful independent wording reports. Its gate verifies original source and artifact hashes and missing/failed selected rows. This gate has not yet run on the cluster.
- Original calibration page53 contains accounting prose despite its misleading financial-table filename. The repaired selector finds the actual balance sheet on page66. Original hashed artifacts are preserved; the new unreviewed image is separate in `data/processed/document_pilot/table_calibration_v2`.
- Both wording reports still explicitly report options `not_ready`, forecast null and feature export ineligible. No price-model training or OCR fine-tuning ran.

Next diagnostic is prepared as `ocr-diagnostic-v1`. Its interactive PowerShell SSH window is awaiting password/Duo; no diagnostic job ID exists yet. It compares current vs explicit image inputs, slow preprocessing and a page crop, recording tensor shapes, pixel statistics and full/generated decoding without changing production inference. The existing environment/cache are reused, with inference restricted to Slurm. Twenty-seven focused pilot/GLM/selector/collection tests passed locally after the acceptance repair.

## First runtime result and repair

The user-supplied logs show setup job44610314 completed its environment installation, imports, model downloads and processor checks. GPU pilot44610315 reached the offline FinBERT lookup and failed with `IncompleteSnapshotError` before document processing. Setup intentionally cached inference files, while the pilot requested an unfiltered whole-repository snapshot. Hugging Face Hub1.33.0 consequently required omitted README and legacy-format files. The shell errors beginning `[kkatiyar@login8` came from pasted prompt text and are separate from this Python failure.

The fix makes setup, pilot and LoRA preparation use the same filtered resolver. A mocked full-pilot regression reproduced the failure before the fix and passed afterward; 30 focused checks passed. Independent review found no concrete P1/P2 blockers. Original logs are retained in `data/processed/hipergator/original-job-log.txt`.

A reviewed retry helper created a fresh `repairs/cache-scope-v1` directory, verified original file hashes, changed three cache-related Python files, and reused the original environment/cache. Its offline cache preflight succeeded; job44612514 and collected outputs are described above. `retry-status.json` tracks the latest attempt and `retry-events.jsonl` retains the event history.

## Submitted jobs

- **44610314:** CPU environment setup and pinned model-cache preparation.
- **44610315:** one-L4 document/wording pilot, dependent on successful setup.
- Deployed directory: `/blue/ai-workshop/kkatiyar/quanthaxs-pilot-26a0b8a5ff60`.
- Evidence: local `data/processed/hipergator/submission-status.json` and `submission-output.txt`, SSH exit code 0; remote `deployment-jobs.json` records the exact requests.
- Retry44612514 completed with actual GPU/wording artifacts; OCR content validation failed as described above. No trained adapter or fitted options predictor exists.

Check from the existing HiPerGator terminal:

```bash
squeue -j 44610314,44610315
sacct -j 44610314,44610315 --format=JobID,State,ExitCode,Elapsed
tail -n 30 /blue/ai-workshop/kkatiyar/quanthaxs-pilot-26a0b8a5ff60/results/setup-44610314.log
tail -n 30 /blue/ai-workshop/kkatiyar/quanthaxs-pilot-26a0b8a5ff60/results/pilot-slurm-44610315.log
```

The pilot log may not exist until its dependency completes and the GPU job starts.

## What ran on real data

- Downloaded the complete SEC submissions for Apple `0000320193-24-000005` and General Dynamics `0001193125-24-003197`. Selection used the earliest ordinary 8-K within the fixed 2024 interval for named tickers, without filtering on outcomes. MSFT had no matching row in the selected catalog; it was not silently substituted.
- Processed four selected HTML documents: each primary filing and EX-99.1 exhibit. Viewer scripts and XBRL support files remain in the source inventory but cannot contaminate wording analysis.
- Verified four successful native batch extractions, zero failures. This did not load FinBERT or GLM weights and does not measure sentiment or OCR accuracy.
- Confirmed historical bid/ask access and collected a complete one-minute sample with 36 quotes. Original SIP nanoseconds, immutable response hashes and actual retrieval time are retained. Historical system receipt is unknown. This sample is an acquisition check, not a matched training event or a performance result.

The original deployment manifest contains those four SEC documents and an accounting-prose image rendered from page53 of the existing Realty Income annual report. Its financial-table filename was a selector mistake, corrected for future inputs. The image is an unreviewed GPU smoke-test input, not an 8-K or a corrected training label.

## What was built

### Document processing

- Pinned GLM-OCR CUDA inference, native extraction where possible, resumable finite batches and source/version provenance.
- Reviewed image/transcript export and a LoRA Slurm recipe using the configured interpreter. Training rejects existing output directories and unreviewed labels.
- Combined GPU pilot that passes OCR artifacts into accession reports, then scores wording with pinned frozen FinBERT. Missing filings/providers or selected extraction failures cannot count as a completed pilot.
- A portable, hashed bundle containing explicit code and pilot data. Credentials, private keys, model weights and unselected datasets are excluded.

### Options prediction

- Deterministic call/put selection and four observed targets: call/put midpoint changes and call/put after-cost returns.
- As-of feature/quote checks, event-group chronological splits, overlapping-label purging, train-only preprocessing, validation-selected ridge models and a mean-prediction baseline.
- A persistent holdout ledger that rejects reuse of overlapping test cohorts.
- A finite quote collector, with explicit gaps, pagination bounds and no invented historical receipt times.

See [model training and input contracts](options-model-training.md), [quote collection](options-quote-collection.md), and [GPU processing](hipergator-document-processing.md).

## What still prevents actual runs

1. **Cluster completion verification.** The user authenticated an SSH terminal as `kkatiyar@login8` and confirmed account/default QOS `ai-workshop`, existing directory `/blue/ai-workshop/kkatiyar`, allocation of 5 GPUs (1 in use at observation), `hpg-turin` L4 nodes, system Python 3.9.25, and `conda/26.7`. The bundle upload and job submission succeeded. Completion states and actual logs/results still need to be collected. The tools cannot type into the existing app SSH terminal; the interactive upload/submission sessions have finished.
2. **OCR adaptation labels.** LoRA needs independently corrected image/transcript pairs with the required company/time separation. Machine OCR is not accepted as human-reviewed truth. No such dataset has been supplied or claimed.
3. **Market training dataset.** The training software exists, but a complete paired dataset still needs verified first-public times, dated issuer/contract mappings, trading sessions, eligible feature provenance and entry/exit bid/ask coverage across sufficient event groups. The four current documents and one quote sample do not satisfy these requirements. The report-to-feature dataset is not automatically certified for historical use.

Historical documents processed today cannot be labeled as if the system actually received and processed them years ago. The model documentation distinguishes retrospective research from historical deployability and records the remaining pretrained-model contamination limitation.

## Prepared deployment

The reviewed bootstrap uses the observed account and partitions:

- CPU setup: 4 CPUs, 16 GB RAM, one-hour limit, `hpg-default`. Creates a fresh Python 3.11 environment through `conda/26.7`, installs torch 2.9.1 and torchvision 0.24.1 from the official CUDA 12.6 wheel repository, verifies imports, and downloads/validates the pinned GLM and FinBERT caches. [Official PyTorch version combinations](https://pytorch.org/get-started/previous-versions/), [UF environment guidance](https://docs.rc.ufl.edu/software/conda_environments/).
- GPU pilot: 1 L4, 2 CPUs, 16 GB RAM, 30-minute limit, `hpg-turin`. Runs only after successful setup. If the dependency becomes impossible, Slurm is instructed to cancel the pilot. Actual driver compatibility, queue timing and runtime memory remain to be measured. [UF GPU scheduling](https://docs.rc.ufl.edu/scheduler/gpu_access/).
- These resource sizes are proposed pilot requests within the observed group limits, not performance measurements or reserved capacity.

Bundle SHA256: `26a0b8a5ff60a2a072f8ae4e3f22f300302a3a3938cdc5d0c4d624152f19bcef`.
Remote archive name: `quanthaxs-pilot-26a0b8a5ff60.tar.gz`.

The interactive submission window runs the equivalent commands automatically. Use the following only if that window has not submitted the deployment (the exclusive directory/state checks prevent duplicates). In the existing HiPerGator terminal, press `q` first if still in the module pager:

```bash
cd /blue/ai-workshop/kkatiyar &&
mkdir quanthaxs-pilot-26a0b8a5ff60 &&
tar -xzf quanthaxs-pilot-26a0b8a5ff60.tar.gz -C quanthaxs-pilot-26a0b8a5ff60 &&
cd quanthaxs-pilot-26a0b8a5ff60 &&
python3 hpc/start_ai_workshop.py
```

This verifies the bundled file hashes, writes the concrete configuration, and submits both Slurm jobs. It prints both job IDs and a status command. `deployment-jobs.json` records submission state and prevents duplicate submission. It does not run model inference on the login node. Setup and model output logs live in the deployed `results` directory. A submitted job is not evidence of successful completion. Confirmed discovery values are saved locally in `data/processed/hipergator/discovery.json`.

## Verification

- All 94 relevant document, market and deployment tests passed together after the final fixes. Independent review found no remaining P1/P2 issues in the reviewed fixes.
- Subsequent account-specific setup/launch changes passed 29 focused tests, Python 3.9 bootstrap syntax checks and Bash syntax checks. Independent review found no concrete P1/P2 setup findings. No real model inference was performed by these checks.
- A full repository run at that point executed 179 tests and reported two errors in concurrently edited REIT tests: an invalid duplicate XML-attribute fixture and a missing `src.reit_tables` module. No whole-repository clean claim is made.
- Archive verification checks entry paths, every file hash, staged source hashes, the five-document count, two filing submissions and Linux shell line endings.
- Offline/mocked tests verify software behavior. They do not demonstrate GPU runtime compatibility, prediction accuracy, LoRA improvement or strategy profitability.
