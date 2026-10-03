"""GLEIF parent and subsidiary relationships for the companies that have an LEI.

Fills the parent-child item in checklist section 1. For each LEI in output/company_lei.csv
it asks GLEIF for the direct parent, the ultimate parent, and the direct children (public
API, no key). A 404 on a parent endpoint is recorded as one of two states, because they
mean different things:
  no_record             GLEIF holds no parent relationship for the entity
  reporting_exception   the entity has filed a reason it cannot or will not name its parent

Writes:
  output/company_gleif_parents.csv       one row per company with parent and child summaries
  output/company_gleif_children.csv      one row per (company, subsidiary LEI) for the children found

Caveat: GLEIF only records relationships the entities themselves report, and coverage of
subsidiaries is incomplete. A missing child is not evidence the company has no subsidiaries.
Standard library only.
"""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LEI_FILE = HERE / "output" / "company_lei.csv"
CACHE = ROOT / "data" / "extracts" / "_cache" / "gleif_parents"
OUT_PARENTS = HERE / "output" / "company_gleif_parents.csv"
OUT_CHILDREN = HERE / "output" / "company_gleif_children.csv"
BASE = "https://api.gleif.org/api/v1/lei-records/{lei}"
MAX_CHILDREN = 200  # GLEIF pages children; the first page covers all but the largest groups


def get_json(url: str, cache_name: str) -> tuple[str, dict | None]:
    """Return (status, body). status is 'ok', 'no_record', 'reporting_exception' or 'error'."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / f"{cache_name}.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        return cached["status"], cached.get("body")
    req = urllib.request.Request(url, headers={"User-Agent": "quanthacks-research", "Accept": "application/vnd.api+json"})
    status, body = "error", None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            status = "ok"
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                status = "no_record"
                break
            if attempt == 2:
                status = "error"
            else:
                time.sleep(2 ** attempt)
        except Exception:
            if attempt == 2:
                status = "error"
            else:
                time.sleep(2 ** attempt)
    # A parent that is a reporting exception returns 404 on the record's relationship link
    cache_file.write_text(json.dumps({"status": status, "body": body}), encoding="utf-8")
    time.sleep(0.25)
    return status, body


def entity_summary(record: dict) -> dict:
    attrs = record.get("attributes", {})
    entity = attrs.get("entity", {})
    return {
        "lei": attrs.get("lei", ""),
        "name": (entity.get("legalName") or {}).get("name", ""),
        "jurisdiction": entity.get("legalJurisdiction", ""),
        "country": (entity.get("legalAddress") or {}).get("country", ""),
    }


def parent_state(lei: str, kind: str) -> tuple[str, dict]:
    url = BASE.format(lei=lei) + f"/{kind}"
    status, body = get_json(url, f"{lei}_{kind}")
    if status == "ok" and body and body.get("data"):
        return "found", entity_summary(body["data"])
    if status == "no_record":
        # Distinguish a reporting exception from simply having no record
        rec_status, rec = get_json(BASE.format(lei=lei), f"{lei}_record")
        if rec_status == "ok" and rec:
            link = (rec["data"]["relationships"].get(kind) or {}).get("links", {}).get("reporting-exception")
            if link:
                return "reporting_exception", {}
        return "no_record", {}
    return status, {}


def children_of(lei: str) -> list[dict]:
    url = BASE.format(lei=lei) + f"/direct-children?page[size]={MAX_CHILDREN}"
    status, body = get_json(url, f"{lei}_direct_children")
    if status != "ok" or not body:
        return []
    return [entity_summary(r) for r in body.get("data", [])]


def main() -> int:
    with LEI_FILE.open(newline="", encoding="utf-8") as f:
        companies = [c for c in csv.DictReader(f) if c["lei"]]
    print(f"{len(companies)} companies with an LEI")

    parent_rows, child_rows = [], []
    for i, c in enumerate(companies, 1):
        lei = c["lei"]
        direct_state, direct = parent_state(lei, "direct-parent")
        ult_state, ult = parent_state(lei, "ultimate-parent")
        children = children_of(lei)
        parent_rows.append({
            "cik": c["cik"], "ticker": c["ticker"], "name": c["name"], "lei": lei,
            "direct_parent_status": direct_state,
            "direct_parent_lei": direct.get("lei", ""),
            "direct_parent_name": direct.get("name", ""),
            "direct_parent_country": direct.get("country", ""),
            "ultimate_parent_status": ult_state,
            "ultimate_parent_lei": ult.get("lei", ""),
            "ultimate_parent_name": ult.get("name", ""),
            "ultimate_parent_country": ult.get("country", ""),
            "direct_children_found": len(children),
        })
        for ch in children:
            child_rows.append({"ticker": c["ticker"], "parent_lei": lei, "child_lei": ch["lei"],
                               "child_name": ch["name"], "child_country": ch["country"]})
        print(f"[{i}/{len(companies)}] {c['ticker']}: parent={direct_state} children={len(children)}")

    OUT_PARENTS.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PARENTS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(parent_rows[0].keys()))
        w.writeheader()
        w.writerows(parent_rows)
    with OUT_CHILDREN.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "parent_lei", "child_lei", "child_name", "child_country"])
        w.writeheader()
        w.writerows(child_rows)

    from collections import Counter
    print(f"\nDirect parent status: {dict(Counter(r['direct_parent_status'] for r in parent_rows))}")
    print(f"Ultimate parent status: {dict(Counter(r['ultimate_parent_status'] for r in parent_rows))}")
    print(f"Subsidiary links found: {len(child_rows)} across {sum(1 for r in parent_rows if r['direct_children_found'])} companies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
