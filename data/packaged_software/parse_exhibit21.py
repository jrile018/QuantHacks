"""Subsidiary lists from Exhibit 21 of each 10-K (checklist item 1.9).

Exhibit 21 is the only reliable source for the parent-child map here: the GLEIF pull came
back with a reporting exception for 117 of the 120 companies that have an LEI, so their
ownership structure is not disclosed there.

The exhibit is usually a two-column table of subsidiary name and jurisdiction, but the
layout varies: some filers use an HTML table, some a plain list, some add an ownership
percentage column. This reads the table rows when present and falls back to line parsing,
and records which method produced each row so the weaker ones can be reviewed.

Writes:
  output/subsidiaries.csv        one row per (parent, subsidiary, filing)
  output/subsidiary_counts.csv   one row per company: latest subsidiary count and filing

Caveats:
  - Exhibit 21 lists only subsidiaries the filer considers significant; it is not a complete
    group structure.
  - A filer may omit the exhibit entirely when it has no significant subsidiaries, which is
    recorded as no_exhibit_found rather than zero.
Standard library only. Read-only on the extract folder.
"""

from __future__ import annotations

import csv
import html
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEC = HERE / "extracts" / "sec"
COMPANIES = HERE / "packaged_software_companies.csv"
OUT = HERE / "output"
EX21_NAME_RE = re.compile(r"(ex[-_]?21|exhibit[-_]?21|subsidiar)", re.I)
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
# Jurisdictions as filers write them, used to tell a name column from a place column
JURISDICTION_RE = re.compile(
    r"^(?:[A-Z][a-z]+\s?){1,3}$|^(?:Delaware|California|Nevada|New York|Texas|Washington|"
    r"England|Ireland|India|Israel|Japan|Canada|Germany|France|Netherlands|Singapore|"
    r"Australia|Luxembourg|Cayman|Bermuda|China|Brazil|Mexico|Spain|Sweden|Switzerland)\b", re.I)
FOOTNOTE_RE = re.compile(r"^\(?\d{1,3}\)?[.*]?$|^[*†‡]+$")
NOISE_RE = re.compile(r"^(?:name|subsidiar|jurisdiction|state|country|entity|organization|"
                      r"place of|percentage|ownership|exhibit|list of|of incorporation)", re.I)


def clean(fragment: str) -> str:
    return " ".join(html.unescape(TAG_RE.sub(" ", fragment)).split())


def parse_table(raw: str) -> list[tuple[str, str]]:
    out = []
    for row in ROW_RE.findall(raw):
        cells = [clean(c) for c in CELL_RE.findall(row)]
        cells = [c for c in cells if c]
        if not cells or NOISE_RE.match(cells[0]):
            continue
        name = cells[0]
        jurisdiction = ""
        for c in cells[1:]:
            if JURISDICTION_RE.match(c):
                jurisdiction = c
                break
        # Footnote markers such as "(1)" sit in the name column of many exhibits
        if len(name) > 2 and not name.replace(".", "").isdigit() and not FOOTNOTE_RE.match(name):
            out.append((name, jurisdiction))
    return out


def parse_lines(raw: str) -> list[tuple[str, str]]:
    """Fallback for exhibits with no table: one subsidiary per line, place after a separator."""
    text = clean(raw)
    out = []
    for part in re.split(r"(?:\s{3,}|;|•)", text):
        part = part.strip(" .,-")
        if len(part) < 4 or NOISE_RE.match(part):
            continue
        m = re.match(r"(.+?)\s*[-–—(]\s*([A-Z][A-Za-z .]+)\)?$", part)
        if m and JURISDICTION_RE.match(m.group(2).strip()):
            out.append((m.group(1).strip(), m.group(2).strip()))
        elif re.search(r"\b(inc|llc|ltd|corp|gmbh|b\.?v\.?|s\.?a\.?|pty|limited|ag|oy|ab)\b\.?$", part, re.I):
            out.append((part, ""))
    return out


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    rows, per_company = [], []
    for c in companies:
        ticker = (c["ticker"] or "").strip()
        if not ticker:
            continue
        found = []
        for form in ("10-K", "10-K_A"):
            folder = SEC / ticker / form
            if not folder.exists():
                continue
            for doc in folder.glob("*/*"):
                if doc.is_file() and EX21_NAME_RE.search(doc.name):
                    found.append((doc.parent.name.split("_")[0], doc))
        latest_count, latest_date, status = "", "", "no_exhibit_found"
        for date, doc in sorted(found):
            raw = doc.read_bytes().decode("utf-8", errors="ignore")
            subs = parse_table(raw)
            method = "table"
            if not subs:
                subs = parse_lines(raw)
                method = "lines"
            # Drop duplicates while keeping order
            seen, unique = set(), []
            for name, juris in subs:
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    unique.append((name, juris))
            for name, juris in unique:
                rows.append({
                    "parent_cik": c["cik"].zfill(10), "parent_ticker": ticker,
                    "parent_name": c["name"], "filing_date": date,
                    "subsidiary_name": name, "jurisdiction": juris,
                    "parse_method": method,
                    "source_file": str(doc.relative_to(HERE)).replace("\\", "/"),
                })
            if unique:
                latest_count, latest_date, status = len(unique), date, f"parsed_{method}"
            elif status == "no_exhibit_found":
                status = "exhibit_found_but_unparsed"
        per_company.append({
            "cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
            "exhibit21_filings_found": len(found),
            "latest_subsidiary_count": latest_count,
            "latest_filing_date": latest_date,
            "status": status,
        })

    OUT.mkdir(parents=True, exist_ok=True)
    if rows:
        with (OUT / "subsidiaries.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    with (OUT / "subsidiary_counts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(per_company[0].keys()))
        w.writeheader()
        w.writerows(per_company)

    status_counts = defaultdict(int)
    for r in per_company:
        status_counts[r["status"]] += 1
    print(f"subsidiaries: {len(rows)} rows across {len({r['parent_ticker'] for r in rows})} companies")
    print("status:", dict(status_counts))
    by_method = defaultdict(int)
    for r in rows:
        by_method[r["parse_method"]] += 1
    print("parse method:", dict(by_method))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
