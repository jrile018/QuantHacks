"""Dated membership for the full SIC 7372 population (survivorship repair).

The 168-company universe is a list of companies that are listed today, so it omits any
software company that was public in 2022-2026 and then acquired, merged or delisted. This
builds the complete population from the SEC's SIC 7372 filers and records, for each one,
when it was in the market and how it left, so the panel can be restricted to companies
that were actually investable on each date.

For every SIC 7372 CIK it reads the SEC submissions record (cached) and derives:
  first_filing_in_window  earliest filing dated on or after 2022-01-01
  last_filing             latest filing of any kind
  deregistered            a Form 15 (deregistration) was filed on or after 2022-01-01
  delisted                a Form 25 (exchange delisting notice) was filed in the window
  status                  active | deregistered | delisted | stopped_filing
  exit_date               the deregistration or delisting date, or the last filing date

"active" means the company was still filing in mid-2026. "stopped_filing" with no Form 15
is ambiguous (it may have been acquired without a deregistration), so it is labelled rather
than assumed to mean acquired. Acquisition itself is not in the submissions record; the
8-K Item 2.01 completion reports and the merger filings already in the extract are the
evidence for it, and the membership table points to them via the cik.

Writes:
  output/membership_universe.csv     one row per company in the 168-company universe

Standard library only. Respects the SEC rate limit and caches responses.
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "output"
CACHE = ROOT / "data" / "packaged_software" / "extracts" / "identity" / "cache"
SIC_FILE = OUT / "sec_sic.csv"
CURRENT = HERE / "packaged_software_companies.csv"
WINDOW_START = "2022-01-01"
WINDOW_END = "2026-10-03"
ACTIVE_SINCE = "2026-06-01"
URL = "https://data.sec.gov/submissions/CIK{cik}.json"


def user_agent() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("SEC_USER_AGENT="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("SEC_USER_AGENT is not set in .env")


def fetch(cik: str, ua: str) -> dict | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"CIK{cik}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    req = urllib.request.Request(URL.format(cik=cik), headers={"User-Agent": ua, "Accept-Encoding": "identity"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            f.write_text(json.dumps(data), encoding="utf-8")
            time.sleep(0.12)
            return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == 3:
                return None
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == 3:
                return None
            time.sleep(2 ** attempt)
    return None


def all_filings(record: dict, ua: str) -> list[tuple[str, str]]:
    """(filing_date, form) across the recent list and every older page."""
    recent = record.get("filings", {}).get("recent", {})
    out = list(zip(recent.get("filingDate", []), recent.get("form", [])))
    for extra in record.get("filings", {}).get("files", []):
        page_file = CACHE / "files" / extra["name"]
        if page_file.exists():
            page = json.loads(page_file.read_text(encoding="utf-8"))
        else:
            req = urllib.request.Request(f"https://data.sec.gov/submissions/{extra['name']}",
                                         headers={"User-Agent": ua, "Accept-Encoding": "identity"})
            try:
                page = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
            except Exception:
                continue
            page_file.parent.mkdir(parents=True, exist_ok=True)
            page_file.write_text(json.dumps(page), encoding="utf-8")
            time.sleep(0.12)
        out += list(zip(page.get("filingDate", []), page.get("form", [])))
    return out


def main() -> int:
    ua = user_agent()
    current = {r["cik"].zfill(10) for r in csv.DictReader(CURRENT.open(encoding="utf-8")) if r["cik"]}
    population = []
    seen = set()
    for r in csv.DictReader(SIC_FILE.open(encoding="utf-8")):
        if r["sic"].strip().zfill(4) != "7372":
            continue
        cik = r["cik"].zfill(10)
        if cik in seen:
            continue
        seen.add(cik)
        population.append({"cik": cik, "name": r["name"]})
    print(f"SIC 7372 population: {len(population)}; current universe: {len(current)}")

    rows = []
    for i, p in enumerate(population, 1):
        record = fetch(p["cik"], ua)
        if record is None:
            rows.append({**p, "in_current_universe": "yes" if p["cik"] in current else "no",
                         "first_filing_in_window": "", "last_filing": "", "deregistered": "",
                         "delisted": "", "status": "no_submissions_record", "exit_date": "",
                         "filings_in_window": 0})
            continue
        filings = all_filings(record, ua)
        dated = sorted(d for d, _ in filings if d)
        in_window = sorted(d for d, _ in filings if WINDOW_START <= d <= WINDOW_END)
        forms = [(d, f) for d, f in filings if d >= WINDOW_START]
        dereg = sorted(d for d, f in forms if f in ("15-12G", "15-12B", "15-15D", "15F-12G", "15F-12B"))
        delist = sorted(d for d, f in forms if f in ("25", "25-NSE", "15-12B"))
        last = dated[-1] if dated else ""
        # Still filing in mid-2026 means still in the market, whatever earlier forms say.
        # A Form 25 is also filed for an exchange transfer (Palantir, Oracle, Shopify moved
        # listings and kept filing), and a Form 15 for a re-domicile (Atlassian), so neither
        # counts as an exit when filings continue afterwards.
        if last and last >= ACTIVE_SINCE:
            status, exit_date = "active", ""
        elif dereg and (not last or dereg[-1] >= last):
            status, exit_date = "deregistered", dereg[0]
        elif delist and (not last or delist[-1] >= last):
            status, exit_date = "delisted", delist[0]
        elif last:
            status, exit_date = "stopped_filing", last
        else:
            status, exit_date = "no_filings", ""
        rows.append({
            **p,
            "in_current_universe": "yes" if p["cik"] in current else "no",
            "first_filing_in_window": in_window[0] if in_window else "",
            "last_filing": last,
            "deregistered": dereg[0] if dereg else "",
            "delisted": delist[0] if delist else "",
            "status": status, "exit_date": exit_date,
            "filings_in_window": len(in_window),
        })
        if i % 50 == 0:
            print(f"  {i}/{len(population)}")

    OUT.mkdir(parents=True, exist_ok=True)
    fields = ["cik", "name", "in_current_universe", "first_filing_in_window", "last_filing",
              "deregistered", "delisted", "status", "exit_date", "filings_in_window"]
    # Scope is the 168-company universe only. Other SIC 7372 filers are not added (decision:
    # the universe stays at 168), so their membership is not written.
    universe_rows = [r for r in rows if r["in_current_universe"] == "yes"]
    with (OUT / "membership_universe.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(universe_rows, key=lambda r: r["name"]))
    missing = [r for r in rows if r["in_current_universe"] == "no"]

    from collections import Counter
    print("\nstatus of companies outside the current universe:", dict(Counter(r["status"] for r in missing)))
    print("status of the whole population:", dict(Counter(r["status"] for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
