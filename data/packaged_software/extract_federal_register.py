"""Federal Register documents mentioning each company, 2022 onward (public API, no key).

Fills part of checklist section 12. The Federal Register full-text search is the
classification step the checklist calls for: a document is linked to a company only when
it mentions that company's name.

Writes:
  output/federal_register_documents.csv   one row per (company, document)
  output/federal_register_by_company.csv  one row per company, with counts by document type

Matching caveat: this is a full-text name search, so a common company name can pull in
unrelated documents, and a document that discusses a company without naming it is missed.
Each row keeps the document title and URL so a match can be checked.
Standard library only.
"""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPANIES = HERE / "packaged_software_companies.csv"
CACHE = HERE / "extracts" / "_cache" / "federal_register"
OUT_DOCS = HERE / "output" / "federal_register_documents.csv"
OUT_COMPANY = HERE / "output" / "federal_register_by_company.csv"
API = "https://www.federalregister.gov/api/v1/documents.json"
START = "2022-01-01"
# Document types the API returns: Rule, Proposed Rule, Notice, Presidential Document
TYPES = ["Rule", "Proposed Rule", "Notice", "Presidential Document"]
SUFFIX_RE = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|llc|plc|holdings?|group|the)\b\.?", re.IGNORECASE)


def search_name(name: str) -> str:
    """Keep the full legal name, including its suffix.

    Dropping the suffix made short names match common words: searching "Aware" or "BOX"
    returned 10,000 documents each, and "Block" 3,110, none of which were about the
    company. Keeping "Aware, Inc." makes the phrase search specific. Only the punctuation
    that breaks the API's phrase query is removed.
    """
    cleaned = re.sub(r"[^\w&'. -]+", " ", name)
    return " ".join(cleaned.split()) or name


def fetch(term: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")[:80]
    cache_file = CACHE / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    params = [
        ("conditions[term]", f'"{term}"'),
        ("conditions[publication_date][gte]", START),
        ("per_page", "100"),
        ("order", "newest"),
    ]
    for field in ("document_number", "title", "type", "publication_date", "agencies", "html_url"):
        params.append(("fields[]", field))
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "quanthacks-research", "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception:
            if attempt == 2:
                return {"results": [], "count": 0, "error": True}
            time.sleep(2 ** attempt)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.3)
    return data


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    doc_rows: list[dict] = []
    totals: dict[str, int] = {}
    for i, c in enumerate(companies, 1):
        term = search_name(c["name"])
        data = fetch(term)
        results = data.get("results") or []
        totals[c["ticker"]] = data.get("count", len(results))
        for d in results:
            doc_rows.append({
                "cik": c["cik"].zfill(10), "ticker": c["ticker"], "name": c["name"],
                "search_term": term,
                "document_number": d.get("document_number", ""),
                "publication_date": d.get("publication_date", ""),
                "type": d.get("type", ""),
                "title": (d.get("title") or "").replace("\n", " "),
                "agencies": "; ".join(a.get("name", "") for a in (d.get("agencies") or [])),
                "html_url": d.get("html_url", ""),
            })
        print(f"[{i}/{len(companies)}] {c['ticker']}: {totals[c['ticker']]} documents")

    OUT_DOCS.parent.mkdir(parents=True, exist_ok=True)
    fields = ["cik", "ticker", "name", "search_term", "document_number", "publication_date",
              "type", "title", "agencies", "html_url"]
    with OUT_DOCS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(doc_rows)

    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for r in doc_rows:
        by_ticker[r["ticker"]].append(r)
    with OUT_COMPANY.open("w", newline="", encoding="utf-8") as f:
        cols = ["cik", "ticker", "name", "search_term", "total_matching_documents", "documents_returned"] + \
               [t.lower().replace(" ", "_") for t in TYPES]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in companies:
            mine = by_ticker.get(c["ticker"], [])
            row = {
                "cik": c["cik"].zfill(10), "ticker": c["ticker"], "name": c["name"],
                "search_term": search_name(c["name"]),
                "total_matching_documents": totals.get(c["ticker"], 0),
                "documents_returned": len(mine),
            }
            for t in TYPES:
                row[t.lower().replace(" ", "_")] = sum(1 for r in mine if r["type"] == t)
            w.writerow(row)

    with_docs = sum(1 for c in companies if totals.get(c["ticker"], 0) > 0)
    print(f"Wrote {len(doc_rows)} document rows; {with_docs} of {len(companies)} companies have at least one")
    print("Note: documents_returned caps at 100 per company; total_matching_documents is the real count")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
