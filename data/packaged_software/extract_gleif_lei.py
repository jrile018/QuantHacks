"""LEI codes for the 168-company universe, from the public GLEIF API (no key).

Looks each company up by legal name and records the match with a confidence label, so a
wrong match can be spotted rather than silently trusted:
  exact          normalized GLEIF legal name equals the normalized SEC name
  single_result  one result returned, but the name differs
  multiple       several results; the first is recorded and the count kept
  none           no result

Writes output/company_lei.csv. Fills part of checklist section 1. UEI is not here: that
comes from SAM.gov, which needs an API key.
Standard library only.
"""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPANIES = HERE / "packaged_software_companies.csv"
CACHE = ROOT / "data" / "extracts" / "_cache" / "gleif"
OUT = HERE / "output" / "company_lei.csv"
API = "https://api.gleif.org/api/v1/lei-records"
FIELDS = ["cik", "ticker", "name", "lei", "gleif_legal_name", "match_confidence",
          "result_count", "legal_jurisdiction", "entity_status", "registration_status"]


def normalize(name: str) -> str:
    name = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|holdings?|group|the)\b", " ", name.lower())
    return re.sub(r"[^a-z0-9]+", "", name)


def lookup(name: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:80]
    cache_file = CACHE / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    query = urllib.parse.urlencode({"filter[entity.legalName]": name, "page[size]": 5})
    req = urllib.request.Request(f"{API}?{query}",
                                 headers={"User-Agent": "quanthacks-research", "Accept": "application/vnd.api+json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception:
            if attempt == 2:
                return {"data": [], "error": True}
            time.sleep(2 ** attempt)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.2)
    return data


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    rows = []
    for c in companies:
        data = lookup(c["name"])
        results = data.get("data", []) or []
        row = {"cik": c["cik"].zfill(10), "ticker": c["ticker"], "name": c["name"],
               "lei": "", "gleif_legal_name": "", "match_confidence": "none",
               "result_count": len(results), "legal_jurisdiction": "",
               "entity_status": "", "registration_status": ""}
        if results:
            first = results[0]
            attrs = first.get("attributes", {})
            entity = attrs.get("entity", {})
            gleif_name = entity.get("legalName", {}).get("name", "")
            row.update({
                "lei": attrs.get("lei", ""),
                "gleif_legal_name": gleif_name,
                "legal_jurisdiction": entity.get("legalJurisdiction", ""),
                "entity_status": entity.get("status", ""),
                "registration_status": attrs.get("registration", {}).get("status", ""),
            })
            if normalize(gleif_name) == normalize(c["name"]):
                row["match_confidence"] = "exact"
            elif len(results) == 1:
                row["match_confidence"] = "single_result"
            else:
                row["match_confidence"] = "multiple"
        rows.append(row)
        print(f"{c['ticker']}: {row['match_confidence']} {row['lei']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    print(f"Wrote {len(rows)} companies to {OUT}")
    print("match confidence:", dict(Counter(r["match_confidence"] for r in rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
