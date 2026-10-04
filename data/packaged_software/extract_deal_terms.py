"""Deal terms from merger filings on disk: per-share price and aggregate consideration.

Checklist item 5. Reads the merger proxy (DEFM14A, PREM14A) and registration statement (S-4)
documents for the 168 companies and pulls out two kinds of figure:
  per_share_cash      a price stated as "$X in cash" or "$X per share in cash"
  aggregate_value     a total stated as "aggregate consideration ... $X" or "approximately $X billion"

Each figure is a candidate, not a verified term. The matched sentence is kept with the row,
so each value can be read in context. Deals with no matched figure are still listed, so
missing terms are visible.

Writes output/deal_terms_candidates.csv, one row per (deal filing, figure type).
Standard library only.
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
OUT = HERE / "output" / "deal_terms_candidates.csv"
DEAL_FORMS = ["DEFM14A", "PREM14A", "S-4", "S-4_A"]
TAG_RE = re.compile(r"<[^>]+>")
PER_SHARE_RE = re.compile(
    r"\$\s?(\d{1,4}(?:\.\d{1,4})?)\s*(?:per share\s*)?in cash", re.I)
AGG_RE = re.compile(
    r"(?:aggregate\s+(?:transaction\s+|deal\s+)?(?:consideration|value|purchase price)"
    r"|transaction value|enterprise value|equity value)[^.$]{0,120}?"
    r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(billion|million)?", re.I)
MULT = {"billion": 1e9, "million": 1e6, None: 1.0}
# Phrases near a match that mean the figure is not the deal price. Spot-checking showed
# trust-account balances, IPO proceeds and termination fees being picked up as deal terms.
NOT_DEAL_TERMS = re.compile(
    r"trust account|termination fee|initial public offering|\bIPO\b|held in|"
    r"private placement|convertible|promissory note|working capital loan", re.I)


def is_deal_term(t: str, start: int, end: int) -> bool:
    return not NOT_DEAL_TERMS.search(t[max(0, start - 150): end + 150])


def text_of(path: Path) -> str:
    raw = path.read_bytes().decode("utf-8", errors="ignore")
    return " ".join(html.unescape(TAG_RE.sub(" ", raw)).split())


def snippet(text: str, start: int, end: int, pad: int = 120) -> str:
    return text[max(0, start - pad): end + pad]


def main() -> int:
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        companies = list(csv.DictReader(f))

    rows = []
    for c in companies:
        ticker = (c["ticker"] or "").strip()
        if not ticker:
            continue
        # Merger agreements filed as Exhibit 2.x to 8-Ks, kept only when the text is an
        # "Agreement and Plan of Merger" (other Exhibit 2 files are plans or asset sales)
        agreements = []
        for doc in sorted((SEC / ticker / "8-K").glob("*/*ex*2*.htm*")) if (SEC / ticker / "8-K").exists() else []:
            if "agreement and plan of merger" in text_of(doc).lower()[:20000]:
                agreements.append(("MERGER_AGREEMENT", doc))

        jobs = [(form, doc) for form in DEAL_FORMS
                if (SEC / ticker / form).exists()
                for doc in sorted((SEC / ticker / form).glob("*/*.htm*"))] + agreements
        if True:
            for form, doc in jobs:
                filing_date = doc.parent.name.split("_")[0]
                t = text_of(doc)
                form_label = form.replace("_", "/")
                ps = next((m for m in PER_SHARE_RE.finditer(t) if is_deal_term(t, m.start(), m.end())), None)
                ag = next((m for m in AGG_RE.finditer(t) if is_deal_term(t, m.start(), m.end())), None)
                base_row = {
                    "cik": c["cik"].zfill(10), "ticker": ticker, "name": c["name"],
                    "form": form_label, "filing_date": filing_date,
                    "local_path": str(doc.relative_to(ROOT)).replace("\\", "/"),
                }
                if ps:
                    rows.append({**base_row, "figure_type": "per_share_cash",
                                 "value": ps.group(1), "unit": "USD per share",
                                 "context": snippet(t, ps.start(), ps.end())})
                if ag:
                    amount = float(ag.group(1).replace(",", "")) * MULT[(ag.group(2) or "").lower() or None]
                    rows.append({**base_row, "figure_type": "aggregate_value",
                                 "value": round(amount), "unit": "USD",
                                 "context": snippet(t, ag.start(), ag.end())})
                if not ps and not ag:
                    rows.append({**base_row, "figure_type": "none_matched", "value": "",
                                 "unit": "", "context": ""})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = ["cik", "ticker", "name", "form", "filing_date", "figure_type", "value", "unit", "context", "local_path"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    print(f"Wrote {len(rows)} rows to {OUT}")
    print(Counter(r["figure_type"] for r in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
