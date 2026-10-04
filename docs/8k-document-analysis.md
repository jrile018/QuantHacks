# 8-K document analysis

This first build produces an auditable document assessment. It does **not** train a price model or claim that positive language increases an option premium.

## Run the offline example

From the repository root (Python 3.10+):

```powershell
python scripts/analyze_8k_documents.py --cik 1234 --accession 0000001234-24-000001 --submission examples/8k_document_analysis/submission.txt
```

The example is synthetic, not SEC data. The command prints the absolute path to a new `report.json`. Open the neighboring `report.md` for the two answers. Core HTML/text extraction and offline tests use the standard library. PDF/image processing uses the existing optional dependencies in `requirements-ocr.txt` and the existing Tesseract setup.

## What the report contains

1. **Wording:** exact quotations with document and text hashes, offsets, sections and page references where available; optional dictionary counts and frozen FinBERT probabilities. Every machine assessment is unreviewed. No rhetorical or numeric-change labels are invented.
2. **Options:** missing or unvalidated inputs, a proposed fixed contract rule and `forecast: null`. Daily bars cannot substitute for synchronized bid/ask quotes. Even supplied quote records are diagnostic until issuer identity, timestamps, coverage and the session calendar are independently validated.

`inventory.json`, transcript files and `run.json` accompany each report. Raw sources are content-addressed under ignored `data/raw/8k_documents`; reports live under ignored `data/processed/8k_document_analysis`. Each invocation creates a new run directory. Completed source downloads are reused after hash verification; successful transcript checkpoints survive interruptions, but a rerun deliberately reprocesses transcripts and gives them new processing timestamps. Source and transcript versions are never silently overwritten. Duplicate content is identifiable by its hash; duplicates within a submission also link to their first document ID. This is not a cross-filing event deduplication engine.

The complete SEC submission supplies both the primary document and exhibits. Wording analysis selects the primary filing and EX-99 exhibits; viewer scripts, XBRL support files and other attachments remain inventoried but are excluded from sentiment. Item 2.02 is the initial family. Additional material items yield `mixed_event`; Item 9.01 is administrative. Item detection is lexical and must be reviewed for references versus actual headings. Missing attachments, decoding errors and unresolved tables remain visible. Table cells and row evidence are retained, but units, financial concepts and numeric changes are not inferred from proximity.

## Fetch an explicit filing from the existing catalog

Set `SEC_CONTACT_EMAIL` privately in the process environment to the authorized contact address. Then use the real CIK and accession from your catalog:

```powershell
python scripts/analyze_8k_documents.py --catalog data/processed/sec_8k_urls/filings.csv --cik YOUR_CIK --accession YOUR_ACCESSION --fetch
```

Fetches only that complete submission; it does not download the corpus. Requests are restricted to the corresponding SEC archive identity, limited to five per second, and stop on 403/429. The contact is not written into reports. A constructed child URL remains identified as a document contained in a fetched submission, rather than claimed to have been individually fetched.

For local use, `--submission` accepts complete SGML submission bytes. The catalog is optional for local input. `--amends-accession` explicitly links an amendment while preserving its separate accession. The local receipt time is this run's time, not its historical publication time.

## Add calibrated OCR output

Use `--ocr-map path/to/map.json`. Its keys are the exact embedded filenames and its values are OCR JSON paths relative to the map:

```json
{"release.htm": "ocr/release.json"}
```

OCR JSON accepts the existing `OCRDocument` serialization:

```json
{
  "sha256": "SHA256_OF_THE_ORIGINAL_DOCUMENT_BYTES",
  "engine": "glm-ocr",
  "engine_version": "PINNED_CHECKPOINT_REVISION",
  "settings": {"adapter_revision": "YOUR_REVIEWED_ADAPTER_VERSION"},
  "pages": [{"number": 1, "text": "Reviewed transcript text.", "confidence": null}]
}
```

The source hash must match the inventoried document. Supply source_path when available to verify original bytes; the importer otherwise flags unverified provenance. For HTML rendered into page images, record the source document hash and rendering/crop settings when creating the OCR artifact. Preserve separate image hashes in settings. Do not pass a page-image hash as the original-document hash. Original OCR JSON is retained. Engine confidence is not semantic confidence. SEC uuencoded PDF exhibits are decoded with separate container and decoded-source hashes. Other unsupported binary encodings and extraction failures remain explicit coverage gaps.

The accession analyzer imports OCR output. A separate pinned GLM-OCR CUDA adapter, resumable batch runner, Slurm launcher and reviewed-pair LoRA exporter are now implemented; see [HiPerGator processing](hipergator-document-processing.md). Actual cluster inference and training remain unverified until job output is collected. The existing PDF path uses native text where available and Tesseract fallback. This accession-analysis command never downloads weights or submits training. OCR labels, financial-language labels and realized-market labels remain distinct datasets.

## Add frozen wording providers

Supply a locally obtained Loughran–McDonald master dictionary, respecting its license:

```powershell
python scripts/analyze_8k_documents.py --cik YOUR_CIK --accession YOUR_ACCESSION --submission submission.txt --dictionary dictionary.csv --dictionary-revision YOUR_DICTIONARY_RELEASE
```

The CSV must contain `Word` and recognized category columns such as `Negative`, `Positive`, `Uncertainty`, `Litigious`, `Strong_Modal`, `Weak_Modal`, `Constraining`. Positive numeric values mark membership in the supplied snapshot; no historical version is reconstructed. Dictionary SHA256 and revision are stored. Negation is retained in evidence, but word counts do not resolve its meaning.

Optional FinBERT uses separately installed `torch` and `transformers` and a **local safetensors** classifier with explicit positive/negative/neutral labels:

```powershell
python scripts/analyze_8k_documents.py --cik YOUR_CIK --accession YOUR_ACCESSION --submission submission.txt --finbert-model path/to/local/finbert --finbert-revision PINNED_REVISION
```

CPU is the default for a small explicit filing; `--device cuda` is available in an appropriately configured compute environment. Long evidence is truncated at the model limit and flagged. Missing providers stay unavailable. This build's tests do not establish model accuracy and do not execute a real checkpoint.

## Prior comparisons and timing

`--public-metadata metadata.json` supplies a filename-keyed record with `public_at_utc` and `public_at_evidence` for **each** document. Evidence should cite an independently checked announcement/archive record. A timestamp alone, SEC acceptance, or the source-download time does not prove first public availability. The software records your evidence; it does not verify an external archive assertion automatically.

`--prior-report path/to/earlier/report.json` compares the explicitly supplied earlier report. All compared documents require supported timestamps, the same issuer, and chronological eligibility. Prior hashes/spans are checked. Exact lexical matches are `unchanged`; similarity at least 0.65 is `changed`; lower similarity is `new_statement`. Similarity is case sensitive, ignores whitespace differences, and only compares within the same SEC item. New means absent from this one comparator; it does not prove novelty to investors or consensus surprise.

`--decision 2024-02-01T14:00:00Z` checks an explicit cutoff. Actual receipt or processing after the cutoff blocks historical readiness. `--mode anticipation --target-accession FUTURE_ACCESSION` also excludes that target and any unavailable/late evidence from the wording assessment. Original documents remain in the audit report. No output from this command is exported as a point-in-time feature dataset (`feature_export_eligible` is false); that dataset builder is a later stage.

Human calibration should store separate annotations keyed by evidence_id with rubric version, annotator, label and adjudication status. Do not show future returns to semantic annotators, or overwrite source evidence to fit a label.

Available SEC header accession and issuer identifiers must match the requested identity. Missing headers produce `submission_identity_unverified`, which blocks eligible prior comparisons and anticipation wording. Do not infer the issuer CIK from the accession prefix; a filing agent may submit it.

Freeze dictionary and model versions before evaluation. A modern pretrained checkpoint may contain information from after a historical decision; these software guards do not remove pretraining contamination or prove a historically deployable model. Record checkpoint publication/training provenance and evaluate that limitation separately.

## Frozen target and separate market learner

The supervised dataset, chronological split, ridge training and held-out evaluation code now exists separately; see [options-model training](options-model-training.md). No real price model has been fitted. This document report still returns `forecast: null`, and its wording output is not automatically a validated historical feature dataset.

`configs/8k_document_analysis.json` records the proposed shared 90–180 day expiry nearest 120 days, call strike nearest 105% of spot, put strike nearest 95%, and next eligible session close after the entry session. Configuration changes to this frozen family/target are rejected. Quote-age/spread bounds and cost assumptions intentionally start unset.

Optional `--market-metadata` accepts a JSON object with diagnostic `issuer_mapping`, `underlying`, and `quotes`. Quotes require contract_id, option_type (call/put), strike, expiry, timestamp, bid, ask, bid_size, ask_size and multiplier. Underlying requires price and timestamp. A candidate pair may be shown when quote settings are configured; it is not certified tradable. Quote receipt times, point-in-time contract/deliverable mapping, calendars, executable entry/exit coverage and a trained/evaluated predictor remain prerequisites. No returns, IV labels, hedge profits or no-trade successes are manufactured.

## Verification

```powershell
python -m unittest tests.test_document_manifest tests.test_document_transcript tests.test_document_evidence tests.test_document_language tests.test_document_report tests.test_analyze_8k_documents
```

These are offline software tests. They are not a backtest, financial experiment, OCR benchmark or model training run.
