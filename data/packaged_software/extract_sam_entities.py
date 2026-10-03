"""SAM.gov entity registration data (UEI, CAGE) for the 168-company universe.

Fills the UEI field in checklist section 1 and the SAM entity data line in section 11.
Reads the SAM.gov key from .env, accepting either SAM_GOV_API_KEY (preferred, a valid
shell variable name) or SAM.GOV_KEY (the name currently in the file; a dot cannot be used
with a normal shell export, so the conventional name is read first).

The API's legalBusinessName search is loose: querying "Adobe Inc." also returns
"Adobe Lumber, Inc." and "ADOBE PRECISION GEAR, INC.". So each returned record is scored
against the company name and only an exact normalized match is recorded as the entity:
  exact            normalized SAM legal name equals the normalized company name
  prefix           SAM name starts with the company name (e.g. a divisional registration)
  unmatched        records came back, none matched; the candidates are kept for review
  none             no records returned

Writes:
  output/sam_entities.csv            one row per company, best match plus confidence
  output/sam_entity_candidates.csv   every returned record, so a miss can be checked

A company with no SAM registration is normal: only entities that do business with the
federal government register.
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPANIES = HERE / "packaged_software_companies.csv"
CACHE = ROOT / "data" / "extracts" / "_cache" / "sam_entities"
OUT = HERE / "output" / "sam_entities.csv"
OUT_CANDIDATES = HERE / "output" / "sam_entity_candidates.csv"
API = "https://api.sam.gov/entity-information/v4/entities"
KEY_NAMES = ("SAM_GOV_API_KEY", "SAM.GOV_KEY")
WORKERS = 10
FIELDS = ["cik", "ticker", "name", "uei", "cage_code", "sam_legal_name", "match_confidence",
          "records_returned", "registration_status", "registration_expiration",
          "entity_structure", "state_of_incorporation", "physical_city", "physical_state",
          "primary_naics", "status"]
SUFFIX_RE = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|holdings?|group|the)\b\.?", re.I)


def read_key() -> str:
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    for name in KEY_NAMES:
        if values.get(name):
            return values[name]
    raise SystemExit(f"No SAM.gov key in .env. Add one of: {', '.join(KEY_NAMES)}")


def normalize(name: str) -> str:
    stripped = SUFFIX_RE.sub(" ", name.lower())
    return re.sub(r"[^a-z0-9]+", "", stripped)


def search_term(name: str) -> str:
    """Query SAM without the legal suffix.

    The suffix makes the search fail outright rather than match loosely: searching
    "ACI Worldwide, Inc." returns 0 records, while "ACI Worldwide" returns the real
    registration, which SAM lists as "ACI Worldwide Corp.". Since normalize() strips the
    suffix on both sides, dropping it from the query loses no matching precision.
    """
    stripped = SUFFIX_RE.sub(" ", name)
    cleaned = re.sub(r"[^\w&' -]+", " ", stripped)
    return " ".join(cleaned.split()) or name


def fetch(name: str, key: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / (re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:80] + ".json")
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    query = urllib.parse.urlencode({
        "api_key": key,
        "legalBusinessName": search_term(name),
        "includeSections": "entityRegistration,coreData",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{API}?{query}", timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            # 429 means the daily or per-minute quota is used up; stop rather than spin
            if exc.code == 429:
                raise SystemExit("SAM.gov returned 429 (rate limit). Re-run later; results so far are cached.")
            if attempt == 2:
                return {"entityData": [], "error": f"http {exc.code}"}
            time.sleep(2 ** attempt)
        except Exception:
            if attempt == 2:
                return {"entityData": [], "error": "request failed"}
            time.sleep(2 ** attempt)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def main() -> int:
    key = read_key()
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    # Each SAM request takes about a minute regardless of load, and concurrent requests
    # return in the same wall-clock time as one, so the pull is run in parallel.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        responses = list(pool.map(lambda c: fetch(c["name"], key), companies))

    rows, candidates = [], []
    for i, (c, data) in enumerate(zip(companies, responses), 1):
        records = data.get("entityData") or []
        target = normalize(c["name"])
        row = {k: "" for k in FIELDS}
        row.update({"cik": c["cik"].zfill(10), "ticker": c["ticker"], "name": c["name"],
                    "records_returned": len(records),
                    "match_confidence": "none" if not records else "unmatched",
                    "status": data.get("error", "ok")})

        best = None
        for rec in records:
            reg = rec.get("entityRegistration", {}) or {}
            core = rec.get("coreData", {}) or {}
            sam_name = reg.get("legalBusinessName", "") or ""
            key_name = normalize(sam_name)
            candidates.append({
                "ticker": c["ticker"], "company_name": c["name"], "sam_legal_name": sam_name,
                "uei": reg.get("ueiSAM", ""), "cage_code": reg.get("cageCode", ""),
                "registration_status": reg.get("registrationStatus", ""),
                "exact_match": "yes" if key_name == target else "no",
            })
            if key_name == target and best is None:
                best = ("exact", reg, core, sam_name)
            elif best is None and target and key_name.startswith(target):
                best = ("prefix", reg, core, sam_name)

        if best:
            confidence, reg, core, sam_name = best
            addr = (core.get("physicalAddress", {}) or {})
            naics = core.get("naicsInformation", []) or core.get("naicsList", []) or []
            primary = ""
            if isinstance(naics, list):
                for n in naics:
                    if isinstance(n, dict) and (n.get("sbaSmallBusiness") or n.get("naicsCode")):
                        primary = n.get("naicsCode", "") or primary
                        break
            row.update({
                "uei": reg.get("ueiSAM", ""),
                "cage_code": reg.get("cageCode", ""),
                "sam_legal_name": sam_name,
                "match_confidence": confidence,
                "registration_status": reg.get("registrationStatus", ""),
                "registration_expiration": reg.get("registrationExpirationDate", ""),
                "entity_structure": (core.get("generalInformation", {}) or {}).get("entityStructureDesc", ""),
                "state_of_incorporation": (core.get("generalInformation", {}) or {}).get("stateOfIncorporationCode", ""),
                "physical_city": addr.get("city", ""),
                "physical_state": addr.get("stateOrProvinceCode", ""),
                "primary_naics": primary,
            })
        rows.append(row)
        print(f"[{i}/{len(companies)}] {c['ticker']}: {row['match_confidence']} {row['uei']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with OUT_CANDIDATES.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "company_name", "sam_legal_name", "uei",
                                          "cage_code", "registration_status", "exact_match"])
        w.writeheader()
        w.writerows(candidates)

    from collections import Counter
    print(f"\nWrote {len(rows)} companies to {OUT}")
    print("match confidence:", dict(Counter(r["match_confidence"] for r in rows)))
    print(f"with a UEI: {sum(1 for r in rows if r['uei'])}")
    print(f"candidate records kept for review: {len(candidates)} in {OUT_CANDIDATES.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
