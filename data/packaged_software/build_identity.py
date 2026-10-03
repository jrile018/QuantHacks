"""Company identity from SEC submissions records, for the 168-company universe.

Fetches each CIK's submissions JSON (cached under data/extracts/identity/cache/) and writes
output/company_identity.csv with: exchange, former names, fiscal year end, state of
incorporation, business and mailing addresses, phone, EIN, and filer category.

Uses SEC_USER_AGENT from the repo .env, as SEC requires. Standard library only.
Not included: LEI and UEI (not in the SEC submissions record; see the GLEIF and SAM.gov
notes in the checklist), executives, headcount, and IPO date.
"""

from __future__ import annotations

import csv
import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPANIES = HERE / "packaged_software_companies.csv"
CACHE = ROOT / "data" / "extracts" / "identity" / "cache"
OUT = HERE / "output" / "company_identity.csv"
URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FIELDS = ["cik", "ticker", "name", "sic", "sic_description", "exchanges", "former_names",
          "fiscal_year_end", "state_of_incorporation", "ein", "category", "phone",
          "business_address", "mailing_address", "website", "status"]


def user_agent() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("SEC_USER_AGENT="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("SEC_USER_AGENT is not set in .env")


def fetch(cik: str, ua: str) -> dict:
    cache_file = CACHE / f"CIK{cik}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    req = urllib.request.Request(URL.format(cik=cik), headers={"User-Agent": ua, "Accept-Encoding": "identity"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(0.12)  # SEC allows 10 requests per second
    return data


def address(a: dict) -> str:
    parts = [a.get("street1", ""), a.get("street2", ""), a.get("city", ""), a.get("stateOrCountry", ""), a.get("zipCode", "")]
    return ", ".join(p for p in parts if p)


def main() -> int:
    ua = user_agent()
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))
    rows = []
    for c in companies:
        cik = c["cik"].zfill(10)
        try:
            d = fetch(cik, ua)
        except Exception as exc:
            rows.append({"cik": cik, "ticker": c["ticker"], "name": c["name"], "status": f"failed: {exc}"})
            continue
        addr = d.get("addresses", {})
        fye = d.get("fiscalYearEnd", "")
        rows.append({
            "cik": cik,
            "ticker": c["ticker"],
            "name": d.get("name", c["name"]),
            "sic": d.get("sic", ""),
            "sic_description": d.get("sicDescription", ""),
            "exchanges": "; ".join(d.get("exchanges", [])),
            "former_names": "; ".join(n.get("name", "") for n in d.get("formerNames", [])),
            "fiscal_year_end": f"{fye[:2]}-{fye[2:]}" if len(fye) == 4 else fye,
            "state_of_incorporation": d.get("stateOfIncorporation", ""),
            "ein": d.get("ein", ""),
            "category": d.get("category", ""),
            "phone": d.get("phone", ""),
            "business_address": address(addr.get("business", {})),
            "mailing_address": address(addr.get("mailing", {})),
            "website": d.get("website", ""),
            "status": "ok" if d else "empty record",
        })
        print(f"{c['ticker'] or cik}: {d.get('name', '')}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    ok = sum(1 for r in rows if r.get("status") == "ok")
    print(f"Wrote {len(rows)} companies ({ok} ok) to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
