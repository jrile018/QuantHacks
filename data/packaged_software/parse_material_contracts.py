"""Index the material contracts filed as Exhibit 10 (checklist item 6.3).

Exhibit 10 is where a filer puts the contracts it considers material: credit agreements,
leases, licences, reseller and partner agreements, and executive employment terms. The
exhibits are already on disk from the 10-K and 8-K downloads; this reads each one and
records what it is, so the set is searchable without opening files.

Per contract: the filer, filing date, exhibit file, document title, a contract type from
the title and opening text, the counterparties named in the preamble where they can be
read, and the length.

Writes:
  output/material_contracts.csv        one row per exhibit
  output/material_contract_types.csv   counts by company and type

Caveats:
  - The type comes from keywords, so a contract covering several things gets one label.
  - Counterparties are read from the agreement preamble ("between X and Y"). Many exhibits
    are forms or plans with no counterparty, which is recorded as blank rather than guessed.
  - Employment and equity-plan exhibits dominate Exhibit 10 for most filers; they are
    labelled so they can be filtered out when looking for customer or partner contracts.
Standard library only. Read-only on the extract folder.
"""

from __future__ import annotations

import csv
import html
import re
from collections import defaultdict
from pathlib import Path

import sec_common

HERE = Path(__file__).resolve().parent
SEC = HERE / "extracts" / "sec"
COMPANIES = HERE / "packaged_software_companies.csv"
OUT = HERE / "output"
TAG_RE = re.compile(r"<[^>]+>")
EX10_RE = re.compile(r"(?:\b|_|-)(?:ex|exhibit)[-_]?10", re.I)

CONTRACT_TYPES = [
    ("credit_or_loan", re.compile(r"credit agreement|loan agreement|term loan|revolving|note purchase|indenture|security agreement", re.I)),
    ("lease", re.compile(r"lease", re.I)),
    ("license_or_ip", re.compile(r"licen[cs]e|patent|trademark|intellectual property", re.I)),
    ("reseller_or_partner", re.compile(r"reseller|distributor|channel partner|partnership agreement|collaboration", re.I)),
    ("customer_or_supply", re.compile(r"master services|services agreement|supply agreement|subscription agreement|statement of work|hosting", re.I)),
    ("merger_or_purchase", re.compile(r"purchase agreement|merger|asset purchase|share purchase|contribution agreement", re.I)),
    ("employment_or_comp", re.compile(r"employment|severance|offer letter|transition|retention|separation|change in control|incentive plan|equity plan|option agreement|restricted stock|deferred compensation|indemnification", re.I)),
    ("settlement", re.compile(r"settlement", re.I)),
]
PARTIES_RE = re.compile(
    r"\b(?:by and between|between|among)\b\s+(?P<a>[A-Z][A-Za-z0-9&.,'\- ]{2,70}?)\s+"
    r"(?:and|,)\s+(?P<b>[A-Z][A-Za-z0-9&.,'\- ]{2,70}?)(?:\s*[,.(]|\s+dated|\s+is\b)", re.S)


def text_of(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    return " ".join(html.unescape(TAG_RE.sub(" ", raw)).split())


def title_of(text: str) -> str:
    """The first line that reads like a document title."""
    head = text[:1500]
    for candidate in re.split(r"(?<=[A-Za-z])\s{2,}|\s*\|\s*", head):
        c = candidate.strip(" .,-*")
        if 8 < len(c) < 130 and re.search(r"agreement|plan|lease|amendment|note|letter|indenture|contract|policy", c, re.I):
            return c
    return head[:120].strip()


def classify(text: str, title: str) -> str:
    probe = f"{title} {text[:3000]}"
    for name, rx in CONTRACT_TYPES:
        if rx.search(probe):
            return name
    return "other"


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    rows = []
    for c in companies:
        ticker = (c["ticker"] or "").strip()
        if not ticker:
            continue
        for form in ("10-K", "10-K_A", "8-K", "8-K_A"):
            base = SEC / ticker / form
            if not base.exists():
                continue
            for filing in sorted(base.iterdir()):
                if not filing.is_dir():
                    continue
                for doc in sorted(filing.iterdir()):
                    if not doc.is_file() or not EX10_RE.search(doc.name):
                        continue
                    text = text_of(doc)
                    if len(text) < 400:      # stub or cross-reference page
                        continue
                    title = title_of(text)
                    parties = PARTIES_RE.search(text[:6000])
                    rows.append({
                        "cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
                        "form": form.replace("_", "/"),
                        "filing_date": filing.name.split("_")[0],
                        "exhibit_file": doc.name,
                        "title": title,
                        "contract_type": classify(text, title),
                        "party_a": (parties.group("a").strip() if parties else ""),
                        "party_b": (parties.group("b").strip() if parties else ""),
                        "chars": len(text),
                        "source_file": str(doc.relative_to(HERE)).replace("\\", "/"),
                    })

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "material_contracts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    by_type: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        by_type[(r["ticker"], r["contract_type"])] += 1
    with (OUT / "material_contract_types.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "contract_type", "contracts"])
        for (ticker, t), n in sorted(by_type.items()):
            w.writerow([ticker, t, n])

    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r["contract_type"]] += 1
    print(f"material_contracts: {len(rows)} exhibits across {len({r['ticker'] for r in rows})} companies")
    for t, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {t:22} {n}")
    print(f"  with counterparties read: {sum(1 for r in rows if r['party_b'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
