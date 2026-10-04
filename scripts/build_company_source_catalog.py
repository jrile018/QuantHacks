"""Build a CIK-keyed SEC source catalog for the Tiger 8-K issuer universe.

Base mode needs only the input CSV. Full mode requests SEC submissions,
Company Facts, and filing directories, with caching and a single rate limiter.
Run full mode as one Slurm job from HiPerGator Blue storage.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


RESOURCE_FIELDS = (
    "kind", "form", "filing_date", "report_date", "accession", "filename",
    "format", "url", "verification",
)
FILING_FIELDS = (
    "cik", "accession", "form", "filing_date", "report_date", "index_url",
    "directory_json_url", "primary_document_url", "complete_text_url",
)
NODE_FIELDS = ("id", "kind", "label", "url", "format", "form", "cik")
EDGE_FIELDS = ("source", "target", "relation")
SEC_DATA = "https://data.sec.gov"
SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
INDEX_FORMS = (
    "10-K", "10-Q", "8-K", "20-F", "40-F", "6-K", "DEF 14A", "DEFA14A",
    "S-1", "F-1", "S-3", "F-3", "S-4", "424B", "DEFM14A", "11-K",
    "N-CSR", "N-CSRS", "N-PORT", "10-D",
)


class SecAccessBlocked(RuntimeError):
    """SEC denied access, so the caller must stop rather than keep requesting."""


class RateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        if not 0 < requests_per_second <= 10:
            raise ValueError("SEC request rate must be above 0 and at most 10/sec")
        self.interval = 1.0 / requests_per_second
        self.next_at = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        if now < self.next_at:
            time.sleep(self.next_at - now)
        self.next_at = time.monotonic() + self.interval


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def fetch_json(url: str, cache: Path, user_agent: str, limiter: RateLimiter) -> dict | None:
    if cache.exists():
        with cache.open(encoding="utf-8") as handle:
            return json.load(handle)
    cache.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(5):
        limiter.wait()
        request = Request(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            },
        )
        try:
            with urlopen(request, timeout=45) as response:
                body = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    body = gzip.decompress(body)
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError(f"Expected JSON object from {url}")
            write_json(cache, data)
            return data
        except HTTPError as error:
            if error.code == 404:
                return None
            if error.code == 403:
                raise SecAccessBlocked(f"SEC returned 403 for {url}; stopped requests") from error
            if error.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise
            time.sleep(min(2 ** attempt * 2, 30))
        except (URLError, TimeoutError):
            if attempt == 4:
                raise
            time.sleep(min(2 ** attempt * 2, 30))
    raise AssertionError("Unreachable retry state")


def normalized_cik(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if not digits or len(digits) > 10:
        raise ValueError(f"Invalid CIK: {value!r}")
    return digits.zfill(10)


def filing_base(cik: str, accession: str) -> str:
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
        raise ValueError(f"Invalid accession: {accession!r}")
    return f"{SEC_ARCHIVE}/{int(cik)}/{accession.replace('-', '')}"


def resource(kind: str, url: str, **values: str) -> dict[str, str]:
    row = {field: "" for field in RESOURCE_FIELDS}
    row.update(kind=kind, url=url, verification="constructed")
    row.update(values)
    return row


def base_resources(cik: str) -> list[dict[str, str]]:
    return [
        resource("sec_company_page", f"https://www.sec.gov/edgar/browse/?CIK={cik}&owner=exclude", format="html"),
        resource("sec_submissions_api", f"{SEC_DATA}/submissions/CIK{cik}.json", format="json"),
        resource("sec_companyfacts_api", f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json", format="json"),
        resource(
            "sec_financial_notes_datasets",
            "https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets",
            format="html",
        ),
    ]


def submissions_rows(data: dict) -> list[dict[str, str]]:
    recent = data.get("filings", {}).get("recent", {})
    if not isinstance(recent, dict):
        return []
    accessions = recent.get("accessionNumber", [])
    if not isinstance(accessions, list):
        return []
    fields = {
        "accession": "accessionNumber",
        "form": "form",
        "filing_date": "filingDate",
        "report_date": "reportDate",
        "primary_document": "primaryDocument",
    }
    rows: list[dict[str, str]] = []
    for index, accession in enumerate(accessions):
        row = {}
        for output, source in fields.items():
            column = recent.get(source, [])
            row[output] = str(column[index] or "") if isinstance(column, list) and index < len(column) else ""
        if re.fullmatch(r"\d{10}-\d{2}-\d{6}", row["accession"]):
            rows.append(row)
    return rows


def should_index(form: str) -> bool:
    clean = form.strip().upper()
    return any(clean == prefix or clean.startswith(prefix + "/") or
               (prefix == "424B" and clean.startswith("424B")) for prefix in INDEX_FORMS)


def document_format(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix or "unknown"


def directory_documents(
    index_data: dict,
    base: str,
    form: str,
    filing_date: str,
    report_date: str,
    accession: str,
) -> list[dict[str, str]]:
    items = index_data.get("directory", {}).get("item", [])
    if not isinstance(items, list):
        return []
    found: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("name", ""))
        if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
            continue
        found.append(resource(
            "filed_document",
            f"{base}/{quote(filename, safe='-._~')}",
            form=form,
            filing_date=filing_date,
            report_date=report_date,
            accession=accession,
            filename=filename,
            format=document_format(filename),
            verification="listed_by_sec",
        ))
    return found


def company_files(row: dict[str, str], output: Path, mode: str, user_agent: str, limiter: RateLimiter | None) -> dict:
    cik = normalized_cik(row["cik"])
    folder = output / "companies" / f"CIK{cik}"
    folder.mkdir(parents=True, exist_ok=True)
    cache = output / "cache" / f"CIK{cik}"
    company = {
        "cik": cik,
        "input_company_name": row["company_name"],
        "input_tickers": row.get("tickers", ""),
        "input_other_recorded_names": row.get("other_recorded_names", ""),
        "sec_company_url": f"https://www.sec.gov/edgar/browse/?CIK={cik}&owner=exclude",
        "catalog_mode": mode,
    }
    resources = base_resources(cik)
    filings: list[dict[str, str]] = []
    documents: list[dict[str, str]] = []
    errors: list[str] = []

    if mode == "full":
        assert limiter is not None
        url = f"{SEC_DATA}/submissions/CIK{cik}.json"
        submissions = fetch_json(url, cache / "submissions.json", user_agent, limiter)
        if submissions is None:
            errors.append("Submissions API returned 404")
        else:
            company["sec_company_name"] = str(submissions.get("name", ""))
            company["sic"] = str(submissions.get("sic", ""))
            company["fiscal_year_end"] = str(submissions.get("fiscalYearEnd", ""))
            company["entity_type"] = str(submissions.get("entityType", ""))
            resources[1]["verification"] = "downloaded"
            all_rows = submissions_rows(submissions)
            for history in submissions.get("filings", {}).get("files", []):
                name = history.get("name", "") if isinstance(history, dict) else ""
                if not re.fullmatch(r"CIK\d{10}-submissions-\d{3}\.json", name):
                    errors.append(f"Unrecognized older-history filename: {name}")
                    continue
                history_url = f"{SEC_DATA}/submissions/{name}"
                resources.append(resource(
                    "sec_submissions_history", history_url, format="json", verification="listed_by_sec",
                ))
                history_data = fetch_json(history_url, cache / name, user_agent, limiter)
                if history_data:
                    all_rows.extend(submissions_rows({"filings": {"recent": history_data}}))
                    resources[-1]["verification"] = "downloaded"
            by_accession = {item["accession"]: item for item in all_rows}
            for item in sorted(by_accession.values(), key=lambda x: (x["filing_date"], x["accession"]), reverse=True):
                accession = item["accession"]
                base = filing_base(cik, accession)
                index_url = f"{base}/{accession}-index.html"
                directory_url = f"{base}/index.json"
                text_url = f"{base}/{accession}.txt"
                primary = item["primary_document"]
                primary_url = f"{base}/{quote(primary, safe='-._~')}" if primary and "/" not in primary and "\\" not in primary else ""
                filing = {
                    "cik": cik,
                    "accession": accession,
                    "form": item["form"],
                    "filing_date": item["filing_date"],
                    "report_date": item["report_date"],
                    "index_url": index_url,
                    "directory_json_url": directory_url,
                    "primary_document_url": primary_url,
                    "complete_text_url": text_url,
                }
                filings.append(filing)
                common = dict(
                    form=item["form"], filing_date=item["filing_date"],
                    report_date=item["report_date"], accession=accession,
                    verification="listed_by_sec",
                )
                resources.append(resource("filing_index", index_url, format="html", **common))
                resources.append(resource("filing_directory_json", directory_url, format="json", **common))
                resources.append(resource("filing_complete_text", text_url, format="txt", **common))
                if primary_url:
                    resources.append(resource(
                        "filing_primary_document", primary_url, filename=primary,
                        format=document_format(primary), **common,
                    ))
                if should_index(item["form"]):
                    index_cache = cache / "filing_indexes" / f"{accession}.json"
                    index_data = fetch_json(directory_url, index_cache, user_agent, limiter)
                    if index_data:
                        resources[-(3 if primary_url else 2)]["verification"] = "downloaded"
                        documents.extend(directory_documents(
                            index_data, base, item["form"], item["filing_date"],
                            item["report_date"], accession,
                        ))
                    else:
                        errors.append(f"Filing directory returned 404: {accession}")

        facts_url = f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json"
        facts = fetch_json(facts_url, cache / "companyfacts.json", user_agent, limiter)
        if facts is None:
            errors.append("Company Facts API returned 404 (possibly no qualifying XBRL)")
        else:
            shutil.copyfile(cache / "companyfacts.json", folder / "companyfacts.json")
            resources[2]["verification"] = "downloaded"
            company["companyfacts_taxonomies"] = {
                taxonomy: len(tags) for taxonomy, tags in facts.get("facts", {}).items()
                if isinstance(tags, dict)
            }

    documents = sorted(
        {doc["url"]: doc for doc in documents}.values(),
        key=lambda doc: (doc["filing_date"], doc["accession"], doc["filename"]),
        reverse=True,
    )
    resources.extend(documents)
    resources = list({(item["kind"], item["url"]): item for item in resources}.values())
    pdfs = [item for item in documents if item["format"] == "pdf"]
    write_json(folder / "company.json", company)
    write_csv(folder / "resources.csv", RESOURCE_FIELDS, resources)
    write_csv(folder / "filings.csv", FILING_FIELDS, filings)
    write_csv(folder / "documents.csv", RESOURCE_FIELDS, documents)
    write_csv(folder / "pdfs.csv", RESOURCE_FIELDS, pdfs)
    guide = [
        f"# {company.get('sec_company_name') or company['input_company_name']}",
        "",
        f"CIK: {cik}. Input tickers: {company['input_tickers'] or '(none listed)'}.",
        "",
        f"SEC company page: {company['sec_company_url']}",
        f"Submissions JSON: {SEC_DATA}/submissions/CIK{cik}.json",
        f"Company Facts JSON: {SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json",
        "",
        "Read the latest annual report first, then interim reports, material event",
        "filings and their exhibits, proxy statements, and offerings. Each filing",
        "index lists its actual documents. A PDF list may be empty because many",
        "filed financial reports use HTML and XBRL.",
        "",
        f"Discovered filings: {len(filings)}. Listed filed documents: {len(documents)}.",
        f"Listed PDFs: {len(pdfs)}. Catalog mode: {mode}.",
        "",
        "Local tables: resources.csv, filings.csv, documents.csv, pdfs.csv.",
        "Verification values distinguish constructed links from SEC-listed files",
        "and downloaded API responses. See the repository source-map guide.",
    ]
    if errors:
        guide.extend(["", "## Gaps and errors", ""])
        guide.extend(f"- {error}" for error in errors)
    (folder / "README.md").write_text("\n".join(guide) + "\n", encoding="utf-8")
    result = {
        "cik": cik, "mode": mode, "filings": len(filings),
        "documents": len(documents), "pdfs": len(pdfs), "errors": errors,
    }
    write_json(folder / "complete.json", result)
    return result


def graph(output: Path) -> dict[str, int]:
    nodes: dict[str, dict[str, str]] = {}
    edges: set[tuple[str, str, str]] = set()
    for folder in sorted((output / "companies").glob("CIK*")):
        company_path = folder / "company.json"
        resources_path = folder / "resources.csv"
        if not company_path.exists() or not resources_path.exists():
            continue
        company = json.loads(company_path.read_text(encoding="utf-8"))
        cik = company["cik"]
        issuer_id = f"issuer:{cik}"
        nodes[issuer_id] = {
            "id": issuer_id, "kind": "issuer",
            "label": company.get("sec_company_name") or company["input_company_name"],
            "url": company["sec_company_url"], "cik": cik,
        }
        with resources_path.open(encoding="utf-8", newline="") as handle:
            for item in csv.DictReader(handle):
                url = item["url"]
                resource_id = "url:" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
                nodes[resource_id] = {
                    "id": resource_id, "kind": item["kind"],
                    "label": item["filename"] or item["kind"],
                    "url": url, "format": item["format"],
                    "form": item["form"], "cik": cik,
                }
                accession = item["accession"]
                if accession:
                    filing_id = f"filing:{accession}"
                    nodes.setdefault(filing_id, {
                        "id": filing_id, "kind": "filing", "label": accession,
                        "url": "", "form": item["form"], "cik": cik,
                    })
                    edges.add((issuer_id, filing_id, "FILED"))
                    edges.add((filing_id, resource_id, "HAS_RESOURCE"))
                else:
                    edges.add((issuer_id, resource_id, "HAS_SOURCE"))
    node_rows = [{field: node.get(field, "") for field in NODE_FIELDS} for node in nodes.values()]
    edge_rows = [dict(zip(EDGE_FIELDS, edge)) for edge in sorted(edges)]
    write_csv(output / "graph" / "nodes.csv", NODE_FIELDS, node_rows)
    write_csv(output / "graph" / "edges.csv", EDGE_FIELDS, edge_rows)
    (output / "graph" / "source-map.mmd").write_text(
        "graph LR\n"
        "  issuer[Issuer CIK] --> submissions[SEC Submissions JSON]\n"
        "  issuer --> facts[SEC Company Facts JSON]\n"
        "  issuer --> filing[SEC filing accession]\n"
        "  filing --> index[Filing document index]\n"
        "  filing --> primary[Primary report HTML or PDF]\n"
        "  filing --> exhibit[Exhibits and other filed files]\n"
        "  filing --> text[Complete submission text]\n"
        "  exhibit --> pdf[PDF where actually filed]\n",
        encoding="utf-8",
    )
    return {"nodes": len(node_rows), "edges": len(edge_rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("base", "full"), default="full")
    parser.add_argument("--contact-email", default=os.environ.get("SEC_CONTACT_EMAIL", ""))
    parser.add_argument("--rate", type=float, default=5.0)
    parser.add_argument("--max-companies", type=int, default=0, help="Pilot limit; 0 means all")
    parser.add_argument("--refresh", action="store_true", help="Rebuild completed company folders")
    args = parser.parse_args()
    if args.mode == "full" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", args.contact_email):
        parser.error("Full mode needs --contact-email or SEC_CONTACT_EMAIL")
    if args.max_companies < 0:
        parser.error("--max-companies cannot be negative")
    limiter = RateLimiter(args.rate) if args.mode == "full" else None
    user_agent = f"QuantHaxs financial source research {args.contact_email}" if args.contact_email else ""
    with args.companies_csv.open(encoding="utf-8-sig", newline="") as handle:
        company_rows = list(csv.DictReader(handle))
    if args.max_companies:
        company_rows = company_rows[:args.max_companies]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    status = {"mode": args.mode, "input_companies": len(company_rows), "completed": 0,
              "skipped": 0, "errors": [], "blocked": False}
    try:
        for number, company_row in enumerate(company_rows, start=1):
            cik = normalized_cik(company_row["cik"])
            complete_path = args.output_dir / "companies" / f"CIK{cik}" / "complete.json"
            if not args.refresh and complete_path.exists():
                old = json.loads(complete_path.read_text(encoding="utf-8"))
                if old.get("mode") == args.mode or (old.get("mode") == "full" and args.mode == "base"):
                    status["skipped"] += 1
                    continue
            result = company_files(company_row, args.output_dir, args.mode, user_agent, limiter)
            status["completed"] += 1
            status["errors"].extend({"cik": cik, "detail": error} for error in result["errors"])
            if number % 25 == 0 or number == len(company_rows):
                print(f"{number}/{len(company_rows)} issuers processed; {result['filings']} filings for CIK {cik}", flush=True)
    except SecAccessBlocked as error:
        status["blocked"] = True
        status["errors"].append({"detail": str(error)})
        print(str(error), file=sys.stderr)
    except Exception as error:
        status["errors"].append({"detail": f"{type(error).__name__}: {error}"})
        print(f"Catalog stopped: {type(error).__name__}: {error}", file=sys.stderr)
    finally:
        status["graph"] = graph(args.output_dir)
        write_json(args.output_dir / "runs" / "run-status.json", status)
    print(json.dumps(status, ensure_ascii=False), flush=True)
    return 1 if status["blocked"] or status["completed"] + status["skipped"] < len(company_rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
