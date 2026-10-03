"""California WARN notices, 2022 onward, matched to the 168-company universe.

Fills the layoff item in checklist section 17. The EDD publishes one PDF per fiscal year
(July to June). This downloads them, reads each with pdftotext -layout, and parses the
rows. The company name appears only on the first row of each group of notices, so it is
carried forward until the next name.

Each parsed notice has: notice date, effective date, received date, company, city or county,
employees affected, and layoff or closure with permanent, temporary, or unknown status.

Writes:
  output/warn_ca_notices.csv     every California notice received since 2022-07-01
  output/warn_ca_by_company.csv  one row per company, with matched notices and employees

Matching caveat: a WARN notice names the employer as filed, which is often the legal entity
or a site name, not the public company. Matching is on normalized name, so a subsidiary or a
differently-named site is missed, and a common name can match an unrelated employer.
Every matched row keeps the raw name so it can be checked.

Requires pdftotext (poppler) on PATH. Standard library only otherwise.
"""

from __future__ import annotations

import csv
import html
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPANIES = HERE / "packaged_software_companies.csv"
IDENTITY = HERE / "output" / "company_identity.csv"
WORK = ROOT / "data" / "extracts" / "warn" / "ca"
OUT_NOTICES = HERE / "output" / "warn_ca_notices.csv"
OUT_COMPANY = HERE / "output" / "warn_ca_by_company.csv"
INDEX_URL = "https://edd.ca.gov/en/jobs_and_training/Layoff_Services_WARN"
BASE = "https://edd.ca.gov"
PDF_RE = re.compile(r'(/siteassets/files/jobs_and_training/warn/[^"\']+\.pdf)', re.I)
START = "2022-07-01"
DATES_RE = re.compile(r"^\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(?:(\d{2}/\d{2}/\d{4})\s+)?")
# The headcount, action and status anchor each notice. In the 2014-15 layout they end the
# line; in later layouts a street address follows them, so the match is not anchored to the end.
ACTION_RE = re.compile(
    r"(?P<count>\d[\d,]*)\s+(?P<action>Layoff|Closure)\s+"
    r"(?P<status>Permanent|Temporary|Unknown at this time)"
)
SUFFIX_RE = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|plc|holdings?|group|the)\b\.?", re.I)


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", SUFFIX_RE.sub(" ", name.lower()))


def pdf_urls() -> list[str]:
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": "quanthacks-research"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
    return sorted({BASE + urllib.parse.quote(p, safe="/") for p in PDF_RE.findall(html)})


def download(url: str) -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    local = WORK / Path(urllib.parse.unquote(url)).name
    if not local.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "quanthacks-research"})
        local.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return local


def to_text(pdf: Path) -> str:
    txt = pdf.with_suffix(".txt")
    if not txt.exists():
        subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], check=True)
    return txt.read_text(encoding="utf-8", errors="ignore")


def us_date(s: str) -> str:
    m, d, y = s.split("/")
    return f"{y}-{m}-{d}"


def parse(text: str) -> list[dict]:
    """Return notices.

    Dates come from the line itself when it has them, otherwise from the most recent date
    line. Company and city carry forward from the last named row, because the employer is
    printed only once for a group of notices. A notice whose line has no action pattern is
    skipped, which covers headers and the county-only lines that wrap above a notice.
    """
    notices = []
    company, city = "", ""
    dates = ("", "", "")
    for line in text.splitlines():
        d = DATES_RE.match(line)
        if d:
            dates = (d.group(1), d.group(2), d.group(3) or "")
            middle = line[d.end():]
        else:
            middle = line
        act = ACTION_RE.search(middle)
        if not act:
            continue
        head = html.unescape(middle[: act.start()]).strip()
        parts = [p for p in re.split(r"\s{2,}", head) if p]
        if len(parts) >= 2:
            company, city = parts[0], parts[1]
        elif len(parts) == 1:
            company = parts[0]
        notice_date, effective, received = dates
        if not notice_date:
            continue
        notices.append({
            "notice_date": us_date(notice_date),
            "effective_date": us_date(effective),
            "received_date": us_date(received) if received else "",
            "company_as_filed": company,
            "city_or_county": city,
            "employees_affected": act.group("count").replace(",", ""),
            "action": act.group("action"),
            "status": act.group("status"),
        })
    return notices


def main() -> int:
    urls = pdf_urls()
    print(f"{len(urls)} California WARN PDFs listed")
    all_notices = []
    for url in urls:
        pdf = download(url)
        notices = parse(to_text(pdf))
        all_notices.extend(notices)
        print(f"{pdf.name}: {len(notices)} notices")

    recent = [n for n in all_notices if n["notice_date"] >= START and n["company_as_filed"]]
    print(f"Notices from {START}: {len(recent)}")

    # Universe: the 168 companies, with their CA-headquartered names matched by normalized key
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        universe = list(csv.DictReader(f))
    keys: dict[str, dict] = {}
    for c in universe:
        key = normalize(c["name"])
        if len(key) >= 6:
            keys[key] = c

    matched = []
    for n in recent:
        nk = normalize(n["company_as_filed"])
        for key, c in keys.items():
            if nk == key or (len(key) >= 8 and nk.startswith(key)):
                matched.append({**n, "ticker": c["ticker"], "cik": c["cik"].zfill(10),
                                "universe_name": c["name"]})
                break

    OUT_NOTICES.parent.mkdir(parents=True, exist_ok=True)
    if matched:
        with OUT_NOTICES.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(matched[0].keys()))
            w.writeheader()
            w.writerows(sorted(matched, key=lambda r: (r["ticker"], r["notice_date"])))

    by = {c["ticker"]: {"cik": c["cik"].zfill(10), "ticker": c["ticker"], "name": c["name"],
                        "notices": 0, "employees": 0} for c in universe}
    for m in matched:
        by[m["ticker"]]["notices"] += 1
        by[m["ticker"]]["employees"] += int(m["employees_affected"] or 0)
    with OUT_COMPANY.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cik", "ticker", "name", "notices", "employees"])
        w.writeheader()
        w.writerows(by.values())

    hit = sum(1 for v in by.values() if v["notices"])
    print(f"Matched {len(matched)} notices to {hit} of {len(universe)} companies")
    print(f"Wrote {OUT_NOTICES.name} and {OUT_COMPANY.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
