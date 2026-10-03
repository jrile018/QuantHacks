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

Use `--max-events 1` for an API-access smoke test. The runner writes `events.csv`, `dropped.csv`, `results.csv`, `scoreboard.csv`, `capacity.csv`, and `manifest.json` to ignored `data/processed/`. It accepts `--capital`, `--risk-fraction`, `--participation`, and `--cost-haircut` to state sizing assumptions. Run `python run_all.py --help` for all arguments. To compare windows, run it once per window with different `--output-dir` values; the notebook includes the in-sample, placebo, and out-of-sample comparison plots.

The client also accepts `MASSIVE_API_KEY` from the environment. A first full notebook run can take around ten minutes; later runs reuse `.massive_cache/`.

**Timing rule:** the raw 8-K API gives a filing date without an acceptance time. To avoid entering before an after-close filing, `post` enters at the close of the first trading session strictly **after** that date. `pre` is the last trading close strictly **before** the filing date. The placebo uses the same one-session lag. This conservative rule can miss a same-day opportunity after a morning filing; it prevents timing lookahead without requiring a second data source. The notebook's optional SEC section audits acceptance times but does not change a completed backtest.
This changes the starter notebook's same-day entry assumption, so its P&L can differ from an unmodified starter run.

## Repository layout

| Path | Purpose |
|---|---|
| `gator-quant-hacks-8k-options-challenge.ipynb` | Visual research walkthrough and comparative analysis |
| `run_all.py`, `src/main.py` | Reproducible command-line runner and CSV/manifest output |
| `src/data.py` | API access, cache, calendar, disclosure events, and options bars |
| `src/implementation.py` | Option leg pricing and six-strategy P&L engine |
| `src/risk_management.py` | Bootstrap uncertainty, comparison tables, and loss budget |
| `src/capital_liquidity.py` | Cash collateral, option volume limits, and cost assumptions |
| `src/config.py` | Shared study parameters |
| `scripts/import_tiger.py` | Repeatable import of local API cache and study outputs into Tiger Cloud |
| `tests/` | Offline tests for event construction, P&L, risk, and capacity |
| `requirements.txt`, `setup.ps1`, `setup.sh`, `.env.example` | Reproducible setup and key template |
| `data/README.md` | Data handling and download notes |
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

## Copy local data to Tiger Cloud

After authenticating with the Tiger CLI (`tiger auth login`) and running a study, import the local cache and all manifested runs under `data/processed/`:

```bash
python scripts/import_tiger.py --service-id YOUR_TIGER_SERVICE_ID
```

Use `--dry-run` to see the file and row counts without writing. The importer uses the CLI's saved credentials; no database password enters the repository. It creates the `quant_hacks` schema with `source_files` (exact file bytes and SHA-256 hashes), `study_runs` (manifests), `study_rows` (CSV rows as JSON), and an `api_responses` JSON view. Repeating the import updates the same files and study run instead of adding duplicate rows. See [data/README.md](data/README.md) for example queries. Local files remain in place as a second copy.
