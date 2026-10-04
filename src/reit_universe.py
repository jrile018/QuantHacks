"""Pure, evidence-driven REIT discovery and dated security eligibility.

No network access: source acquisition belongs to the shared broker. Intervals
are half open [valid_from, valid_to); known_from is an aware timestamp.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from hashlib import sha256
from html.parser import HTMLParser
from itertools import product
import json
import re
from urllib.parse import urljoin, urlsplit

NAREIT_TICKER_URL = "https://www.reit.com/data-research/reit-indexes/reits-by-ticker-symbol"


class _TickerTableParser(HTMLParser):
    """Read the observed Drupal table by its headers, without CSS dependencies."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.table is not None:
                raise ValueError("Nested ticker tables are unsupported")
            self.table = []
        elif self.table is not None and tag == "tr":
            self.row = []
        elif self.row is not None and tag in {"th", "td"}:
            self.cell = {"text": [], "hrefs": []}
        elif self.cell is not None and tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.cell["hrefs"].append(href)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"].append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.cell["text"] = " ".join("".join(self.cell["text"]).split())
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def parse_nareit_ticker_table(payload: str | bytes, *, source_url: str = NAREIT_TICKER_URL,
                             retrieved_at: str | None = None) -> list[dict]:
    """Import the saved Nareit RTC Ticker / Company name HTML table.

    No per-row REIT/REOC or common-share classification exists in the observed
    source. Return unresolved candidates with exact source fingerprint/locator.
    """
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    parser = _TickerTableParser()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    if parser.table is not None or parser.cell is not None:
        raise ValueError("Incomplete Nareit HTML table")
    digest = sha256(raw).hexdigest()
    result = []
    matched_tables = 0
    for table_index, table in enumerate(parser.tables):
        if not table:
            continue
        headers = [cell["text"].casefold() for cell in table[0]]
        if "rtc ticker" not in headers or "company name" not in headers:
            continue
        matched_tables += 1
        ticker_index, name_index = headers.index("rtc ticker"), headers.index("company name")
        for row_index, cells in enumerate(table[1:], 1):
            if len(cells) != len(headers):
                raise ValueError("Nareit ticker row does not match header width")
            ticker, name = cells[ticker_index]["text"], cells[name_index]["text"]
            if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,19}", ticker) or not name:
                raise ValueError(f"Invalid Nareit candidate row {row_index}")
            hrefs = cells[name_index]["hrefs"] or cells[ticker_index]["hrefs"]
            profile = urljoin(source_url, hrefs[0]) if hrefs else None
            result.append({"cik": None, "ticker": ticker, "name": name,
                "source_classification": "unknown_reit_or_reoc", "profile_url": profile,
                "source_url": source_url, "source_sha256": digest,
                "source_locator": f"HTML table[{table_index}] row[{row_index}]: RTC Ticker / Company name",
                "retrieved_at": _known(retrieved_at) if retrieved_at else None,
                "discovery_status": "candidate_only"})
    if matched_tables != 1 or not result:
        raise ValueError("Expected exactly one nonempty Nareit ticker table")
    if len({row["ticker"] for row in result}) != len(result):
        raise ValueError("Duplicate Nareit ticker rows require explicit reconciliation")
    return sorted(result, key=lambda row: row["ticker"])


def normalize_cik(value):
    text = str(value).strip()
    if not text.isdigit() or len(text) > 10 or int(text) <= 0:
        raise ValueError(f"Invalid CIK: {value!r}")
    return text.zfill(10)


def _date(value):
    return date.fromisoformat(value).isoformat()


def _known(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("known_from requires an explicit timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parse_sec_exchange_map(payload: dict) -> list[dict]:
    """Import SEC company_tickers_exchange.json's observed fields/data format.

    Exchanges/tickers are discovery metadata, never proof of REIT status or class.
    """
    fields = payload.get("fields")
    data = payload.get("data")
    if not isinstance(fields, list) or len(set(fields)) != len(fields) or not isinstance(data, list):
        raise ValueError("Expected SEC fields/data arrays")
    if not {"cik", "name", "ticker", "exchange"}.issubset(fields):
        raise ValueError("Missing SEC exchange map fields")
    result = []
    for row in data:
        if not isinstance(row, list) or len(row) != len(fields):
            raise ValueError("Unequal SEC exchange row length")
        item = dict(zip(fields, row))
        item["cik"] = normalize_cik(item["cik"])
        item["discovery_source"] = "https://www.sec.gov/files/company_tickers_exchange.json"
        result.append(item)
    return sorted(result, key=lambda row: (row["cik"], str(row["ticker"])))


def _evidence(row):
    item = dict(row)
    if not isinstance(item.get("kind"), str) or not item["kind"].strip():
        raise ValueError("Missing or invalid evidence kind")
    item["cik"] = normalize_cik(item["cik"])
    item["valid_from"] = _date(item["valid_from"])
    if item.get("valid_to"):
        item["valid_to"] = _date(item["valid_to"])
        if item["valid_to"] <= item["valid_from"]:
            raise ValueError("Empty or reversed validity interval")
    item["known_from"] = _known(item["known_from"])
    for field in ("source_available_at", "accepted_at", "published_at"):
        if item.get(field):
            source_clock = _known(item[field])
            if item["known_from"] < source_clock:
                raise ValueError(f"known_from precedes {field}")
    if item.get("known_to"):
        item["known_to"] = _known(item["known_to"])
        if item["known_to"] <= item["known_from"]:
            raise ValueError("Empty or reversed knowledge interval")
    source_url = item.get("source_url", "")
    parts = urlsplit(source_url)
    if (parts.scheme != "https" or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.port not in {None, 443}
            or any(ord(char) < 33 or ord(char) == 127 for char in source_url)):
        raise ValueError("Evidence requires an exact HTTPS source URL")
    if not (item.get("source_sha256") or (item.get("locator") and item.get("quote"))):
        raise ValueError("Evidence requires source_sha256 or locator and quote")
    if item.get("source_sha256") and (len(item["source_sha256"]) != 64 or
                                      any(c not in "0123456789abcdef" for c in item["source_sha256"].lower())):
        raise ValueError("Invalid source SHA256")
    item.setdefault("evidence_id", _fingerprint(item))
    return item


def _matches(row, security):
    if row["cik"] != security["cik"]:
        return False
    if row["kind"] in {"listing", "security_type", "exit"}:
        if row.get("security_id"):
            return row["security_id"] == security["security_id"]
        return bool(row.get("ticker")) and row["ticker"] == security.get("ticker")
    return True


def _active(row, day, clock):
    return (row["valid_from"] <= day and (not row.get("valid_to") or day < row["valid_to"])
            and row["known_from"] <= clock and (not row.get("known_to") or clock < row["known_to"]))


def build_universe(candidates: list[dict], evidence: list[dict], as_of: str) -> dict:
    """Validate a dated snapshot; retain historical assertions and intersections.

    Date-only as_of means UTC end of day. Evidence errors are retained in coverage;
    candidate CIK errors raise because silent identity repair is unsafe.
    """
    if "T" in as_of:
        clock = _known(as_of)
        day = clock[:10]
    else:
        day = _date(as_of)
        clock = datetime.combine(date.fromisoformat(day), time.max, timezone.utc).isoformat()
    proof, errors = [], []
    for index, row in enumerate(evidence):
        try:
            proof.append(_evidence(row))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append({"index": index, "error": str(exc), "evidence": row})
    proof.sort(key=lambda row: row["evidence_id"])
    issuers, securities = {}, {}
    for row in candidates:
        item = dict(row)
        if not item.get("cik"):
            item["cik"] = None
            key = item.get("security_id") or "unresolved:" + _fingerprint(item)
        else:
            item["cik"] = normalize_cik(item["cik"])
            key = item.get("security_id") or f"{item['cik']}:{item.get('ticker', '')}:{item.get('security_type', 'unknown')}"
            issuer = issuers.setdefault(item["cik"], {"issuer_id": "cik:" + item["cik"],
                "cik": item["cik"], "name": item.get("name", item.get("company_name", "")),
                "aliases": [], "history": []})
            issuer["aliases"] = [ev for ev in proof if ev["cik"] == item["cik"] and ev["kind"] == "alias"]
            issuer["history"] = [ev for ev in proof if ev["cik"] == item["cik"] and ev["kind"] in {"merger", "exit", "reit_status"}]
        item["security_id"] = key
        if key in securities and securities[key]["cik"] != item["cik"]:
            raise ValueError("Security identity collision across CIKs")
        if key not in securities:
            item["candidate_sources"] = [dict(row)]
            securities[key] = item
        else:
            securities[key]["candidate_sources"].append(dict(row))
    validated, pending, excluded = [], [], []
    for security in sorted(securities.values(), key=lambda row: row["security_id"]):
        rows = [ev for ev in proof if _matches(ev, security)] if security["cik"] else []
        security["evidence"] = rows
        groups = [[ev for ev in rows if ev["kind"] == kind and ev.get("value") == value]
                  for kind, value in [("reit_status", True), ("listing", True), ("security_type", "common")]]
        groups[1] = [ev for ev in groups[1] if ev.get("exchange") in {"NYSE", "Nasdaq", "NASDAQ", "NYSE American", "NYSE Arca", "Cboe"}]
        intervals = []
        for combo in product(*groups):
            start = max(ev["valid_from"] for ev in combo)
            ends = [ev["valid_to"] for ev in combo if ev.get("valid_to")]
            end = min(ends) if ends else None
            if end and start >= end:
                continue
            known_start = max(ev["known_from"] for ev in combo)
            known_end = min((ev["known_to"] for ev in combo if ev.get("known_to")), default=None)
            if known_end and known_start >= known_end:
                continue
            blockers = [ev["evidence_id"] for ev in rows if
                (ev["kind"] == "exit" or (ev["kind"] in {"listing", "reit_status"} and ev.get("value") is False)
                 or (ev["kind"] == "security_type" and ev.get("value") != "common"))
                and (not end or ev["valid_from"] < end)
                and (not ev.get("valid_to") or start < ev["valid_to"])]
            intervals.append({"valid_from": start, "valid_to": end,
                "known_from": known_start, "known_to": known_end,
                "evidence_ids": [ev["evidence_id"] for ev in combo],
                "blocking_evidence_ids": blockers,
                "status": "requires_dated_blocker_resolution" if blockers else "supported_intersection"})
        security["eligibility_intervals"] = sorted(intervals, key=lambda row: (row["valid_from"], row["known_from"], row["evidence_ids"]))
        active = [ev for ev in rows if _active(ev, day, clock)]
        reasons = []
        for kind, value in [("reit_status", True), ("listing", True), ("security_type", "common")]:
            matches = [ev for ev in active if ev["kind"] == kind]
            values = {str(ev.get("value")) for ev in matches}
            if len(values) > 1:
                reasons.append("conflicting_" + kind + "_evidence")
            elif not any(ev.get("value") == value for ev in matches):
                reasons.append(("security_type_" + str(matches[0].get("value"))) if kind == "security_type" and matches else "missing_" + kind + "_evidence")
        if any(ev["kind"] == "listing" and ev.get("value") is True and ev.get("exchange") not in {"NYSE", "Nasdaq", "NASDAQ", "NYSE American", "NYSE Arca", "Cboe"} for ev in active):
            reasons.append("unsupported_us_exchange")
        if any(ev["kind"] == "reit_status" and ev.get("value") is False for ev in active):
            reasons.append("not_reit")
        if any(ev["kind"] == "listing" and ev.get("value") is False for ev in active):
            reasons.append("not_listed")
        if any(ev["kind"] == "exit" for ev in active):
            reasons.append("exited")
        security["reasons"] = reasons
        if not reasons:
            validated.append(security)
        elif any(reason.startswith("security_type_") or reason in {"not_reit", "not_listed", "exited", "unsupported_us_exchange"} for reason in reasons):
            excluded.append(security)
        else:
            pending.append(security)
    return {"schema_version": "reit-universe-1", "as_of": as_of,
        "input_sha256": _fingerprint({"candidates": candidates, "evidence": evidence, "as_of": as_of}),
        "issuers": sorted(issuers.values(), key=lambda row: row["cik"]),
        "securities": sorted(securities.values(), key=lambda row: row["security_id"]),
        "validated": validated, "candidates": pending, "exclusions": excluded,
        "coverage": {"candidate_count": len(securities), "validated_count": len(validated),
            "unverified_count": len(pending), "excluded_count": len(excluded), "evidence_errors": errors,
            "history_complete": False, "gaps": ["discovery_not_exhaustive", "historical_membership_not_exhaustive"]}}
