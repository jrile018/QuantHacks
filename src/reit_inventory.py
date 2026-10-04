"""Deterministic SEC submissions inventory, including historical file pages."""
from __future__ import annotations

from datetime import date
import re
from urllib.parse import quote, unquote, urlsplit

from src.reit_universe import normalize_cik, _fingerprint

DEFAULT_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A"}


def _rows(data, cik, source):
    required = ("accessionNumber", "filingDate", "form", "primaryDocument")
    if not isinstance(data, dict) or any(not isinstance(data.get(key), list) for key in required):
        raise ValueError("Missing required submissions arrays")
    count = len(data["accessionNumber"])
    for key, values in data.items():
        if isinstance(values, list) and len(values) != count:
            raise ValueError(f"Unequal submissions array length: {key}")
    result = []
    for index in range(count):
        row = {key: values[index] for key, values in data.items() if isinstance(values, list)}
        accession, primary = row["accessionNumber"], row["primaryDocument"]
        if not isinstance(accession, str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            raise ValueError("Invalid SEC accession")
        if (not isinstance(primary, str) or not primary or primary.startswith("/")
                or any(char in unquote(primary) for char in "\\?#:")
                or any(segment in {".", "..", ""} for segment in unquote(primary).split("/"))):
            raise ValueError("Unsafe or missing primaryDocument")
        filed = date.fromisoformat(row["filingDate"]).isoformat()
        if row.get("reportDate"):
            date.fromisoformat(row["reportDate"])
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
        result.append({**row, "cik": cik, "accession": accession, "filing_date": filed,
            "report_date": row.get("reportDate") or None, "accepted_at": row.get("acceptanceDateTime") or None,
            "availability_status": "not_verified", "url": base + quote(primary, safe="/.-_"),
            "index_url": base + accession + "-index.htm", "metadata_sources": [source]})
    return result


def build_inventory(scope: dict, metadata: list[dict]) -> dict:
    """Select all scoped forms from Jan 2024 onward plus opening/predecessor context.

    Uses filing date for scope selection. SEC acceptance is retained separately
    and is not promoted to verified public availability. Never truncates by count.
    """
    start = date.fromisoformat(scope.get("start_date", "2024-01-01")).isoformat()
    end_value = scope.get("end_date", scope.get("as_of"))
    if not end_value:
        raise ValueError("Explicit end_date or as_of required for deterministic inventory")
    end = date.fromisoformat(end_value[:10]).isoformat()
    if end < start:
        raise ValueError("Inventory end precedes start")
    requested = scope.get("ciks")
    if requested is None:
        requested = [row["cik"] for row in scope.get("issuers", scope.get("validated", [])) if row.get("cik")]
    ciks = {normalize_cik(value) for value in requested}
    predecessors = {normalize_cik(value) for value in scope.get("predecessor_ciks", [])}
    ciks |= predecessors
    forms = set(scope.get("forms", DEFAULT_FORMS))
    errors, missing_pages, conflicts = [], [], []
    seen_ciks, records = set(), {}
    for item in sorted(metadata, key=lambda row: str(row.get("cik", ""))):
        try:
            cik = normalize_cik(item["cik"])
            if cik not in ciks:
                continue
            submissions = item["submissions"]
            if submissions.get("cik") and normalize_cik(submissions["cik"]) != cik:
                raise ValueError("Submissions CIK does not match metadata identity")
            filings = submissions["filings"]
            seen_ciks.add(cik)
            recent = filings.get("recent", {})
            sources = [("recent", recent, item.get("source_url", f"https://data.sec.gov/submissions/CIK{cik}.json"))]
            pages = {}
            for page in item.get("historical_pages", []):
                if page["name"] in pages:
                    raise ValueError("Duplicate historical page name")
                pages[page["name"]] = page
            references = filings.get("files", [])
            if not isinstance(references, list):
                raise ValueError("Historical files must be an array")
            for reference in references:
                name = reference.get("name", "")
                if not re.fullmatch(rf"CIK{cik}-submissions-\d+\.json", name):
                    raise ValueError("Historical filename identity mismatch")
                for field in ("filingFrom", "filingTo"):
                    if reference.get(field):
                        date.fromisoformat(reference[field])
                if name not in pages:
                    missing_pages.append({"cik": cik, **reference,
                        "url": "https://data.sec.gov/submissions/" + name})
                else:
                    page = pages.pop(name)
                    sources.append((name, page.get("data"), page.get("source_url", "https://data.sec.gov/submissions/" + name)))
            for name in pages:
                errors.append({"cik": cik, "source": name, "error": "unreferenced_historical_page"})
            for name, data, source in sources:
                try:
                    receipt = item if name == "recent" else next(p for p in item.get("historical_pages", []) if p["name"] == name)
                    rows = _rows(data, cik, {"name": name, "url": source,
                        "input_sha256": _fingerprint(data), "source_sha256": receipt.get("source_sha256"),
                        "retrieved_at": receipt.get("retrieved_at"), "source_path": receipt.get("source_path")})
                except (ValueError, TypeError, KeyError) as exc:
                    errors.append({"cik": cik, "source": name, "error": str(exc)})
                    continue
                for row in rows:
                    key = (cik, row["accession"])
                    if key in records:
                        prior = records[key]
                        if any(prior.get(field) != row.get(field) for field in ("form", "filing_date", "url", "report_date", "accepted_at")):
                            conflicts.append({"cik": cik, "accession": row["accession"], "variants": [prior, row]})
                        else:
                            prior["metadata_sources"].extend(row["metadata_sources"])
                    else:
                        records[key] = row
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({"cik": item.get("cik"), "error": str(exc)})
    conflict_keys = {(row["cik"], row["accession"]) for row in conflicts}
    selected, excluded = [], []
    opening = {}
    if scope.get("opening_context", True):
        for row in records.values():
            if (row["cik"], row["accession"]) in conflict_keys:
                continue
            if row["filing_date"] < start and row["form"] == "10-K":
                prior = opening.get(row["cik"])
                if prior is None or (row["filing_date"], row["accession"]) > (prior["filing_date"], prior["accession"]):
                    opening[row["cik"]] = row
    context = set(scope.get("context_accessions", []))
    for row in sorted(records.values(), key=lambda r: (r["cik"], r["filing_date"], r["accession"])):
        reason = None
        if (row["cik"], row["accession"]) in conflict_keys:
            reason = "conflicting_metadata"
        elif row["filing_date"] > end:
            reason = "after_end_date"
        elif row["accession"] in context:
            row["selection_reason"] = "explicit_agreement_context"
        elif opening.get(row["cik"]) is row:
            row["selection_reason"] = "opening_context"
        elif row["form"] not in forms:
            reason = "form_out_of_scope"
        elif row["filing_date"] < start:
            reason = "before_start_date"
        else:
            row["selection_reason"] = "predecessor_period" if row["cik"] in predecessors else "study_period"
        if reason:
            excluded.append({**row, "exclusion_reason": reason})
        else:
            selected.append(row)
    documents = [{"cik": row["cik"], "accession": row["accession"], "url": row["url"],
        "type": row["form"], "document_role": "primary", "selected": True,
        "document_inventory_status": "exhibits_unverified"} for row in selected]
    selected_keys = {(row["cik"], row["accession"]) for row in selected}
    for doc in scope.get("document_evidence", []):
        try:
            cik = normalize_cik(doc["cik"])
            accession = doc.get("accession", doc.get("accessionNumber"))
            parts = urlsplit(doc["url"])
            expected = f"/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
            if (parts.scheme != "https" or parts.hostname != "www.sec.gov"
                    or parts.username is not None or parts.password is not None or parts.port not in {None, 443}
                    or any(ord(char) < 33 or ord(char) == 127 for char in doc["url"])
                    or not parts.path.startswith(expected) or ".." in unquote(parts.path).split("/")
                    or "\\" in unquote(parts.path) or parts.query or parts.fragment):
                raise ValueError("Document URL does not match SEC filing identity")
            if (cik, accession) in selected_keys and not any(row["url"] == doc["url"] and row["cik"] == cik for row in documents):
                documents.append({**doc, "cik": cik, "accession": accession, "selected": True,
                    "document_role": doc.get("document_role", "exhibit")})
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            errors.append({"source": "document_evidence", "error": str(exc)})
    gaps = ["document_inventory_unverified", "agreement_predecessor_context_unverified"]
    missing_opening = sorted(ciks - set(opening)) if scope.get("opening_context", True) else []
    if missing_opening:
        gaps.append("missing_opening_context")
    if missing_pages:
        gaps.append("missing_history_pages")
    if errors:
        gaps.append("metadata_errors")
    if conflicts:
        gaps.append("conflicting_filing_metadata")
    missing_ciks = sorted(ciks - seen_ciks)
    if missing_ciks:
        gaps.append("missing_issuer_metadata")
    missing_context = sorted(context - {row["accession"] for row in selected})
    if missing_context:
        gaps.append("missing_requested_context")
    return {"schema_version": "reit-inventory-1", "scope": scope,
        "input_sha256": _fingerprint({"scope": scope, "metadata": metadata}),
        "filings": sorted(records.values(), key=lambda r: (r["cik"], r["filing_date"], r["accession"])),
        "documents": sorted(documents, key=lambda r: (r["cik"], r["accession"], r["url"])),
        "selected": selected, "excluded": excluded,
        "coverage": {"history_complete": False, "filing_metadata_complete": not (errors or missing_pages or missing_ciks or conflicts),
            "requested_cik_count": len(ciks), "selected_filing_count": len(selected),
            "excluded_filing_count": len(excluded), "missing_ciks": missing_ciks,
            "missing_opening_context_ciks": missing_opening,
            "missing_context_accessions": missing_context,
            "missing_history_pages": missing_pages, "metadata_errors": errors,
            "conflicts": conflicts, "gaps": gaps}}
