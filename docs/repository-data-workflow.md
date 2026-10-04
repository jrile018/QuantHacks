# Repository data notebook and offline backtest

[Open the notebook](../notebooks/repository-data-and-backtest.ipynb) to inventory local data and run two independent replays of the bundled **synthetic DEMO** snapshot. It calls the existing options engine and verifies identical scientific CSV hashes. This engineering example establishes no qualified real-data performance, net portfolio return, OCR-derived signal or trading recommendation. Post Benchmark retains its canonical account and qualification workflow.

The [original challenge notebook](../gator-quant-hacks-8k-options-challenge.ipynb) is the licensed/live Massive study and requires its provider access and requested data. The offline notebook needs no API key, downloads, GPU or model training after dependency installation.

## Install and run

Use Python **3.11.9** for the CI-tested environment. `requirements-notebook-lock.txt` pins direct notebook/replay dependencies exactly; it is not a complete transitive lock. Run these commands from the repository root. Creating a separate environment keeps notebook dependencies independent from OCR/ML workloads.

Windows PowerShell:

```powershell
py -3.11 -m venv .venv-notebook
.venv-notebook\Scripts\python.exe -m pip install -r requirements-notebook-lock.txt
.venv-notebook\Scripts\python.exe -m ipykernel install --sys-prefix --name quanthaxs-offline --display-name "QuantHaxs offline (Python 3.11)"
.venv-notebook\Scripts\python.exe -m jupyterlab notebooks/repository-data-and-backtest.ipynb
```

Linux/macOS:

```bash
python3.11 -m venv .venv-notebook
.venv-notebook/bin/python -m pip install -r requirements-notebook-lock.txt
.venv-notebook/bin/python -m ipykernel install --sys-prefix --name quanthaxs-offline --display-name "QuantHaxs offline (Python 3.11)"
.venv-notebook/bin/python -m jupyterlab notebooks/repository-data-and-backtest.ipynb
```

Select **QuantHaxs offline (Python 3.11)**, restart the kernel and run all cells. Each execution creates a fresh UUID-named directory under ignored `data/processed/repository_notebook/`. The committed notebook has no saved outputs. Runtime metadata can contain local paths and belongs in ignored storage.

For unattended execution, the script launches a fresh kernel using the **calling Python interpreter**, without requiring the named project kernel to be registered:

```powershell
.venv-notebook\Scripts\python.exe scripts/execute_repository_notebook.py --output data/processed/notebook-executions/run-1.ipynb
```

On Linux/macOS use `.venv-notebook/bin/python` instead. Choose a new output filename for each execution; the script refuses to overwrite the notebook or its execution receipt. The receipt records interpreter, source/output hashes, timestamps and the executed code-cell count. A failed cell causes a nonzero exit and no completed execution receipt.

## Reproduce the synthetic backtest directly

Use the same environment's Python:

```bash
python scripts/reproduce_backtest.py --snapshot-dir examples/backtest_replay --output-dir data/processed/replay-check/run-1
python scripts/reproduce_backtest.py --snapshot-dir examples/backtest_replay --output-dir data/processed/replay-check/run-2 --compare data/processed/replay-check/run-1
python -m unittest tests.test_backtest_replay tests.test_repository_data_catalog
```

Use the explicit environment interpreter above if it is not activated. Each output directory must be new. The runner checks input hashes and frozen settings before calculation and records input/code/environment/output identities. Scientific tables must match; local paths and execution timestamps may differ. `.github/workflows/backtest-notebook.yml` installs the same direct pins on Python 3.11.9, runs these focused contracts and executes the whole notebook.

The results are **gross unit P&L**, with last-trade option marks and synthetic spot. Hypothetical pre-entry rows compare mechanics. Capacity/cost assumptions appear in a separate event-level table; this demo has no account allocation or net portfolio NAV model. One invented event supports no statistical performance inference.

## Canonical wording account workflow

The same notebook also invokes the existing canonical wording controller using its pinned **SYNTHETIC FABRICATED engineering** fixture. It saves and displays both regular wording and baseline account panels from the existing marked-account exporter, retaining their valuation grid and missing/status fields. This section adds no account or strategy engine.

From the repository root, use the configured environment interpreter:

```bash
python scripts/run_simple_wording_backtest.py --root . --mode engineering --output-dir data/processed/wording-engineering/run-1
```

Choose a fresh root-relative output directory. `report.json`, `panel_wording.json`, `panel_baseline.json` and `trials.jsonl` stay under ignored processed storage. The fixture does not supply qualified real inputs, accepted market evidence or complete approvals. The existing controller withholds P&L, Sharpe, win-rate, confidence interval and edge headlines, and keeps economic qualification/headline eligibility false. CI smoke-runs this exact engineering CLI before the full notebook.

## Storage and lineage

| Location | Meaning |
| --- | --- |
| `data/raw/` | Original documents, quotes and acquisition records; ignored |
| `.massive_cache/` | Licensed API response cache when locally available; ignored |
| `data/processed/` | Derived tables, transcripts, evidence and runtime receipts; ignored |
| `artifacts/` | Retained research and diagnostic outputs when available |
| `configs/` | Parameters and source registrations |
| `examples/` | Small synthetic fixtures and documentation examples |
| `references/` | Challenge briefs and starter references |

The catalog reads file metadata, not raw/protected data contents. File counts are storage counts, not usable observations or accepted features. A source URL is metadata; processing needs local original bytes. Preserve document identities, raw/text hashes, definitions, clock evidence and adapter versions. Publication, receipt, download and processing times remain distinct; unsupported values and identities remain unknown. Read the [team data guide](team-data/README.md) and [source contract](team-data/source-contract.md) before adding a source.

| Object | Grain and meaning |
| --- | --- |
| File catalog | One local file: relative path, area, extension, bytes, status |
| Transcript/evidence | Document hashes, normalized text and exact quotation offsets |
| Event | Issuer/accession/ticker and event/pre/post dates; filing date alone is not acceptance time |
| Selected option legs | Event, bucket and leg; frozen contract/strike/expiry/multiplier |
| Option bars | Contract and session; last-trade close and volume, not executable bid/ask |
| Results | Event, strategy settings and horizon; gross unit P&L |
| Capacity | Event-level capital, risk, volume and cost assumptions |
| Run manifest | Settings, environment and input/code/output hashes; reproduction is separate from qualification |

## Incomplete coverage and historical runs

**Team-reported project limitation:** OCR and model processing over the full PDF dataset could not be completed with the GPU compute and processing resources available to the team. The extracted and reviewed subset is incomplete, so the entire dataset and planned analysis could not be examined. This public walkthrough does not independently measure full-corpus OCR accuracy or compute capacity. Successful extraction still needs semantic review, clocks, identity, market coverage and producer/consumer acceptance.

A clean clone need not contain historical smoke manifests, licensed data, original PDFs or processed reports. The notebook reports missing local inputs explicitly. Historical row counts remain manifest claims until exact local bytes pass the original hash checks. Git LFS pointers are not restored source bytes. Missing documents or market tables do not imply empty observations, neutral sentiment, zero returns or absence of an edge.

To reproduce a real historical study, restore permitted exact input bytes and their recorded hashes, matching code/config/environment and the applicable owner-approved runner. A fresh provider download is a new snapshot and may differ. Complete source, clock, model, market and account qualification before interpreting economic results. Do not commit raw/licensed data, private audit reports, broker databases or runtime notebook outputs.

## Reading period context and performance

The notebook derives an asset/date context table from the frozen events, quotes, calendar and settings. DEMO and FAKE-* are fictional; dates do not establish a real asset's bull/bear, volatility or liquidity regime. The options example has one invented date-only event; the wording example has three fabricated candidates and a 2024 regular account grid. No real AMT trade is represented. UTC publication/processing/entry/exit clocks remain distinct, and hypothetical pre-entry comparisons are labeled.

The notebook explains gross unit P&L versus full account net results, same-opportunity baseline, idle cash, integer-share exposure, fees, borrow/collateral, sparse marks, capacity and lookahead exclusions before the corresponding outputs. Sharpe, win rate, turnover and maximum drawdown remain N/A for real performance, with explicit definitions and missing-evidence reasons. It does not create fake headline metrics from synthetic tables.

Continued OCR/model data is unavailable because the full PDF workload and reviewed historical coverage remain incomplete. Access/runtime/resource readiness, human gold labels and exact historical review are separate gaps. Native HTML can bypass OCR but cannot fill absent scanned information. Missing extraction is never neutral sentiment or zero return, and the retained subset is not a representative full-corpus sample.

### Equity implementation and reuse across strategies and universes

The bundled canonical engineering route runs on **equities**: wording signal -> historical eligibility -> frozen long/short target policy -> executable quotes, costs and borrow -> single account ledger -> complete-calendar NAV and matched baseline -> qualified metrics. This fixture exercises the wiring with fabricated data; it does not qualify historical trading performance.

The architecture separates those responsibilities so the same account workflow can support other strategy definitions and security universes. Reuse requires each strategy to produce **causal trade intents** from accepted point-in-time features, and each universe to supply tested lifecycle adapters and a frozen protocol. It is not an arbitrary asset or strategy plug-in that becomes validated merely by producing a signal.

| Boundary | Current equity route | Required for another strategy or universe |
| --- | --- | --- |
| Signal and decision policy | Frozen wording sign, eligibility, timing, equal-dollar integer-share long/short targets | Accepted point-in-time features, past-only selection, causal intents and frozen sizing/entry/exit rules; test unavailable or late information |
| Security universe and market lifecycle | Dated equity identity, reference sessions, executable quotes and same-session corporate-action coverage | Dated security mapping, calendars/timezones, pricing units and multipliers, expiry/settlement/corporate-action lifecycle adapters and independent acceptance |
| Portfolio and execution policy | Existing single account ledger, cash, restricted short proceeds, borrow, margin/collateral and costs | Tested cash/margin/collateral and cost/financing lifecycle adapters; accepted fills/no-fills, capacity, exposure and account reconciliation |
| Comparison and reporting gates | Complete regular-calendar NAV, matched always-long/zero-cash baselines, withheld unqualified headlines | Same eligible opportunity set and valuation window, complete ledger/marks, relevant comparator and independently qualified metric evidence |

The separate options example reports gross unit mechanics and does not inherit equity account qualification. Futures or other universes need their own dated contract/unit/settlement and margin adapters, frozen strategy protocols and independent qualification. They should reuse the existing account engine through tested adapters rather than introduce a second account engine. A reusable interface preserves missing-evidence gates; it does not erase asset-specific risks or imply that every strategy is implemented here.

## Sharpe presentation

The notebook presents Sharpe as **one scalar point estimate** per qualified strategy, rather than a 95% confidence interval. Its current Sharpe is **N/A** because qualified real account returns are unavailable. Synthetic demonstrations do not supply a replacement number. Existing canonical report uncertainty fields and protocol schemas remain intact; they are not the primary Sharpe display.
