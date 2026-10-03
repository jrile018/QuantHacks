"""
One-ticker smoke test for the Massive filing index.

Pulls filings for a single ticker since a start date and prints a few rows,
so you can confirm the API key and the date/sort behaviour the catalog script relies on.

Run from the repo root:  python scripts/test_massive_one_ticker.py
"""
import os

from massive import RESTClient

TICKER = "AAPL"
SINCE = "2024-01-01"

# Read the key from the environment, then from the root .env file (same order as src/data.py).
key = os.environ.get("MASSIVE_API_KEY", "").strip()
if not key:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")) as f:
        key = next(line.split("=", 1)[1].strip().strip('"').strip("'")
                   for line in f if line.startswith("MASSIVE_API_KEY="))

client = RESTClient(key, retries=2)

# Date filter plus oldest-first sort, the same combination the catalog script uses.
rows = list(client.list_stocks_filings_index(
    ticker=TICKER, filing_date_gte=SINCE, sort="filing_date.asc", limit=5))

print(f"{TICKER} filings since {SINCE}: {len(rows)} rows")
for r in rows[:10]:
    print(f"  {r.filing_date}  {r.form_type:<10}  {r.ticker}  {r.cik}  {r.issuer_name}")
