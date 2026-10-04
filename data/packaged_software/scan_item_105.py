"""Find Item 1.05 (cybersecurity incident) 8-K filings for each company in the extract.

Scans every downloaded 8-K / 8-K/A primary document under data/packaged_software/extracts/sec/<TICKER>/
for an "Item 1.05" heading and writes:
  output/item_105_filings.csv   one row per matching filing
  output/item_105_by_company.csv   one row per company, including companies with zero hits

Standard library only. Read-only on the extract folder.
"""

from __future__ import annotations

import csv
import html
import re
from pathlib import Path

import sec_common

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXTRACT = HERE / "extracts" / "sec"
COMPANIES = HERE / "packaged_software_companies.csv"
OUT_DIR = HERE / "output"
ITEM_RE = re.compile(r"item\s*1\.05\b", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def read_text(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    return html.unescape(TAG_RE.sub(" ", raw))


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))
    tickers = [((c["ticker"] or c["cik"]).strip()) for c in companies]

    hits: list[dict] = []
    scanned: dict[str, int] = {t: 0 for t in tickers}
    for ticker in tickers:
        for form in ("8-K", "8-K_A"):
            for _d, _f, doc in sec_common.filing_documents(EXTRACT / ticker, [form]):
                scanned[ticker] += 1
                text = read_text(doc)
                m = ITEM_RE.search(text)
                if m:
                    snippet = " ".join(text[m.start(): m.start() + 200].split())
                    hits.append({
                        "ticker": ticker,
                        "form": form.replace("_", "/"),
                        "filing_folder": doc.parent.name,
                        "local_path": str(doc.relative_to(ROOT)).replace("\\", "/"),
                        "snippet": snippet,
                    })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "item_105_filings.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "form", "filing_folder", "local_path", "snippet"])
        w.writeheader()
        w.writerows(hits)

    counts: dict[str, int] = {t: 0 for t in tickers}
    for h in hits:
        counts[h["ticker"]] += 1
    with (OUT_DIR / "item_105_by_company.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "8k_docs_scanned", "item_105_filings"])
        w.writeheader()
        for t in tickers:
            w.writerow({"ticker": t, "8k_docs_scanned": scanned[t], "item_105_filings": counts[t]})

    print(f"Companies: {len(tickers)}  8-K docs scanned: {sum(scanned.values())}  Item 1.05 hits: {len(hits)}")
    print(f"Companies with at least one hit: {sum(1 for v in counts.values() if v)}")
    print(f"Wrote {OUT_DIR / 'item_105_filings.csv'} and {OUT_DIR / 'item_105_by_company.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
