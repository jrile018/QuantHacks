"""Bounded, read-only historical capture probe; raw captures stay on home-pc."""

import difflib
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
TARGETS = {
    "feb_sec": "https://www.sec.gov/Archives/edgar/data/1053507/000105350724000009/pressreleaseq42023.htm",
    "feb_issuer": "https://americantower.gcs-web.com/news-releases/news-release-details/american-tower-corporation-reports-fourth-quarter-and-full-19",
    "feb_wire": "https://www.businesswire.com/news/home/20240227784442/en/American-Tower-Corporation-Reports-Fourth-Quarter-and-Full-Year-2023-Financial-Results",
}
MAX_REQUESTS = 16
MAX_BYTES = 8 * 1024 * 1024
requests = 0
bytes_read = 0
last_request = 0.0


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        elif tag in {"p", "div", "br", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        elif tag in {"p", "div", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def normalized(data):
    parser = Text()
    parser.feed(data.decode("utf-8", errors="replace"))
    s = html.unescape("".join(parser.parts))
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).replace("\u00ad", "")).strip()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fetch(key, url, cap):
    global requests, bytes_read, last_request
    if requests >= MAX_REQUESTS or bytes_read + cap > MAX_BYTES:
        return {"url": url, "error": "request_or_byte_budget"}
    pause = 1.0 - (time.monotonic() - last_request)
    if pause > 0:
        time.sleep(pause)
    requests += 1
    last_request = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": "QuantHaxs public-bound research (contact: research@example.invalid)", "Accept": "text/html,application/json;q=0.9,*/*;q=0.5"})
    item = {"url": url, "attempt": requests}
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            item["status"] = r.status
            item["final_url"] = r.url
            item["headers"] = {k: v for k, v in r.headers.items() if k.lower() in {"content-type", "content-length", "memento-datetime", "last-modified", "date", "x-archive-orig-date"}}
            data = r.read(cap + 1)
            bytes_read += len(data)
            item["bytes"] = len(data)
            if len(data) > cap:
                item["error"] = "response_cap_exceeded"
                return item
            (ROOT / (key + ".raw")).write_bytes(data)
            item["sha256"] = sha(data)
            if b"<html" in data[:10000].lower() or b"<!doctype html" in data[:10000].lower():
                norm = normalized(data)
                (ROOT / (key + ".text")).write_text(norm, encoding="utf-8")
                item["normalized_text_sha256"] = sha(norm.encode())
                item["normalized_text_chars"] = len(norm)
            return item
    except Exception as exc:
        item["error"] = type(exc).__name__ + ": " + str(exc)[:250]
        return item


receipt = {"scope": "AMT February 2024 historical full-content capture", "algorithm": "Python html.parser skips script/style/noscript; HTML entities decoded; Unicode NFKC; soft hyphen removed; whitespace collapsed; no semantic/boilerplate trimming", "tool": "Python stdlib urllib/html.parser/hashlib", "targets": TARGETS, "results": {}, "captures": [], "comparisons": []}
for key, url in TARGETS.items():
    params = urllib.parse.urlencode({"url": url, "from": "2024", "to": "2024", "output": "json", "filter": "statuscode:200", "collapse": "timestamp:4", "fl": "timestamp,original,statuscode,mimetype,digest"})
    cdx = fetch(key + "_cdx", "https://web.archive.org/cdx/search/cdx?" + params, 256 * 1024)
    receipt["results"][key + "_cdx"] = cdx
    if "sha256" not in cdx:
        continue
    try:
        rows = json.loads((ROOT / (key + "_cdx.raw")).read_text(encoding="utf-8"))
        receipt["results"][key + "_cdx"]["rows"] = rows[:5]
        if len(rows) <= 1:
            continue
        first = rows[1]
        if len(first) < 2 or not re.fullmatch(r"2024\d{10}", first[0]):
            continue
        replay = "https://web.archive.org/web/" + first[0] + "id_/" + first[1]
        cap = fetch(key + "_capture", replay, 2 * 1024 * 1024)
        cap["archive_timestamp_utc"] = first[0]
        receipt["captures"].append({"target": key, **cap})
    except Exception as exc:
        receipt["results"][key + "_cdx"]["parse_error"] = type(exc).__name__ + ": " + str(exc)[:200]

current = fetch("feb_sec_current", TARGETS["feb_sec"], 2 * 1024 * 1024)
receipt["results"]["feb_sec_current"] = current
for capture in receipt["captures"]:
    key = capture["target"] + "_capture"
    if "normalized_text_sha256" in capture and "normalized_text_sha256" in current:
        a = (ROOT / (key + ".text")).read_text(encoding="utf-8")
        b = (ROOT / "feb_sec_current.text").read_text(encoding="utf-8")
        receipt["comparisons"].append({"capture": key, "against": "feb_sec_current", "normalized_exact_equal": a == b, "ratio": difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), "capture_chars": len(a), "reference_chars": len(b)})
receipt["total_requests"] = requests
receipt["total_bytes_read"] = bytes_read
receipt["utc_finished"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
(ROOT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"requests": requests, "bytes": bytes_read, "captures": len(receipt["captures"]), "comparisons": receipt["comparisons"], "errors": {k:v.get("error") for k,v in receipt["results"].items() if v.get("error")}}, indent=2))
