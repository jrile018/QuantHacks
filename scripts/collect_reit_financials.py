"""Collect a bounded set of REIT SEC filings and source-linked cash flow facts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit, urljoin
from urllib.request import Request, urlopen

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.document_ocr import extract_document
from src import document_ocr
from src.reit_cash_facts import cash_bridge_checks, cash_flow_rows


DEFAULT_COMPANIES = Path(__file__).resolve().parents[1] / "configs" / "reit_pilot_companies.csv"
DEFAULT_OUTPUT = Path("data/processed/reit_financials")
FACT_FIELDS = ("cik", "metric", "tag", "value", "unit", "accession", "form", "filed",
               "period_start", "period_end", "fiscal_year", "fiscal_period", "filing_url",
               "data_url", "source_method", "amount_kind", "cash_basis", "decimals", "precision_status", "cash_direction",
               "data_sha256", "data_path")
EXTRACTION_REVISION = "collector-2:" + getattr(document_ocr, "EXTRACTION_REVISION", "1")
RELEVANT_ITEMS = {"1.01", "1.02", "2.01", "2.02", "2.03", "8.01"}
CHECK_FIELDS = ("cik", "accession", "period_start", "period_end", "unit", "status",
                "missing", "calculated_cash_change", "reported_cash_change", "difference", "filing_url", "cash_basis", "fx_included", "precision_status",
                "component_tags", "duplicate_fact_count", "tolerance")


class SecAccessBlocked(RuntimeError):
    pass


class SecClient:
    def __init__(self, root: Path, contact_email: str, *, rate: float = 2, offline: bool = False):
        if not 0 < rate < 10:
            raise ValueError("rate must be greater than zero and below 10 requests/second")
        if not offline and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact_email):
            raise ValueError("A real contact email is required for live SEC requests")
        self.root, self.offline = root, offline
        self.user_agent = f"QuantHaxs REIT research {contact_email}"
        self.interval = 1 / rate
        self.next_at = 0.0
        self.blocked = None
        self.receipts = []

    def read(self, url: str, cache_path: Path, *, force: bool = False, validator=None) -> bytes:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in {"data.sec.gov", "www.sec.gov"}:
            raise ValueError(f"Unapproved SEC URL: {url}")
        if cache_path.is_file() and not force:
            self.receipts.append({"url": url, "source": "cache", "cache_path": str(cache_path),
                                  "cache_age_seconds": max(0, time.time() - cache_path.stat().st_mtime)})
            return cache_path.read_bytes()
        if self.offline:
            raise FileNotFoundError(f"Offline cache missing: {cache_path}")
        if self.blocked:
            raise SecAccessBlocked(self.blocked)
        wait = self.next_at - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.next_at = time.monotonic() + self.interval
        request = Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
        try:
            with urlopen(request, timeout=40) as response:
                body = response.read(50_000_001)
        except HTTPError as exc:
            self.receipts.append({"url": url, "source": "http", "http_status": exc.code})
            if exc.code in {403, 429}:
                self.blocked = f"SEC returned {exc.code} for {url}; collection stopped"
                raise SecAccessBlocked(self.blocked) from exc
            raise
        if len(body) > 50_000_000:
            raise ValueError(f"SEC response exceeds 50 MB: {url}")
        if validator is not None:
            validator(body)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_name(cache_path.name + ".tmp")
        temporary.write_bytes(body)
        os.replace(temporary, cache_path)
        self.receipts.append({"url": url, "source": "http", "http_status": 200,
                              "cache_path": str(cache_path), "cache_age_seconds": 0})
        return body

    def read_json(self, url: str, cache_path: Path, *, max_age_seconds: int = 86400) -> dict:
        fresh = (cache_path.is_file() and
                 (self.offline or time.time() - cache_path.stat().st_mtime <= max_age_seconds))
        if fresh:
            try:
                cached = json.loads(cache_path.read_bytes())
                if isinstance(cached, dict):
                    self.receipts.append({"url": url, "source": "cache", "cache_path": str(cache_path),
                                          "cache_age_seconds": max(0, time.time() - cache_path.stat().st_mtime)})
                    return cached
            except (OSError, ValueError):
                pass
            if self.offline:
                raise ValueError(f"Invalid offline JSON cache: {cache_path}")
        def validate(body: bytes) -> None:
            parsed = json.loads(body)
            if not isinstance(parsed, dict):
                raise ValueError(f"Expected JSON object from {url}")
        return json.loads(self.read(url, cache_path, force=not self.offline, validator=validate))


def load_reit_companies(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    selected, seen = [], set()
    for row in rows:
        cik = str(row.get("cik", "")).strip()
        if str(row.get("sic", "")).strip() != "6798" or not cik.isdigit():
            continue
        cik = cik.zfill(10)
        if cik not in seen:
            selected.append(dict(row, cik=cik))
            seen.add(cik)
    return selected


def select_filings(cik: str, submissions: dict, limit: int) -> list[dict]:
    recent = submissions.get("filings", {}).get("recent", {})
    required = ("accessionNumber", "form", "filingDate", "primaryDocument")
    if not isinstance(recent, dict):
        raise ValueError("Malformed filings.recent: expected an object")
    if recent and (any(not isinstance(recent.get(key), list) for key in required)
                   or len({len(recent[key]) for key in required}) != 1):
        raise ValueError("Malformed filings.recent: required arrays must have matching lengths")
    for key in ("acceptanceDateTime", "reportDate", "items"):
        if key in recent and (not isinstance(recent[key], list)
                              or len(recent[key]) != len(recent.get("accessionNumber", []))):
            raise ValueError(f"Malformed filings.recent: {key} must match accessionNumber")
    candidates = []
    for index, (accession, form, filed, filename) in enumerate(zip(
        recent.get("accessionNumber", []), recent.get("form", []),
        recent.get("filingDate", []), recent.get("primaryDocument", []),
    )):
        if form not in {"10-K", "10-Q", "10-K/A", "10-Q/A", "8-K", "8-K/A"}:
            continue
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", filename) or filename in {".", ".."}:
            continue
        if not filename.lower().endswith((".htm", ".html", ".pdf", ".txt")):
            continue
        folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
        metadata = {key: recent.get(key, [])[index] if index < len(recent.get(key, [])) else ""
                    for key in ("acceptanceDateTime", "reportDate", "items")}
        items = set(re.findall(r"\d\.\d{2}", metadata["items"] or ""))
        if form.startswith("8-K") and items and not items & RELEVANT_ITEMS:
            continue
        candidates.append({"cik": cik, "accession": accession, "form": form,
                           "filed": filed, "filename": filename, "url": folder + filename,
                           **metadata, "items_status": "known" if items else "unknown"})
    candidates.sort(key=lambda f: (f["filed"], f["acceptanceDateTime"], f["accession"]), reverse=True)
    reserved = []
    for form in ("10-K", "10-Q"):
        match = next((f for f in candidates if f["form"] == form), None)
        if match:
            reserved.append(match)
    reserved.sort(key=lambda f: (f["filed"], f["accession"]), reverse=True)
    return (reserved + [f for f in candidates if f not in reserved])[:max(0, limit)]


class _Exhibits(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.cells, self.rows, self.cell, self.href = [], [], None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            self.active = attrs.get("summary", "").lower() == "document format files"
        if not self.active:
            return
        if tag == "tr":
            self.cells, self.href = [], None
        elif tag == "td":
            self.cell = []
        elif tag == "a" and self.cell is not None:
            self.href = attrs.get("href")

    def handle_data(self, data):
        if self.active and self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.active and len(self.cells) >= 4 and self.href:
            self.rows.append((self.cells[1], self.href, self.cells[3]))
        elif tag == "table":
            self.active = False


def select_exhibits(filing: dict, raw: bytes, limit: int) -> list[dict]:
    parser = _Exhibits()
    parser.feed(raw.decode("utf-8", errors="replace"))
    folder = filing["url"].rsplit("/", 1)[0] + "/"
    exhibits = []
    for description, href, kind in parser.rows:
        url = urljoin(folder, href)
        filename = urlsplit(url).path.rsplit("/", 1)[-1]
        if not re.fullmatch(r"EX-(?:10|4|99)(?:\.\d+)?", kind, re.I):
            continue
        if url != folder + filename or not re.fullmatch(r"[A-Za-z0-9_.-]+", filename):
            continue
        if not filename.lower().endswith((".htm", ".html", ".pdf", ".txt")):
            continue
        if any(e["url"] == url for e in exhibits):
            continue
        exhibits.append({**filing, "filename": filename, "url": url, "sec_type": kind,
                         "description": description, "document_role": "exhibit"})
    exhibits.sort(key=lambda e: (0 if re.search(r"credit|loan|financ|indenture|debt|mortgage", e["description"], re.I) else 1,
                                 0 if e["sec_type"].startswith("EX-10") else 1, e["filename"]))
    return exhibits[:limit]


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        elif tag in {"p", "div", "tr", "br", "li"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.skip:
            self.skip -= 1
        elif tag in {"p", "div", "tr", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def document_text(path: Path, url: str, accession: str, settings: dict | None = None) -> dict:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if path.suffix.lower() == ".pdf":
        result = extract_document(path, **(settings or {}))
        pages = [{"number": page.number, "text": page.text, "method": page.method,
                  "confidence": page.confidence} for page in result.pages]
        method = result.engine
        for page, extracted in zip(result.pages, pages):
            for key in ("quality_flags", "words", "native_text"):
                if hasattr(page, key):
                    extracted[key] = getattr(page, key)
    elif path.suffix.lower() in {".htm", ".html"}:
        parser = _Text()
        parser.feed(raw.decode("utf-8", errors="replace"))
        pages = [{"number": 1, "text": "".join(parser.parts), "method": "html_native_text",
                  "confidence": None}]
        method = "html_native_text"
    else:
        pages = [{"number": 1, "text": raw.decode("utf-8", errors="replace"),
                  "method": "plain_text", "confidence": None}]
        method = "plain_text"
    return {"accession": accession, "source_url": url, "source_path": str(path.resolve()),
            "sha256": digest, "source_method": method, "page_count": len(pages), "pages": pages,
            "extraction_revision": EXTRACTION_REVISION, "extraction_settings": settings or {},
            "engine_version": getattr(result, "engine_version", None) if path.suffix.lower() == ".pdf" else None,
            "settings": getattr(result, "settings", {}) if path.suffix.lower() == ".pdf" else {}}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def collect(companies_csv: Path, output_dir: Path, *, contact_email: str = "", offline: bool = False,
            max_companies: int = 1, max_filings_per_company: int = 4, rate: float = 2,
            max_exhibits_per_filing: int = 2, extraction_settings: dict | None = None) -> dict:
    if max_companies < 1 or max_filings_per_company < 1 or max_exhibits_per_filing < 0:
        raise ValueError("Company and filing limits must be positive; exhibit limit cannot be negative")
    settings = extraction_settings or {}
    companies = load_reit_companies(companies_csv)[:max_companies]
    client = SecClient(output_dir, contact_email, rate=rate, offline=offline)
    documents, facts, summaries, warnings, errors = [], [], [], [], []
    run_status = "complete"

    def save_document(filing, raw_path, text_path):
        client.read(filing["url"], raw_path)
        digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        extracted = None
        if text_path.is_file():
            try:
                previous = json.loads(text_path.read_text(encoding="utf-8"))
                if (isinstance(previous, dict) and previous.get("sha256") == digest
                        and previous.get("extraction_revision") == EXTRACTION_REVISION
                        and previous.get("extraction_settings") == settings
                        and previous.get("source_url") == filing["url"]
                        and previous.get("source_path") == str(raw_path.resolve())
                        and previous.get("accession") == filing["accession"]
                        and isinstance(previous.get("pages"), list)
                        and "source_method" in previous and "page_count" in previous):
                    extracted = previous
            except (ValueError, OSError):
                pass
        reused = extracted is not None
        if extracted is None:
            extracted = document_text(raw_path, filing["url"], filing["accession"], settings)
            _write_json(text_path, extracted)
        documents.append({**filing, "source_path": str(raw_path.resolve()), "text_path": str(text_path.resolve()),
                          "sha256": digest, "source_method": extracted["source_method"],
                          "page_count": extracted["page_count"], "extraction_reused": reused,
                          "quality_flags": sorted({flag for page in extracted["pages"]
                                                   for flag in page.get("quality_flags", [])})})

    for company in companies:
        cik = company["cik"]
        cache = output_dir / "cache" / cik
        coverage = {"companyfacts": "not_attempted", "periodic_forms_selected": [],
                    "periodic_forms_collected": [], "exhibits_selected": 0, "exhibits_collected": 0,
                    "index_status": {}, "facts_collected": 0}
        summary = {"cik": cik, "company_name": company["company_name"], "coverage": coverage,
                   "status": "collecting"}
        summaries.append(summary)
        receipt_start = len(client.receipts)
        try:
            submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            submissions = client.read_json(submissions_url, cache / "submissions.json")
            selected = select_filings(cik, submissions, max_filings_per_company)
            coverage["filing_history"] = "available" if submissions.get("filings", {}).get("recent", {}).get("accessionNumber") else "none_found"
            coverage["periodic_forms_selected"] = [f["form"] for f in selected if f["form"] in {"10-K", "10-Q"}]
            coverage["periodic_forms_missing"] = [form for form in ("10-K", "10-Q") if form not in coverage["periodic_forms_selected"]]
            if coverage["periodic_forms_missing"]:
                warnings.append({"cik": cik, "stage": "periodic_coverage",
                                 "message": "No selected original " + ", ".join(coverage["periodic_forms_missing"])})
            companyfacts = None
            try:
                companyfacts = client.read_json(facts_url, cache / "companyfacts.json")
                coverage["companyfacts"] = "available"
                coverage["companyfacts_sha256"] = hashlib.sha256((cache / "companyfacts.json").read_bytes()).hexdigest()
            except (HTTPError, FileNotFoundError) as exc:
                if not (isinstance(exc, HTTPError) and exc.code == 404 or isinstance(exc, FileNotFoundError) and offline):
                    raise
                coverage["companyfacts"] = "unavailable"
                warnings.append({"cik": cik, "stage": "companyfacts", "message": str(exc)})
            accessions = {filing["accession"] for filing in selected}
            rows = [row for row in cash_flow_rows(cik, companyfacts or {}) if row["accession"] in accessions]
            for row in rows:
                row.update(data_sha256=coverage["companyfacts_sha256"],
                           data_path=str((cache / "companyfacts.json").resolve()))
            facts.extend(rows)
            coverage["facts_collected"] = len(rows)
            for filing in selected:
                accn = filing["accession"]
                suffix = Path(filing["filename"]).suffix.lower()
                save_document({**filing, "document_role": "primary", "sec_type": filing["form"], "description": "Primary document"},
                              cache / f"{accn}{suffix}", output_dir / "text" / cik / accn / (filing["filename"] + ".json"))
                if filing["form"] in {"10-K", "10-Q"}:
                    coverage["periodic_forms_collected"].append(filing["form"])
                if max_exhibits_per_filing == 0:
                    coverage["index_status"][accn] = "disabled"
                    continue
                index_url = filing["url"].rsplit("/", 1)[0] + f"/{accn}-index.html"
                try:
                    index = client.read(index_url, cache / f"{accn}-index.html")
                except FileNotFoundError as exc:
                    coverage["index_status"][accn] = "unavailable"
                    warnings.append({"cik": cik, "accession": accn, "stage": "filing_index", "message": str(exc)})
                    continue
                exhibits = select_exhibits(filing, index, max_exhibits_per_filing)
                coverage["index_status"][accn] = "available"
                coverage["exhibits_selected"] += len(exhibits)
                for exhibit in exhibits:
                    save_document(exhibit, cache / accn / "exhibits" / exhibit["filename"],
                                  output_dir / "text" / cik / accn / (exhibit["filename"] + ".json"))
                    coverage["exhibits_collected"] += 1
            summary["status"] = "complete"
        except Exception as exc:
            run_status = "blocked" if isinstance(exc, SecAccessBlocked) else "error"
            summary["status"] = run_status
            errors.append({"cik": cik, "error_type": type(exc).__name__, "message": str(exc)})
            break
        finally:
            summary["metadata_receipts"] = client.receipts[receipt_start:]
    checks = cash_bridge_checks(facts)
    _write_csv(output_dir / "facts.csv", FACT_FIELDS, facts)
    _write_csv(output_dir / "checks.csv", CHECK_FIELDS, checks)
    completed = sum(c["status"] == "complete" for c in summaries)
    manifest = {"company_count": completed, "requested_company_count": len(companies),
                "attempted_company_count": len(summaries), "completed_company_count": completed,
                "document_count": len(documents),
                "fact_count": len(facts), "check_count": len(checks), "offline": offline,
                "collected_at": datetime.now(timezone.utc).isoformat(), "run_status": run_status,
                "companies": summaries, "documents": documents, "warnings": warnings, "errors": errors,
                "coverage_scope": "Bounded public filing evidence; does not represent every loan or bank transaction"}
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies-csv", type=Path, default=DEFAULT_COMPANIES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--contact-email", default="", help="real SEC request contact for live mode")
    parser.add_argument("--max-companies", type=int, default=1)
    parser.add_argument("--max-filings-per-company", type=int, default=4)
    parser.add_argument("--max-exhibits-per-filing", type=int, default=2)
    parser.add_argument("--rate", type=float, default=2)
    parser.add_argument("--offline", action="store_true", help="read previously cached SEC responses only")
    args = parser.parse_args(argv)
    try:
        result = collect(args.companies_csv, args.output_dir, contact_email=args.contact_email,
                         offline=args.offline, max_companies=args.max_companies,
                         max_filings_per_company=args.max_filings_per_company, rate=args.rate,
                         max_exhibits_per_filing=args.max_exhibits_per_filing)
    except (SecAccessBlocked, FileNotFoundError, ValueError) as exc:
        parser.exit(1, f"Collection stopped: {exc}\n")
    print(f"Collected {result['document_count']} documents and {result['fact_count']} facts in {args.output_dir}")
    return 0 if result["run_status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
