# Financial OCR calibration and conditional LoRA plan

Research date: 2026-10-03. Scope: research and planning; no jobs, installations, weight downloads, or product changes performed.

**Recommendation:** establish a finite financial OCR benchmark, compare task prompts and crops, and collect recurring errors before considering LoRA. Retain GLM-OCR 0.9B; no model above 3B is proposed.

## Evidence and limits

Session evidence supplied by the coordinating agent: HiPerGator job 44620388 actually ran on an NVIDIA L4 using checkpoint `2e85a62840ccac27daa451df36c736c4636b8628`, Transformers 5.3.0, explicit `Glm46VProcessor`, and a local snapshot. One prose page yielded 251 words agreeing with native PDF text after whitespace normalization; footer `45` was omitted. Four SEC HTML documents used native extraction; FinBERT processed 408 fragments. No financial table benchmark or LoRA training has run.

Inspected `src/glm_document_ocr.py`, `scripts/export_ocr_training_pairs.py`, `hpc/prepare_lora_config.py`, `docs/hipergator-document-processing.md`, and `tests/test_gpu_calibration_selection.py`. The adapter uses deterministic `Text Recognition:` for every whole page, caps generation at 4096 tokens, and explicitly flags unverified table/reading order. Selector tests establish that title-plus-numeric-density logic avoids prose and contents pages; mocked selection/rendering is not recognition evidence.

Native PDF comparison can detect discrepancies against embedded text and validate plumbing on a sampled page. It cannot independently establish visual completeness, cell alignment, sign/decimal fidelity, units, reading order, or scan performance. Embedded text may omit or misorder visible material. Keep both full-page and body-only scores: removing footers must be a declared rubric rule, not an adjustment made after observing errors.

Reuse `src/reit_inline_facts.py`, `src/reit_money_records.py`, and `src/reit_pdf_money.py` for sign/currency/scale/provenance interpretation. Map benchmark cells to their existing `value`, `unit_measure`, period and evidence fields; retain page/cell linkage. The dated `docs/reit-real-filing-pilot.md` 14-assertion native sample and 35-document/four-issuer collection are development evidence, not independent OCR gold. Do not add a broad financial parser.

The official model card and SDK distinguish model-only recognition from a layout pipeline and list `Table Recognition:` as a supported prompt [S1–S3]. Their published benchmark scores and throughput are not measurements of this checkpoint/adapter on financial filings or the allocated L4.

## Finite benchmark and annotation contract

Start with **60 distinct financial-document pages from 12 issuers**, five per issuer: four table pages and one prose page. Assign eight issuers/40 earlier pages to development and four unseen issuers/20 later pages to sealed test; every development publication must precede every test publication. Freeze accession/source hashes and assignment before inference. If the available corpus cannot satisfy this, acquire additional filings rather than silently weaken the split. Multiple crops and degradation variants inherit their original document split.

Across the 48 table pages, balance statement types: balance sheet, income/cash-flow statement, earnings exhibit, and reconciliation/footnote table. Cross-tag rather than multiply all combinations: native-rendered versus genuine scan/image; simple versus merged/multilevel header; parenthetical loss/minus sign; decimals, currency, percentage and per-share amounts; thousands/millions; narrow fonts, rotated or low-quality images; multi-column text and table continuation. Include at least 1,000 annotated numeric cells overall and 300 in test. Native-rendered pages measure raster recognition separately from genuine scans; synthetic degradation is a stress slice, not a substitute for scans. Public OmniDocBench/FinTabNet examples, if later licensed and obtained, belong in a separate diagnostic slice.

For each page/crop record preserve `document_id`, issuer, accession, UTC publication time, source/image hashes, page number, bounding box, render DPI, degradation recipe, task, prompt, split, annotator and rubric revision. Ground truth includes exact visible transcription, table HTML with row/column spans, ordered region IDs, and financial cell tuples `(row_label, column_period, raw_value, signed_decimal, currency, scale, percent_or_per_share, footnote_reference)`.

Two reviewers independently label test financial cells, headers, units and reading order; adjudicate disagreements against the image. Development gets one review plus a second review of all critical cells and ambiguous regions. Preserve minus versus dash, parentheses, zero versus blank versus not-applicable, decimal/comma conventions, superscript markers, and negative percentages. Never infer illegible values from arithmetic or another filing; mark unreadable and exclude them from exact-value denominators while reporting the exclusion count. Totals are consistency diagnostics, not replacement labels. Store original labels and adjudication reasons.

Score:

- Character/word error and missing-region rate for prose, with declared Unicode/whitespace normalization.
- TEDS and structure-only TEDS-S for HTML tables, using pinned evaluator revisions [S4–S5]. Count parse failures as failures; do not silently discard malformed outputs.
- Exact signed-value accuracy **with correct row/period attachment**, header/unit accuracy, critical error counts and table-perfect rate. A correct number in the wrong column fails.
- Reading-order pair accuracy on annotated region pairs; missing regions fail their relevant pairs. Report footer/footnote coverage separately.
- Per-stratum results, page/issuer aggregates, latency, peak CUDA memory, token-limit flags and abstentions. Bootstrap by issuer/document, not dependent cells; four test issuers yield limited uncertainty estimates.

**Our proposed engineering gates, not source-certified financial accuracy:** test signed-value accuracy ≥99.5%; mean TEDS ≥0.95 and TEDS-S ≥0.97; header/unit accuracy ≥99%; reading-order pair accuracy ≥99%; zero sign, scale, period-attachment or critical omission errors in the test's designated material cells. Any failed critical cell requires review before downstream numeric use. Small-sample success authorizes a wider pilot, not unattended production or profitable options decisions.

## Prompt/layout experiment before training

Compare three frozen configurations on development: A current whole-page text baseline; B manually reviewed table crops with `Table Recognition:` plus text crops with `Text Recognition:`; C detector-generated regions with task-specific prompts and preserved reading order. Official SDK configuration maps region tasks to these prompts and permits CPU layout placement [S2–S3]. Manual crops isolate recognition from detector errors; score C end to end so missed crops remain visible. Keep titles, period headers, scale labels and footnotes linked to the table even when they sit outside its bounding box.

Choose crop/prompt configuration and make the LoRA go/no-go decision using development only. Finish any training and validation selection before opening test; freeze the base pipeline and selected candidate, then evaluate them together once on sealed test. If test was opened earlier or its results drive redesign, reserve a new independent test. Dense output reaching 4096 tokens is incomplete: prefer linked table/continuation crops; inspect lengths before increasing caps. Preserve the pinned processor/loading path. CPU layout adds a separately pinned detector/dependencies; full SDK adoption is a separate integration choice.

Public benchmark/checkpoint contamination remains unknown. Public financial filings may have appeared in pretraining; issuer/time separation protects our experimental splits, not base-model provenance. Use newly collected later filings and independently annotated scans where practical, report dates and uncertainty, and avoid claiming contamination-free evaluation without training-corpus evidence.

## LoRA decision and compatibility audit

Proceed only when development errors recur after prompt/crop fixes and independent test coverage is viable. **Conditional annotation budget:** 120 training and 30 validation pairs, plus the sealed 20-page test. These counts are not guaranteed available or sufficient; additional pages and issuers may be needed for exporter constraints and error diversity. Oversample development errors in training while validation/test preserve declared strata. Test labels never enter optimization or selection.

Current exporter accepts only `train`/`validation`, requires both, enforces disjoint document/company/source/image hashes, and requires all training dates strictly before all validation dates. Consequently the same issuer, single report, or contemporaneous small calibration sample cannot populate both. Keep test in an independent evaluator manifest; do not relabel test as validation. Exporter hardcodes `<image>Text Recognition:`; table-crop HTML labels require an explicit task-aware schema/prompt extension and corresponding inference provenance. It lacks dedicated crop/task semantics. Relative original source paths are hashed as written, so staging must preserve resolution or use validated absolute paths.

Preparation validates immutable sources/exports and demands a fresh output directory. Rank 8, batch 1, accumulation 4, learning rate 1e-4 and three epochs are recipe defaults. The official guide advertises an ≥8 GB LoRA recipe; measure actual memory and truncation on L4 [S6]. Run a short fit/validation smoke check before one bounded run. Select checkpoints on validation, then freeze before the joint base/candidate test. Adopt only if test critical errors decrease without new critical errors, value accuracy improves, and prose/structure do not materially regress. Validation loss alone is insufficient.

**Source conflict:** GLM's guide says Factory defaults to Transformers 5.0.0; current Factory `pyproject.toml` instead permits `>=4.55.0,<=5.8.0` excluding 4.57.0/5.6.0 and requires Python ≥3.11 [S6–S7]. Thus compatibility is checkout-specific. Pin a reviewed Factory SHA, verify `glm_ocr` template/plugin and explicit processor support, resolver constraints, PEFT/TRL/PyTorch versions, `pip check`, image-token counts and effective trainable modules. A bypassed version guard is not proof of compatibility. Keep training isolated from the verified inference environment and save exact package/config hashes.

## Capacity and parallel work packages

Initial ceiling: **one L4 concurrently** under the observed shared `ai-workshop` allocation. Observed five-GPU quota is an allocation ceiling, not present availability or exclusive ownership. Inspect associations/queue before future submission, then measure a ten-page sample to derive GPU hours, RAM, wall time and cost. Native extraction, labeling and scoring run on CPU; serialize OCR and LoRA GPU use. All future cluster compute uses Slurm; this plan submits nothing.

| Task / ownership | Depends on | Concrete output and verification |
|---|---|---|
| 1. Benchmark curator: `data/ocr-calibration/`, rubric/manifest | None | Hashed 60-page split, reviewed labels and coverage counts; verify document/issuer/time and variant leakage. |
| 2. Evaluator owner: `scripts/evaluate_financial_ocr.py`, evaluator tests | Task 1 schema | Metrics JSON keyed by page/config plus error ledger; fixtures must detect wrong sign, scale, column, omitted footnote and malformed HTML. |
| 3. OCR owner: `src/glm_document_ocr.py`, crop runner, adapter tests | Task 1 schema; Task 2 for comparison | A/B/C artifacts with region coordinates, task/prompt and revision; verify token-limit and missing-region failures; freeze chosen configuration. |
| 4. Training owner: exporter, LoRA preparer, training tests | Can audit environment alongside 1–3; training waits for errors and viable labels | Task-aware reviewed export, immutable environment audit and bounded run plan; reject split leakage/task mismatches. Compare base/adapter through Task 2. |

Interfaces: Task 1 supplies frozen manifest/labels; Task 3 supplies raw region/page predictions; Task 2 supplies metrics/error IDs; Task 4 consumes development errors and emits adapter provenance for Task 3 evaluation. One owner edits each shared module. Wording/options research can proceed with native SEC HTML and source provenance while OCR gates remain unresolved; OCR improvement is not forecast validation.

## Primary source ledger and open questions

All sources accessed **2026-10-03**; `main` pages are mutable and require immutable pins during execution.

- **S1:** [GLM model card](https://huggingface.co/zai-org/GLM-OCR): 0.9B, supported recognition prompts, SDK versus model-only scope.
- **S2:** [GLM SDK README](https://github.com/zai-org/GLM-OCR/blob/main/README.md): layout plus region recognition, CPU layout option.
- **S3:** [SDK configuration](https://raw.githubusercontent.com/zai-org/GLM-OCR/main/glmocr/config.yaml): task/prompt mapping, region and layout settings.
- **S4:** [OmniDocBench repository](https://github.com/opendatalab/OmniDocBench): separate text, table, structure and reading-order metrics; aggregate score definition.
- **S5:** [Original PubTabNet/TEDS repository](https://github.com/ibm-aur-nlp/PubTabNet): image-to-HTML annotation and original TEDS evaluator; scientific-domain scope.
- **S6:** [Official GLM fine-tuning guide](https://raw.githubusercontent.com/zai-org/GLM-OCR/main/examples/finetune/README.md): task-aware ShareGPT, minimal recipe, stated memory and historical dependency advice.
- **S7:** [Factory dependency metadata](https://raw.githubusercontent.com/hiyouga/LLaMA-Factory/main/pyproject.toml): current Python/package bounds; does not certify a training run.

Open questions: genuine scan availability; human annotation capacity; temporal cutoff satisfying all split rules; checkpoint pretraining overlap; actual L4 memory/runtime; reviewed Factory commit; detector behavior on dense SEC exhibits. FinTabNet's original IBM page/repository did not resolve during this research; no unsupported dataset-size or performance claim is used.
