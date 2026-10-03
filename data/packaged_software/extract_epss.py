"""Historical product-vulnerability EPSS features for the packaged-software universe.

Standard library only. See EPSS_README.md for interpretation and mapping limits.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import itertools
import json
import os
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
EPSS_URL = "https://epss.empiricalsecurity.com/epss_scores-{date}.csv.gz"
EPSS_LEGACY_URL = "https://epss.cyentia.com/epss_scores-{date}.csv.gz"
LIMITATION = "retrospective_current_universe_and_nvd_mapping_not_point_in_time"
IDENTITY = ["cik", "ticker", "name"]
SUMMARY_FIELDS = IDENTITY + [
    "score_date", "model_version", "coverage_status", "mapping_status",
    "cpe_vendors", "eligible_cve_count", "scored_cve_count", "missing_epss_count",
    "score_coverage_fraction", "mean_product_cve_epss", "median_product_cve_epss",
    "max_product_cve_epss", "high_epss_cve_count", "high_epss_threshold",
    "historical_mapping_limitation",
]
DETAIL_FIELDS = IDENTITY + [
    "score_date", "model_version", "cve", "published", "matched_cpe_vendors",
    "epss", "epss_percentile", "epss_status", "historical_mapping_limitation",
]


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def api_key():
    """Environment overrides .env. Never log secret values."""
    if "NVD_API_KEY" in os.environ:
        return os.environ["NVD_API_KEY"].strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            match = re.match(r"\s*(?:export\s+)?NVD_API_KEY\s*=\s*(.*)", line)
            if match:
                value = match[1].strip()
                if value[:1] in ("'", '"'):
                    quote = value[0]
                    return value[1:value.find(quote, 1)] if quote in value[1:] else value[1:]
                return value.split(" #", 1)[0].strip()
    return ""


class Client:
    def __init__(self, key=""):
        self.key = key
        self.last_nvd = None

    def get(self, url, nvd=False):
        for attempt in range(5):
            if nvd and self.last_nvd is not None:
                # Across pages, vendors AND retries. Conservative margin over rolling limit.
                pause = 0.75 if self.key else 6.5
                time.sleep(max(0, pause - (time.monotonic() - self.last_nvd)))
            headers = {"User-Agent": "QuantHacks-EPSS-research/1.0"}
            if nvd:
                self.last_nvd = time.monotonic()
                if self.key:
                    headers["apiKey"] = self.key
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                if not nvd and exc.code == 403:
                    raise  # Try the other EPSS host rather than repeatedly retrying access denial.
                if exc.code not in (403, 429, 500, 502, 503, 504) or attempt == 4:
                    raise
                retry_after = exc.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 10 * 2 ** attempt
            except (urllib.error.URLError, TimeoutError):
                if attempt == 4:
                    raise
                delay = 10 * 2 ** attempt
            time.sleep(min(delay, 60))


def configuration_matches(cve, vendor):
    """Only directly vulnerable application CPEs, not environmental prerequisites."""
    def visit(node):
        # Negated configurations are not direct evidence of affected software.
        if node.get("negate"):
            return False
        for match in node.get("cpeMatch", []):
            components = match.get("criteria", "").split(":")
            if (match.get("vulnerable") is True and len(components) >= 5
                    and components[2] == "a" and components[3] == vendor):
                return True
        return any(visit(child) for key in ("nodes", "children") for child in node.get(key, []))
    return any(visit(config) for config in cve.get("configurations", []))


def vendor_cves(client, vendor, cache):
    if not re.fullmatch(r"[a-z0-9_.-]+", vendor):
        raise ValueError(f"Unsupported CPE vendor: {vendor!r}")
    target = cache / "nvd" / f"{vendor}.json"
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    start, records, fetched = 0, {}, dt.datetime.now(dt.timezone.utc).isoformat()
    while True:
        query = urllib.parse.urlencode({"virtualMatchString": f"cpe:2.3:a:{vendor}",
                                       "startIndex": start, "resultsPerPage": 2000})
        page_file = cache / "nvd_pages" / f"{vendor}_{start}.json"
        if page_file.exists():
            data = json.loads(page_file.read_text(encoding="utf-8"))
        else:
            data = json.loads(client.get(f"{NVD_URL}?{query}", nvd=True))
            write_json(page_file, data)
        if "totalResults" not in data or "vulnerabilities" not in data:
            raise ValueError("Unexpected NVD response; refusing to treat it as zero CVEs")
        for item in data["vulnerabilities"]:
            cve = item["cve"]
            if cve.get("vulnStatus") == "Rejected" or not configuration_matches(cve, vendor):
                continue
            records[cve["id"]] = {"cve": cve["id"], "published": cve.get("published", ""),
                                   "last_modified": cve.get("lastModified", "")}
        if start + len(data["vulnerabilities"]) >= data["totalResults"]:
            break
        if not data["vulnerabilities"]:
            raise ValueError("NVD returned an empty page before totalResults was reached")
        start += len(data["vulnerabilities"])
    result = {"vendor": vendor, "retrieved_at": fetched,
              "nvd_total_matches": data["totalResults"], "cves": list(records.values())}
    write_json(target, result)
    return result


def parse_epss(raw, wanted, expected_date):
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as zipped:
        with io.TextIOWrapper(zipped, encoding="utf-8-sig") as stream:
            first = stream.readline().strip()
            if first.startswith("#"):
                meta = dict(part.strip().split(":", 1) for part in first.lstrip("#").split(","))
                reader = csv.DictReader(stream)
            elif expected_date < "2022-02-04":
                # EPSS v1 files predate the metadata comment introduced with v2.
                meta = {"score_date": expected_date, "model_version": "v1_inferred_from_release_date",
                        "date_source": "dated_download_filename_no_embedded_metadata"}
                reader = csv.DictReader(itertools.chain([first + "\n"], stream))
            else:
                raise ValueError("Missing EPSS metadata")
            if meta.get("score_date", "")[:10] != expected_date:
                raise ValueError(f"EPSS score date does not match requested date {expected_date}")
            if not meta.get("model_version"):
                raise ValueError("Missing EPSS model version")
            scores = {}
            if not reader.fieldnames or not {"cve", "epss"}.issubset(reader.fieldnames):
                raise ValueError(f"Unexpected EPSS columns: {reader.fieldnames}")
            for row in reader:
                if row["cve"] in wanted:
                    score = float(row["epss"])
                    percentile = float(row["percentile"]) if row.get("percentile") else ""
                    if not (0 <= score <= 1 and (percentile == "" or 0 <= percentile <= 1)):
                        raise ValueError("EPSS probability or percentile outside [0, 1]")
                    scores[row["cve"]] = (score, percentile)
    return scores, meta


def api_snapshot(client, date, cache):
    """Recover unavailable bulk dates from FIRST's dated API; verify every row date."""
    target = cache / "epss_api" / f"{date}.csv.gz"
    if target.exists():
        return target.read_bytes()
    body = io.StringIO(newline="")
    body.write(f"#model_version:unavailable_from_api,score_date:{date}\n")
    writer = csv.DictWriter(body, fieldnames=["cve", "epss", "percentile"])
    writer.writeheader()
    offset = 0
    while True:
        query = urllib.parse.urlencode({"date": date, "limit": 10000, "offset": offset})
        page = json.loads(client.get(f"https://api.first.org/data/v1/epss?{query}"))
        if page.get("status") != "OK" or "total" not in page or not page.get("data"):
            raise ValueError("FIRST API did not return a complete dated snapshot")
        for row in page["data"]:
            if row.get("date") != date:
                raise ValueError("FIRST API row date differs from requested historical date")
            writer.writerow({key: row[key] for key in ("cve", "epss", "percentile")})
        offset += len(page["data"])
        if offset >= int(page["total"]):
            break
        time.sleep(0.1)  # Sequential, comfortably below FIRST's public rate limit.
    raw = gzip.compress(body.getvalue().encode("utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return raw


def dates_between(start, end, frequency):
    day = start
    while day <= end:
        if frequency == "daily" or day == start or day.day == 1:
            yield day.isoformat()
        day += dt.timedelta(days=1)


def summary(company, mapping, cves, scores, date, model, threshold, failed=False):
    vendors = mapping.get("cpe_vendors", "")
    eligible = [] if failed else [c for c in cves if c["published"] and c["published"][:10] <= date]
    values = [scores[c["cve"]][0] for c in eligible if c["cve"] in scores]
    status = ("unmapped" if not vendors else "nvd_fetch_failed" if failed else
              "no_current_matching_cves" if not cves else
              "no_eligible_cves_on_date" if not eligible else
              "no_epss_scores" if not values else
              "partial_epss_coverage" if len(values) < len(eligible) else "scored")
    counts_known = bool(vendors) and not failed
    return {**{key: company[key] for key in IDENTITY}, "score_date": date, "model_version": model,
            "coverage_status": status, "mapping_status": mapping.get("mapping_status", "unmapped"),
            "cpe_vendors": vendors,
            "eligible_cve_count": len(eligible) if counts_known else "",
            "scored_cve_count": len(values) if counts_known else "",
            "missing_epss_count": len(eligible) - len(values) if counts_known else "",
            "score_coverage_fraction": len(values) / len(eligible) if eligible and counts_known else "",
            "mean_product_cve_epss": statistics.mean(values) if values else "",
            "median_product_cve_epss": statistics.median(values) if values else "",
            "max_product_cve_epss": max(values) if values else "",
            "high_epss_cve_count": sum(v >= threshold for v in values) if values else "",
            "high_epss_threshold": threshold, "historical_mapping_limitation": LIMITATION}


def run(args):
    companies = read_csv(args.companies)
    if not companies or not set(IDENTITY).issubset(companies[0]):
        raise ValueError("Company CSV requires cik,ticker,name")
    if len({c["cik"] for c in companies}) != len(companies):
        raise ValueError("Company CSV contains duplicate CIKs")
    if args.tickers:
        selected = set(args.tickers.upper().split(","))
        available = {c["ticker"] for c in companies}
        if selected - available:
            raise ValueError(f"Unknown tickers: {sorted(selected - available)}")
        companies = [c for c in companies if c["ticker"] in selected]
    mappings_list = read_csv(args.mapping)
    if len({m["cik"] for m in mappings_list}) != len(mappings_list):
        raise ValueError("Mapping CSV contains duplicate CIKs")
    mappings = {m["cik"]: m for m in mappings_list}
    for company in companies:
        m = mappings.get(company["cik"], {})
        if m.get("cpe_vendors") and m.get("mapping_status") != "curated_current_brand":
            raise ValueError("Only curated_current_brand mappings may be used; review proposed aliases first")
    client = Client(api_key())
    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / "manifest.json"
    manifest = {"started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "status": "running", "start": str(args.start), "end": str(args.end),
                "frequency": args.frequency, "company_count": len(companies),
                "mapping_limitation": LIMITATION, "product_scope": "application CPEs only",
                "threshold": args.threshold, "errors": [], "snapshots": [], "nvd_vendors": {}}
    # Manifest fingerprint prevents silently resuming with changed mappings/parameters.
    identity = {"companies": companies, "mappings": mappings_list, "start": str(args.start),
                "end": str(args.end), "frequency": args.frequency, "threshold": args.threshold,
                "detail": not args.summary_only, "schema_version": 1}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if old.get("fingerprint") != fingerprint:
            raise ValueError("Output already belongs to a different run. Choose a new --output directory.")
    manifest["fingerprint"] = fingerprint
    write_json(manifest_path, manifest)
    cves_by_company, failures, wanted = {}, set(), set()
    vendors = sorted({v for c in companies for v in mappings.get(c["cik"], {}).get("cpe_vendors", "").split(";") if v})
    vendor_data = {}
    for i, vendor in enumerate(vendors, 1):
        print(f"NVD {i}/{len(vendors)}: {vendor}", flush=True)
        try:
            vendor_data[vendor] = vendor_cves(client, vendor, args.cache)
            manifest["nvd_vendors"][vendor] = {k: v for k, v in vendor_data[vendor].items() if k != "cves"}
            manifest["nvd_vendors"][vendor]["directly_vulnerable_cve_count"] = len(vendor_data[vendor]["cves"])
        except Exception as exc:
            # Exception type/code only: never include API headers or secrets.
            manifest["errors"].append({"vendor": vendor, "error": type(exc).__name__,
                                       "http_status": getattr(exc, "code", None)})
            print(f"  failed: {type(exc).__name__}", flush=True)
            if isinstance(exc, ValueError):
                print(f"  validation: {exc}", flush=True)
        write_json(manifest_path, manifest)
    for company in companies:
        merged = {}
        for vendor in filter(None, mappings.get(company["cik"], {}).get("cpe_vendors", "").split(";")):
            if vendor not in vendor_data:
                failures.add(company["cik"])
                continue
            for cve in vendor_data[vendor]["cves"]:
                record = merged.setdefault(cve["cve"], {**cve, "vendors": []})
                record["vendors"].append(vendor)
        # Incomplete vendor pulls cannot masquerade as complete company coverage.
        records = [] if company["cik"] in failures else sorted(merged.values(), key=lambda c: c["cve"])
        cves_by_company[company["cik"]] = records
        wanted.update(c["cve"] for c in records)
    write_json(args.output / "company_cve_inventory.json", cves_by_company)
    review_fields = IDENTITY + ["cpe_vendors", "observed_application_vendors", "unconfirmed_aliases",
                               "mapping_status", "current_matching_cve_count", "notes"]
    with (args.output / "mapping_coverage.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=review_fields)
        writer.writeheader()
        for company in companies:
            mapping = mappings.get(company["cik"], {})
            aliases = list(filter(None, mapping.get("cpe_vendors", "").split(";")))
            observed = [v for v in aliases if vendor_data.get(v, {}).get("cves")]
            writer.writerow({**{key: company[key] for key in IDENTITY},
                             "cpe_vendors": ";".join(aliases),
                             "observed_application_vendors": ";".join(observed),
                             "unconfirmed_aliases": ";".join(v for v in aliases if v not in observed),
                             "mapping_status": mapping.get("mapping_status", "unmapped"),
                             "current_matching_cve_count": len(cves_by_company[company["cik"]])
                             if aliases and company["cik"] not in failures else "",
                             "notes": mapping.get("notes", "")})
    inventory_hash = hashlib.sha256(json.dumps(cves_by_company, sort_keys=True).encode()).hexdigest()
    for date in dates_between(args.start, args.end, args.frequency):
        summary_path = args.output / "summary" / f"{date}.csv"
        detail_path = args.output / "cves" / f"{date}.csv.gz"
        done = args.output / "completed" / f"{date}.json"
        if done.exists():
            checkpoint = json.loads(done.read_text(encoding="utf-8"))
            if (checkpoint.get("inventory_hash") == inventory_hash and not failures
                    and summary_path.exists() and (args.summary_only or detail_path.exists())):
                manifest["snapshots"].append(checkpoint)
                continue
        print(f"EPSS {date}: {len(wanted)} target CVEs", flush=True)
        if not wanted:
            manifest["errors"].append({"date": date, "error": "No usable mapped CVEs; EPSS not downloaded"})
            break
        try:
            raw_path = args.cache / "epss" / f"{date}.csv.gz"
            if raw_path.exists():
                raw = raw_path.read_bytes()
                source_url = "local_bulk_cache"
            else:
                source_url = EPSS_URL.format(date=date)
                try:
                    raw = client.get(source_url)
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
                    source_url = EPSS_LEGACY_URL.format(date=date)
                    try:
                        raw = client.get(source_url)
                    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
                        print(f"  bulk unavailable; trying FIRST's dated API for {date}", flush=True)
                        source_url = f"https://api.first.org/data/v1/epss?date={date}"
                        raw = api_snapshot(client, date, args.cache)
            scores, meta = parse_epss(raw, wanted, date)
            if meta["model_version"] == "unavailable_from_api":
                meta["date_source"] = "verified_api_row_dates"
            if args.keep_bulk_cache and not raw_path.exists():
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(raw)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = summary_path.with_suffix(".tmp")
            with temporary.open("w", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(output, fieldnames=SUMMARY_FIELDS)
                writer.writeheader()
                for company in companies:
                    writer.writerow(summary(company, mappings.get(company["cik"], {}),
                                             cves_by_company[company["cik"]], scores, date,
                                             meta["model_version"], args.threshold,
                                             company["cik"] in failures))
            temporary.replace(summary_path)
            detail_count = 0
            if not args.summary_only:
                detail_path.parent.mkdir(parents=True, exist_ok=True)
                temp_detail = detail_path.with_suffix(".tmp")
                with gzip.open(temp_detail, "wt", newline="", encoding="utf-8") as output:
                    writer = csv.DictWriter(output, fieldnames=DETAIL_FIELDS)
                    writer.writeheader()
                    for company in companies:
                        for cve in cves_by_company[company["cik"]]:
                            if not cve["published"] or cve["published"][:10] > date:
                                continue
                            score, pct = scores.get(cve["cve"], ("", ""))
                            writer.writerow({**{key: company[key] for key in IDENTITY},
                                             "score_date": date, "model_version": meta["model_version"],
                                             "cve": cve["cve"], "published": cve["published"],
                                             "matched_cpe_vendors": ";".join(cve["vendors"]),
                                             "epss": score, "epss_percentile": pct,
                                             "epss_status": "scored" if score != "" else "missing",
                                             "historical_mapping_limitation": LIMITATION})
                            detail_count += 1
                temp_detail.replace(detail_path)
            snapshot = {"date": date, "model_version": meta["model_version"],
                        "source_url": source_url,
                        "date_source": meta.get("date_source", "embedded_metadata"),
                        "company_rows": len(companies), "cve_rows": detail_count,
                        "inventory_hash": inventory_hash}
            if not failures:
                write_json(done, snapshot)
            manifest["snapshots"].append(snapshot)
        except Exception as exc:
            manifest["errors"].append({"date": date, "error": type(exc).__name__,
                                       "http_status": getattr(exc, "code", None)})
            print(f"  failed: {type(exc).__name__}", flush=True)
            if isinstance(exc, ValueError):
                print(f"  validation: {exc}", flush=True)
        write_json(manifest_path, manifest)
    # Combine small company summaries; detailed files stay partitioned and compressed.
    with (args.output / "company_epss_history.csv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for snapshot in manifest["snapshots"]:
            writer.writerows(read_csv(args.output / "summary" / f"{snapshot['date']}.csv"))
    manifest["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest["status"] = "complete_with_errors" if manifest["errors"] else "complete"
    write_json(manifest_path, manifest)
    print(f"{manifest['status']}: {len(manifest['snapshots'])} snapshots -> {args.output}", flush=True)
    return 1 if manifest["errors"] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=Path, default=HERE / "packaged_software_companies.csv")
    parser.add_argument("--mapping", type=Path, default=HERE / "epss_company_mapping.csv")
    parser.add_argument("--start", type=dt.date.fromisoformat, default=dt.date(2022, 1, 1))
    # Yesterday avoids requesting today's file before publication.
    parser.add_argument("--end", type=dt.date.fromisoformat, default=dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1))
    parser.add_argument("--frequency", choices=["daily", "monthly"], default="daily")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "extracts" / "epss")
    parser.add_argument("--cache", type=Path, default=ROOT / "data" / "extracts" / "_cache" / "epss")
    parser.add_argument("--tickers", help="Optional comma-separated subset for a smoke test")
    parser.add_argument("--threshold", type=float, default=0.10)
    parser.add_argument("--summary-only", action="store_true", help="Omit per-CVE daily files")
    parser.add_argument("--keep-bulk-cache", action="store_true", help="Keep full compressed FIRST files (several GB for daily history)")
    args = parser.parse_args()
    if args.start < dt.date(2021, 4, 14) or args.end < args.start:
        parser.error("Date range must start on/after 2021-04-14 and end on/after start")
    if args.end >= dt.datetime.now(dt.timezone.utc).date():
        parser.error("Use an end date before today to ensure scores have been published")
    if not 0 <= args.threshold <= 1:
        parser.error("Threshold must be in [0, 1]")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
