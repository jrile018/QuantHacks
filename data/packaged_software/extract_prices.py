"""Daily adjusted stock prices for the 168-company universe, 2022 onward, from Massive.

Uses MASSIVE_API_KEY from .env. One aggregates request per ticker covers the whole window.
Adjusted prices account for splits and dividends, so returns computed from them are total
returns. Each ticker's response is cached under data/packaged_software/extracts/_cache/prices/.

Writes data/packaged_software/extracts/prices/daily_bars.csv with one row per ticker per trading day:
  ticker, date, open, high, low, close, volume, vwap, transactions

Tickers with no bars come back with a status row in data/packaged_software/extracts/prices/price_coverage.csv,
so a missing price is visible rather than silently absent.
Standard library only.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPANIES = HERE / "packaged_software_companies.csv"
CACHE = HERE / "extracts" / "_cache" / "prices"
OUT_DIR = HERE / "extracts" / "prices"
START = "2022-01-01"
API = "https://api.massive.com/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
WORKERS = 5
FIELDS = ["ticker", "date", "open", "high", "low", "close", "volume", "vwap", "transactions"]


def api_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("MASSIVE_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if key:
                return key
    raise SystemExit("MASSIVE_API_KEY is not set in .env")


def fetch(ticker: str, end: str, key: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / f"{ticker}_{START}_{end}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    url = API.format(ticker=urllib.parse.quote(ticker), start=START, end=end) + \
        f"?adjusted=true&sort=asc&limit=50000&apiKey={key}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                data = {"status": "NOT_FOUND", "results": []}
                break
            if exc.code == 429 or attempt == 3:
                return {"status": f"http {exc.code}", "results": []}
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == 3:
                return {"status": "request failed", "results": []}
            time.sleep(2 ** attempt)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def to_date(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date().isoformat()


def main() -> int:
    key = api_key()
    end = dt.date.today().isoformat()
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        tickers = [(c["ticker"] or "").strip() for c in csv.DictReader(f)]
    tickers = sorted({t for t in tickers if t})
    print(f"{len(tickers)} tickers, {START} to {end}")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        responses = list(pool.map(lambda t: (t, fetch(t, end, key)), tickers))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bars, coverage = [], []
    for ticker, data in responses:
        results = data.get("results") or []
        for b in results:
            bars.append({
                "ticker": ticker, "date": to_date(b["t"]),
                "open": b.get("o", ""), "high": b.get("h", ""), "low": b.get("l", ""),
                "close": b.get("c", ""), "volume": b.get("v", ""), "vwap": b.get("vw", ""),
                "transactions": b.get("n", ""),
            })
        coverage.append({
            "ticker": ticker,
            "status": "ok" if results else data.get("status", "no bars"),
            "bars": len(results),
            "first_date": to_date(results[0]["t"]) if results else "",
            "last_date": to_date(results[-1]["t"]) if results else "",
        })

    with (OUT_DIR / "daily_bars.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(sorted(bars, key=lambda r: (r["ticker"], r["date"])))
    with (OUT_DIR / "price_coverage.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "status", "bars", "first_date", "last_date"])
        w.writeheader()
        w.writerows(coverage)

    ok = sum(1 for c in coverage if c["status"] == "ok")
    print(f"\nWrote {len(bars)} bars for {ok} of {len(tickers)} tickers")
    print(f"Tickers with no bars: {[c['ticker'] for c in coverage if c['status'] != 'ok']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
