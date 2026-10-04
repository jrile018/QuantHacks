"""SEC litigation releases, 2022 onward, matched against the 168-company universe.

Fills part of checklist section 10. The SEC publishes litigation releases month by month
on a public page (no API key). This fetches every month from 2022-01 to today, parses the
date and defendant text from each row, and flags releases whose text names one of the
companies.

Writes:
  output/sec_litigation_releases.csv   every release in the window
  output/sec_enforcement_by_company.csv one row per company, with matched release count

Matching caveat: a release names defendants in free text, so matching is by company name
with legal suffixes removed. A short or common company name can match a release about a
different party, and a release about a company's officers may not name the company. Every
matched row keeps the release text so it can be checked. A company with zero matches has
no litigation release naming it, which is the normal case.
Standard library only.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPANIES = HERE / "packaged_software_companies.csv"
CACHE = HERE / "extracts" / "_cache" / "sec_enforcement"
OUT_RELEASES = HERE / "output" / "sec_litigation_releases.csv"
OUT_COMPANY = HERE / "output" / "sec_enforcement_by_company.csv"
# Three enforcement streams. Litigation releases are civil court actions (mostly against
# individuals and small issuers); accounting/auditing releases and administrative
# proceedings are where a public company is more likely to appear.
SOURCES = {
    "litigation_release": "https://www.sec.gov/enforcement-litigation/litigation-releases",
    "accounting_auditing_release": "https://www.sec.gov/enforcement-litigation/accounting-auditing-enforcement-releases",
    "administrative_proceeding": "https://www.sec.gov/enforcement-litigation/administrative-proceedings",
}
START_YEAR = 2022
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TAG_RE = re.compile(r"<[^>]+>")
LINK_RE = re.compile(r'href="([^"]+)"')
SUFFIX_RE = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|llc|plc|holdings?|group|the)\b\.?", re.I)
# A single-word company name this short is matched only with its legal suffix attached.
# Without this, "Block" matched "Blockchain", "Blockworks" and "Block Bits Capital" in
# five unrelated releases; those were the only "matches" the first run produced.
MIN_SINGLE_TOKEN_LENGTH = 10


def clean(html_fragment: str) -> str:
    return " ".join(TAG_RE.sub(" ", html_fragment).split())


def normalize_words(text: str) -> str:
    """Lowercase, keep only words and single spaces, so matching can use word boundaries."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def match_key(name: str) -> str:
    stripped = SUFFIX_RE.sub(" ", name.lower())
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", stripped).split())


def build_pattern(name: str) -> tuple[re.Pattern | None, str]:
    """A word-boundary pattern for one company, and a label saying which form was used.

    A multi-word name ("manhattan associates") is specific enough on its own. A single
    short word ("block", "box", "aware") is matched only with its legal suffix, so the
    release has to say "Block Inc" rather than merely "Blockchain".
    """
    bare = match_key(name)
    if not bare:
        return None, "(no usable name)"
    tokens = bare.split()
    if len(tokens) >= 2 or len(bare) >= MIN_SINGLE_TOKEN_LENGTH:
        return re.compile(rf"\b{re.escape(bare)}\b"), bare
    full = normalize_words(name)
    if full != bare:
        return re.compile(rf"\b{re.escape(full)}\b"), f"{full} (suffix required: name is one short word)"
    return None, f"{bare} (one short word, no suffix to anchor on; skipped)"


def user_agent() -> str:
    """SEC asks every client to identify itself. Read the contact from .env rather than
    hardcoding a personal address, so this file can be shared."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("SEC_USER_AGENT="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    raise SystemExit("Set SEC_USER_AGENT in .env to 'Your Name your-email@example.com'")


def fetch_month(source: str, year: int, month: int) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / f"{source}_{year}-{month:02d}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8", errors="ignore")
    url = f"{SOURCES[source]}?year={year}&month={month}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
            break
        except Exception:
            if attempt == 2:
                return ""
            time.sleep(2 ** attempt)
    cache_file.write_text(body, encoding="utf-8")
    time.sleep(0.4)
    return body


def parse_month(html_text: str, year: int, month: int, source: str) -> list[dict]:
    releases = []
    for row in ROW_RE.findall(html_text):
        cells = CELL_RE.findall(row)
        if len(cells) < 2:
            continue
        date_text = clean(cells[0])
        if not date_text:
            continue
        body = clean(cells[1])
        link = LINK_RE.search(cells[1])
        url = link.group(1) if link else ""
        if url.startswith("/"):
            url = "https://www.sec.gov" + url
        release_no = ""
        m = re.search(r"LR-\s*(\d+)", body)
        if m:
            release_no = f"LR-{m.group(1)}"
        releases.append({
            "source": source,
            "year": year, "month": f"{year}-{month:02d}",
            "release_date": date_text,
            "release_number": release_no,
            "defendants_text": body,
            "url": url,
        })
    return releases


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    today = dt.date.today()
    releases: list[dict] = []
    for source in SOURCES:
        count = 0
        for year in range(START_YEAR, today.year + 1):
            last_month = today.month if year == today.year else 12
            for month in range(1, last_month + 1):
                html_text = fetch_month(source, year, month)
                found = parse_month(html_text, year, month, source)
                releases.extend(found)
                count += len(found)
        print(f"{source}: {count} releases")

    # Match company names against the defendant text of each release, on word boundaries
    patterns = {}
    labels = {}
    for c in companies:
        pattern, label = build_pattern(c["name"])
        labels[c["ticker"]] = label
        if pattern is not None:
            patterns[c["ticker"]] = (pattern, c)
    matches: dict[str, list[dict]] = defaultdict(list)
    for r in releases:
        haystack = normalize_words(r["defendants_text"])
        for ticker, (pattern, c) in patterns.items():
            if pattern.search(haystack):
                r.setdefault("matched_tickers", []).append(ticker)
                matches[ticker].append(r)

    OUT_RELEASES.parent.mkdir(parents=True, exist_ok=True)
    fields = ["source", "month", "release_date", "release_number", "defendants_text", "url", "matched_tickers"]
    with OUT_RELEASES.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in releases:
            row = dict(r)
            row["matched_tickers"] = "; ".join(r.get("matched_tickers", []))
            w.writerow(row)

    with OUT_COMPANY.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cik", "ticker", "name", "match_key_used",
                                          "matched_releases", "litigation_releases",
                                          "accounting_auditing_releases", "administrative_proceedings",
                                          "release_dates", "release_urls"])
        w.writeheader()
        for c in companies:
            mine = matches.get(c["ticker"], [])
            w.writerow({
                "cik": c["cik"].zfill(10), "ticker": c["ticker"], "name": c["name"],
                "match_key_used": labels[c["ticker"]],
                "matched_releases": len(mine),
                "litigation_releases": sum(1 for r in mine if r["source"] == "litigation_release"),
                "accounting_auditing_releases": sum(1 for r in mine if r["source"] == "accounting_auditing_release"),
                "administrative_proceedings": sum(1 for r in mine if r["source"] == "administrative_proceeding"),
                "release_dates": "; ".join(r["release_date"] for r in mine),
                "release_urls": "; ".join(r["url"] for r in mine),
            })

    skipped = sum(1 for t in labels if t not in patterns)
    print(f"\nReleases in window: {len(releases)}")
    print(f"Companies with a matched release: {len(matches)} of {len(companies)}")
    if skipped:
        print(f"Companies whose name was too short to match safely: {skipped}")
    print(f"Wrote {OUT_RELEASES.name} and {OUT_COMPANY.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
