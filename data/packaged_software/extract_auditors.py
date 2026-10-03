"""Independent auditor for each company, from its latest 10-K on disk.

Fills the auditor part of checklist section 1. Auditor names are matched against a list of
audit firms, not free text, so a match is a firm the filing names. The 10-K's report of
independent registered public accounting firm names the auditor, and it appears in the
filing text as "/s/ <Firm>" near the audit report.

Writes output/company_auditors.csv with one row per company: the firm found, the number of
distinct firms named in the filing, the filing date it came from, and a status. A company
with no recognized firm is marked for review rather than guessed.

Standard library only. Read-only on the extract folder.
"""

from __future__ import annotations

import csv
import html
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEC = HERE / "extracts" / "sec"
COMPANIES = HERE / "packaged_software_companies.csv"
OUT = HERE / "output" / "company_auditors.csv"
TAG_RE = re.compile(r"<[^>]+>")
# Firm names as they appear in audit reports. Longer forms first so the shorter one doesn't win.
FIRMS = [
    "PricewaterhouseCoopers", "Ernst & Young", "Deloitte & Touche", "KPMG",
    "Grant Thornton", "BDO USA", "Moss Adams", "Marcum", "RSM US", "Crowe LLP",
    "Baker Tilly", "Plante & Moran", "Wolf & Company", "CohnReznick", "Friedman LLP",
    "Armanino", "Haskell & White", "Weinberg & Company", "Withum", "EisnerAmper",
    "Mazars", "Frazier & Deeter", "Rotenberg Meril", "MaloneBailey", "M&K CPAS",
    "Boyle CPA", "Turner, Stone", "BF Borgers", "Fruci & Associates", "Assurance Dimensions",
    "Salberg & Company", "Liggett & Webb", "Marcum Asia", "UHY LLP", "Sadler, Gibb",
    "Pinaki & Associates", "Haynie & Company", "Daszkal Bolton", "Tanner LLP",
]
FIRM_RE = re.compile("|".join(re.escape(f) for f in FIRMS), re.I)
ENTITY_PATTERNS = [(re.compile(re.escape(f), re.I), f) for f in FIRMS]
# Up to six capitalized words ending in a firm suffix, e.g. "CBIZ Canada LLP", "BPM LLP"
GENERIC_RE = re.compile(
    r"((?:[A-Z][A-Za-z&.'-]*\s?){1,6}?(?:LLP|PLLC|LLC|CPAs|CPA|P\.C\.|PC))\b")


def latest_10k(ticker: str) -> Path | None:
    base = SEC / ticker / "10-K"
    if not base.exists():
        return None
    docs = sorted(base.glob("*/*.htm*"))
    return docs[-1] if docs else None


def text_of(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    return " ".join(html.unescape(TAG_RE.sub(" ", raw)).split())


TAG_AUDITOR_RE = re.compile(r'name="dei:AuditorName"[^>]*>(.*?)</ix:nonNumeric>', re.S)


def tagged_auditor(path: Path) -> str:
    """The auditor name from the cover-page XBRL tag, with entities and spacing cleaned."""
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    m = TAG_AUDITOR_RE.search(raw)
    if not m:
        return ""
    name = html.unescape(TAG_RE.sub("", m.group(1))).replace("\xa0", " ")
    return " ".join(name.split())


def audit_context(text: str) -> str:
    """The text around 'independent registered public accounting firm', where the auditor signs."""
    spots = [m.start() for m in re.finditer(r"independent\s+registered\s+public\s+accounting\s+firm", text, re.I)]
    return " ".join(text[s: s + 1200] for s in spots)


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    rows = []
    for c in companies:
        ticker = (c["ticker"] or "").strip()
        row = {"cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
               "auditor": "", "firms_named_in_filing": 0, "filing_date": "", "status": ""}
        doc = latest_10k(ticker) if ticker else None
        if doc is None:
            row["status"] = "no 10-K on disk"
            rows.append(row)
            continue
        row["filing_date"] = doc.parent.name.split("_")[0]
        tagged = tagged_auditor(doc)
        if tagged:
            # Inline XBRL cover-page tag dei:AuditorName, present on 10-Ks since 2021
            row["auditor"] = tagged
            row["firms_named_in_filing"] = 1
            row["status"] = "tagged (dei:AuditorName)"
            rows.append(row)
            continue
        context = audit_context(text_of(doc))
        if not context:
            row["status"] = "auditor sentence not found"
            rows.append(row)
            continue
        found = []
        for rx, firm in ENTITY_PATTERNS:
            if rx.search(context) and firm not in found:
                found.append(firm)
        if found:
            row["auditor"] = found[0]
            row["firms_named_in_filing"] = len(found)
            row["status"] = "ok" if len(found) == 1 else "multiple firms named; check"
        else:
            # Smaller firms are not on the list. Take a firm-suffixed name next to the audit
            # wording (e.g. "CBIZ Canada LLP", "BPM LLP") and flag it for a glance.
            generic = GENERIC_RE.search(context)
            if generic:
                row["auditor"] = generic.group(1).strip()
                row["firms_named_in_filing"] = 1
                row["status"] = "generic match; check"
            else:
                row["status"] = "no firm name found; review"
        rows.append(row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    print(f"Wrote {len(rows)} companies to {OUT}")
    print(Counter(r["status"] for r in rows))
    print("auditor found:", sum(1 for r in rows if r["auditor"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
