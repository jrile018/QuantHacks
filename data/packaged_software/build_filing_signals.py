"""Filing-based signals for the 168-company universe, from data already on disk.

Two sources, no new downloads:
  1. Cached SEC submissions records (data/packaged_software/extracts/identity/cache/): counts of insider
     trades (Form 3/4), ownership filings (SC 13D/G), late-filing notices (NT 10-K/10-Q),
     SEC comment letters (CORRESP, UPLOAD), over the last 24 months.
  2. The latest 10-K in data/packaged_software/extracts/sec/<TICKER>/10-K/: text flags for Item 1C cyber
     governance, going-concern doubt, material weakness, and customer concentration.

Writes output/filing_signals.csv. Standard library only.
"""

from __future__ import annotations

import csv
import html
import json
import re
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / "extracts" / "identity" / "cache"
SEC = HERE / "extracts" / "sec"
COMPANIES = HERE / "packaged_software_companies.csv"
OUT = HERE / "output" / "filing_signals.csv"

WINDOW_START = "2022-01-01"
UA_FILE = ROOT / ".env"
FILES_CACHE = CACHE / "files"
FORM_GROUPS = {
    "form3_4_insider_filings": {"3", "4", "4/A", "3/A"},
    "sc13d_13g_ownership_filings": {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"},
    "late_filing_notices": {"NT 10-K", "NT 10-Q", "NT 10-K/A", "NT 10-Q/A"},
    "sec_comment_letters": {"CORRESP", "UPLOAD"},
    # Registration statements: new securities issued (S-1, S-3) and employee plan shares (S-8)
    "registration_statements": {"S-1", "S-1/A", "S-3", "S-3/A", "S-8", "S-8/A"},
}
TEXT_FLAGS = {
    "item_1c_cyber_section": re.compile(r"item\s*1c\b", re.I),
    "going_concern_doubt": re.compile(r"substantial\s+doubt[^.]{0,80}going\s+concern|going\s+concern", re.I),
    "material_weakness": re.compile(r"material\s+weakness", re.I),
    "customer_over_10pct": re.compile(r"(?:accounted|represent(?:ed|s)?)\s+(?:for\s+)?(?:approximately\s+)?(?:more\s+than\s+)?\d{1,2}(?:\.\d)?%\s+of\s+(?:our\s+)?(?:total\s+)?(?:revenue|net revenue|revenues)", re.I),
}


def user_agent() -> str:
    for line in UA_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("SEC_USER_AGENT="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("SEC_USER_AGENT is not set in .env")


def fetch_older_pages(cik: str, record: dict, ua: str) -> list[dict]:
    """Older submissions pages (the 'files' list) are fetched once and cached."""
    pages = []
    FILES_CACHE.mkdir(parents=True, exist_ok=True)
    for extra in record.get("filings", {}).get("files", []):
        name = extra["name"]
        cache_file = FILES_CACHE / name
        if not cache_file.exists():
            req = urllib.request.Request(f"https://data.sec.gov/submissions/{name}",
                                         headers={"User-Agent": ua, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                cache_file.write_bytes(resp.read())
            time.sleep(0.12)
        pages.append(json.loads(cache_file.read_text(encoding="utf-8")))
    return pages


def all_filings(cik: str, ua: str) -> tuple[list[str], list[str]]:
    f = CACHE / f"CIK{cik}.json"
    if not f.exists():
        return [], []
    record = json.loads(f.read_text(encoding="utf-8"))
    recent = record.get("filings", {}).get("recent", {})
    forms = list(recent.get("form", []))
    dates = list(recent.get("filingDate", []))
    for page in fetch_older_pages(cik, record, ua):
        forms += page.get("form", [])
        dates += page.get("filingDate", [])
    return forms, dates


def cached_counts(cik: str, ua: str) -> dict[str, int]:
    counts = {k: 0 for k in FORM_GROUPS}
    counts["latest_filing_in_cache"] = ""
    forms, dates = all_filings(cik, ua)
    for form, date in zip(forms, dates):
        if date < WINDOW_START:
            continue
        for key, group in FORM_GROUPS.items():
            if form in group:
                counts[key] += 1
    if dates:
        counts["latest_filing_in_cache"] = max(dates)
    return counts


def latest_10k_text(ticker: str) -> str:
    folders = sorted((SEC / ticker / "10-K").glob("*/*.htm*")) if (SEC / ticker / "10-K").exists() else []
    if not folders:
        return ""
    raw = folders[-1].read_bytes().decode("utf-8", errors="ignore")
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", raw)).split())


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))
    ua = user_agent()
    rows = []
    for c in companies:
        cik = c["cik"].zfill(10)
        ticker = c["ticker"].strip()
        row = {"cik": cik, "ticker": ticker, "name": c["name"], "window_start": WINDOW_START}
        row.update(cached_counts(cik, ua))
        text = latest_10k_text(ticker)
        row["latest_10k_text_available"] = "yes" if text else "no"
        for flag, rx in TEXT_FLAGS.items():
            row[flag] = len(rx.findall(text)) if text else ""
        rows.append(row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} companies to {OUT}")
    for key in list(FORM_GROUPS) + list(TEXT_FLAGS):
        n = sum(1 for r in rows if isinstance(r[key], int) and r[key] > 0)
        print(f"  {key}: {n} companies with at least one")
    print(f"  latest 10-K text available: {sum(1 for r in rows if r['latest_10k_text_available'] == 'yes')} of {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
