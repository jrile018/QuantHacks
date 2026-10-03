"""Scan downloaded 8-K / 8-K/A documents for the event items on the checklist.

For every company folder under data/packaged_software/extracts/sec/<TICKER>/, reads each 8-K and 8-K/A
primary document, finds which "Item X.XX" headings it contains, and writes:
  output/8k_item_filings.csv    one row per (filing, item) match, with a short snippet
  output/8k_item_by_company.csv one row per company with a count per item

Also flags "cybersecurity incident" wording in any item (checklist section 9), since
companies often disclose incidents under 8.01 or 7.01 instead of 1.05.

Standard library only. Read-only on the extract folder.
"""

from __future__ import annotations

import csv
import html
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXTRACT = HERE / "extracts" / "sec"
OUT_DIR = HERE / "output"

# Items from the checklist: 1.01/1.02 agreements, 2.01 acquisitions, 2.03/2.04 debt,
# 2.05/2.06 exit costs and impairments, 4.01 auditor change, 4.02 restatements,
# 5.02 executive changes, plus 8.01 and 7.01 which often carry incident disclosures.
ITEMS = ["1.01", "1.02", "1.05", "2.01", "2.02", "2.03", "2.04", "2.05", "2.06",
         "4.01", "4.02", "5.02", "5.07", "8.01", "7.01"]
ITEM_RE = re.compile(r"item\s*(\d\.\d\d)\b", re.IGNORECASE)
CYBER_RE = re.compile(r"cybersecurity\s+incident", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def read_text(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    return " ".join(html.unescape(TAG_RE.sub(" ", raw)).split())


def tickers_from_extract() -> list[str]:
    return sorted(p.name for p in EXTRACT.iterdir() if p.is_dir() and p.name != "_cache")


def main() -> int:
    tickers = tickers_from_extract()
    filing_rows: list[dict] = []
    counts: dict[str, dict[str, int]] = {t: {i: 0 for i in ITEMS} for t in tickers}
    cyber_counts: dict[str, int] = {t: 0 for t in tickers}
    docs_scanned = 0

    for ticker in tickers:
        for form_dir in ("8-K", "8-K_A"):
            for doc in (EXTRACT / ticker / form_dir).glob("*/*"):
                if not doc.is_file():
                    continue
                docs_scanned += 1
                text = read_text(doc)
                found = {m.group(1) for m in ITEM_RE.finditer(text)}
                local = str(doc.relative_to(ROOT)).replace("\\", "/")
                for item in sorted(found):
                    if item in ITEMS:
                        counts[ticker][item] += 1
                        filing_rows.append({
                            "ticker": ticker, "form": form_dir.replace("_", "/"),
                            "filing_folder": doc.parent.name, "item": item,
                            "local_path": local, "cyber_wording": "",
                        })
                cyber = CYBER_RE.search(text)
                if cyber:
                    cyber_counts[ticker] += 1
                    # Tag the filing so the cyber wording can be read next to its item
                    filing_rows.append({
                        "ticker": ticker, "form": form_dir.replace("_", "/"),
                        "filing_folder": doc.parent.name, "item": ",".join(sorted(found)) or "none",
                        "local_path": local, "cyber_wording": "yes",
                    })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "8k_item_filings.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "form", "filing_folder", "item", "local_path", "cyber_wording"])
        w.writeheader()
        w.writerows(filing_rows)

    fields = ["ticker"] + ITEMS + ["cyber_wording_filings"]
    with (OUT_DIR / "8k_item_by_company.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in tickers:
            row = {"ticker": t, "cyber_wording_filings": cyber_counts[t]}
            row.update(counts[t])
            w.writerow(row)

    totals = {i: sum(counts[t][i] for t in tickers) for i in ITEMS}
    print(f"Companies: {len(tickers)}  8-K docs scanned: {docs_scanned}")
    for i in ITEMS:
        companies = sum(1 for t in tickers if counts[t][i])
        print(f"  Item {i}: {totals[i]} filings across {companies} companies")
    print(f"  cyber wording: {sum(cyber_counts.values())} filings across {sum(1 for v in cyber_counts.values() if v)} companies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
