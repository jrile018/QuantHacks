"""Ticker reference details from the Massive API, for the 168-company universe.

Uses the existing MASSIVE_API_KEY. Fills checklist section 1 fields the SEC submissions
record does not carry, and supplies the company domain that the web-popularity, Wayback
and status-page sources all need before they can run.

Per company: homepage URL and domain, employee headcount, list (IPO) date, market cap,
share class and weighted shares outstanding, primary exchange, SIC code, and description.

Writes output/ticker_details.csv.

Caveats: headcount and market cap are point-in-time values as the vendor reports them
today, not a 2022-onward history, so they are a snapshot and not comparable across the
window. list_date is the listing date of the current ticker, which for a company that
came to market through a SPAC or changed ticker is not its original IPO date.
Standard library only.
"""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPANIES = HERE / "packaged_software_companies.csv"
CACHE = ROOT / "data" / "extracts" / "_cache" / "ticker_details"
OUT = HERE / "output" / "ticker_details.csv"
API = "https://api.massive.com/v3/reference/tickers/{ticker}"
FIELDS = ["cik", "ticker", "name", "vendor_name", "homepage_url", "domain", "total_employees",
          "list_date", "market_cap", "share_class_shares_outstanding",
          "weighted_shares_outstanding", "primary_exchange", "sic_code", "sic_description",
          "currency", "locale", "description_chars", "status"]


def api_key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("MASSIVE_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if key:
                return key
    raise SystemExit("MASSIVE_API_KEY is not set in .env")


def domain_of(url: str) -> str:
    if not url:
        return ""
    host = urllib.parse.urlsplit(url).hostname or ""
    return re.sub(r"^www\.", "", host)


def fetch(ticker: str, key: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / f"{ticker}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    url = API.format(ticker=urllib.parse.quote(ticker)) + f"?apiKey={key}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                data = {"results": {}, "status": "NOT_FOUND"}
                break
            if attempt == 2:
                return {"results": {}, "status": f"error {exc.code}"}
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == 2:
                return {"results": {}, "status": "error"}
            time.sleep(2 ** attempt)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.15)
    return data


def main() -> int:
    key = api_key()
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    rows = []
    for i, c in enumerate(companies, 1):
        ticker = (c["ticker"] or "").strip()
        row = {k: "" for k in FIELDS}
        row.update({"cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"]})
        if not ticker:
            row["status"] = "no ticker in universe file"
            rows.append(row)
            continue
        data = fetch(ticker, key)
        r = data.get("results") or {}
        if not r:
            row["status"] = data.get("status", "no results")
        else:
            row.update({
                "vendor_name": r.get("name", ""),
                "homepage_url": r.get("homepage_url", ""),
                "domain": domain_of(r.get("homepage_url", "")),
                "total_employees": r.get("total_employees", ""),
                "list_date": r.get("list_date", ""),
                "market_cap": r.get("market_cap", ""),
                "share_class_shares_outstanding": r.get("share_class_shares_outstanding", ""),
                "weighted_shares_outstanding": r.get("weighted_shares_outstanding", ""),
                "primary_exchange": r.get("primary_exchange", ""),
                "sic_code": r.get("sic_code", ""),
                "sic_description": r.get("sic_description", ""),
                "currency": r.get("currency_name", ""),
                "locale": r.get("locale", ""),
                "description_chars": len(r.get("description") or ""),
                "status": "ok",
            })
        rows.append(row)
        print(f"[{i}/{len(companies)}] {ticker}: {row['status']} {row['domain']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"\nWrote {len(rows)} companies to {OUT} ({ok} ok)")
    for field in ("domain", "total_employees", "list_date", "market_cap"):
        print(f"  {field}: {sum(1 for r in rows if r[field] not in ('', None))} filled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
