"""Download SEC filings and XBRL financials for the packaged-software companies.

For each company in packaged_software_companies.csv:
  - reads its EDGAR submissions record (including older "files" pages),
  - keeps the core forms filed on or after --start,
  - downloads each filing's primary document,
  - downloads the company's XBRL companyfacts JSON (standardized financials).

Output (data/extracts/sec/):
  <TICKER>/<FORM>/<YYYY-MM-DD>_<accession>/<primary document>
  <TICKER>/companyfacts.json
  filings_index.csv   one row per filing with its local path and status
  manifest.json       run summary

Re-running skips anything already on disk.

Usage (from the repo root). Set SEC_USER_AGENT in .env to your name and real email:
    python data/packaged_software/extract_sec_filings.py
    python data/packaged_software/extract_sec_filings.py --with-exhibits --refresh-facts

Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path

from sec_common import env_value

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPANIES = HERE / "packaged_software_companies.csv"
OUT = ROOT / "data" / "extracts" / "sec"
SUBMISSIONS = "https://data.sec.gov/submissions/{name}"
COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"
CORE_FORMS = {
    "10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A",
    "DEF 14A", "S-1", "S-1/A", "S-3", "S-3/A", "S-8",
    "20-F", "20-F/A", "40-F", "40-F/A", "6-K", "6-K/A",
    # Deal documents: registration statements and merger proxies (checklist section 5)
    "S-4", "S-4/A", "DEFM14A", "PREM14A", "DEFA14A", "425",
}
# SEC allows 10 requests per second; stay under it.
MIN_INTERVAL = 0.12
_last_call = 0.0
INDEX_FIELDS = ["ticker", "cik", "form", "filing_date", "acceptance_datetime", "accession", "primary_document", "document_role", "local_path", "status"]


def get(url: str, user_agent: str) -> bytes:
    """Rate-limited GET with retries. Raises on final failure."""
    global _last_call
    wait = MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
    for attempt in range(4):
        try:
            wait = MIN_INTERVAL - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            _last_call = time.monotonic()
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404 or attempt == 3:
                raise
        except Exception:
            if attempt == 3:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def safe_form(form: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]+", "_", form)


def collect_filings(cik: str, user_agent: str, start: str) -> list[dict]:
    """All core-form filings for one CIK on or after `start`, across every submissions page."""
    cik_int = str(int(cik))
    record = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json", user_agent))
    pages = [record.get("filings", {}).get("recent", {})]
    for extra in record.get("filings", {}).get("files", []):
        pages.append(json.loads(get(SUBMISSIONS.format(name=extra["name"]), user_agent)))

    filings = []
    for page in pages:
        forms = page.get("form", [])
        for i, form in enumerate(forms):
            date = page["filingDate"][i]
            if form not in CORE_FORMS or date < start:
                continue
            filings.append({
                "cik": cik,
                "cik_int": cik_int,
                "form": form,
                "filing_date": date,
                "accession": page["accessionNumber"][i],
                "primary_document": page["primaryDocument"][i],
                "acceptance_datetime": (page.get("acceptanceDateTime", [])[i]
                                        if i < len(page.get("acceptanceDateTime", [])) else ""),
            })
    return filings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2022-01-01", help="Earliest filing date to keep, YYYY-MM-DD")
    parser.add_argument("--end", default=dt.date.today().isoformat(), help="Last filing date, YYYY-MM-DD")
    parser.add_argument("--max-companies", type=int, default=None, help="Only process the first N (for testing)")
    parser.add_argument("--skip-facts", action="store_true", help="Skip companyfacts downloads")
    parser.add_argument("--refresh-facts", action="store_true", help="Refresh Company Facts even when cached")
    parser.add_argument("--with-exhibits", action="store_true", help="Also download linked press-release / contract exhibits in current-report filings")
    parser.add_argument("--companies", type=Path, default=COMPANIES, help="CSV with cik and ticker columns")
    args = parser.parse_args()
    if dt.date.fromisoformat(args.end) < dt.date.fromisoformat(args.start):
        parser.error("End must be on/after start")

    user_agent = env_value("SEC_USER_AGENT")
    if not user_agent:
        print("Set SEC_USER_AGENT to 'Your Name your-email@example.com' before running.", file=sys.stderr)
        return 1

    with args.companies.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))
    if args.max_companies:
        companies = companies[: args.max_companies]
    OUT.mkdir(parents=True, exist_ok=True)

    index_rows: list[dict] = []
    failures: list[dict] = []
    downloaded = skipped = 0
    print(f"{len(companies)} companies, filings on or after {args.start}")

    for i, c in enumerate(companies, 1):
        ticker = (c["ticker"] or c["cik"]).strip()
        cik = c["cik"].zfill(10)
        company_dir = OUT / ticker
        company_dir.mkdir(parents=True, exist_ok=True)
        try:
            filings = [f for f in collect_filings(cik, user_agent, args.start) if f["filing_date"] <= args.end]
        except Exception as exc:
            failures.append({"ticker": ticker, "item": "submissions", "error": str(exc)})
            print(f"[{i}/{len(companies)}] {ticker}: submissions FAILED ({exc})", file=sys.stderr)
            continue

        if not args.skip_facts:
            facts = company_dir / "companyfacts.json"
            if args.refresh_facts or not facts.exists():
                try:
                    facts.write_bytes(get(COMPANYFACTS.format(cik=cik), user_agent))
                except Exception as exc:
                    failures.append({"ticker": ticker, "item": "companyfacts", "error": str(exc)})

        for fl in filings:
            folder = company_dir / safe_form(fl["form"]) / f"{fl['filing_date']}_{fl['accession']}"
            local = folder / fl["primary_document"]
            row = {
                "ticker": ticker, "cik": cik, "form": fl["form"], "filing_date": fl["filing_date"],
                "acceptance_datetime": fl.get("acceptance_datetime", ""), "document_role": "primary",
                "accession": fl["accession"], "primary_document": fl["primary_document"],
                "local_path": str(local.relative_to(ROOT)).replace("\\", "/"), "status": "",
            }
            if local.exists():
                row["status"] = "exists"
                skipped += 1
            else:
                url = ARCHIVE.format(cik_int=fl["cik_int"], acc_nodash=fl["accession"].replace("-", ""), doc=fl["primary_document"])
                try:
                    body = get(url, user_agent)
                    folder.mkdir(parents=True, exist_ok=True)
                    local.write_bytes(body)
                    row["status"] = "downloaded"
                    downloaded += 1
                except Exception as exc:
                    row["status"] = f"failed: {exc}"
                    failures.append({"ticker": ticker, "item": f"{fl['form']} {fl['accession']}", "error": str(exc)})
            index_rows.append(row)
            if args.with_exhibits and local.exists() and fl["form"] in ("8-K", "8-K/A", "6-K", "6-K/A"):
                base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{fl['accession'].replace('-', '')}/"
                content = local.read_text(encoding="utf-8", errors="replace")
                links = re.findall(r'href\s*=\s*[\"\']([^\"\']+)[\"\']', content, re.I)
                exhibits = set()
                for link in links:
                    absolute = urllib.parse.urljoin(base, html.unescape(link))
                    parsed = urllib.parse.urlparse(absolute)
                    filename = Path(parsed.path).name
                    # Exhibit 2.x holds merger and purchase agreements (checklist item 5)
                    if (absolute.startswith(base) and re.search(r'(?:ex(?:hibit)?[-_ ]?(?:99|10|2)|press[-_]?release)', filename, re.I)
                            and filename != fl["primary_document"] and filename.lower().endswith((".htm", ".html", ".txt"))):
                        exhibits.add(filename)
                for filename in sorted(exhibits):
                    exhibit = folder / filename
                    exhibit_row = {**row, "primary_document": filename, "document_role": "linked_exhibit",
                                   "local_path": str(exhibit.relative_to(ROOT)).replace("\\", "/")}
                    try:
                        if exhibit.exists():
                            skipped += 1
                            exhibit_row["status"] = "exists"
                        else:
                            exhibit.write_bytes(get(base + filename, user_agent))
                            downloaded += 1
                            exhibit_row["status"] = "downloaded"
                    except Exception as exc:
                        exhibit_row["status"] = "failed"
                        failures.append({"ticker": ticker, "item": filename, "error": type(exc).__name__})
                    index_rows.append(exhibit_row)
        print(f"[{i}/{len(companies)}] {ticker}: {len(filings)} filings")

    with (OUT / "filings_index.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(index_rows)
    if failures:
        with (OUT / "failures.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ticker", "item", "error"])
            writer.writeheader()
            writer.writerows(failures)

    manifest = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "companies": len(companies),
        "forms": sorted(CORE_FORMS),
        "start": args.start,
        "end": args.end,
        "with_linked_exhibits": args.with_exhibits,
        "filings_listed": len(index_rows),
        "downloaded": downloaded,
        "already_on_disk": skipped,
        "failures": len(failures),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
