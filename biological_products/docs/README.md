> **SUPERSEDED (2026-10-04).** This file describes the first, per-filing pipeline (scripts 00 to 15). The current dataset is the daily FDS built by `scripts/16_build_fds.py`; read `data/fds/README_FDS.md` and `HANDOFF_BIOLOGICS.md` instead.

# Biological Products (SIC 2836) data collection

Goal: a feature matrix (one row per 8-K) for the 139 tickers in SIC 2836, using only information known before each filing,
to predict what an 8-K will be about. See DATA_DICTIONARY.md for every column.

## Run it
Needs Python with pandas, numpy, requests, scikit-learn (pip install -r requirements.txt).
Set two environment variables first (never commit keys):
  MASSIVE_API_KEY   your Massive key
  SEC_UA            "Your Name your@email.com"   (SEC asks callers to identify themselves)
Then run the scripts in scripts/ in number order. Each one reads and writes through bp_paths.py:
  00 pull_companyfacts     SEC financial statements (one JSON per ticker)
  01 flatten_facts         financials into one table
  02 pull_trials           ClinicalTrials.gov studies per sponsor
  03 pull_8k_events        Massive 8-K rows with categories (the thing to predict)
  04 pull_news             Massive news
  05 pull_prices           Massive daily prices, plus XBI and SPY
  06 pull_edgar_filings    SEC filing index per company
  07 pull_form4            insider buys and sells from Form 4 (about 1 hour)
  08 pull_pdufa            PDUFA dates found in full 8-K text (about 40 minutes)
  09 build_base_matrix     financials and trial features
  10 add_news              news counts and sentiment (trains a small model on Massive's tags)
  11 add_prices            price features and outcomes
  12 fix_stale_prices      blanks prices more than 5 days stale
  13 drop_etf_and_splits   drops PRTO (an ETF) and one unadjusted split
  14 add_edgar_features    shelf, offering, activist, late filing counts
  15 add_form4_pdufa_features   insider and PDUFA features, writes data/final/feature_matrix_final.csv
Optional side pulls: optional_purplebook.py, optional_fda_drugs.py (not used in the matrix).

## Folders
scripts/         code
data/raw/        pulled data (not committed, rebuilt by scripts)
data/processed/  intermediate matrices (not committed)
data/final/      feature_matrix_final.csv, the shared result
docs/            this file and the data dictionary
scratch/         old one-off scripts (not committed)

## Known gaps
- Options coverage (coverage.csv: which trial-result events have tradable options) came from a one-off PowerShell command that was not saved. It is not reproducible from this repo yet.
- Step 00 is checked for syntax only. Run it once to confirm.
- The news sentiment model gives slightly different numbers on different library versions (correlation 0.999 between versions).
- Rerunning 02, 03, 04, 05, 06 later gives newer data, so results will drift from the saved files.
