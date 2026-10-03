"""Extract Census industry data and USAspending awards for the packaged-software list.

Writes to data/packaged_software/extracts/:
  census/cbp_naics5112/   County Business Patterns, software publishers (NAICS 5112),
                          one CSV per year, national plus state level.
  usaspending/<TICKER>/   Federal contract awards for each company, one CSV per company.
  manifest.json           Run time, parameters, row counts, and any failures.

Inputs:
  data/packaged_software/packaged_software_companies.csv  (cik, ticker, name, sic, industry)
  CENSUS_API_KEY in the repo's .env file

Usage (from the repo root):
    python data/packaged_software/extract_census_usaspending.py
    python data/packaged_software/extract_census_usaspending.py --skip-usaspending

Standard library only. Responses are cached under data/packaged_software/extracts/_cache/.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import pull_federal_contracts as usa  # noqa: E402  (reuses the USAspending query code)

COMPANIES = HERE / "packaged_software_companies.csv"
EXTRACTS = HERE / "extracts"
CACHE = EXTRACTS / "_cache"
CENSUS_YEARS = range(2017, 2024)  # CBP currently publishes through 2023; 2024+ return 404
CBP_VARS = ["NAME", "NAICS2017", "ESTAB", "EMP", "PAYANN", "PAYQTR1"]


def read_env_value(name: str) -> str:
    """Read one value from the repo's .env without printing it."""
    env = ROOT / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    raise KeyError(f"{name} not found in .env")


def get_json(url: str, cache_name: str) -> list:
    """GET a JSON URL with a disk cache and simple retries."""
    cache_file = CACHE / cache_name
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            CACHE.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data), encoding="utf-8")
            return data
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def census_cbp(year: int, key: str, geo: str) -> list[dict]:
    """Rows of County Business Patterns for NAICS 5112 at one geography level."""
    params = {
        "get": ",".join(CBP_VARS),
        "for": geo,
        "NAICS2017": "5112",
        "key": key,
    }
    url = f"https://api.census.gov/data/{year}/cbp?{urllib.parse.urlencode(params)}"
    safe_geo = geo.replace(":", "_").replace("*", "all")
    table = get_json(url, f"cbp_{year}_{safe_geo}.json")
    header, *body = table
    return [dict(zip(header, row)) for row in body]


def extract_census(key: str, failures: list[dict]) -> int:
    out_dir = EXTRACTS / "census" / "cbp_naics5112"
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for year in CENSUS_YEARS:
        rows: list[dict] = []
        for geo in ("us:*", "state:*"):
            try:
                rows.extend({**r, "year": year, "geo_level": geo.split(":")[0]} for r in census_cbp(year, key, geo))
            except Exception as exc:
                failures.append({"source": "census", "year": year, "geo": geo, "error": str(exc)})
                print(f"Census {year} {geo}: FAILED ({exc})", file=sys.stderr)
        if not rows:
            continue
        fields = list(dict.fromkeys(k for r in rows for k in r))
        with (out_dir / f"cbp_naics5112_{year}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        total += len(rows)
        print(f"Census {year}: {len(rows)} rows")
    return total


def load_companies() -> list[dict]:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def extract_usaspending(companies: list[dict], start: str, end: str, pause: float, failures: list[dict]) -> int:
    base = EXTRACTS / "usaspending"
    total = 0
    for i, c in enumerate(companies, 1):
        ticker = c["ticker"] or c["cik"]
        company = {"cik": c["cik"].zfill(10), "name": c["name"], "sic": c["sic"]}
        try:
            rows = usa.pull_company(company, start, end, 100, pause)
        except Exception as exc:
            failures.append({"source": "usaspending", "ticker": ticker, "error": str(exc)})
            print(f"[{i}/{len(companies)}] {ticker}: FAILED ({exc})", file=sys.stderr)
            continue
        out_dir = base / ticker
        out_dir.mkdir(parents=True, exist_ok=True)
        fields = list(rows[0].keys()) if rows else ["cik", "company_name", "recipient_name", "exact_name_match", "award_id", "start_date", "end_date", "award_amount", "awarding_agency", "awarding_sub_agency", "description", "usaspending_internal_id"]
        with (out_dir / "contract_awards.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        total += len(rows)
        print(f"[{i}/{len(companies)}] {ticker}: {len(rows)} awards")
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-census", action="store_true")
    parser.add_argument("--skip-usaspending", action="store_true")
    parser.add_argument("--start", default="2022-01-01", help="USAspending award window start")
    parser.add_argument("--end", default=dt.date.today().isoformat(), help="USAspending award window end")
    parser.add_argument("--pause", type=float, default=0.3, help="Seconds between USAspending pages")
    args = parser.parse_args()

    EXTRACTS.mkdir(parents=True, exist_ok=True)
    failures: list[dict] = []
    manifest: dict = {
        "run_at": dt.datetime.now().isoformat(timespec="seconds"),
        "companies_file": str(COMPANIES.relative_to(ROOT)),
    }

    if not args.skip_census:
        census_rows = extract_census(read_env_value("CENSUS_API_KEY"), failures)
        manifest["census"] = {"source": "Census CBP, NAICS 5112", "years": list(CENSUS_YEARS), "rows": census_rows}

    if not args.skip_usaspending:
        companies = load_companies()
        print(f"USAspending: {len(companies)} companies, {args.start} to {args.end}")
        usa_rows = extract_usaspending(companies, args.start, args.end, args.pause, failures)
        manifest["usaspending"] = {"companies": len(companies), "award_rows": usa_rows, "window": {"start": args.start, "end": args.end}}

    manifest["failures"] = len(failures)
    (EXTRACTS / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if failures:
        with (EXTRACTS / "failures.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=sorted({k for x in failures for k in x}))
            writer.writeheader()
            writer.writerows(failures)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
