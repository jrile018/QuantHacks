"""Export SEC Submissions-listed 8-K URLs for a CIK-keyed company list.

Only SEC filing metadata is downloaded. Archive links are constructed from
SEC-listed accessions and primary-document filenames; their HTTP availability
is not checked one by one. Raw JSON responses are cached for repeatable runs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SEC_DATA = "https://data.sec.gov/submissions"
SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}\Z")
HISTORY_NAME = re.compile(r"CIK\d{10}-submissions-\d{3}\.json\Z")
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+\Z")
FIELDS = (
    "cik", "company_name", "tickers", "form", "filing_date", "report_date",
    "acceptance_datetime", "accession", "index_url", "primary_document_url",
    "complete_text_url", "source_submissions_url", "url_status",
)
COVERAGE_FIELDS = ("cik", "company_name", "tickers", "status", "filing_count", "history_files", "detail")


class SecAccessBlocked(RuntimeError):
    """The SEC denied automated access; stop rather than retrying at scale."""


class RateLimiter:
    def __init__(self, requests_per_second: float):
        if not 0 < requests_per_second <= 10:
            raise ValueError("rate must be above zero and at most 10 requests per second")
        self.interval = 1.0 / requests_per_second
        self.next_at = 0.0

    def __call__(self) -> None:
        delay = self.next_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.next_at = time.monotonic() + self.interval


def normalized_cik(value: str) -> str:
    raw = str(value).strip()
    if not raw.isdigit() or len(raw) > 10:
        raise ValueError(f"invalid CIK: {value!r}")
    return raw.zfill(10)


def valid_primary_name(value: str) -> bool:
    return bool(value and value not in {".", ".."} and "/" not in value and "\\" not in value
                and not any(ord(char) < 32 for char in value))


def _column(table: dict, name: str, index: int) -> str:
    column = table.get(name, [])
    return str(column[index] or "") if isinstance(column, list) and index < len(column) else ""


def validate_filing_table(table: object, source: str) -> None:
    """Reject truncated or malformed SEC column arrays before claiming coverage."""
    if not isinstance(table, dict):
        raise ValueError(f"invalid filing table in {source}")
    required = ("accessionNumber", "form", "filingDate", "primaryDocument")
    for name in required:
        if not isinstance(table.get(name), list):
            raise ValueError(f"missing {name} array in {source}")
    expected = len(table["accessionNumber"])
    for name in (*required, "reportDate", "acceptanceDateTime"):
        if name in table and (not isinstance(table[name], list) or len(table[name]) != expected):
            raise ValueError(f"misaligned {name} array in {source}")


def validate_submission(submission: object, source: str) -> list:
    if not isinstance(submission, dict) or not isinstance(submission.get("filings"), dict):
        raise ValueError(f"missing filings object in {source}")
    filings = submission["filings"]
    validate_filing_table(filings.get("recent"), source)
    if not isinstance(filings.get("files"), list):
        raise ValueError(f"missing history-file list in {source}")
    return filings["files"]


def filing_rows(
    cik: str, company_name: str, submission: dict, history_payloads: list[dict | None],
    tickers: str = "",
) -> list[dict[str, str]]:
    """Return unique 8-K/8-K/A rows from the recent and older SEC arrays."""
    cik = normalized_cik(cik)
    main_url = f"{SEC_DATA}/CIK{cik}.json"
    files = submission.get("filings", {}).get("files", [])
    sources = [(main_url, submission.get("filings", {}).get("recent", {}))]
    for index, history in enumerate(history_payloads):
        item = files[index] if index < len(files) and isinstance(files[index], dict) else {}
        filename = str(item.get("name", ""))
        source_url = f"{SEC_DATA}/{filename}" if HISTORY_NAME.fullmatch(filename) else main_url
        sources.append((source_url, history))

    unique: dict[str, dict[str, str]] = {}
    for source_url, table in sources:
        if not isinstance(table, dict):
            continue
        accessions = table.get("accessionNumber", [])
        if not isinstance(accessions, list):
            continue
        for index, raw_accession in enumerate(accessions):
            accession = str(raw_accession or "")
            form = _column(table, "form", index).upper()
            if form not in {"8-K", "8-K/A"} or not ACCESSION.fullmatch(accession):
                continue
            archive_root = f"{SEC_ARCHIVE}/{int(cik)}"
            document_dir = f"{archive_root}/{accession.replace('-', '')}"
            primary = _column(table, "primaryDocument", index)
            filing_date = _column(table, "filingDate", index)
            unique.setdefault(accession, {
                "cik": cik,
                "company_name": company_name,
                "tickers": tickers,
                "form": form,
                "filing_date": filing_date,
                "report_date": _column(table, "reportDate", index),
                "acceptance_datetime": _column(table, "acceptanceDateTime", index),
                "accession": accession,
                "index_url": f"{archive_root}/{accession}-index.html",
                "primary_document_url": (
                    f"{document_dir}/{quote(primary, safe='-._~')}"
                    if filing_date >= "2000-05-26" and valid_primary_name(primary) else ""
                ),
                "complete_text_url": f"{archive_root}/{accession}.txt",
                "source_submissions_url": source_url,
                "url_status": "constructed_from_sec_submissions_metadata",
            })
    return sorted(unique.values(), key=lambda row: (row["filing_date"], row["accession"]), reverse=True)


def fetch_json(url: str, cache_path: Path, user_agent: str, limiter, opener=urlopen) -> dict | None:
    """Fetch and cache SEC JSON, stopping immediately on a blocked response."""
    if cache_path.is_file():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    request = Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
    for attempt in range(3):
        limiter()
        try:
            with opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError(f"SEC JSON is not an object: {url}")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_name(cache_path.name + ".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, cache_path)
            return payload
        except HTTPError as error:
            if error.code in {401, 403, 429}:
                raise SecAccessBlocked(f"SEC returned HTTP {error.code} for {url}") from error
            if error.code == 404:
                return None
            if error.code < 500 or attempt == 2:
                raise
        except URLError:
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)
    raise AssertionError("retry loop exhausted")


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def write_snapshot(output_dir: Path, filings: list[dict[str, str]], coverage: list[dict[str, str]], input_path: Path,
                   requested: int, stopped: str = "") -> None:
    write_csv(output_dir / "filings.csv", FIELDS, sorted(filings, key=lambda row: (row["cik"], row["filing_date"], row["accession"])))
    write_csv(output_dir / "coverage.csv", COVERAGE_FIELDS, coverage)
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "input_companies": requested,
        "companies_processed": len(coverage),
        "companies_complete": sum(row["status"] == "complete" for row in coverage),
        "filings": len(filings),
        "stopped": stopped,
        "source": "SEC EDGAR Submissions API; primary and archive URLs constructed from listed metadata",
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def collect(input_path: Path, output_dir: Path, contact_email: str, rate: float = 5.0,
            max_companies: int = 0) -> dict:
    if not EMAIL.fullmatch(contact_email):
        raise ValueError("a real SEC contact email is required in --contact-email or SEC_CONTACT_EMAIL")
    limiter = RateLimiter(rate)
    user_agent = f"QuantHaxs 8-K research {contact_email}"
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        companies = list(csv.DictReader(handle))
    if max_companies:
        companies = companies[:max_companies]
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = output_dir / "cache"
    filings: list[dict[str, str]] = []
    coverage: list[dict[str, str]] = []
    stopped = ""
    seen_ciks: set[str] = set()
    try:
        for number, company in enumerate(companies, start=1):
            cik = normalized_cik(company["cik"])
            if cik in seen_ciks:
                continue
            seen_ciks.add(cik)
            root_url = f"{SEC_DATA}/CIK{cik}.json"
            folder = cache_dir / f"CIK{cik}"
            record = {"cik": cik, "company_name": company.get("company_name", ""),
                      "tickers": company.get("tickers", ""), "status": "", "filing_count": "0",
                      "history_files": "0", "detail": ""}
            try:
                submission = fetch_json(root_url, folder / "submissions.json", user_agent, limiter)
                if submission is None:
                    record["status"] = "missing_submissions"
                else:
                    old_files = validate_submission(submission, root_url)
                    histories = []
                    for older in old_files:
                        name = str(older.get("name", "")) if isinstance(older, dict) else ""
                        if not HISTORY_NAME.fullmatch(name):
                            record["detail"] += f"Invalid history filename: {name}; "
                            histories.append(None)
                            continue
                        try:
                            payload = fetch_json(f"{SEC_DATA}/{name}", folder / name, user_agent, limiter)
                            if payload is None:
                                record["detail"] += f"Missing history: {name}; "
                            else:
                                validate_filing_table(payload, name)
                        except SecAccessBlocked as error:
                            stopped = str(error)
                            record["detail"] += f"Blocked history: {name}; "
                            payload = None
                        except (HTTPError, URLError, ValueError, json.JSONDecodeError) as error:
                            record["detail"] += f"History error {name}: {type(error).__name__}: {error}; "
                            payload = None
                        histories.append(payload)
                        if stopped:
                            break
                    company_filings = filing_rows(cik, record["company_name"], submission, histories,
                                                  tickers=record["tickers"])
                    filings.extend(company_filings)
                    record["filing_count"] = str(len(company_filings))
                    record["history_files"] = str(sum(payload is not None for payload in histories))
                    record["status"] = "blocked" if stopped else ("complete" if not record["detail"] else "incomplete_history")
            except SecAccessBlocked as error:
                stopped = str(error)
                record["status"] = "blocked"
                record["detail"] = stopped
            except (HTTPError, URLError, ValueError, json.JSONDecodeError) as error:
                record["status"] = "error"
                record["detail"] = f"{type(error).__name__}: {error}"
            coverage.append(record)
            if number % 25 == 0:
                write_snapshot(output_dir, filings, coverage, input_path, len(companies))
                print(f"{number}/{len(companies)} CIKs processed; {len(filings)} 8-K filings", flush=True)
            if stopped:
                break
    except KeyboardInterrupt:
        stopped = "interrupted"
    finally:
        write_snapshot(output_dir, filings, coverage, input_path, len(companies), stopped)
    return json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies-csv", type=Path, default=ROOT / "data/processed/tiger_8k_company_names.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed/sec_8k_urls")
    parser.add_argument("--contact-email", default=os.environ.get("SEC_CONTACT_EMAIL", ""))
    parser.add_argument("--rate", type=float, default=5.0)
    parser.add_argument("--max-companies", type=int, default=0)
    args = parser.parse_args(argv)
    if args.max_companies < 0:
        parser.error("--max-companies must be nonnegative")
    try:
        result = collect(args.companies_csv, args.output_dir, args.contact_email, args.rate, args.max_companies)
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["companies_complete"] == result["input_companies"] and not result["stopped"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
