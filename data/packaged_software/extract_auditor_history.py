"""Auditor history and auditor changes, 2022 onward, from every 10-K on disk.

Checklist item 9 (auditor changes, from 8-K Item 4.01). For each company it reads the
dei:AuditorName tag in every 10-K and 10-K/A, orders them by filing date, and records
each year where the auditor differs from the one before.

Writes:
  output/auditor_history.csv   one row per 10-K: filing date, auditor, changed-from-prior flag
  output/auditor_changes.csv   one row per detected change: date, from-auditor, to-auditor

Caveats:
  - The change is detected at the filing date of the first 10-K naming the new auditor, so
    the actual change happened sometime in the prior fiscal year.
  - Names are normalized for case and punctuation before comparing, so "DELOITTE & TOUCHE LLP"
    and "Deloitte & Touche LLP" are the same firm.
  - Companies with only one 10-K on disk can show no change even if one occurred earlier.
Standard library only. Read-only on the extract folder.
"""

from __future__ import annotations

import csv
import html
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEC = ROOT / "data" / "extracts" / "sec"
COMPANIES = HERE / "packaged_software_companies.csv"
OUT_HISTORY = HERE / "output" / "auditor_history.csv"
OUT_CHANGES = HERE / "output" / "auditor_changes.csv"
START = "2022-01-01"
TAG_AUDITOR_RE = re.compile(r'name="dei:AuditorName"[^>]*>(.*?)</ix:nonNumeric>', re.S)
TAG_RE = re.compile(r"<[^>]+>")


def clean_name(raw: str) -> str:
    text = html.unescape(TAG_RE.sub("", raw)).replace("\xa0", " ")
    return " ".join(text.split())


# Legal-form and office words that name the same firm in different filings
NOISE_WORDS = {"llp", "llc", "pc", "pa", "cpa", "cpas", "inc", "company", "co", "us", "usa",
               "canada", "the", "and", "consent", "of", "p", "c", "a", "l", "lc", "pllc"}


def key_of(name: str) -> str:
    """A comparison key for the firm, so formatting differences do not count as a change.

    Lowercases, drops parenthesized tags such as "(RSM)", treats "&" and "and" alike, and
    removes legal-form words. "Ernst & Young LLP", "Ernst and Young, LLP" and "Ernst & Young"
    all give the same key.
    """
    text = re.sub(r"\([^)]*\)", " ", name.lower())
    text = text.replace("&", " ")
    words = [w for w in re.split(r"[^a-z0-9]+", text) if w and w not in NOISE_WORDS]
    return "".join(words)


def auditor_of(path: Path) -> str:
    m = TAG_AUDITOR_RE.search(path.read_bytes().decode("utf-8", errors="ignore"))
    return clean_name(m.group(1)) if m else ""


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    history, changes = [], []
    for c in companies:
        ticker = (c["ticker"] or "").strip()
        if not ticker:
            continue
        filings = []
        for form in ("10-K", "10-K_A"):
            base = SEC / ticker / form
            if not base.exists():
                continue
            for doc in base.glob("*/*.htm*"):
                date = doc.parent.name.split("_")[0]
                if date >= START:
                    filings.append((date, form.replace("_", "/"), doc))
        filings.sort()

        prior_name, prior_key = "", ""
        for date, form, doc in filings:
            name = auditor_of(doc)
            k = key_of(name)
            changed = bool(prior_key and k and k != prior_key)
            history.append({
                "cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
                "filing_date": date, "form": form, "auditor": name,
                "changed_from_prior": "yes" if changed else "no",
            })
            if changed:
                changes.append({
                    "cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
                    "first_filing_with_new_auditor": date,
                    "from_auditor": prior_name, "to_auditor": name,
                })
            if k:
                prior_name, prior_key = name, k

    OUT_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with OUT_HISTORY.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cik", "ticker", "name", "filing_date", "form", "auditor", "changed_from_prior"])
        w.writeheader()
        w.writerows(history)
    with OUT_CHANGES.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cik", "ticker", "name", "first_filing_with_new_auditor", "from_auditor", "to_auditor"])
        w.writeheader()
        w.writerows(changes)

    tickers_with_change = {c["ticker"] for c in changes}
    print(f"10-K filings checked: {len(history)}")
    print(f"Auditor changes detected: {len(changes)} across {len(tickers_with_change)} companies")
    for c in sorted(changes, key=lambda r: r["first_filing_with_new_auditor"]):
        print(f"  {c['ticker']:6} {c['first_filing_with_new_auditor']}  {c['from_auditor'][:28]:28} -> {c['to_auditor'][:28]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
