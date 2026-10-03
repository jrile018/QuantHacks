"""Pull federal contract awards for prepackaged-software (SIC 7372) filers.

Reads the company universe, keeps SIC 7372, and queries USAspending.gov
(public API, no key needed) for prime contract awards to each company.

Usage (from the repo root):
    python data/packaged_software/pull_federal_contracts.py \
        --input data/processed/tiger_8k_company_sectors.csv \
        --names data/processed/tiger_8k_companies.csv

Only the Python standard library is used.

Matching caveat: USAspending does not know SEC CIKs. Awards are matched by
recipient name search, which can pull in subsidiaries and name-alikes. Each
award is flagged with exact_name_match so you can separate the two.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
# Prime contract award type codes: definitive contracts (A-D).
CONTRACT_CODES = ["A", "B", "C", "D"]
FIELDS = [
    "Award ID",
    "Recipient Name",
    "Start Date",
    "End Date",
    "Award Amount",
    "Awarding Agency",
    "Awarding Sub Agency",
    "Description",
    "generated_internal_id",
]
HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "output"
CACHE_DIR = HERE / "cache"
SUFFIX_RE = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|ltd|llc|plc|holdings?|group|the)\b\.?",
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    """Lowercase, drop punctuation and legal suffixes for comparison."""
    name = SUFFIX_RE.sub(" ", name.lower())
    name = re.sub(r"[^a-z0-9 ]+", " ", name)
    return " ".join(name.split())


def load_universe(sector_path: Path, names_path: Path | None, sic: str) -> list[dict]:
    """Return [{cik, name, sic}] for companies whose SIC matches `sic`."""
    names: dict[str, str] = {}
    if names_path:
        with names_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                cik = row.get("cik", "").strip().zfill(10)
                names[cik] = row.get("name") or row.get("company") or ""

    companies = []
    with sector_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_sic = (row.get("sic") or "").strip()
            if row_sic.zfill(4) != sic:
                continue
            cik = row["cik"].strip().zfill(10)
            name = names.get(cik) or row.get("name") or row.get("sicDescription", "")
            companies.append({"cik": cik, "name": name.strip(), "sic": row_sic})
    return companies


def search_query(name: str) -> str:
    """Drop legal suffixes so 'Foo Software, Inc.' searches as 'Foo Software'."""
    query = SUFFIX_RE.sub(" ", name)
    query = re.sub(r"[^\w&' -]+", " ", query)
    return " ".join(query.split()) or name


def fetch_page(query: str, start: str, end: str, page: int, limit: int) -> dict:
    """POST one page of spending_by_award results, cached on disk."""
    cache_key = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")
    cache_file = CACHE_DIR / f"{cache_key}_{start}_{end}_p{page}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    body = {
        "filters": {
            "recipient_search_text": [query],
            "time_period": [{"start_date": start, "end_date": end}],
            "award_type_codes": CONTRACT_CODES,
        },
        "fields": FIELDS,
        "page": page,
        "limit": limit,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "quanthacks-packaged-software"},
        method="POST",
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:  # network / 5xx: back off and retry
            if attempt == 3:
                raise
            print(f"  retry after error: {exc}", file=sys.stderr)
            time.sleep(2 ** attempt)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def pull_company(company: dict, start: str, end: str, limit: int, pause: float) -> list[dict]:
    """Return all award rows for one company's name search."""
    query = search_query(company["name"])
    target = normalize_name(company["name"])
    rows: list[dict] = []
    page = 1
    while True:
        data = fetch_page(query, start, end, page, limit)
        for r in data.get("results", []):
            recipient = r.get("Recipient Name") or ""
            rows.append({
                "cik": company["cik"],
                "company_name": company["name"],
                "recipient_name": recipient,
                "exact_name_match": normalize_name(recipient) == target,
                "award_id": r.get("Award ID") or "",
                "start_date": r.get("Start Date") or "",
                "end_date": r.get("End Date") or "",
                "award_amount": r.get("Award Amount") or 0,
                "awarding_agency": r.get("Awarding Agency") or "",
                "awarding_sub_agency": r.get("Awarding Sub Agency") or "",
                "description": (r.get("Description") or "").replace("\n", " ").strip(),
                "usaspending_internal_id": r.get("generated_internal_id") or "",
            })
        if not data.get("page_metadata", {}).get("hasNext"):
            break
        page += 1
        time.sleep(pause)
    return rows


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def summarize(companies: list[dict], awards: list[dict]) -> list[dict]:
    """One row per company: totals for all name matches and exact matches."""
    by_cik: dict[str, list[dict]] = defaultdict(list)
    for a in awards:
        by_cik[a["cik"]].append(a)

    grand_total = sum(float(a["award_amount"] or 0) for a in awards if a["exact_name_match"]) or 1.0
    summary = []
    for c in companies:
        rows = by_cik.get(c["cik"], [])
        exact = [r for r in rows if r["exact_name_match"]]
        agency_totals: dict[str, float] = defaultdict(float)
        for r in exact:
            agency_totals[r["awarding_agency"] or "Unknown"] += float(r["award_amount"] or 0)
        top_agency = max(agency_totals, key=agency_totals.get) if agency_totals else ""
        exact_total = sum(float(r["award_amount"] or 0) for r in exact)
        summary.append({
            "cik": c["cik"],
            "company_name": c["name"],
            "sic": c["sic"],
            "award_count_all_matches": len(rows),
            "total_all_matches": round(sum(float(r["award_amount"] or 0) for r in rows), 2),
            "award_count_exact_name": len(exact),
            "total_exact_name": round(exact_total, 2),
            "share_of_exact_total_pct": round(100 * exact_total / grand_total, 4),
            "top_awarding_agency_exact": top_agency,
        })
    summary.sort(key=lambda r: r["total_exact_name"], reverse=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True,
                        help="CSV with cik and sic columns (e.g. tiger_8k_company_sectors.csv)")
    parser.add_argument("--names", type=Path, default=None,
                        help="Optional CSV with cik and name/company columns (e.g. tiger_8k_companies.csv)")
    parser.add_argument("--sic", default="7372", help="SIC code to pull (default 7372, prepackaged software)")
    parser.add_argument("--start", default="2022-01-01", help="Award start-date window, YYYY-MM-DD")
    parser.add_argument("--end", default=dt.date.today().isoformat(), help="Award end-date window, YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=100, help="Rows per API page (max 100)")
    parser.add_argument("--pause", type=float, default=0.3, help="Seconds between API pages")
    parser.add_argument("--max-companies", type=int, default=None, help="Only process the first N (for testing)")
    args = parser.parse_args()

    companies = load_universe(args.input, args.names, args.sic)
    if args.max_companies:
        companies = companies[: args.max_companies]
    if not companies:
        print(f"No companies with SIC {args.sic} found in {args.input}", file=sys.stderr)
        return 1
    print(f"Pulling federal contracts for {len(companies)} SIC {args.sic} companies, {args.start} to {args.end}")

    awards: list[dict] = []
    failures: list[dict] = []
    for i, company in enumerate(companies, 1):
        try:
            rows = pull_company(company, args.start, args.end, args.limit, args.pause)
            awards.extend(rows)
            print(f"[{i}/{len(companies)}] {company['name']}: {len(rows)} awards")
        except Exception as exc:
            failures.append({"cik": company["cik"], "company_name": company["name"], "error": str(exc)})
            print(f"[{i}/{len(companies)}] {company['name']}: FAILED ({exc})", file=sys.stderr)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    award_fields = list(awards[0].keys()) if awards else ["cik"]
    write_csv(OUT_DIR / "contract_awards.csv", awards, award_fields)
    summary = summarize(companies, awards)
    write_csv(OUT_DIR / "company_summary.csv", summary, list(summary[0].keys()))
    if failures:
        write_csv(OUT_DIR / "failures.csv", failures, ["cik", "company_name", "error"])

    manifest = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": API_URL,
        "sic": args.sic,
        "window": {"start": args.start, "end": args.end},
        "award_type_codes": CONTRACT_CODES,
        "companies_requested": len(companies),
        "companies_failed": len(failures),
        "award_rows": len(awards),
        "exact_name_award_rows": sum(1 for a in awards if a["exact_name_match"]),
        "exact_name_total_usd": round(sum(float(a["award_amount"] or 0) for a in awards if a["exact_name_match"]), 2),
    }
    (OUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print(f"Wrote outputs to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
