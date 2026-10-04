# HiPerGator document OCR and reviewed LoRA training

The batch runner processes only a supplied JSONL file. HTML and text stay native; PDF pages with usable embedded text stay native. Scanned pages and images use the explicitly selected OCR provider. `glm` loads the pinned checkpoint on CUDA only when a page actually needs OCR. It returns the existing OCR JSON schema and a normalized transcript, keeping page boundaries, original source SHA-256, checkpoint and adapter revisions, settings and unknown confidence.

Inference is model-only text recognition. It does not include GLM's separate layout detector, establish financial table accuracy, or produce market forecasts. The official model card describes GLM-OCR as a 0.9B model; checkpoint memory requirements should be measured on the actual allocation. [Official GLM-OCR model card](https://huggingface.co/zai-org/GLM-OCR), [official Transformers v5.3.0 inference recipe](https://github.com/huggingface/transformers/blob/v5.3.0/docs/source/en/model_doc/glm_ocr.md).

## Configure the actual allocation

Connect with your authorized HiPerGator account. Run allocation inspection before filling `configs/hipergator.example.json`:

```bash
module load ufrc
slurmInfo
sinfo
sacctmgr show assoc where user="$USER" format=Account,Partition,QOS
```

Copy the example config and replace every null runtime field using the available association, approved resource request and actual deployed paths. `account`, `qos`, `partition`, `gres`, CPU count, memory, time limit, working directory, environment script, Python executable, checkpoint cache and output directory are required. `training_dataset_dir` is required only for LoRA. The launcher deliberately has no default allocation. Association information can be restricted; use your group's confirmed configuration if that inspection is unavailable. [UF allocation and QOS documentation](https://help.rc.ufl.edu/doc/Account_and_QOS_limits_under_SLURM), [current UF scheduler and resource FAQ](https://docs.rc.ufl.edu/support/faq/).

The environment script is a real Bash file owned by the user, containing the exact module/environment activation commands for their installed CUDA and Python environment. Both Slurm scripts source it. Inference does not run on a login node. UF requires scheduled resource use and GPU jobs must use their assigned GPU. Use a CPU allocation for batches containing only native HTML/text; the GPU pilot should include a real scanned page requiring GLM. [UF HiPerGator usage policies](https://it.ufl.edu/rc/documentation/policies/hipergator-usage-policies/).

## Prepare the environment and pinned cache

On the chosen deployed workspace, create an environment using the site's selected Python and install the CUDA-enabled PyTorch build appropriate for that environment. The following commands assume that environment has been activated:

```bash
python -m pip install -r requirements-gpu-ocr.txt
python -c 'from transformers import AutoProcessor, GlmOcrForConditionalGeneration; import torch; print(torch.__version__)'
python hpc/setup_model_cache.py --cache-dir /actual/model/cache --model both --download
```

`--download` explicitly enables network access for model setup. Without it, setup only checks an existing cache. Inference and training Slurm scripts use offline mode. GLM revision `2e85a62840ccac27daa451df36c736c4636b8628` was resolved from the official model API; FinBERT uses `db38d3727cbaed87c9aed72df7b3519e2ba5cca1`. Setup downloads safetensors and processor/tokenizer files, without inference or legacy pickle weights. [GLM checkpoint API](https://huggingface.co/api/models/zai-org/GLM-OCR), [FinBERT checkpoint](https://huggingface.co/ProsusAI/finbert/tree/db38d3727cbaed87c9aed72df7b3519e2ba5cca1).

Setup, the FinBERT pilot lookup and LoRA preparation share `resolve_model_snapshot` and its inference-file filter. This matters with Hugging Face Hub 1.33.0: offline snapshot validation checks completeness for the requested file set. An unfiltered lookup incorrectly demanded omitted README/legacy-format files during the first cluster pilot. The repair keeps offline mode and the same pinned revisions while requesting exactly the subset setup downloaded. Required inference files must still be present. [Official snapshot completeness implementation](https://github.com/huggingface/huggingface_hub/blob/v1.33.0/src/huggingface_hub/_snapshot_download.py).

The batch runner extracts documents; the existing `scripts/analyze_8k_documents.py` builds accession reports. It accepts generated OCR files through `--ocr-map` when the map's filenames match the accession inventory. FinBERT wording assessments remain an independent configured provider.

For the bundled five-document pilot, `--mode pilot` runs both stages and connects completed OCR artifacts to the accession reports. The selected input manifest must have a sibling `filings.json` with at least one valid filing. Populate both pinned model caches first. This mode requires a fresh output directory; its Slurm log is written beside that directory. It uses the verified GLM revision above and automatically chooses BF16 or FP16 after checking the allocated GPU.

```bash
python hpc/submit_document_job.py --config /actual/hipergator.json --manifest /actual/pilot/documents.jsonl --mode pilot --dry-run
python hpc/submit_document_job.py --config /actual/hipergator.json --manifest /actual/pilot/documents.jsonl --mode pilot
```

## Explicit batch input and launch

Create an input file with one JSON object per document. Paths may be absolute or relative to the input manifest. Additional inventory metadata is retained in each durable output record.

```json
{"document_id":"explicit-document-id","source_path":"sources/one.pdf","source_sha256":"actual-64-character-sha256","company_id":"verified-issuer-id"}
```

Use actual hashes; the example is a schema illustration. Duplicate document IDs, an empty manifest or malformed JSON are rejected. A supplied source hash is checked before extraction. Missing or failed documents produce durable failure records while later documents continue. Exit status is nonzero when any selected document fails.

```bash
python scripts/run_document_batch.py --manifest /actual/pilot.jsonl --output-dir /actual/native-output --engine native
python hpc/submit_document_job.py --config /actual/hipergator.json --manifest /actual/pilot.jsonl --mode ocr --dry-run
python hpc/submit_document_job.py --config /actual/hipergator.json --manifest /actual/pilot.jsonl --mode ocr
```

Run the Slurm launcher on HiPerGator with deployed paths. The dry run validates configuration and the finite input manifest and prints the `sbatch` command. Submission produces a Slurm job ID. Inspect it with `squeue -j JOB_ID`, `sacct -j JOB_ID --format=JobID,State,ExitCode,Elapsed`, and the configured `slurm-JOB_ID.log`. The runner writes an fsynced `manifest.jsonl` after every result, plus hashed `.transcript.json` and optional `.ocr.json` artifacts. Resume skips only completed records matching source hash, the complete canonical input record (including company/time metadata), configuration, provider/normalizer revisions and installed dependency versions; it verifies saved output hashes before skipping. Failed records retry.

A process lock prevents concurrent writers. After an ungraceful kill, check that no worker is alive before removing `.batch.lock`. A torn/corrupt journal blocks resume and must be preserved and repaired explicitly; it is never silently truncated. Failed integrity checks preserve earlier artifacts.

## Reviewed image/transcript LoRA inputs

Each training JSONL record requires `document_id`, original `source_path` and `source_sha256`, `image_path`, `page_number`, `company_id`, timezone-aware `public_at_utc`, `split`, exact corrected `transcript`, `annotation_status`, `annotator` and `rubric_revision`. Optional `image_sha256` is verified. Annotation status must be `human_reviewed` or `adjudicated`; OCR outputs are not accepted as reviewed labels automatically. Multiple page/crop records may share a document inside one split.

Use explicit `train` and `validation` splits. Document IDs, companies, source hashes and image hashes must be disjoint between them. Every training timestamp must strictly precede every validation timestamp. This conservative held-out issuer/time rule is intentional; exporter output is not evidence that OCR accuracy improved.

```bash
python scripts/export_ocr_training_pairs.py --manifest /actual/reviewed-pairs.jsonl --output-dir /actual/reviewed-dataset
```

The output is ShareGPT `messages`/`images`, `dataset_info.json`, copied image files and `provenance.json` preserving source/image/transcript hashes and review metadata. The prompt is `<image>Text Recognition:`. This follows GLM's own multimodal LoRA recipe. [Official GLM LoRA guide](https://github.com/zai-org/GLM-OCR/blob/main/examples/finetune/README.md), [official LoRA configuration](https://github.com/zai-org/GLM-OCR/blob/main/examples/finetune/glm_ocr_lora_sft.yaml).

## Prepare and launch LoRA

Clone LLaMA-Factory and choose a reviewed immutable checkout that supports the `glm_ocr` template. Record the actual commit. After editable installation, reinstall this project's Transformers pin because the factory's constraints can otherwise select an older release without GLM-OCR:

```bash
git clone https://github.com/hiyouga/LLaMA-Factory.git /actual/LLaMA-Factory
git -C /actual/LLaMA-Factory checkout ACTUAL_REVIEWED_FACTORY_COMMIT
python -m pip install -e /actual/LLaMA-Factory
python -m pip install -r requirements-gpu-ocr.txt
llamafactory-cli version
git -C /actual/LLaMA-Factory rev-parse HEAD
python hpc/submit_document_job.py --config /actual/hipergator.json --manifest /actual/reviewed-pairs.jsonl --mode lora --dry-run
python hpc/submit_document_job.py --config /actual/hipergator.json --manifest /actual/reviewed-pairs.jsonl --mode lora
```

The `lora` job requires a previously nonexistent training output directory. Its Slurm log is written beside that directory as `OUTPUT_NAME-slurm-JOB_ID.log`, allowing the preparer to create the run directory exclusively. Existing output, config, provenance or adapters are rejected; there is no implicit checkpoint resume. The job revalidates reviewed source hashes, split policy, exported labels/images, and manifest before writing `lora-config.yaml` (JSON content is valid YAML and uses the factory's YAML loader). It resolves the pinned checkpoint only from the local cache. It follows the official guide's `DISABLE_VERSION_CHECK=1` setting for the GLM-compatible Transformers release and stores `pip freeze` beside the training provenance. Training runs as `"$python_bin" -m llamafactory.cli train`, using the same configured interpreter as the CUDA check and preparer. The config uses LoRA rank 8, all linear modules, the `glm_ocr` template, separate evaluation data, batch size 1, accumulation 4, learning rate 1e-4 and three epochs. Adapter output goes to a new `adapter` directory with overwriting disabled. The manifest and model/config provenance are stored beside it. These are runnable recipe settings, not tuned performance claims. A compatible LLaMA-Factory environment and independently reviewed pairs are prerequisites; no fabricated training dataset is supplied. [Official factory CLI entry point](https://github.com/hiyouga/LLaMA-Factory/blob/main/src/llamafactory/cli.py), [official configuration parser](https://github.com/hiyouga/LLaMA-Factory/blob/main/src/llamafactory/hparams/parser.py).

The requested GitHub training skill was located at the current official [Hugging Face LLM trainer skill](https://github.com/huggingface/skills/blob/main/skills/huggingface-llm-trainer/SKILL.md); the old `hugging-face-model-trainer` path no longer resolves. Its useful guidance here is validating multimodal data and tracking training output. It targets Hugging Face Jobs; this user's selected compute target is HiPerGator, so the implementation uses Slurm and GLM's official image/transcript LLaMA-Factory recipe.

## Verification and remaining runtime prerequisites

```bash
python -m unittest tests.test_glm_document_ocr tests.test_document_batch -v
```

The offline tests mock model calls and verify routing, source mutation checks, pinned/no-download loading, continuation decoding, durable resume, per-record failures, manifest validation, training review and split leakage, and dry-run allocation validation. They do not load checkpoints or claim actual GPU OCR/training success. Real execution needs authenticated HiPerGator access, verified allocation/runtime fields, staged sources, installed compatible CUDA/Python dependencies and the explicitly populated pinned cache. LoRA additionally needs reviewed pairs and the chosen factory checkout; validation loss alone does not establish financial-sign/table OCR accuracy.
