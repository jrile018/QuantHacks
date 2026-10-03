# Gator Quant Hacks 2026 — Trade the 8-K

This repository contains the Massive 8-K options challenge starter notebook. The notebook is the single entry point for downloading disclosures and options data, building event and strategy tables, and producing the research output. It ships without saved results.

## Run the notebook

You need Python 3.10+ and a Massive API key with access to the challenge data.

1. Run `powershell -ExecutionPolicy Bypass -File setup.ps1` on Windows, or `./setup.sh` on macOS or Linux. This creates `.venv`, installs `requirements.txt`, registers a Jupyter kernel, and copies `.env.example` to `.env`.
2. Put your key in `.env` as `MASSIVE_API_KEY=your-key`. Keep this file private.
3. Start JupyterLab with `.venv\Scripts\activate; jupyter lab` on Windows, or `source .venv/bin/activate && jupyter lab` on macOS or Linux.
4. Open [`gator-quant-hacks-8k-options-challenge.ipynb`](gator-quant-hacks-8k-options-challenge.ipynb), select **Python (Gator Quant Hacks .venv)**, and run all cells.

The notebook also accepts `MASSIVE_API_KEY` from the environment. Its configuration cell sets the event tag and date windows. A first full run can take around ten minutes; later runs reuse `.massive_cache/`.

## Repository layout

| Path | Purpose |
|---|---|
| `gator-quant-hacks-8k-options-challenge.ipynb` | Complete data download, event construction, backtest, and analysis pipeline |
| `requirements.txt`, `setup.ps1`, `setup.sh`, `.env.example` | Reproducible setup and key template |
| `data/README.md` | Data handling and download notes |
| `examples/` | Documentation example showing the raw API response shape; **not** study data |
| `references/` | Downloaded challenge briefs and original starter archives |

The general [systematic-trading brief](references/systematic-trading-track-brief.txt) shows a separate `data/`, `src/`, and `run_all.py` layout as an **example**. The [Massive challenge brief](references/massive-bonus-challenge-brief.txt) specifies a notebook that runs the whole study, so this repository keeps that notebook intact as its runnable entry point.

## Data and secrets

The notebook fetches disclosures from Massive's `/stocks/filings/8-K/vX/disclosures` endpoint and obtains options data from Massive. Its raw API responses are cached in `.massive_cache/`. The cache, `.env`, and any downloaded raw or processed data under `data/` are ignored by Git. Do not commit licensed market data or API keys.

The JSON file in `examples/` is copied from [Massive's public 8-K Disclosures documentation](https://massive.com/docs/rest/stocks/filings/8-k-disclosures) solely to explain the response format. It is not a live query or a result from the notebook.

This repository currently contains the starter materials only. A Massive API key is required to produce actual event rows and results.
