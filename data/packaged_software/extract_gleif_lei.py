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
CACHE = HERE / "extracts" / "_cache" / "gleif"
OUT = HERE / "output" / "company_lei.csv"
API = "https://api.gleif.org/api/v1/lei-records"
FIELDS = ["cik", "ticker", "name", "lei", "gleif_legal_name", "match_confidence",
          "result_count", "legal_jurisdiction", "entity_status", "registration_status"]


def normalize(name: str) -> str:
    name = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|holdings?|group|the)\b", " ", name.lower())
    return re.sub(r"[^a-z0-9]+", "", name)


# The universe file carries the security name, not the entity name: "Appian Corporation
# Class A Common Stock". GLEIF matches on legal entity name, so the security wording has to
# come off or the lookup returns nothing. This was why 48 companies had no LEI.
SECURITY_SUFFIX_RE = re.compile(
    r"\s*(?:Class\s+[A-Z]\s+)?(?:"
    r"Common\s+Stock|Common\b|Ordinary\s+Shares?|Common\s+Shares?|Capital\s+Stock|"
    r"American\s+Depositary\s+Shares?|subordinate\s+voting\s+shares?|"
    r"Warrants?|Units?|Rights?"
    r")(?:\s*,?\s*(?:no\s+par\s+value|par\s+value.*)?)?\s*$", re.I)
# A trailing bare share class ("Marchex, Inc. Class B") or state tag ("Progress Software Corp (DE)")
TRAILING_NOISE_RE = re.compile(r"\s*(?:Class\s+[A-Z]|\([A-Z]{2}\))\s*$")


def pick_best(candidates: list[dict], target_key: str) -> list[dict]:
    """Keep candidates whose normalized name matches, best first.

    Normalizing strips the legal form, so a dormant entity named exactly "Microsoft" ties
    with "MICROSOFT CORPORATION". The tie-break is the LEI registration: the dormant one is
    LAPSED and the operating company is ISSUED. Without this, Microsoft was assigned a
    lapsed LEI belonging to a different entity.
    """
    matches = [r for r in candidates
               if normalize((r.get("attributes", {}).get("entity", {})
                             .get("legalName", {}) or {}).get("name", "")) == target_key]

    def score(r: dict) -> tuple:
        attrs = r.get("attributes", {})
        reg = (attrs.get("registration", {}) or {}).get("status", "")
        entity_status = (attrs.get("entity", {}) or {}).get("status", "")
        return (reg != "ISSUED", entity_status != "ACTIVE")

    return sorted(matches, key=score)


def search_name(name: str) -> str:
    """The entity name to query GLEIF with, without the security description."""
    cleaned = name
    for _ in range(3):  # "... Inc. Class A Common Stock" needs more than one pass
        stripped = TRAILING_NOISE_RE.sub("", SECURITY_SUFFIX_RE.sub("", cleaned)).strip().rstrip(",")
        if stripped == cleaned:
            break
        cleaned = stripped
    return cleaned or name


def lookup(name: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:80]
    cache_file = CACHE / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    # filter[entity.legalName] matches whole words, so the abbreviation in "Microsoft Corp"
    # misses GLEIF's "MICROSOFT CORPORATION". The fallback drops the legal suffix entirely
    # and asks for more rows, and the caller keeps only an exact normalized match.
    if name.endswith("\x00bare"):
        name = name[: -len("\x00bare")]
        query = urllib.parse.urlencode({"filter[entity.legalName]": name, "page[size]": 25})
    else:
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
        query = search_name(c["name"])
        data = lookup(query)
        results = data.get("data", []) or []
        used_fulltext = False
        single_word_fallback = False
        if not results:
            # Drop the legal suffix ("Microsoft Corp" -> "Microsoft") and keep only an exact
            # normalized match, so the looser query cannot attach an unrelated entity
            bare = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|holdings?)\b\.?",
                          " ", query, flags=re.I)
            bare = " ".join(bare.split()).rstrip(",")
            if bare and bare.lower() != query.lower():
                data = lookup(bare + "\x00bare")
                results = pick_best(data.get("data", []) or [], normalize(query))
                used_fulltext = bool(results)
                # A one-word name is too generic for this fallback: "Meridian Holdings Inc."
                # matched the unrelated "MERIDIAN CORPORATION". Those need a human look.
                single_word_fallback = used_fulltext and len(bare.split()) == 1
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
            if normalize(gleif_name) == normalize(query):
                # The fulltext fallback only keeps exact normalized matches, but say so
                if single_word_fallback:
                    row["match_confidence"] = "suffix_drop_one_word_CHECK"
                elif used_fulltext:
                    row["match_confidence"] = "exact_via_suffix_drop"
                else:
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
