"""CISA Known Exploited Vulnerabilities (KEV) for the 168-company universe.

Downloads the public KEV catalog (no API key) and matches each entry's vendorProject
against the curated CPE vendor aliases in epss_company_mapping.csv, the same mapping the
EPSS extract uses.

Writes:
  output/kev_company_cves.csv   one row per (company, KEV entry)
  output/kev_by_company.csv     one row per company, including companies with no KEV entry

Matching caveat: KEV's vendorProject is a free-text label ("Microsoft", "Progress
Software"), not a CPE vendor string, so matching is by normalized name. Each row keeps
the raw vendorProject so a match can be checked. Subsidiaries and acquired product lines
are only covered where the curated mapping lists them.
Standard library only.
"""

from __future__ import annotations

import csv
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MAPPING = HERE / "epss_company_mapping.csv"
CACHE = HERE / "extracts" / "_cache" / "kev"
OUT_CVES = HERE / "output" / "kev_company_cves.csv"
OUT_COMPANY = HERE / "output" / "kev_by_company.csv"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
WINDOW_START = "2022-01-01"


def normalize(text: str) -> str:
    """Lowercase and strip punctuation, spaces and common corporate suffixes."""
    text = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|llc|plc|software|systems|technologies|technology|group|holdings?)\b", " ", text.lower())
    return re.sub(r"[^a-z0-9]+", "", text)


def fetch_kev() -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / "known_exploited_vulnerabilities.json"
    req = urllib.request.Request(KEV_URL, headers={"User-Agent": "quanthacks-research", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
        cache_file.write_bytes(body)
        return json.loads(body)
    except Exception as exc:
        if cache_file.exists():
            print(f"Download failed ({exc}); using cached catalog")
            return json.loads(cache_file.read_text(encoding="utf-8"))
        raise


def main() -> int:
    catalog = fetch_kev()
    entries = catalog.get("vulnerabilities", [])
    print(f"KEV catalog: {len(entries)} entries, released {catalog.get('catalogVersion', '?')}")

    with MAPPING.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    # One normalized alias -> list of companies, since two companies can share an alias
    alias_to_companies: dict[str, list[dict]] = defaultdict(list)
    for c in companies:
        for alias in (c["cpe_vendors"] or "").split(";"):
            alias = alias.strip()
            if alias:
                alias_to_companies[normalize(alias)].append(c)
        alias_to_companies[normalize(c["name"])].append(c)

    rows: list[dict] = []
    for e in entries:
        vendor_key = normalize(e.get("vendorProject", ""))
        if not vendor_key:
            continue
        for c in alias_to_companies.get(vendor_key, []):
            rows.append({
                "cik": c["cik"], "ticker": c["ticker"], "name": c["name"],
                "cve_id": e.get("cveID", ""),
                "kev_vendor_project": e.get("vendorProject", ""),
                "kev_product": e.get("product", ""),
                "vulnerability_name": e.get("vulnerabilityName", ""),
                "date_added": e.get("dateAdded", ""),
                "due_date": e.get("dueDate", ""),
                "known_ransomware_use": e.get("knownRansomwareCampaignUse", ""),
                "in_window_2022_onward": "yes" if e.get("dateAdded", "") >= WINDOW_START else "no",
            })

    OUT_CVES.parent.mkdir(parents=True, exist_ok=True)
    fields = ["cik", "ticker", "name", "cve_id", "kev_vendor_project", "kev_product",
              "vulnerability_name", "date_added", "due_date", "known_ransomware_use",
              "in_window_2022_onward"]
    with OUT_CVES.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["ticker"], r["date_added"])))

    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_ticker[r["ticker"]].append(r)
    with OUT_COMPANY.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cik", "ticker", "name", "cpe_vendors", "kev_total",
                                          "kev_since_2022", "kev_ransomware_linked", "first_date_added", "last_date_added"])
        w.writeheader()
        for c in companies:
            mine = by_ticker.get(c["ticker"], [])
            in_window = [r for r in mine if r["in_window_2022_onward"] == "yes"]
            dates = sorted(r["date_added"] for r in mine if r["date_added"])
            w.writerow({
                "cik": c["cik"], "ticker": c["ticker"], "name": c["name"],
                "cpe_vendors": c["cpe_vendors"],
                "kev_total": len(mine), "kev_since_2022": len(in_window),
                "kev_ransomware_linked": sum(1 for r in mine if r["known_ransomware_use"].lower() == "known"),
                "first_date_added": dates[0] if dates else "",
                "last_date_added": dates[-1] if dates else "",
            })

    matched = len(by_ticker)
    print(f"Matched {len(rows)} KEV entries to {matched} of {len(companies)} companies")
    print(f"  entries added 2022 onward: {sum(1 for r in rows if r['in_window_2022_onward'] == 'yes')}")
    print(f"Wrote {OUT_CVES.name} and {OUT_COMPANY.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
