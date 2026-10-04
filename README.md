# Gator Quant Hacks 2026 — Trade the 8-K

This repository contains a modular version of the Massive 8-K options challenge starter. The notebook remains the visual research walkthrough; `run_all.py` is a command-line entry point for one study window. Both use the same `src/` implementation and ship without saved results.

## Run the notebook

You need Python 3.10+ and a Massive API key with access to the challenge data.

1. Run `powershell -ExecutionPolicy Bypass -File setup.ps1` on Windows, or `./setup.sh` on macOS or Linux. This creates `.venv`, installs `requirements.txt`, registers a Jupyter kernel, and copies `.env.example` to `.env`.
2. Put your key in the local `.env` file by replacing `your-key-here` there. Keep this file private; leave `.env.example` as the public template.
3. Start JupyterLab with `.venv\Scripts\activate; jupyter lab` on Windows, or `source .venv/bin/activate && jupyter lab` on macOS or Linux.
4. Edit [`src/config.py`](src/config.py) for the research tag, date windows, universe, and assumptions. Restart the notebook kernel after a change.
5. Open [`gator-quant-hacks-8k-options-challenge.ipynb`](gator-quant-hacks-8k-options-challenge.ipynb), select **Python (Gator Quant Hacks .venv)**, and run all cells.

For a repeatable single-window run, use:

```bash
python run_all.py --tag cfo_appointment --start 2024-01-01 --end 2025-12-31
```

Use `--max-events 1` for an API-access smoke test. The runner writes `events.csv`, `dropped.csv`, `results.csv`, `scoreboard.csv`, `capacity.csv`, selected `option_legs.csv`, observed `option_bars.csv`, and `manifest.json` to ignored `data/processed/`. The manifest records each table's row count and SHA-256 hash. It accepts `--capital`, `--risk-fraction`, `--participation`, and `--cost-haircut` to state sizing assumptions. Run `python run_all.py --help` for all arguments. To compare windows, run it once per window with different `--output-dir` values; the notebook includes the in-sample, placebo, and out-of-sample comparison plots. The selected option tables can be ingested by [Lattice](stat-arb/docs/options-native.md).

The client also accepts `MASSIVE_API_KEY` from the environment. A first full notebook run can take around ten minutes; later runs reuse `.massive_cache/`.

**Timing rule:** the raw 8-K API gives a filing date without an acceptance time. To avoid entering before an after-close filing, `post` enters at the close of the first trading session strictly **after** that date. `pre` is the last trading close strictly **before** the filing date. The placebo uses the same one-session lag. This conservative rule can miss a same-day opportunity after a morning filing; it prevents timing lookahead without requiring a second data source. The notebook's optional SEC section audits acceptance times but does not change a completed backtest.
This changes the starter notebook's same-day entry assumption, so its P&L can differ from an unmodified starter run.

## Repository layout

| Path | Purpose |
|---|---|
| `gator-quant-hacks-8k-options-challenge.ipynb` | Visual research walkthrough and comparative analysis |
| `run_all.py`, `src/main.py` | Reproducible command-line runner and CSV/manifest output |
| `src/data.py` | API access, cache, calendar, disclosure events, and options bars |
| `src/document_ocr.py` | Selective PDF text extraction and OCR with per-page provenance |
| `src/reit_cash_facts.py`, `scripts/collect_reit_financials.py` | Bounded SEC REIT document and cash movement collection |
| `src/implementation.py` | Option leg pricing and six-strategy P&L engine |
| `src/risk_management.py` | Bootstrap uncertainty, comparison tables, and loss budget |
| `src/capital_liquidity.py` | Cash collateral, option volume limits, and cost assumptions |
| `src/config.py` | Shared study parameters |
| `scripts/import_tiger.py` | Repeatable import of local API cache and study outputs into Tiger Cloud |
| `tests/` | Offline tests for event construction, P&L, risk, and capacity |
| `requirements.txt`, `setup.ps1`, `setup.sh`, `.env.example` | Reproducible setup and key template |
| `requirements-ocr.txt` | Optional OCR Python dependencies |
| `data/README.md` | Data handling and download notes |
| `docs/financial-profile-research.md` | SEC form coverage, no-key data sources, document/OCR access, and financial reconciliation design for the Tiger CIK universe |
| `docs/company-sector-breakdown.md` | SIC-based industry split of the 1,630 Tiger 8-K filers, with counts, definitions, sources, and limits |
| `examples/` | Documentation example showing the raw API response shape; **not** study data |
| `references/` | Downloaded challenge briefs and original starter archives |

The general [systematic-trading brief](references/systematic-trading-track-brief.txt) shows a separate `data/`, `src/`, and `run_all.py` layout as an **example**. The [Massive challenge brief](references/massive-bonus-challenge-brief.txt) specifies a notebook that runs the whole comparative study, so this repository also keeps the notebook as a runnable report.

## Risk and capacity assumptions

`src/risk_management.py` limits whole contracts by a chosen maximum loss per event. `src/capital_liquidity.py` further limits contracts by available cash and a chosen fraction of the least-traded required option leg's daily volume. A cash-secured put reserves the full strike amount. Strategies that represent stock with an ATM call and put reserve a 100-share stock equivalent. The cost model applies a configurable fraction of each option premium on each side, including the ATM synthetic pair. These are research assumptions from last-trade marks and daily volume, not live quotes or broker margin checks.
Both cash and maximum-loss contract limits include the modeled round-trip costs. Each event is sized independently; simultaneous positions need a portfolio-level allocation rule before trading.

Run offline checks with `.venv\Scripts\python.exe -m unittest discover -s tests -v`.

## Data and secrets

The notebook fetches disclosures from Massive's `/stocks/filings/8-K/vX/disclosures` endpoint and obtains options data from Massive. Its raw API responses are cached in `.massive_cache/`. The cache, `.env`, and any downloaded raw or processed data under `data/` are ignored by Git. Do not commit licensed market data or API keys.

The JSON file in `examples/` is copied from [Massive's public 8-K Disclosures documentation](https://massive.com/docs/rest/stocks/filings/8-k-disclosures) solely to explain the response format. It is not a live query or a result from the notebook.

The repository contains the runner, notebook, tests, downloaded challenge references, and a public API response example. A Massive API key is required to download the study data and reproduce event rows and results.

For a proposed company-financials dataset based on the 1,630 CIKs exported from Tiger, read the [financial profile research](docs/financial-profile-research.md). SEC public filing and XBRL APIs require no API key. The proposed financial statements and documents have not yet been imported into Tiger.

## Collect REIT filings and cash movement facts

The default pilot uses [`configs/reit_pilot_companies.csv`](configs/reit_pilot_companies.csv), keyed by CIK. AMT comes first because it is the REIT in the configured options universe; AAT, BXMT, and AGNC provide different disclosure patterns for comparison. A live run needs a real email address for the SEC request User-Agent. Start with AMT and the default limits of four primary filings and two selected exhibits per filing:

```powershell
.venv\Scripts\python.exe scripts\collect_reit_financials.py --contact-email you@example.com --max-companies 1
```

Replace the example email with your own. Selection reserves the newest original annual and quarterly reports when available, then adds relevant event filings or separate amendments within the cap. Filing indexes identify a bounded set of EX-10, EX-4 and EX-99 agreements and supplements. `--max-exhibits-per-filing 0` disables exhibits. To use the broader 53-candidate Tiger export, pass `--companies-csv data/processed/tiger_8k_company_sectors.csv`.

The command writes to ignored `data/processed/reit_financials/`: `cache/` keeps original SEC responses and filings; `text/CIK/accession/` holds source-linked text, extraction methods, hashes and quality diagnostics; `facts.csv` contains selected monetary flows and balance snapshots with tags, periods, units and response hashes; `checks.csv` reports cash arithmetic and any known rounding bound; `manifest.json` records coverage, cache receipts, partial failures, and completed versus requested companies. Online runs refresh SEC metadata after 24 hours. Unchanged document text is reused when source identity, hash, extraction settings and revision match. `--offline` reruns from a populated cache without SEC requests. A 403 or 429 stops further SEC requests and saves partial outputs. The request rate defaults to 2 per second and must stay below 10.

Company Facts covers standard entity-wide tags; company-specific debt tables and loan terms remain in the filing text. Flows and balances are labeled separately, and overlapping detail rows are not automatically summed. An `incomplete` cash check means a required component is missing or ambiguous; `balanced` means only that selected reported figures agree arithmetically, at a supplied precision when available. Review material amounts and table associations in the original filing. Read the [workflow audit](docs/reit-workflow-audit.md) for tested improvements and the remaining coverage/evaluation work.

### Organize retained REIT loan and money evidence offline

After a retained collection exists, run `.venv\Scripts\python.exe scripts\analyze_reit_money.py --collection-dir data/processed/reit_financials`. This separate step reads original HTML/Inline XBRL and cached page text without fetching, re-running OCR or calling a model. It retains exact entity/period/dimension/unit context, applies supported numeric transformations and consolidates equivalent same-filing facts with all source references.

`money_analysis/money_records.jsonl` contains parsed or review-required filing observations; `review_candidates.jsonl` preserves actual table cells and relevant text with unresolved loan meanings; `comparison_facts.jsonl` keeps verified CompanyFacts separate. `analysis_manifest.json` records coverage, omissions, errors, reuse and output hashes. `parsed` means supported extraction succeeded, not financial verification. Custom meanings, conflicting values, missing units and uncertain loan terms remain review items. No automatic transaction totals or refinancing links are inferred. Read the [step 3 research](docs/reit-money-extraction-research.md) for the evidence, implemented limits and evaluation strategy.

## OCR scanned documents

Install optional Python dependencies with `.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt` on Windows (or `.venv/bin/python -m pip install -r requirements-ocr.txt` on macOS/Linux). Install the [Tesseract executable](https://tesseract-ocr.github.io/tessdoc/Installation.html) separately and make it available on `PATH`. The module reads PNG, JPEG, TIFF (including all pages), BMP, WebP, and PDF files. It reuses native PDF text and OCRs scanned pages or sparse-text pages with substantial image coverage. Dense hybrid pages retain completeness warnings for review.

```powershell
.venv\Scripts\python.exe -m src.document_ocr data\raw\sample-scan.pdf --output data\processed\ocr\sample-scan.json
```

The module also detects common Windows user and system installation paths. For another location, add `--tesseract-cmd "C:\path\to\tesseract.exe"`. Output includes per-page methods, word coordinates/confidence, review flags, native/OCR overlap diagnostics, actual rendered resolution, engine versions, settings and input hash. `--force-ocr` handles defective embedded text; `--psm 3`, `6` or `11` selects a Tesseract segmentation mode for controlled comparisons. Confidence is a recognition diagnostic, **not** proof of a correct amount or table. OCR text is not automatically parsed into financial statements or imported into Tiger.

This module uses the image-to-text architecture reviewed in [Sun-Biz-Aggregator](https://github.com/IlanDanial/Sun-Biz-Aggregator/tree/060050d6daa376049e0fe60edf8ee27c0d3a7e40). It is independently implemented here because that repository does not include a license file; its Florida UCC form parsers and training scripts are not bundled.

## Copy local data to Tiger Cloud

After authenticating with the Tiger CLI (`tiger auth login`) and running a study, import the local cache and all manifested runs under `data/processed/`:

```bash
python scripts/import_tiger.py --service-id YOUR_TIGER_SERVICE_ID
```

Use `--dry-run` to see the file and row counts without writing. The importer uses the CLI's saved credentials; no database password enters the repository. It creates the `quant_hacks` schema with `source_files` (exact file bytes and SHA-256 hashes), `study_runs` (manifests), `study_rows` (CSV rows as JSON), and an `api_responses` JSON view. Repeating the import updates the same files and study run instead of adding duplicate rows. See [data/README.md](data/README.md) for example queries. Local files remain in place as a second copy.

## Teammate sources and passing PR merges

Benchmark and Benchmark Part 2 contributors use this repository's shared document schema and independent `codex/source-<source-id>-<owner>` branches. Start with the [team data guide](docs/team-data/README.md), [source contract](docs/team-data/source-contract.md) and [agent instructions](AGENTS.md). The guide includes a copyable agent prompt, source registration, OCR setup, synthetic fixtures, safe rebasing and exact-head merging.

Register `configs/sources/<source-id>/{source.json,manifest.jsonl,README.md}` using the [source metadata](templates/team-data/source.template.json) and [manifest](templates/team-data/manifest.template.jsonl) templates. Commit URLs, adapters, matching tests and small synthetic fixtures. Download originals into ignored `data/raw/team_sources/<source-id>/` and write results into ignored `data/processed/team_sources/<source-id>/`; full-data storage will be decided later.

Run these setup checks before opening a source PR:

```powershell
python scripts/validate_team_sources.py --repo-root .
python scripts/run_document_batch.py --manifest examples/team_data/manifest.jsonl --output-dir data/processed/team_sources/onboarding-smoke --engine native
python -m unittest tests.test_source_validation tests.test_source_pr_policy tests.test_shared_review tests.test_document_manifest tests.test_document_transcript tests.test_document_evidence tests.test_document_language tests.test_document_report tests.test_analyze_8k_documents
git fetch origin
python scripts/check_source_pr.py --repo-root . --base origin/main --head HEAD --branch YOUR_SOURCE_BRANCH
```

Run source adapter tests as well. The validator rejects missing metadata, unresolved placeholders, duplicate or unnamespaced IDs, invalid URLs/paths/hashes and invalid UTC fields. Sources marked extracted also need a hashed synthetic TXT/HTML fixture; validation runs extraction and checks transcript hashes and evidence slices. Discovery registrations can pass without downloading originals and do not claim OCR readiness.

Teammate agents are authorized to merge passing **source-only** PRs using the [source PR checklist](.github/PULL_REQUEST_TEMPLATE/data-source.md). GitHub requires `source-configuration` and `Source adapter tests` on the current PR version. The first uses trusted base code to validate candidate configuration and source-only scope; the second runs the published offline suite and adapter tests without write credentials. Main must be up to date, and the merge command must use `--match-head-commit` as shown in the guide. Shared schema, pipeline, workflow or validator changes need a separate maintainer-reviewed PR.

For shared changes, the repository owner must approve the current commit in GitHub. For a PR they authored, they can instead post the exact comment `approve-shared-change: FULL_HEAD_SHA`. The owner then applies or reapplies a label (for example, run-source-checks) to rerun the trusted check. A new push invalidates the previous approval. Using a different branch name does not bypass this review requirement.

These checks establish configuration and reproducible intake behavior. Actual scanned-page recognition requires a local OCR pilot with the selected backend; accepted benchmark features still require the relevant producer/consumer checks.
