"""Rebuild the company universe from SEC data.

1. Takes every CIK that filed an 8-K in the local filings catalog.
2. Looks up each CIK's SIC code from SEC's public submissions API.
3. Writes sec_sic.csv (cik, name, sic, sic_description) to output/.

Then keep SIC 7372 with pull_federal_contracts.py:
    python data/packaged_software/pull_federal_contracts.py --input data/packaged_software/output/sec_sic.csv

SEC asks every client to identify itself in the User-Agent header:
    set SEC_USER_AGENT="Your Name your-email@example.com"
Raw responses are cached in cache/sec_submissions/, so reruns skip finished CIKs.
Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parent / "processed" / "filings_catalog.sqlite"
OUT_DIR = HERE / "output"
CACHE_DIR = HERE / "cache" / "sec_submissions"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
# SEC allows up to 10 requests per second; stay under that.
MIN_INTERVAL = 0.12


def load_8k_ciks(catalog: Path) -> list[str]:
    """Distinct 10-digit CIKs with at least one 8-K or 8-K/A in the catalog."""
    con = sqlite3.connect(catalog)
    try:
        rows = con.execute(
            "SELECT DISTINCT company FROM agg WHERE form IN ('8-K', '8-K/A') ORDER BY company"
        ).fetchall()
    finally:
        con.close()
    return [str(r[0]).zfill(10) for r in rows]


def fetch_submissions(cik: str, user_agent: str) -> dict:
    """Return the SEC submissions JSON for one CIK, using the on-disk cache when present."""
    cache_file = CACHE_DIR / f"CIK{cik}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    req = urllib.request.Request(
        SUBMISSIONS_URL.format(cik=cik),
        headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:  # CIK has no submissions record
                data = {}
                break
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-companies", type=int, default=None, help="Only process the first N CIKs (for testing)")
    args = parser.parse_args()

    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not user_agent:
        print("Set SEC_USER_AGENT to 'Your Name your-email@example.com' before running.", file=sys.stderr)
        return 1

    ciks = load_8k_ciks(CATALOG)
    if args.max_companies:
        ciks = ciks[: args.max_companies]
    print(f"Looking up SIC codes for {len(ciks)} CIKs that filed an 8-K")

    rows: list[dict] = []
    failures: list[dict] = []
    last_call = 0.0
    for i, cik in enumerate(ciks, 1):
        cached = (CACHE_DIR / f"CIK{cik}.json").exists()
        if not cached:
            wait = MIN_INTERVAL - (time.monotonic() - last_call)
            if wait > 0:
                time.sleep(wait)
            last_call = time.monotonic()
        try:
            data = fetch_submissions(cik, user_agent)
            rows.append({
                "cik": cik,
                "name": data.get("name", ""),
                "sic": (data.get("sic") or "").strip(),
                "sic_description": data.get("sicDescription", ""),
            })
        except Exception as exc:
            failures.append({"cik": cik, "error": str(exc)})
            print(f"[{i}/{len(ciks)}] {cik}: FAILED ({exc})", file=sys.stderr)
            continue
        if i % 500 == 0:
            print(f"[{i}/{len(ciks)}] done")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "sec_sic.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["cik", "name", "sic", "sic_description"])
        writer.writeheader()
        writer.writerows(rows)
    if failures:
        with (OUT_DIR / "sec_sic_failures.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["cik", "error"])
            writer.writeheader()
            writer.writerows(failures)

    with_sic = sum(1 for r in rows if r["sic"])
    print(f"Wrote {len(rows)} rows to {OUT_DIR / 'sec_sic.csv'}")
    print(f"  with SIC: {with_sic}  without SIC: {len(rows) - with_sic}  failed: {len(failures)}")
    sw = sum(1 for r in rows if r["sic"] == "7372")
    print(f"  SIC 7372 (prepackaged software): {sw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
